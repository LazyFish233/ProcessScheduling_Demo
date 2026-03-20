"""PCB - 进程控制块数据类"""

# 进程状态常量
STATE_READY = 'R'      # 就绪
STATE_EXECUTE = 'E'    # 执行
STATE_WAIT = 'W'       # 等待
STATE_FINISH = 'F'     # 完成

STATE_LABEL = {
    STATE_READY: '就绪(R)',
    STATE_EXECUTE: '执行(E)',
    STATE_WAIT: '等待(W)',
    STATE_FINISH: '完成(F)',
}


class PCB:
    """进程控制块"""

    def __init__(self, name: str, priority: int, arrival_time: int, burst_time: int):
        self.name = name
        self.init_priority = priority   # 初始优先级（静态，不变）
        self.priority = priority        # 当前优先级（Priority RR 中会衰减）
        self.arrival_time = arrival_time
        self.burst_time = burst_time

        self.used_cpu = 0               # 已使用 CPU 时间
        self.remaining = burst_time     # 剩余运行时间
        self.state = STATE_READY

        self.start_time = -1            # 首次开始执行时间
        self.finish_time = -1           # 完成时间

        self.queue_level = 0            # MLFQ 专用：所在队列编号（0/1/2）

    # ------------------------------------------------------------------ #
    def reset(self):
        """将 PCB 重置为初始状态（保留静态字段）"""
        self.priority = self.init_priority
        self.used_cpu = 0
        self.remaining = self.burst_time
        self.state = STATE_READY
        self.start_time = -1
        self.finish_time = -1
        self.queue_level = 0

    # ------------------------------------------------------------------ #
    @property
    def turnaround_time(self) -> int:
        """周转时间 = 完成时间 - 到达时间"""
        if self.finish_time == -1:
            return -1
        return self.finish_time - self.arrival_time

    def __repr__(self):
        return (f"PCB({self.name}, pri={self.priority}, "
                f"arr={self.arrival_time}, burst={self.burst_time}, "
                f"used={self.used_cpu}, rem={self.remaining}, "
                f"state={self.state})")
