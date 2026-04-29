from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .hotkeys import GlobalHotkey
from .ocr import OcrEngine, OcrRow
from .screenshot import capture_primary_screen
from .storage import AppStorage


class UwoHelperApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("UWO Helper")
        self.geometry("1280x820")
        self.minsize(1100, 720)

        self.storage = AppStorage(Path.cwd())
        self.storage.ensure()
        self.ocr = OcrEngine()
        self.hotkey = GlobalHotkey(lambda: self.after(0, self.capture_screen))
        self.current_image: Path | None = None
        self.preview_image: tk.PhotoImage | None = None

        self._configure_style()
        self._build_ui()
        self._load_screenshots()
        self._install_hotkey()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        self.colors = {
            "bg": "#f7f5ee",
            "surface": "#fffdfa",
            "soft": "#fffaf3",
            "line": "#ded8ce",
            "ink": "#2d2926",
            "muted": "#746d65",
            "accent": "#c76842",
            "active": "#f3e9df",
            "dark": "#2d2926",
        }
        self.configure(bg=self.colors["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Surface.TFrame", background=self.colors["surface"], bordercolor=self.colors["line"])
        style.configure("Soft.TFrame", background=self.colors["soft"])
        style.configure("TLabel", background=self.colors["surface"], foreground=self.colors["ink"])
        style.configure("Muted.TLabel", background=self.colors["surface"], foreground=self.colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=self.colors["surface"], foreground=self.colors["ink"], font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Section.TLabel", background=self.colors["soft"], foreground=self.colors["ink"], font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="#ffffff", bordercolor=self.colors["accent"], padding=(14, 8), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#b85f3d")])
        style.configure("TButton", background=self.colors["surface"], foreground=self.colors["ink"], bordercolor=self.colors["line"], padding=(12, 8))
        style.configure("Treeview", background=self.colors["surface"], fieldbackground=self.colors["surface"], foreground=self.colors["ink"], rowheight=30, bordercolor=self.colors["line"])
        style.configure("Treeview.Heading", background="#f1ede4", foreground=self.colors["ink"], font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", self.colors["active"])], foreground=[("selected", self.colors["ink"])])

    def _build_ui(self) -> None:
        shell = tk.Frame(self, bg=self.colors["bg"])
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        self._build_sidebar(shell).grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self._build_workspace(shell).grid(row=0, column=1, sticky="nsew", padx=(0, 14))
        self._build_rail(shell).grid(row=0, column=2, sticky="nsew")

    def _build_sidebar(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.colors["surface"], width=230, highlightthickness=1, highlightbackground=self.colors["line"])
        frame.grid_propagate(False)

        tk.Label(frame, text="航海本地助手", bg=self.colors["surface"], fg=self.colors["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(frame, text="截图 · OCR · 收益计算", bg=self.colors["surface"], fg=self.colors["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=16, pady=(0, 16))

        for text, count in [("工作台", "12"), ("价格簿", "86"), ("航线", "24"), ("OCR 校对", "3"), ("船厂库", "41"), ("导入导出", "")]:
            label = f"{text}{'   ' + count if count else ''}"
            bg = self.colors["active"] if text == "工作台" else self.colors["surface"]
            fg = "#8a4a32" if text == "工作台" else self.colors["ink"]
            tk.Label(frame, text=label, bg=bg, fg=fg, anchor="w", font=("Microsoft YaHei UI", 11), padx=14, pady=10).pack(fill="x", padx=16, pady=2)

        ship = tk.Frame(frame, bg=self.colors["soft"], highlightthickness=1, highlightbackground=self.colors["line"])
        ship.pack(fill="x", padx=16, pady=18)
        tk.Label(ship, text="当前船只", bg=self.colors["soft"], fg=self.colors["muted"], anchor="w").pack(fill="x", padx=12, pady=(12, 2))
        tk.Label(ship, text="探险型商船队", bg=self.colors["soft"], fg=self.colors["ink"], anchor="w", font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", padx=12, pady=2)
        tk.Label(ship, text="货舱 1,280 · 航速 14.6", bg=self.colors["soft"], fg=self.colors["ink"], anchor="w").pack(fill="x", padx=12, pady=(2, 12))
        return frame

    def _build_workspace(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["line"])
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        toolbar = tk.Frame(frame, bg=self.colors["surface"])
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        ttk.Button(toolbar, text="截图", style="Primary.TButton", command=self.capture_screen).pack(side="left")
        ttk.Button(toolbar, text="打开截图目录", command=self.open_screenshot_folder).pack(side="left", padx=8)
        self.hotkey_label = tk.Label(toolbar, text="热键初始化中...", bg=self.colors["surface"], fg=self.colors["muted"])
        self.hotkey_label.pack(side="right")

        content = tk.Frame(frame, bg=self.colors["surface"])
        content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        content.columnconfigure(0, weight=7)
        content.columnconfigure(1, weight=5)
        content.rowconfigure(0, weight=1)

        self._build_capture_panel(content).grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_review_panel(content).grid(row=0, column=1, sticky="nsew")
        return frame

    def _build_capture_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.colors["soft"], highlightthickness=1, highlightbackground=self.colors["line"])
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        tk.Label(frame, text="截图记录", bg=self.colors["soft"], fg=self.colors["ink"], font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        self.screenshot_list = tk.Listbox(frame, height=7, activestyle="none", bg=self.colors["surface"], fg=self.colors["ink"], highlightthickness=1, highlightbackground=self.colors["line"], selectbackground=self.colors["active"], selectforeground=self.colors["ink"], borderwidth=0)
        self.screenshot_list.grid(row=1, column=0, sticky="ew", padx=14)
        self.screenshot_list.bind("<<ListboxSelect>>", self._on_screenshot_selected)

        self.preview_label = tk.Label(frame, text="还没有截图", bg="#f1ede4", fg=self.colors["muted"], anchor="center")
        self.preview_label.grid(row=2, column=0, sticky="nsew", padx=14, pady=14)
        return frame

    def _build_review_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.colors["soft"], highlightthickness=1, highlightbackground=self.colors["line"])
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        tk.Label(frame, text="OCR 校对", bg=self.colors["soft"], fg=self.colors["ink"], font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        self.screen_type = ttk.Combobox(frame, values=["交易所", "船厂", "任务", "其他"], state="readonly")
        self.screen_type.current(0)
        self.screen_type.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        self.review_table = ttk.Treeview(frame, columns=("field", "value", "confidence", "note"), show="headings")
        for key, title, width in [("field", "字段", 90), ("value", "识别结果", 140), ("confidence", "置信度", 70), ("note", "备注", 160)]:
            self.review_table.heading(key, text=title)
            self.review_table.column(key, width=width, stretch=True)
        self.review_table.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 12))

        self.save_review_button = ttk.Button(frame, text="确认入库", style="Primary.TButton", state="disabled")
        self.save_review_button.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        return frame

    def _build_rail(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.colors["surface"], width=320, highlightthickness=1, highlightbackground=self.colors["line"])
        frame.grid_propagate(False)

        profit = tk.Frame(frame, bg=self.colors["dark"])
        profit.pack(fill="x", padx=16, pady=16)
        tk.Label(profit, text="本次推荐净利润", bg=self.colors["dark"], fg="#d8cfc4").pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(profit, text="58,240", bg=self.colors["dark"], fg="#fffdfa", font=("Consolas", 28, "bold")).pack(anchor="w", padx=14, pady=4)
        tk.Label(profit, text="+8,736 / 分", bg=self.colors["dark"], fg="#f1b27d").pack(anchor="w", padx=14, pady=(0, 12))

        tips = tk.Frame(frame, bg=self.colors["soft"], highlightthickness=1, highlightbackground=self.colors["line"])
        tips.pack(fill="x", padx=16, pady=(0, 16))
        for line in ["当前实现", "1. 手动按钮截图", "2. Ctrl+Alt+O 热键截图", "3. OCR 校对占位", "4. 截图本地留档"]:
            tk.Label(tips, text=line, bg=self.colors["soft"], fg=self.colors["ink"], anchor="w").pack(fill="x", padx=12, pady=4)

        self.status_label = tk.Label(frame, text="就绪", bg=self.colors["surface"], fg=self.colors["muted"], anchor="w", wraplength=280, justify="left")
        self.status_label.pack(fill="x", padx=16, pady=6)
        return frame

    def _install_hotkey(self) -> None:
        if self.hotkey.start():
            self.hotkey_label.configure(text="全局热键: Ctrl+Alt+O")
        else:
            self.hotkey_label.configure(text="窗口热键: Ctrl+Alt+O")
            self.bind_all("<Control-Alt-o>", lambda _event: self.capture_screen())

    def capture_screen(self) -> None:
        self._set_status("准备截图...")
        self.withdraw()
        self.after(300, self._capture_after_hide)

    def _capture_after_hide(self) -> None:
        path = self.storage.next_screenshot_path()
        try:
            capture_primary_screen(path)
        except Exception as exc:
            self.deiconify()
            self._set_status(f"截图失败: {exc}")
            return

        self.deiconify()
        self.lift()
        self.focus_force()
        self._set_status(f"截图已保存: {path.name}")
        self._load_screenshots(select_path=path)
        self._load_ocr_rows(self.ocr.recognize(path))

    def open_screenshot_folder(self) -> None:
        self.storage.ensure()
        os.startfile(self.storage.screenshot_dir)

    def _load_screenshots(self, select_path: Path | None = None) -> None:
        self.screenshot_list.delete(0, tk.END)
        self._screenshot_paths: list[Path] = []
        selected_index = 0
        for index, record in enumerate(self.storage.list_screenshots()):
            self._screenshot_paths.append(record.path)
            self.screenshot_list.insert(tk.END, record.display_name)
            if select_path is not None and record.path == select_path:
                selected_index = index

        if self._screenshot_paths:
            self.screenshot_list.selection_set(selected_index)
            self.screenshot_list.activate(selected_index)
            self._show_screenshot(self._screenshot_paths[selected_index])

    def _on_screenshot_selected(self, _event=None) -> None:
        selection = self.screenshot_list.curselection()
        if not selection:
            return
        path = self._screenshot_paths[selection[0]]
        self._show_screenshot(path)
        self._load_ocr_rows(self.ocr.recognize(path))

    def _show_screenshot(self, path: Path) -> None:
        self.current_image = path
        image = tk.PhotoImage(file=str(path))
        max_width = max(self.preview_label.winfo_width(), 520)
        max_height = max(self.preview_label.winfo_height(), 360)
        factor = max(1, int(max(image.width() / max_width, image.height() / max_height)))
        if factor > 1:
            image = image.subsample(factor, factor)
        self.preview_image = image
        self.preview_label.configure(image=image, text="")

    def _load_ocr_rows(self, rows: list[OcrRow]) -> None:
        self.review_table.delete(*self.review_table.get_children())
        for row in rows:
            self.review_table.insert("", tk.END, values=(row.field, row.value, row.confidence, row.note))
        self.save_review_button.configure(state="normal" if self.current_image else "disabled")

    def _set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def _on_close(self) -> None:
        self.hotkey.stop()
        self.destroy()


def main() -> int:
    app = UwoHelperApp()
    app.mainloop()
    return 0
