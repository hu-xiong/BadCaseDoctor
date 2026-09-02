# -*- coding: utf-8 -*-
"""Excel / CSV 一键清洗 — 双击运行即可。"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

DATE_HINT = re.compile(
    r"(date|日期|时间|time|日|月|年)",
    re.IGNORECASE,
)


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                return pd.read_csv(path, encoding=enc)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path, encoding="latin-1")
    raise ValueError(f"不支持的文件类型: {suffix}")


def clean_table(
    df: pd.DataFrame,
    *,
    strip_cells: bool,
    drop_empty_rows: bool,
    drop_dupes: bool,
    normalize_dates: bool,
) -> tuple[pd.DataFrame, dict]:
    out = df.copy()
    stats = {
        "rows_in": len(out),
        "cols": len(out.columns),
        "stripped": 0,
        "empty_dropped": 0,
        "dupes_dropped": 0,
        "dates_fixed": 0,
    }

    if strip_cells:
        for col in out.columns:
            # pandas 3 may use StringDtype instead of object
            if not (pd.api.types.is_string_dtype(out[col]) or out[col].dtype == object):
                continue
            original = out[col]
            as_str = original.map(lambda v: v.strip() if isinstance(v, str) else v)
            changed = original.ne(as_str) & original.notna()
            stats["stripped"] += int(changed.sum())
            out[col] = as_str

    if drop_empty_rows:
        before = len(out)
        out = out.dropna(how="all")
        stats["empty_dropped"] = before - len(out)

    if normalize_dates:
        for col in out.columns:
            if not DATE_HINT.search(str(col)):
                continue
            parsed = pd.to_datetime(out[col], errors="coerce", format="mixed")
            fixed = parsed.notna().sum()
            if fixed:
                out[col] = parsed.dt.strftime("%Y-%m-%d")
                stats["dates_fixed"] += int(fixed)

    if drop_dupes:
        before = len(out)
        out = out.drop_duplicates()
        stats["dupes_dropped"] = before - len(out)

    stats["rows_out"] = len(out)
    return out, stats


def default_out_path(src: Path) -> Path:
    return src.with_name(f"{src.stem}_已清洗.xlsx")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("表格一键清洗 · ¥35 版")
        self.geometry("520x420")
        self.resizable(False, False)

        self.path_var = tk.StringVar()
        self.strip_var = tk.BooleanVar(value=True)
        self.empty_var = tk.BooleanVar(value=True)
        self.dupe_var = tk.BooleanVar(value=True)
        self.date_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="选择一个 Excel 或 CSV 文件开始")

        pad = {"padx": 16, "pady": 6}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Excel / CSV 一键清洗", font=("Microsoft YaHei UI", 14, "bold")).pack(
            anchor="w", **pad
        )
        ttk.Label(
            frm,
            text="去空格 · 去空行 · 去重 · 日期规范化 → 导出干净 Excel",
            foreground="#555",
        ).pack(anchor="w", padx=16)

        row = ttk.Frame(frm)
        row.pack(fill="x", **pad)
        ttk.Entry(row, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览…", command=self.pick_file).pack(side="left", padx=(8, 0))

        opts = ttk.LabelFrame(frm, text="清洗选项", padding=10)
        opts.pack(fill="x", **pad)
        ttk.Checkbutton(opts, text="去掉单元格首尾空格", variable=self.strip_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="删除整行空白", variable=self.empty_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="删除完全重复行", variable=self.dupe_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="自动规范日期列 (→ YYYY-MM-DD)", variable=self.date_var).pack(
            anchor="w"
        )

        ttk.Button(frm, text="开始清洗并导出", command=self.run_clean).pack(fill="x", **pad)
        ttk.Label(frm, textvariable=self.status_var, wraplength=470).pack(anchor="w", **pad)

        self.progress = ttk.Progressbar(frm, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(0, 8))

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择表格",
            filetypes=[
                ("表格文件", "*.xlsx *.xlsm *.xls *.csv"),
                ("全部文件", "*.*"),
            ],
        )
        if path:
            self.path_var.set(path)

    def run_clean(self) -> None:
        raw = self.path_var.get().strip()
        if not raw:
            messagebox.showwarning("提示", "请先选择文件")
            return
        path = Path(raw)
        if not path.exists():
            messagebox.showerror("错误", "文件不存在")
            return

        self.progress.start(12)
        self.status_var.set("清洗中…")
        threading.Thread(target=self._worker, args=(path,), daemon=True).start()

    def _worker(self, path: Path) -> None:
        try:
            df = load_table(path)
            cleaned, stats = clean_table(
                df,
                strip_cells=self.strip_var.get(),
                drop_empty_rows=self.empty_var.get(),
                drop_dupes=self.dupe_var.get(),
                normalize_dates=self.date_var.get(),
            )
            out = default_out_path(path)
            cleaned.to_excel(out, index=False)
            msg = (
                f"完成 → {out.name}\n"
                f"行数 {stats['rows_in']} → {stats['rows_out']}｜"
                f"去空格 {stats['stripped']}｜删空行 {stats['empty_dropped']}｜"
                f"去重 {stats['dupes_dropped']}｜日期 {stats['dates_fixed']}"
            )
            self.after(0, lambda: self._done(True, msg, out))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._done(False, str(exc), None))

    def _done(self, ok: bool, msg: str, out: Path | None) -> None:
        self.progress.stop()
        self.status_var.set(msg)
        if ok and out is not None:
            messagebox.showinfo("清洗完成", msg)
            try:
                import os

                os.startfile(out.parent)  # type: ignore[attr-defined]
            except OSError:
                pass
        else:
            messagebox.showerror("失败", msg)


if __name__ == "__main__":
    App().mainloop()
