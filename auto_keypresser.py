"""
Auto Key Presser — Windows GUI for repeating a keyboard key at an interval.
"""

from __future__ import annotations

import random
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from pynput import keyboard as kb


def _parse_interval_ms(h: int, m: int, s: int, ms: int) -> int:
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def _key_from_choice(choice: str) -> str | kb.Key:
    choice = choice.strip()
    if not choice:
        raise ValueError("Select or enter a key.")
    if len(choice) == 1:
        return choice
    name = choice.lower().replace(" ", "_")
    special = {
        "space": kb.Key.space,
        "enter": kb.Key.enter,
        "return": kb.Key.enter,
        "tab": kb.Key.tab,
        "escape": kb.Key.esc,
        "esc": kb.Key.esc,
        "backspace": kb.Key.backspace,
        "delete": kb.Key.delete,
        "insert": kb.Key.insert,
        "home": kb.Key.home,
        "end": kb.Key.end,
        "page_up": kb.Key.page_up,
        "page_down": kb.Key.page_down,
        "up": kb.Key.up,
        "down": kb.Key.down,
        "left": kb.Key.left,
        "right": kb.Key.right,
        "caps_lock": kb.Key.caps_lock,
        "print_screen": kb.Key.print_screen,
        "scroll_lock": kb.Key.scroll_lock,
        "pause": kb.Key.pause,
        "menu": kb.Key.menu,
        "shift": kb.Key.shift,
        "ctrl": kb.Key.ctrl,
        "alt": kb.Key.alt,
    }
    if name in special:
        return special[name]
    if name.startswith("f") and name[1:].isdigit():
        n = int(name[1:])
        if 1 <= n <= 24:
            return getattr(kb.Key, f"f{n}")
    raise ValueError(
        f"Unknown key: {choice!r}. Use a single letter/digit or a name like Space, Enter, F5."
    )


class AutoKeyPresserApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto Key Presser")
        self.minsize(420, 460)
        self.resizable(True, True)

        self._controller = kb.Controller()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._running = False
        self._hotkey_str = "<f6>"
        self._hotkeys: kb.GlobalHotKeys | None = None
        self._hotkey_thread: threading.Thread | None = None
        self._app_closing = False

        self._build_ui()
        self._start_hotkey_listener()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        lf_interval = ttk.LabelFrame(self, text="Press interval")
        lf_interval.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(lf_interval)
        row1.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row1, text="Hours").grid(row=0, column=0, padx=2)
        ttk.Label(row1, text="Mins").grid(row=0, column=1, padx=2)
        ttk.Label(row1, text="Secs").grid(row=0, column=2, padx=2)
        ttk.Label(row1, text="Milliseconds").grid(row=0, column=3, padx=2)

        self.var_h = tk.StringVar(value="0")
        self.var_m = tk.StringVar(value="0")
        self.var_s = tk.StringVar(value="0")
        self.var_ms = tk.StringVar(value="100")

        ttk.Entry(row1, width=6, textvariable=self.var_h).grid(row=1, column=0, padx=2)
        ttk.Entry(row1, width=6, textvariable=self.var_m).grid(row=1, column=1, padx=2)
        ttk.Entry(row1, width=6, textvariable=self.var_s).grid(row=1, column=2, padx=2)
        ttk.Entry(row1, width=8, textvariable=self.var_ms).grid(row=1, column=3, padx=2)

        row2 = ttk.Frame(lf_interval)
        row2.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.var_random = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Random offset (± ms)", variable=self.var_random).pack(side=tk.LEFT)
        self.var_random_ms = tk.StringVar(value="50")
        ttk.Entry(row2, width=8, textvariable=self.var_random_ms).pack(side=tk.LEFT, padx=(8, 0))

        lf_key = ttk.LabelFrame(self, text="Key to press")
        lf_key.pack(fill=tk.X, **pad)

        rowk = ttk.Frame(lf_key)
        rowk.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(rowk, text="Key:").pack(side=tk.LEFT)
        keys = (
            [chr(c) for c in range(ord("A"), ord("Z") + 1)]
            + [str(d) for d in range(10)]
            + [
                "Space",
                "Enter",
                "Tab",
                "Escape",
                "Backspace",
                "Up",
                "Down",
                "Left",
                "Right",
                "F1",
                "F2",
                "F3",
                "F4",
                "F5",
                "F6",
                "F7",
                "F8",
                "F9",
                "F10",
                "F11",
                "F12",
            ]
        )
        self.combo_key = ttk.Combobox(rowk, width=18, values=keys, state="readonly")
        self.combo_key.set("Space")
        self.combo_key.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(rowk, text="or one character:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_custom = tk.StringVar(value="")
        ttk.Entry(rowk, width=5, textvariable=self.var_custom).pack(side=tk.LEFT, padx=(4, 0))

        lf_rep = ttk.LabelFrame(self, text="Repeat")
        lf_rep.pack(fill=tk.X, **pad)

        rowr = ttk.Frame(lf_rep)
        rowr.pack(fill=tk.X, padx=8, pady=6)
        self.var_repeat_mode = tk.StringVar(value="until_stopped")
        ttk.Radiobutton(
            rowr,
            text="Repeat",
            variable=self.var_repeat_mode,
            value="count",
            command=self._toggle_repeat,
        ).pack(side=tk.LEFT)
        self.var_count = tk.StringVar(value="10")
        self.entry_count = ttk.Entry(rowr, width=10, textvariable=self.var_count)
        self.entry_count.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(rowr, text="times").pack(side=tk.LEFT)

        rowr2 = ttk.Frame(lf_rep)
        rowr2.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Radiobutton(
            rowr2,
            text="Repeat until stopped",
            variable=self.var_repeat_mode,
            value="until_stopped",
            command=self._toggle_repeat,
        ).pack(side=tk.LEFT)
        self._toggle_repeat()

        self.lbl_hotkey = ttk.Label(self, text=self._hotkey_label_text())
        self.lbl_hotkey.pack(anchor=tk.W, padx=12, pady=(4, 0))

        bf = ttk.Frame(self)
        bf.pack(fill=tk.X, **pad)

        self.btn_start = ttk.Button(bf, text="", command=self.start_pressing)
        self.btn_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4, pady=8)

        self.btn_stop = ttk.Button(bf, text="", command=self.stop_pressing, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4, pady=8)

        hf = ttk.Frame(self)
        hf.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(hf, text="Hotkey setting…", command=self._hotkey_dialog).pack(side=tk.LEFT)

        self.status = ttk.Label(self, text="Idle", foreground="gray")
        self.status.pack(anchor=tk.W, padx=12, pady=(0, 8))

        self._refresh_hotkey_ui()

    def _hotkey_display(self) -> str:
        return self._hotkey_str.replace("<", "").replace(">", "")

    def _hotkey_label_text(self) -> str:
        return f"Start / Stop hotkey: {self._hotkey_display()}  ({self._hotkey_str})"

    def _refresh_hotkey_ui(self) -> None:
        d = self._hotkey_display()
        self.lbl_hotkey.configure(text=self._hotkey_label_text())
        self.btn_start.configure(text=f"Start ({d})")
        self.btn_stop.configure(text=f"Stop ({d})")

    def _toggle_repeat(self) -> None:
        if self.var_repeat_mode.get() == "count":
            self.entry_count.configure(state=tk.NORMAL)
        else:
            self.entry_count.configure(state=tk.DISABLED)

    def _resolve_key(self):
        custom = self.var_custom.get().strip()
        if custom:
            return _key_from_choice(custom[:1] if len(custom) >= 1 else custom)
        return _key_from_choice(self.combo_key.get())

    def _read_interval_ms(self) -> tuple[int, int]:
        try:
            h = int(self.var_h.get() or "0")
            m = int(self.var_m.get() or "0")
            s = int(self.var_s.get() or "0")
            ms = int(self.var_ms.get() or "0")
        except ValueError:
            raise ValueError("Interval fields must be whole numbers.") from None
        base = _parse_interval_ms(h, m, s, ms)
        if base < 1:
            raise ValueError("Interval must be at least 1 ms total.")
        rand_max = 0
        if self.var_random.get():
            try:
                rand_max = max(0, int(self.var_random_ms.get() or "0"))
            except ValueError:
                raise ValueError("Random offset must be a whole number.") from None
        return base, rand_max

    def _read_repeat_count(self) -> int | None:
        if self.var_repeat_mode.get() != "count":
            return None
        try:
            n = int(self.var_count.get() or "0")
        except ValueError:
            raise ValueError("Repeat count must be a whole number.") from None
        if n < 1:
            raise ValueError("Repeat count must be at least 1.")
        return n

    def _press_once(self, key) -> None:
        self._controller.press(key)
        self._controller.release(key)

    def _worker_loop(self, key, base_ms: int, rand_max: int, repeat: int | None) -> None:
        try:
            count = 0
            while not self._stop.is_set():
                if repeat is not None and count >= repeat:
                    break
                delay = base_ms
                if rand_max > 0:
                    delay = max(1, base_ms + random.randint(-rand_max, rand_max))
                end = time.perf_counter() + delay / 1000.0
                while time.perf_counter() < end:
                    if self._stop.is_set():
                        return
                    time.sleep(min(0.05, end - time.perf_counter()))
                if self._stop.is_set():
                    break
                self._press_once(key)
                count += 1
        finally:
            # Always reset UI (early return during sleep skipped this before).
            self.after(0, self._on_worker_finished)

    def _on_worker_finished(self) -> None:
        self._running = False
        self._worker = None
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        self.status.configure(text="Stopped", foreground="gray")

    def start_pressing(self) -> None:
        if self._running:
            return
        try:
            key = self._resolve_key()
            base_ms, rand_max = self._read_interval_ms()
            repeat = self._read_repeat_count()
        except ValueError as e:
            messagebox.showerror("Auto Key Presser", str(e))
            return

        self._stop.clear()
        self._running = True
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        mode = f"{repeat} times" if repeat is not None else "until stopped"
        self.status.configure(text=f"Running ({mode})…", foreground="green")

        self._worker = threading.Thread(
            target=self._worker_loop,
            args=(key, base_ms, rand_max, repeat),
            daemon=True,
        )
        self._worker.start()

    def stop_pressing(self) -> None:
        if not self._running:
            return
        self._stop.set()
        self.status.configure(text="Stopping…", foreground="orange")

    def _toggle_start_stop(self) -> None:
        if self._running:
            self.stop_pressing()
        else:
            self.start_pressing()

    def _toggle_start_stop_safe(self) -> None:
        self.after(0, self._toggle_start_stop)

    def _hotkey_listener_loop(self) -> None:
        while not self._app_closing:
            hk = self._hotkey_str
            try:
                with kb.GlobalHotKeys({hk: self._toggle_start_stop_safe}) as h:
                    self._hotkeys = h
                    h.join()
            except ValueError as e:
                self.after(
                    0,
                    lambda err=str(e): messagebox.showerror(
                        "Auto Key Presser", f"Invalid hotkey ({hk}): {err}"
                    ),
                )
                time.sleep(0.3)
            except Exception as e:
                if not self._app_closing:
                    self.after(
                        0,
                        lambda err=str(e): messagebox.showerror("Auto Key Presser", f"Hotkey error: {err}"),
                    )
                time.sleep(0.3)
            self._hotkeys = None

    def _start_hotkey_listener(self) -> None:
        def run() -> None:
            self._hotkey_listener_loop()

        self._hotkey_thread = threading.Thread(target=run, daemon=True)
        self._hotkey_thread.start()

    def _restart_hotkey_listener(self) -> None:
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass

    def _hotkey_dialog(self) -> None:
        d = tk.Toplevel(self)
        d.title("Hotkey setting")
        d.transient(self)
        d.grab_set()
        d.minsize(280, 120)

        ttk.Label(
            d,
            text="Choose the key used to start and stop (same as OP Auto Clicker’s F6).",
            wraplength=320,
        ).pack(padx=12, pady=(12, 8))

        choices = [f"F{i}" for i in range(1, 13)]
        choices += [chr(c) for c in range(ord("a"), ord("z") + 1)]
        choices += ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

        var = tk.StringVar(value="F6")
        cb = ttk.Combobox(d, width=20, values=choices, state="readonly", textvariable=var)
        cb.pack(padx=12, pady=4)

        def on_ok() -> None:
            v = var.get().strip()
            if v.upper().startswith("F") and v[1:].isdigit():
                n = int(v[1:])
                if 1 <= n <= 12:
                    self._hotkey_str = f"<f{n}>"
            elif len(v) == 1:
                self._hotkey_str = v.lower()
            else:
                messagebox.showerror("Hotkey setting", "Pick an F-key or a single character.")
                return
            self._refresh_hotkey_ui()
            self._restart_hotkey_listener()
            d.destroy()

        def on_cancel() -> None:
            d.destroy()

        bf = ttk.Frame(d)
        bf.pack(pady=12)
        ttk.Button(bf, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=4)

    def _on_close(self) -> None:
        self._app_closing = True
        self.stop_pressing()
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = AutoKeyPresserApp()
    app.mainloop()
