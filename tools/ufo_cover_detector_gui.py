from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from ufo_cover_detector import detect_pdf


def desktop_dir() -> Path:
    path = Path.home() / "Desktop"
    return path if path.exists() else Path.home()


def clean_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return cleaned.strip("_") or "ufo_cover_detect"


class UfoCoverDetectorGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("UFO 覆盖区域识别评估")
        self.root.geometry("760x460")
        self.root.minsize(720, 420)

        self.input_pdf = StringVar()
        self.ufo_no = StringVar()
        self.output_dir = StringVar(value=str(desktop_dir()))
        self.min_score = DoubleVar(value=0.55)
        self.open_after_done = BooleanVar(value=True)
        self.status = StringVar(value="选择 RH PDF 后点击生成，原文件不会被修改。")
        self.result_path = StringVar(value="")
        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.build_layout()
        self.root.after(120, self.poll_worker)

    def build_layout(self) -> None:
        self.root.columnconfigure(0, weight=0, minsize=300)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=(18, 16))
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        title = ttk.Label(left, text="UFO 识别评估", font=("Microsoft YaHei UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 12))

        ttk.Label(left, text="RH PDF").grid(row=1, column=0, sticky="w")
        input_row = ttk.Frame(left)
        input_row.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.input_pdf).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="选择", command=self.pick_input_pdf).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="UFO 号码（手填）").grid(row=3, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.ufo_no).grid(row=4, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(left, text="输出目录").grid(row=5, column=0, sticky="w")
        output_row = ttk.Frame(left)
        output_row.grid(row=6, column=0, sticky="ew", pady=(4, 12))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="选择", command=self.pick_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(left, text="识别阈值").grid(row=7, column=0, sticky="w")
        threshold_row = ttk.Frame(left)
        threshold_row.grid(row=8, column=0, sticky="ew", pady=(4, 6))
        threshold_row.columnconfigure(0, weight=1)
        ttk.Scale(
            threshold_row,
            from_=0.20,
            to=0.80,
            variable=self.min_score,
            orient="horizontal",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(threshold_row, textvariable=self.min_score, width=5).grid(row=0, column=1, padx=(8, 0))

        ttk.Checkbutton(left, text="生成后打开 PDF", variable=self.open_after_done).grid(row=9, column=0, sticky="w", pady=(4, 12))

        self.generate_button = ttk.Button(left, text="生成红框评估 PDF", command=self.generate)
        self.generate_button.grid(row=10, column=0, sticky="ew", pady=(6, 8))

        ttk.Button(left, text="打开输出目录", command=self.open_output_dir).grid(row=11, column=0, sticky="ew")

        right = ttk.Frame(self.root, padding=(16, 16))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        ttk.Label(right, text="输出结果", font=("Microsoft YaHei UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(right, textvariable=self.status, wraplength=390).grid(row=1, column=0, sticky="ew", pady=(8, 10))

        self.log = ttk.Treeview(right, columns=("value",), show="tree headings", height=9)
        self.log.heading("#0", text="项目")
        self.log.heading("value", text="内容")
        self.log.column("#0", width=130, anchor="w")
        self.log.column("value", width=320, anchor="w")
        self.log.grid(row=2, column=0, sticky="nsew")

        ttk.Label(right, text="生成的是评估 PDF：红框表示之后会被遮盖的区域；不会修改原文件。", wraplength=390).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )

    def pick_input_pdf(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 RH PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if selected:
            self.input_pdf.set(selected)

    def pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir.get() or str(desktop_dir()))
        if selected:
            self.output_dir.set(selected)

    def output_pdf_path(self, input_pdf: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ufo_part = clean_stem(self.ufo_no.get())
        return Path(self.output_dir.get()) / f"ufo_cover_detect_{input_pdf.stem}_{ufo_part}_{stamp}.pdf"

    def generate(self) -> None:
        input_pdf = Path(self.input_pdf.get().strip())
        if not input_pdf.exists() or input_pdf.suffix.lower() != ".pdf":
            messagebox.showerror("缺少 PDF", "请先选择一个有效的 RH PDF 文件。")
            return
        output_dir = Path(self.output_dir.get().strip())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("输出目录不可用", f"无法创建输出目录：{exc}")
            return

        output_pdf = self.output_pdf_path(input_pdf)
        min_score = float(self.min_score.get())
        ufo_no = self.ufo_no.get().strip()
        self.generate_button.configure(state="disabled")
        self.status.set("正在识别并生成评估 PDF...")
        self.clear_log()
        self.insert_log("输入文件", str(input_pdf))
        self.insert_log("输出文件", str(output_pdf))
        self.insert_log("UFO号码", ufo_no or "未填写")
        self.insert_log("阈值", f"{min_score:.2f}")

        thread = threading.Thread(
            target=self.run_detection,
            args=(input_pdf, output_pdf, min_score),
            daemon=True,
        )
        thread.start()

    def run_detection(self, input_pdf: Path, output_pdf: Path, min_score: float) -> None:
        try:
            detections = detect_pdf(input_pdf, output_pdf, dpi=150, min_score=min_score)
        except Exception as exc:  # noqa: BLE001
            self.worker_queue.put(("error", exc))
            return
        self.worker_queue.put(("done", (output_pdf, detections)))

    def poll_worker(self) -> None:
        try:
            kind, payload = self.worker_queue.get_nowait()
        except queue.Empty:
            self.root.after(120, self.poll_worker)
            return

        self.generate_button.configure(state="normal")
        if kind == "error":
            self.status.set("生成失败。")
            messagebox.showerror("生成失败", str(payload))
        else:
            output_pdf, detections = payload  # type: ignore[misc]
            self.result_path.set(str(output_pdf))
            self.status.set(f"完成：识别到 {len(detections)} 个覆盖候选框。")
            self.insert_log("候选框数量", str(len(detections)))
            for detection in detections:
                self.insert_log(
                    f"第 {detection.page} 页",
                    f"{detection.kind} score={detection.score:.2f}",
                )
            if self.open_after_done.get():
                self.open_path(output_pdf)

        self.root.after(120, self.poll_worker)

    def clear_log(self) -> None:
        for item_id in self.log.get_children():
            self.log.delete(item_id)

    def insert_log(self, name: str, value: str) -> None:
        self.log.insert("", "end", text=name, values=(value,))

    def open_output_dir(self) -> None:
        self.open_path(Path(self.output_dir.get() or desktop_dir()))

    def open_path(self, path: Path) -> None:
        try:
            import os

            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))


def main() -> None:
    root = Tk()
    UfoCoverDetectorGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
