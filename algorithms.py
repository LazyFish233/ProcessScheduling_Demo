"""调度算法模块：基于优先级的时间片轮转（PriorityRR）和多级反馈队列（MLFQ）"""

import copy
from pcb import PCB, STATE_READY, STATE_EXECUTE, STATE_WAIT, STATE_FINISH


# ======================================================================== #
#  辅助：深拷贝 PCB 列表，用于初始化时保存原始数据
# ======================================================================== #

def _snapshot(processes):
    return [copy.copy(p) for p in processes]


# ======================================================================== #
#  Algorithm 1: 基于优先级的时间片轮转（Priority Round-Robin）
# ======================================================================== #

class PriorityRR:
    """
    基于优先级的时间片轮转调度算法。
    - 单就绪队列，按当前 priority 升序（数值小 = 优先级高）。
    - 每执行完一个时间片，优先级衰减 decay（priority += decay）。
    - 若有更高优先级进程到达，抢占当前执行进程。
    - step() 每次推进一个时间片。
    """

    def __init__(self, processes: list[PCB], time_slice: int, decay: int = 2):
        self.original = _snapshot(processes)
        self.time_slice = time_slice
        self.decay = decay
        self._init_state()

    # ------------------------------------------------------------------ #
    def _init_state(self):
        """（重）初始化运行状态"""
        self.processes = _snapshot(self.original)
        for p in self.processes:
            p.reset()

        self.clock = 0          # 当前时钟
        self.ready_queue: list[PCB] = []
        self.current: PCB | None = None   # 当前执行进程
        self.slice_remain = 0   # 当前时间片剩余

        # 甘特图记录：[(进程名, 开始时刻, 结束时刻), ...]
        self.gantt: list[tuple[str, int, int]] = []
        self.log: list[str] = []
        self.deadlock = False

    def reset(self):
        self._init_state()

    # ------------------------------------------------------------------ #
    def _arrive(self):
        """将到达时间 <= clock 且状态为 R 的进程加入就绪队列"""
        for p in self.processes:
            if p.state == STATE_READY and p.arrival_time <= self.clock:
                if p not in self.ready_queue and p is not self.current:
                    self.ready_queue.append(p)
        self._sort_ready()

    def _sort_ready(self):
        self.ready_queue.sort(key=lambda p: (p.priority, p.arrival_time))

    # ------------------------------------------------------------------ #
    def step(self) -> list[str]:
        """
        推进一个时间片，返回本步事件日志列表。
        """
        if self.is_done():
            return []

        events: list[str] = []

        # 1. 新进程到达
        self._arrive()

        # 2. 若无当前执行进程，从就绪队列选一个
        if self.current is None:
            if self.ready_queue:
                self.current = self.ready_queue.pop(0)
                self.current.state = STATE_EXECUTE
                self.slice_remain = self.time_slice
                if self.current.start_time == -1:
                    self.current.start_time = self.clock
                events.append(f"[T={self.clock}] {self.current.name} 开始执行 "
                               f"(优先级={self.current.priority})")
            else:
                # CPU 空闲，时钟推进
                events.append(f"[T={self.clock}] CPU 空闲")
                self.clock += self.time_slice
                self._check_deadlock(events)
                self.log.extend(events)
                return events

        # 3. 执行一个时间片（或剩余时间）
        run = min(self.time_slice, self.current.remaining, self.slice_remain)
        start_t = self.clock
        self.clock += run
        self.current.used_cpu += run
        self.current.remaining -= run
        self.slice_remain -= run

        self.gantt.append((self.current.name, start_t, self.clock))
        events.append(f"[T={start_t}~{self.clock}] {self.current.name} 执行 "
                      f"(已用={self.current.used_cpu}, 剩余={self.current.remaining}, "
                      f"优先级={self.current.priority})")

        # 4. 判断进程是否完成
        if self.current.remaining <= 0:
            self.current.state = STATE_FINISH
            self.current.finish_time = self.clock
            events.append(f"[T={self.clock}] {self.current.name} 完成 "
                          f"(周转时间={self.current.turnaround_time})")
            self.current = None
            self.slice_remain = 0
        else:
            # 5. 时间片用完，优先级衰减，重新入队
            if self.slice_remain <= 0:
                self.current.priority += self.decay
                self.current.state = STATE_READY
                self.ready_queue.append(self.current)
                events.append(f"[T={self.clock}] {self.current.name} 时间片耗尽，"
                               f"优先级降为 {self.current.priority}，重新入队")
                self.current = None
                self.slice_remain = 0

        # 6. 新到达进程检测（抢占）
        self._arrive()
        if self.current is not None and self.ready_queue:
            top = self.ready_queue[0]
            if top.priority < self.current.priority:
                # 抢占
                events.append(f"[T={self.clock}] {top.name}(优先级={top.priority}) "
                               f"抢占 {self.current.name}(优先级={self.current.priority})")
                self.current.state = STATE_READY
                self.ready_queue.append(self.current)
                self._sort_ready()
                self.current = self.ready_queue.pop(0)
                self.current.state = STATE_EXECUTE
                self.slice_remain = self.time_slice
                if self.current.start_time == -1:
                    self.current.start_time = self.clock

        self._check_deadlock(events)
        self.log.extend(events)
        return events

    # ------------------------------------------------------------------ #
    def _check_deadlock(self, events):
        not_done = [p for p in self.processes if p.state != STATE_FINISH]
        if not_done and not self.ready_queue and self.current is None:
            waiting = [p for p in not_done if p.state == STATE_WAIT]
            if len(waiting) == len(not_done):
                self.deadlock = True
                events.append(f"[T={self.clock}] *** 死锁检测：所有剩余进程处于等待状态 ***")

    # ------------------------------------------------------------------ #
    def is_done(self) -> bool:
        all_finish = all(p.state == STATE_FINISH for p in self.processes)
        return all_finish or self.deadlock

    # ------------------------------------------------------------------ #
    def get_queue_snapshot(self) -> dict:
        """返回当前队列快照，供 GUI 显示"""
        return {
            'ready': [p.name for p in self.ready_queue],
            'executing': self.current.name if self.current else None,
        }

    # ------------------------------------------------------------------ #
    def get_stats(self) -> list[dict]:
        """返回各进程统计数据列表"""
        stats = []
        for p in self.processes:
            stats.append({
                'name': p.name,
                'arrival': p.arrival_time,
                'burst': p.burst_time,
                'start': p.start_time,
                'finish': p.finish_time,
                'turnaround': p.turnaround_time,
            })
        return stats

    def avg_turnaround(self) -> float:
        finished = [p for p in self.processes if p.finish_time != -1]
        if not finished:
            return 0.0
        return sum(p.turnaround_time for p in finished) / len(finished)


# ======================================================================== #
#  Algorithm 2: 多级反馈队列（Multi-Level Feedback Queue）
# ======================================================================== #

class MLFQ:
    """
    多级反馈队列调度算法（3 级）。
    - Q0 时间片 = base_ts × 1，Q1 = base_ts × 2，Q2 = base_ts × 4。
    - 新到达进程进入 Q0（FIFO）。
    - 优先调度编号最小的非空队列。
    - 时间片用完未完成 → 降级到下一队列；完成 → 状态 F。
    - 高优先级队列非空时抢占当前低优先级队列的执行进程。
    """

    LEVELS = 3

    def __init__(self, processes: list[PCB], base_ts: int):
        self.original = _snapshot(processes)
        self.base_ts = base_ts
        # 各级时间片大小
        self.ts = [base_ts * (2 ** i) for i in range(self.LEVELS)]
        self._init_state()

    # ------------------------------------------------------------------ #
    def _init_state(self):
        self.processes = _snapshot(self.original)
        for p in self.processes:
            p.reset()

        self.clock = 0
        self.queues: list[list[PCB]] = [[] for _ in range(self.LEVELS)]
        self.current: PCB | None = None
        self.current_level = 0      # 当前执行进程所在队列级别
        self.slice_remain = 0

        self.gantt: list[tuple[str, int, int]] = []
        self.log: list[str] = []
        self.deadlock = False

    def reset(self):
        self._init_state()

    # ------------------------------------------------------------------ #
    def _arrive(self):
        """到达的新进程进入 Q0"""
        for p in self.processes:
            if (p.state == STATE_READY
                    and p.arrival_time <= self.clock
                    and p not in self.queues[0]
                    and p is not self.current
                    and not any(p in q for q in self.queues[1:])):
                p.queue_level = 0
                self.queues[0].append(p)

    def _pick_next(self) -> tuple[PCB | None, int]:
        """从最高优先级非空队列取出队首进程"""
        for level, q in enumerate(self.queues):
            if q:
                return q.pop(0), level
        return None, -1

    # ------------------------------------------------------------------ #
    def step(self) -> list[str]:
        if self.is_done():
            return []

        events: list[str] = []

        # 1. 新进程到达
        self._arrive()

        # 2. 无执行进程时选取
        if self.current is None:
            proc, level = self._pick_next()
            if proc is None:
                events.append(f"[T={self.clock}] CPU 空闲")
                self.clock += self.base_ts
                self._arrive()
                self._check_deadlock(events)
                self.log.extend(events)
                return events
            self.current = proc
            self.current_level = level
            self.slice_remain = self.ts[level]
            self.current.state = STATE_EXECUTE
            if self.current.start_time == -1:
                self.current.start_time = self.clock
            events.append(f"[T={self.clock}] {self.current.name} 从 Q{level} 开始执行 "
                          f"(时间片={self.ts[level]}, 剩余={self.current.remaining})")

        # 3. 执行
        run = min(self.slice_remain, self.current.remaining)
        start_t = self.clock
        self.clock += run
        self.current.used_cpu += run
        self.current.remaining -= run
        self.slice_remain -= run

        self.gantt.append((self.current.name, start_t, self.clock))
        events.append(f"[T={start_t}~{self.clock}] {self.current.name}(Q{self.current_level}) "
                      f"执行 (已用={self.current.used_cpu}, 剩余={self.current.remaining})")

        # 4. 完成判断
        if self.current.remaining <= 0:
            self.current.state = STATE_FINISH
            self.current.finish_time = self.clock
            events.append(f"[T={self.clock}] {self.current.name} 完成 "
                          f"(周转时间={self.current.turnaround_time})")
            self.current = None
            self.slice_remain = 0
        elif self.slice_remain <= 0:
            # 5. 时间片用完，降级
            next_level = min(self.current_level + 1, self.LEVELS - 1)
            self.current.queue_level = next_level
            self.current.state = STATE_READY
            self.queues[next_level].append(self.current)
            events.append(f"[T={self.clock}] {self.current.name} 时间片耗尽，"
                          f"降级到 Q{next_level}")
            self.current = None
            self.slice_remain = 0

        # 6. 检查是否有更高优先级队列到达（抢占）
        self._arrive()
        if self.current is not None:
            for level in range(self.current_level):
                if self.queues[level]:
                    preemptor = self.queues[level][0]
                    events.append(f"[T={self.clock}] Q{level} 中 {preemptor.name} "
                                  f"抢占 Q{self.current_level} 中 {self.current.name}")
                    self.current.state = STATE_READY
                    self.queues[self.current_level].insert(0, self.current)
                    self.current = None
                    self.slice_remain = 0
                    break

        self._check_deadlock(events)
        self.log.extend(events)
        return events

    # ------------------------------------------------------------------ #
    def _check_deadlock(self, events):
        not_done = [p for p in self.processes if p.state != STATE_FINISH]
        if not_done and all(not q for q in self.queues) and self.current is None:
            waiting = [p for p in not_done if p.state == STATE_WAIT]
            if len(waiting) == len(not_done):
                self.deadlock = True
                events.append(f"[T={self.clock}] *** 死锁：所有剩余进程处于等待状态 ***")

    # ------------------------------------------------------------------ #
    def is_done(self) -> bool:
        all_finish = all(p.state == STATE_FINISH for p in self.processes)
        return all_finish or self.deadlock

    # ------------------------------------------------------------------ #
    def get_queue_snapshot(self) -> dict:
        return {
            'queues': [[p.name for p in q] for q in self.queues],
            'executing': self.current.name if self.current else None,
            'executing_level': self.current_level if self.current else None,
            'ts': self.ts,
        }

    # ------------------------------------------------------------------ #
    def get_stats(self) -> list[dict]:
        stats = []
        for p in self.processes:
            stats.append({
                'name': p.name,
                'arrival': p.arrival_time,
                'burst': p.burst_time,
                'start': p.start_time,
                'finish': p.finish_time,
                'turnaround': p.turnaround_time,
            })
        return stats

    def avg_turnaround(self) -> float:
        finished = [p for p in self.processes if p.finish_time != -1]
        if not finished:
            return 0.0
        return sum(p.turnaround_time for p in finished) / len(finished)
