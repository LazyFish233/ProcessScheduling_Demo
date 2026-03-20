"""
进程调度模拟系统
支持：基于优先级的时间片轮转（Priority RR）和多级反馈队列（MLFQ）
"""

import tkinter as tk
from tkinter import ttk, messagebox
from pcb import PCB, STATE_LABEL
from algorithms import PriorityRR, MLFQ

# ─────────────────────────── 全局颜色配置 ─────────────────────────────── #
PROCESS_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
    "#9c755f", "#bab0ac",
]
BG_MAIN = "#f5f5f5"
BG_PANEL = "#ffffff"
COLOR_READY = "#76b7b2"
COLOR_EXEC = "#f28e2b"
COLOR_FINISH = "#59a14f"
COLOR_WAIT = "#e15759"

FONT_TITLE = ("微软雅黑", 11, "bold")
FONT_NORMAL = ("微软雅黑", 9)
FONT_MONO = ("Consolas", 9)


# ════════════════════════════════════════════════════════════════════════ #
#  进程输入面板（可添加/删除行）
# ════════════════════════════════════════════════════════════════════════ #

class ProcessInputPanel(tk.Frame):
    """可编辑的进程参数输入表格"""

    COLS = ("进程名", "优先级(1-100)", "到达时间", "运行时间")

    def __init__(self, master, **kw):
        super().__init__(master, bg=BG_PANEL, **kw)
        self._build()

    def _build(self):
        # 表头
        for c, text in enumerate(self.COLS):
            tk.Label(self, text=text, font=FONT_NORMAL, bg="#dce6f0",
                     relief="groove", width=12).grid(
                row=0, column=c, sticky="nsew", padx=1, pady=1)

        self.entries: list[list[tk.Entry]] = []
        self._row_count = 0

        btn_frame = tk.Frame(self, bg=BG_PANEL)
        btn_frame.grid(row=100, column=0, columnspan=4, pady=4)
        tk.Button(btn_frame, text="+ 添加进程", command=self.add_row,
                  font=FONT_NORMAL, bg="#4e79a7", fg="white",
                  relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(btn_frame, text="- 删除末行", command=self.del_row,
                  font=FONT_NORMAL, bg="#e15759", fg="white",
                  relief="flat", padx=8).pack(side="left", padx=4)

        # 默认填入 4 个进程示例
        defaults = [
            ("P1", "10", "0", "6"),
            ("P2", "30", "2", "4"),
            ("P3", "20", "4", "5"),
            ("P4", "40", "6", "3"),
        ]
        for row in defaults:
            self.add_row(row)

    def add_row(self, values=("", "", "", "")):
        r = self._row_count + 1
        row_entries = []
        for c, val in enumerate(values):
            e = tk.Entry(self, font=FONT_MONO, width=12, justify="center")
            e.insert(0, val)
            e.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
            row_entries.append(e)
        self.entries.append(row_entries)
        self._row_count += 1

    def del_row(self):
        if not self.entries:
            return
        for e in self.entries[-1]:
            e.destroy()
        self.entries.pop()
        self._row_count -= 1

    def get_processes(self) -> list[PCB]:
        """解析输入，返回 PCB 列表；失败则抛出 ValueError"""
        processes = []
        names = set()
        for i, row in enumerate(self.entries):
            name = row[0].get().strip()
            if not name:
                raise ValueError(f"第 {i+1} 行：进程名不能为空")
            if name in names:
                raise ValueError(f"第 {i+1} 行：进程名 '{name}' 重复")
            names.add(name)

            try:
                pri = int(row[1].get())
                arr = int(row[2].get())
                burst = int(row[3].get())
            except ValueError:
                raise ValueError(f"第 {i+1} 行：优先级/到达时间/运行时间必须为整数")

            if not (1 <= pri <= 100):
                raise ValueError(f"第 {i+1} 行：优先级须在 1~100 之间")
            if arr < 0:
                raise ValueError(f"第 {i+1} 行：到达时间须 ≥ 0")
            if burst < 1:
                raise ValueError(f"第 {i+1} 行：运行时间须 ≥ 1")

            processes.append(PCB(name, pri, arr, burst))

        if not processes:
            raise ValueError("请至少添加一个进程")
        return processes

    def set_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for row in self.entries:
            for e in row:
                e.config(state=state)


# ════════════════════════════════════════════════════════════════════════ #
#  甘特图 Canvas
# ════════════════════════════════════════════════════════════════════════ #

class GanttCanvas(tk.Canvas):
    ROW_H = 22
    CELL_W = 28
    LEFT_MARGIN = 60
    TOP_MARGIN = 10

    def __init__(self, master, **kw):
        kw.setdefault("bg", "#fdfdfd")
        kw.setdefault("height", 200)
        super().__init__(master, **kw)
        self._color_map: dict[str, str] = {}
        self._color_idx = 0
        self._proc_rows: dict[str, int] = {}  # 进程名 → 行号

    def reset(self):
        self.delete("all")
        self._color_map = {}
        self._color_idx = 0
        self._proc_rows = {}

    def _proc_color(self, name: str) -> str:
        if name not in self._color_map:
            self._color_map[name] = PROCESS_COLORS[
                self._color_idx % len(PROCESS_COLORS)]
            self._color_idx += 1
        return self._color_map[name]

    def _proc_row(self, name: str) -> int:
        if name not in self._proc_rows:
            self._proc_rows[name] = len(self._proc_rows)
        return self._proc_rows[name]

    def draw_gantt(self, gantt: list[tuple[str, int, int]]):
        """根据甘特图数据重绘"""
        self.delete("all")

        if not gantt:
            return

        max_time = max(end for _, _, end in gantt)
        num_procs = len(set(name for name, _, _ in gantt))

        required_h = self.TOP_MARGIN * 2 + num_procs * (self.ROW_H + 4) + 24
        self.config(height=max(120, required_h))

        # 进程名标签
        for name, row in sorted(self._proc_rows.items(), key=lambda x: x[1]):
            y = self.TOP_MARGIN + row * (self.ROW_H + 4) + self.ROW_H // 2
            self.create_text(self.LEFT_MARGIN - 5, y, text=name,
                             anchor="e", font=FONT_MONO)

        # 色块
        for name, start, end in gantt:
            row = self._proc_row(name)
            color = self._proc_color(name)
            x0 = self.LEFT_MARGIN + start * self.CELL_W
            x1 = self.LEFT_MARGIN + end * self.CELL_W
            y0 = self.TOP_MARGIN + row * (self.ROW_H + 4)
            y1 = y0 + self.ROW_H
            self.create_rectangle(x0, y0, x1, y1, fill=color,
                                  outline="white", width=1)
            if x1 - x0 >= 16:
                self.create_text((x0 + x1) // 2, (y0 + y1) // 2,
                                 text=str(end - start), font=("Consolas", 8),
                                 fill="white")

        # 时间轴
        timeline_y = self.TOP_MARGIN + num_procs * (self.ROW_H + 4) + 8
        for t in range(0, max_time + 1):
            x = self.LEFT_MARGIN + t * self.CELL_W
            self.create_line(x, timeline_y - 3, x, timeline_y + 3, fill="gray")
            if t % max(1, max_time // 20) == 0 or t == max_time:
                self.create_text(x, timeline_y + 10, text=str(t),
                                 font=("Consolas", 7), fill="gray")

        # 更新滚动区域
        self.config(scrollregion=self.bbox("all"))


# ════════════════════════════════════════════════════════════════════════ #
#  队列可视化 Canvas
# ════════════════════════════════════════════════════════════════════════ #

class QueueCanvas(tk.Canvas):
    BOX_W, BOX_H = 52, 26
    GAP = 6

    def __init__(self, master, mode="prr", **kw):
        kw.setdefault("bg", "#fdfdfd")
        kw.setdefault("height", 120)
        super().__init__(master, **kw)
        self.mode = mode  # "prr" or "mlfq"
        self._color_map: dict[str, str] = {}
        self._color_idx = 0

    def _proc_color(self, name: str) -> str:
        if name not in self._color_map:
            self._color_map[name] = PROCESS_COLORS[
                self._color_idx % len(PROCESS_COLORS)]
            self._color_idx += 1
        return self._color_map[name]

    def reset(self):
        self.delete("all")
        self._color_map = {}
        self._color_idx = 0

    def draw_prr(self, snapshot: dict):
        self.delete("all")
        executing = snapshot.get('executing')
        ready = snapshot.get('ready', [])

        # 执行中
        y = 14
        if executing:
            self._draw_box(10, y, executing, COLOR_EXEC, "执行中")
        self.create_text(10, y + self.BOX_H + 10,
                         text="▼ 就绪队列（优先级升序）", anchor="w",
                         font=FONT_NORMAL, fill="#555")
        y2 = y + self.BOX_H + 28
        for i, name in enumerate(ready):
            x = 10 + i * (self.BOX_W + self.GAP)
            self._draw_box(x, y2, name, COLOR_READY)
        if not ready:
            self.create_text(10, y2 + 12, text="（空）",
                             anchor="w", font=FONT_NORMAL, fill="#aaa")
        self.config(scrollregion=self.bbox("all"))

    def draw_mlfq(self, snapshot: dict):
        self.delete("all")
        queues = snapshot.get('queues', [[], [], []])
        executing = snapshot.get('executing')
        exec_level = snapshot.get('executing_level')
        ts_list = snapshot.get('ts', [1, 2, 4])

        y = 10
        if executing is not None:
            lbl = f"执行中 (Q{exec_level})"
            self._draw_box(10, y, executing, COLOR_EXEC, lbl)
            y += self.BOX_H + 14

        for level, q in enumerate(queues):
            ts_val = ts_list[level] if level < len(ts_list) else "?"
            self.create_text(10, y + 10,
                             text=f"Q{level} (时间片={ts_val}):",
                             anchor="w", font=FONT_NORMAL, fill="#333")
            y += 22
            for i, name in enumerate(q):
                x = 10 + i * (self.BOX_W + self.GAP)
                self._draw_box(x, y, name, COLOR_READY)
            if not q:
                self.create_text(10, y + 10, text="（空）",
                                 anchor="w", font=FONT_NORMAL, fill="#aaa")
            y += self.BOX_H + 10

        self.config(scrollregion=self.bbox("all"))

    def _draw_box(self, x, y, name, color, label=None):
        self.create_rectangle(x, y, x + self.BOX_W, y + self.BOX_H,
                              fill=color, outline="white", width=2)
        self.create_text(x + self.BOX_W // 2, y + self.BOX_H // 2,
                         text=name, font=("微软雅黑", 9, "bold"), fill="white")
        if label:
            self.create_text(x + self.BOX_W // 2, y - 8,
                             text=label, font=("微软雅黑", 8), fill="#555")


# ════════════════════════════════════════════════════════════════════════ #
#  单个算法标签页
# ════════════════════════════════════════════════════════════════════════ #

class SchedulerTab(tk.Frame):
    def __init__(self, master, algo_name: str, **kw):
        super().__init__(master, bg=BG_MAIN, **kw)
        self.algo_name = algo_name           # "prr" or "mlfq"
        self.scheduler = None
        self._auto_id = None                 # after() 回调 id
        self._running = False
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self):
        # ── 顶部：输入 + 参数 ──
        top = tk.Frame(self, bg=BG_MAIN)
        top.pack(fill="x", padx=10, pady=6)

        # 左：进程参数表
        proc_frame = tk.LabelFrame(top, text=" 进程参数 ", font=FONT_TITLE,
                                   bg=BG_PANEL, relief="groove")
        proc_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.proc_input = ProcessInputPanel(proc_frame)
        self.proc_input.pack(padx=6, pady=6)

        # 右：算法参数
        param_frame = tk.LabelFrame(top, text=" 算法参数 ", font=FONT_TITLE,
                                    bg=BG_PANEL, relief="groove")
        param_frame.pack(side="left", fill="y", padx=(0, 0))

        tk.Label(param_frame, text="基础时间片：", font=FONT_NORMAL,
                 bg=BG_PANEL).grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.ts_var = tk.StringVar(value="2")
        tk.Entry(param_frame, textvariable=self.ts_var, width=6,
                 font=FONT_MONO, justify="center").grid(row=0, column=1, padx=4)

        if self.algo_name == "prr":
            tk.Label(param_frame, text="优先级衰减值：", font=FONT_NORMAL,
                     bg=BG_PANEL).grid(row=1, column=0, sticky="e", padx=6, pady=4)
            self.decay_var = tk.StringVar(value="2")
            tk.Entry(param_frame, textvariable=self.decay_var, width=6,
                     font=FONT_MONO, justify="center").grid(row=1, column=1, padx=4)

        tk.Label(param_frame, text="自动速度(ms)：", font=FONT_NORMAL,
                 bg=BG_PANEL).grid(row=2, column=0, sticky="e", padx=6, pady=4)
        self.speed_var = tk.IntVar(value=600)
        tk.Scale(param_frame, from_=100, to=2000, orient="horizontal",
                 variable=self.speed_var, length=120,
                 bg=BG_PANEL, font=FONT_NORMAL).grid(row=2, column=1, padx=4)

        # ── 控制按钮栏 ──
        ctrl = tk.Frame(self, bg=BG_MAIN)
        ctrl.pack(fill="x", padx=10, pady=2)

        btn_cfg = dict(font=FONT_NORMAL, relief="flat", padx=12, pady=4)
        self.btn_start = tk.Button(ctrl, text="▶ 开始", bg="#4e79a7", fg="white",
                                   command=self._on_start, **btn_cfg)
        self.btn_start.pack(side="left", padx=4)
        self.btn_step = tk.Button(ctrl, text="⏭ 单步", bg="#76b7b2", fg="white",
                                  command=self._on_step, state="disabled", **btn_cfg)
        self.btn_step.pack(side="left", padx=4)
        self.btn_auto = tk.Button(ctrl, text="⏯ 自动", bg="#f28e2b", fg="white",
                                  command=self._on_auto, state="disabled", **btn_cfg)
        self.btn_auto.pack(side="left", padx=4)
        self.btn_reset = tk.Button(ctrl, text="↺ 重置", bg="#e15759", fg="white",
                                   command=self._on_reset, state="disabled", **btn_cfg)
        self.btn_reset.pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="请设置参数后点击「开始」")
        tk.Label(ctrl, textvariable=self.status_var, font=FONT_NORMAL,
                 bg=BG_MAIN, fg="#555").pack(side="left", padx=16)

        # ── 中部：进程状态表 + 队列可视化 ──
        mid = tk.Frame(self, bg=BG_MAIN)
        mid.pack(fill="both", expand=True, padx=10, pady=4)

        # 进程状态 Treeview
        tree_frame = tk.LabelFrame(mid, text=" 进程状态 ", font=FONT_TITLE,
                                   bg=BG_PANEL, relief="groove")
        tree_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._build_treeview(tree_frame)

        # 队列可视化
        queue_frame = tk.LabelFrame(mid, text=" 队列可视化 ", font=FONT_TITLE,
                                    bg=BG_PANEL, relief="groove")
        queue_frame.pack(side="left", fill="both", expand=True)
        qmode = "mlfq" if self.algo_name == "mlfq" else "prr"
        self.queue_canvas = QueueCanvas(queue_frame, mode=qmode,
                                        width=360, height=180)
        qs = ttk.Scrollbar(queue_frame, orient="vertical",
                           command=self.queue_canvas.yview)
        self.queue_canvas.configure(yscrollcommand=qs.set)
        qs.pack(side="right", fill="y")
        self.queue_canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # ── 甘特图 ──
        gantt_frame = tk.LabelFrame(self, text=" 甘特图（时间轴）",
                                    font=FONT_TITLE, bg=BG_PANEL, relief="groove")
        gantt_frame.pack(fill="x", padx=10, pady=4)
        self.gantt_canvas = GanttCanvas(gantt_frame, height=120)
        gscroll = ttk.Scrollbar(gantt_frame, orient="horizontal",
                                command=self.gantt_canvas.xview)
        self.gantt_canvas.configure(xscrollcommand=gscroll.set)
        gscroll.pack(side="bottom", fill="x")
        self.gantt_canvas.pack(fill="x", padx=4, pady=4)

        # ── 底部：日志 + 统计 ──
        bot = tk.Frame(self, bg=BG_MAIN)
        bot.pack(fill="both", expand=True, padx=10, pady=4)

        log_frame = tk.LabelFrame(bot, text=" 调度日志 ", font=FONT_TITLE,
                                  bg=BG_PANEL, relief="groove")
        log_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.log_text = tk.Text(log_frame, height=8, font=FONT_MONO,
                                state="disabled", bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white", wrap="word")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # 统计结果
        stat_frame = tk.LabelFrame(bot, text=" 统计结果 ", font=FONT_TITLE,
                                   bg=BG_PANEL, relief="groove")
        stat_frame.pack(side="left", fill="both", expand=True)
        self._build_stat_table(stat_frame)

    # ------------------------------------------------------------------ #
    def _build_treeview(self, parent):
        cols = ("进程名", "优先级", "到达", "运行", "已用", "剩余", "状态")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        col_widths = [60, 60, 50, 50, 50, 50, 80]
        for col, w in zip(cols, col_widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center")

        # 状态着色 tag
        self.tree.tag_configure("E", background="#fff3cd")
        self.tree.tag_configure("F", background="#d4edda")
        self.tree.tag_configure("W", background="#f8d7da")
        self.tree.tag_configure("R", background="#d1ecf1")

        ts = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ts.set)
        ts.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_stat_table(self, parent):
        cols = ("进程名", "到达时间", "运行时间", "开始时间", "完成时间", "周转时间")
        self.stat_tree = ttk.Treeview(parent, columns=cols, show="headings", height=6)
        for col in cols:
            self.stat_tree.heading(col, text=col)
            self.stat_tree.column(col, width=72, anchor="center")
        ts = ttk.Scrollbar(parent, orient="vertical",
                           command=self.stat_tree.yview)
        self.stat_tree.configure(yscrollcommand=ts.set)
        ts.pack(side="right", fill="y")
        self.stat_tree.pack(fill="both", expand=True, padx=4, pady=4)

        self.avg_label = tk.Label(parent, text="平均周转时间：—",
                                  font=FONT_TITLE, bg=BG_PANEL, fg="#4e79a7")
        self.avg_label.pack(pady=4)

    # ================================================================== #
    #  控制逻辑
    # ================================================================== #

    def _parse_params(self):
        """解析所有参数，返回 (processes, ts, decay)；失败则弹窗并返回 None"""
        try:
            processes = self.proc_input.get_processes()
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return None

        try:
            ts = int(self.ts_var.get())
            if ts < 1:
                raise ValueError()
        except ValueError:
            messagebox.showerror("输入错误", "基础时间片须为正整数")
            return None

        decay = 2
        if self.algo_name == "prr":
            try:
                decay = int(self.decay_var.get())
                if decay < 1:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("输入错误", "优先级衰减值须为正整数")
                return None

        return processes, ts, decay

    def _on_start(self):
        params = self._parse_params()
        if params is None:
            return
        processes, ts, decay = params

        if self.algo_name == "prr":
            self.scheduler = PriorityRR(processes, ts, decay)
        else:
            self.scheduler = MLFQ(processes, ts)

        # 初始化甘特图颜色映射（按进程名提前注册颜色）
        self.gantt_canvas.reset()
        self.queue_canvas.reset()
        for i, p in enumerate(processes):
            self.gantt_canvas._proc_color(p.name)
            self.gantt_canvas._proc_row(p.name)
            self.queue_canvas._proc_color(p.name)

        self._refresh_treeview()
        self._clear_log()
        self._refresh_stat_table()
        self._update_queue_canvas()

        self.proc_input.set_enabled(False)
        self.btn_start.config(state="disabled")
        self.btn_step.config(state="normal")
        self.btn_auto.config(state="normal")
        self.btn_reset.config(state="normal")
        self.status_var.set("就绪 — 点击「单步」或「自动」开始调度")

    def _on_step(self):
        if self.scheduler is None or self.scheduler.is_done():
            return
        events = self.scheduler.step()
        self._append_log(events)
        self._refresh_treeview()
        self._update_queue_canvas()
        self.gantt_canvas.draw_gantt(self.scheduler.gantt)
        if self.scheduler.is_done():
            self._on_done()

    def _on_auto(self):
        if self._running:
            # 暂停
            self._running = False
            if self._auto_id:
                self.after_cancel(self._auto_id)
                self._auto_id = None
            self.btn_auto.config(text="⏯ 自动")
            self.status_var.set("已暂停")
        else:
            if self.scheduler is None or self.scheduler.is_done():
                return
            self._running = True
            self.btn_auto.config(text="⏸ 暂停")
            self.status_var.set("自动运行中…")
            self._auto_loop()

    def _auto_loop(self):
        if not self._running:
            return
        if self.scheduler is None or self.scheduler.is_done():
            self._running = False
            self.btn_auto.config(text="⏯ 自动")
            self._on_done()
            return
        self._on_step()
        self._auto_id = self.after(self.speed_var.get(), self._auto_loop)

    def _on_reset(self):
        if self._running:
            self._running = False
            if self._auto_id:
                self.after_cancel(self._auto_id)
                self._auto_id = None

        if self.scheduler:
            self.scheduler.reset()

        self.gantt_canvas.reset()
        self.queue_canvas.reset()
        self._clear_log()
        self._clear_treeview()
        self._refresh_stat_table()

        self.proc_input.set_enabled(True)
        self.btn_start.config(state="normal")
        self.btn_step.config(state="disabled")
        self.btn_auto.config(text="⏯ 自动", state="disabled")
        self.btn_reset.config(state="disabled")
        self.status_var.set("已重置 — 请重新设置参数后点击「开始」")
        self.scheduler = None

    def _on_done(self):
        self._running = False
        self.btn_auto.config(text="⏯ 自动", state="disabled")
        self.btn_step.config(state="disabled")
        if self.scheduler and self.scheduler.deadlock:
            self.status_var.set("⚠ 检测到死锁，模拟终止")
            messagebox.showwarning("死锁", "系统检测到死锁，模拟已终止！")
        else:
            self.status_var.set("✓ 所有进程已完成")
        self._refresh_stat_table()

    # ================================================================== #
    #  刷新 UI
    # ================================================================== #

    def _refresh_treeview(self):
        if self.scheduler is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for p in self.scheduler.processes:
            state_str = STATE_LABEL.get(p.state, p.state)
            self.tree.insert("", "end", values=(
                p.name, p.priority, p.arrival_time, p.burst_time,
                p.used_cpu, p.remaining, state_str,
            ), tags=(p.state,))

    def _clear_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _update_queue_canvas(self):
        if self.scheduler is None:
            return
        snap = self.scheduler.get_queue_snapshot()
        if self.algo_name == "prr":
            self.queue_canvas.draw_prr(snap)
        else:
            self.queue_canvas.draw_mlfq(snap)

    def _append_log(self, events: list[str]):
        self.log_text.config(state="normal")
        for e in events:
            self.log_text.insert("end", e + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _refresh_stat_table(self):
        for item in self.stat_tree.get_children():
            self.stat_tree.delete(item)
        if self.scheduler is None:
            self.avg_label.config(text="平均周转时间：—")
            return
        stats = self.scheduler.get_stats()
        for s in stats:
            ta = s['turnaround'] if s['turnaround'] != -1 else "—"
            st = s['start'] if s['start'] != -1 else "—"
            ft = s['finish'] if s['finish'] != -1 else "—"
            self.stat_tree.insert("", "end", values=(
                s['name'], s['arrival'], s['burst'], st, ft, ta))
        avg = self.scheduler.avg_turnaround()
        self.avg_label.config(
            text=f"平均周转时间：{avg:.2f}" if avg else "平均周转时间：—")

    # ------------------------------------------------------------------ #
    def get_avg_turnaround(self) -> float | None:
        if self.scheduler is None:
            return None
        return self.scheduler.avg_turnaround()


# ════════════════════════════════════════════════════════════════════════ #
#  性能对比标签页
# ════════════════════════════════════════════════════════════════════════ #

class CompareTab(tk.Frame):
    def __init__(self, master, prr_tab: SchedulerTab, mlfq_tab: SchedulerTab, **kw):
        super().__init__(master, bg=BG_MAIN, **kw)
        self.prr_tab = prr_tab
        self.mlfq_tab = mlfq_tab
        self._build()

    def _build(self):
        tk.Label(self, text="两种调度算法性能对比", font=("微软雅黑", 14, "bold"),
                 bg=BG_MAIN, fg="#333").pack(pady=16)

        btn = tk.Button(self, text="刷新对比数据", font=FONT_NORMAL,
                        bg="#4e79a7", fg="white", relief="flat",
                        padx=12, pady=6, command=self.refresh)
        btn.pack(pady=6)

        frame = tk.Frame(self, bg=BG_MAIN)
        frame.pack(fill="both", expand=True, padx=30, pady=10)

        # 左：Priority RR
        prr_f = tk.LabelFrame(frame, text=" 基于优先级的时间片轮转（Priority RR）",
                              font=FONT_TITLE, bg=BG_PANEL, relief="groove")
        prr_f.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.prr_avg_lbl = tk.Label(prr_f, text="平均周转时间：—",
                                    font=("微软雅黑", 12, "bold"),
                                    bg=BG_PANEL, fg="#4e79a7")
        self.prr_avg_lbl.pack(pady=10)
        self.prr_desc = tk.Text(prr_f, height=10, font=FONT_NORMAL,
                                state="disabled", bg=BG_PANEL, wrap="word",
                                relief="flat")
        self.prr_desc.pack(fill="both", expand=True, padx=8, pady=4)

        # 右：MLFQ
        mlfq_f = tk.LabelFrame(frame, text=" 多级反馈队列（MLFQ）",
                               font=FONT_TITLE, bg=BG_PANEL, relief="groove")
        mlfq_f.pack(side="left", fill="both", expand=True)
        self.mlfq_avg_lbl = tk.Label(mlfq_f, text="平均周转时间：—",
                                     font=("微软雅黑", 12, "bold"),
                                     bg=BG_PANEL, fg="#f28e2b")
        self.mlfq_avg_lbl.pack(pady=10)
        self.mlfq_desc = tk.Text(mlfq_f, height=10, font=FONT_NORMAL,
                                 state="disabled", bg=BG_PANEL, wrap="word",
                                 relief="flat")
        self.mlfq_desc.pack(fill="both", expand=True, padx=8, pady=4)

        # 结论
        self.conclusion = tk.Label(self, text="", font=FONT_TITLE,
                                   bg=BG_MAIN, fg="#e15759", wraplength=700)
        self.conclusion.pack(pady=12)

        self._write_desc(self.prr_desc,
            "算法原理：\n"
            "  维护一个按优先级排序的就绪队列（优先级数值越小越高）。\n"
            "  每次选取优先级最高的进程执行一个时间片。\n"
            "  执行结束后，该进程优先级衰减（+decay），重新入队排序。\n"
            "  若有更高优先级进程到达则发生抢占。\n\n"
            "特点：\n"
            "  · 响应时间取决于初始优先级设置\n"
            "  · 高优先级进程可能长期占据 CPU（可通过衰减缓解）\n"
            "  · 适合对优先级有严格要求的场景")
        self._write_desc(self.mlfq_desc,
            "算法原理：\n"
            "  设置 3 级就绪队列（Q0/Q1/Q2），时间片分别为 1×/2×/4× 基础时间片。\n"
            "  新进程进入 Q0；时间片内未完成则降级到下一队列。\n"
            "  高编号队列只在低编号队列全空时才获得 CPU。\n"
            "  高优先级队列有进程时立即抢占当前低优先级队列执行进程。\n\n"
            "特点：\n"
            "  · 短作业在 Q0/Q1 快速完成，响应时间短\n"
            "  · 长作业逐渐降入 Q2，获得更大时间片减少切换\n"
            "  · 兼顾公平性与效率，无需预知进程运行时间")

    @staticmethod
    def _write_desc(widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def refresh(self):
        prr_avg = self.prr_tab.get_avg_turnaround()
        mlfq_avg = self.mlfq_tab.get_avg_turnaround()

        if prr_avg is not None and prr_avg > 0:
            self.prr_avg_lbl.config(text=f"平均周转时间：{prr_avg:.2f}")
        else:
            self.prr_avg_lbl.config(text="平均周转时间：— （尚未完成）")

        if mlfq_avg is not None and mlfq_avg > 0:
            self.mlfq_avg_lbl.config(text=f"平均周转时间：{mlfq_avg:.2f}")
        else:
            self.mlfq_avg_lbl.config(text="平均周转时间：— （尚未完成）")

        if prr_avg and mlfq_avg and prr_avg > 0 and mlfq_avg > 0:
            if prr_avg < mlfq_avg:
                diff = mlfq_avg - prr_avg
                msg = (f"结论：Priority RR 平均周转时间更短（少 {diff:.2f}），"
                       f"在本次参数下表现更优。")
            elif mlfq_avg < prr_avg:
                diff = prr_avg - mlfq_avg
                msg = (f"结论：MLFQ 平均周转时间更短（少 {diff:.2f}），"
                       f"在本次参数下表现更优。")
            else:
                msg = "结论：两种算法本次平均周转时间相同。"
            self.conclusion.config(text=msg)
        else:
            self.conclusion.config(text="请先分别运行两种算法至完成，再刷新对比数据。")


# ════════════════════════════════════════════════════════════════════════ #
#  主窗口
# ════════════════════════════════════════════════════════════════════════ #

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("进程调度模拟系统")
        self.geometry("1100x780")
        self.minsize(900, 650)
        self.config(bg=BG_MAIN)
        self._set_style()
        self._build()

    def _set_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_TITLE, padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", "#4e79a7"), ("!selected", "#dce6f0")],
                  foreground=[("selected", "white"), ("!selected", "#333")])
        style.configure("Treeview", font=FONT_MONO, rowheight=22)
        style.configure("Treeview.Heading", font=FONT_NORMAL)

    def _build(self):
        # 标题栏
        header = tk.Frame(self, bg="#4e79a7", height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="进程调度模拟系统",
                 font=("微软雅黑", 14, "bold"), bg="#4e79a7", fg="white").pack(
            side="left", padx=20, pady=10)
        tk.Label(header,
                 text="Priority Round-Robin  &  Multi-Level Feedback Queue",
                 font=("微软雅黑", 9), bg="#4e79a7", fg="#c8d8ed").pack(
            side="left", padx=4)

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        self.prr_tab = SchedulerTab(nb, algo_name="prr")
        self.mlfq_tab = SchedulerTab(nb, algo_name="mlfq")
        self.compare_tab = CompareTab(nb, self.prr_tab, self.mlfq_tab)

        nb.add(self.prr_tab, text="  基于优先级的时间片轮转  ")
        nb.add(self.mlfq_tab, text="  多级反馈队列  ")
        nb.add(self.compare_tab, text="  性能对比  ")


# ════════════════════════════════════════════════════════════════════════ #

if __name__ == "__main__":
    app = App()
    app.mainloop()
