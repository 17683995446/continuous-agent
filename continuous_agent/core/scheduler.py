#!/usr/bin/env python3
"""
任务调度器
=========
负责任务的智能调度和优先级管理
"""

import time
import threading
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import logging
import json
from pathlib import Path

logger = logging.getLogger("TaskScheduler")


class ScheduleStrategy(Enum):
    """调度策略"""
    FIFO = "fifo"                    # 先进先出
    PRIORITY = "priority"            # 优先级优先
    SHORTEST_FIRST = "shortest"      # 最短任务优先
    ROUND_ROBIN = "round_robin"      # 轮询
    SMART = "smart"                  # 智能调度（综合考虑）


@dataclass(order=True)
class ScheduledTask:
    """调度任务包装器"""
    priority: int
    created_time: float = field(compare=True)
    task_id: str = field(compare=False)
    estimated_duration: float = field(default=60.0, compare=False)
    task_data: Dict[str, Any] = field(default_factory=dict, compare=False)


class TaskScheduler:
    """
    任务调度器
    
    功能：
    - 智能任务调度
    - 优先级管理
    - 依赖解析
    - 资源分配
    - 负载均衡
    """
    
    def __init__(
        self,
        strategy: ScheduleStrategy = ScheduleStrategy.SMART,
        max_concurrent: int = 3,
        history_file: Optional[str] = None
    ):
        self.strategy = strategy
        self.max_concurrent = max_concurrent
        self.history_file = Path(history_file) if history_file else None
        
        # 任务队列
        self._queue: List[ScheduledTask] = []
        self._queue_lock = threading.Lock()
        
        # 运行中的任务
        self._running: Dict[str, ScheduledTask] = {}
        self._running_lock = threading.Lock()
        
        # 已完成任务
        self._completed: List[Dict[str, Any]] = []
        
        # 依赖图
        self._dependencies: Dict[str, Set[str]] = {}
        
        # 任务历史（用于学习）
        self._task_history: List[Dict[str, Any]] = []
        
        # 调度统计
        self._stats = {
            "total_scheduled": 0,
            "total_completed": 0,
            "total_failed": 0,
            "avg_wait_time": 0,
            "avg_execution_time": 0
        }
        
        # 回调函数
        self._on_schedule: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
        
        # 加载历史
        self._load_history()
    
    def _load_history(self):
        """加载历史数据"""
        if self.history_file and self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._task_history = data.get("history", [])
                    self._stats = data.get("stats", self._stats)
                    logger.info(f"加载历史数据: {len(self._task_history)} 条记录")
            except Exception as e:
                logger.warning(f"加载历史失败: {e}")
    
    def _save_history(self):
        """保存历史数据"""
        if self.history_file:
            try:
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "history": self._task_history[-1000:],  # 只保留最近1000条
                        "stats": self._stats
                    }, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存历史失败: {e}")
    
    def schedule(
        self,
        task_id: str,
        priority: int = 2,
        estimated_duration: float = 60.0,
        dependencies: Optional[List[str]] = None,
        task_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        调度新任务
        
        Args:
            task_id: 任务ID
            priority: 优先级（0最高，3最低）
            estimated_duration: 预估执行时间（秒）
            dependencies: 依赖的任务ID列表
            task_data: 任务数据
            
        Returns:
            是否成功加入队列
        """
        with self._queue_lock:
            # 检查是否已存在
            if any(t.task_id == task_id for t in self._queue):
                logger.warning(f"任务 {task_id} 已在队列中")
                return False
            
            # 创建调度任务
            scheduled_task = ScheduledTask(
                priority=priority,
                created_time=time.time(),
                task_id=task_id,
                estimated_duration=estimated_duration,
                task_data=task_data or {}
            )
            
            # 添加到队列
            heapq.heappush(self._queue, scheduled_task)
            
            # 记录依赖
            if dependencies:
                self._dependencies[task_id] = set(dependencies)
            
            self._stats["total_scheduled"] += 1
            
            logger.info(f"调度任务 {task_id} (优先级={priority}, 预估时间={estimated_duration}s)")
            
            if self._on_schedule:
                self._on_schedule(task_id, priority)
            
            return True
    
    def get_next(self) -> Optional[ScheduledTask]:
        """
        获取下一个可执行的任务
        
        Returns:
            下一个任务，如果没有则返回None
        """
        with self._queue_lock:
            if not self._queue:
                return None
            
            # 根据策略选择任务
            if self.strategy == ScheduleStrategy.FIFO:
                # FIFO：直接取最早的任务
                task = heapq.heappop(self._queue)
            
            elif self.strategy == ScheduleStrategy.PRIORITY:
                # 优先级：堆已经按优先级排序
                task = heapq.heappop(self._queue)
            
            elif self.strategy == ScheduleStrategy.SHORTEST_FIRST:
                # 最短优先：找到预估时间最短的任务，不破坏堆结构
                shortest_idx = 0
                shortest_duration = self._queue[0].estimated_duration
                for i in range(1, len(self._queue)):
                    if self._queue[i].estimated_duration < shortest_duration:
                        shortest_duration = self._queue[i].estimated_duration
                        shortest_idx = i
                # 交换到堆顶再弹出，保持堆结构
                self._queue[0], self._queue[shortest_idx] = self._queue[shortest_idx], self._queue[0]
                task = heapq.heappop(self._queue)
            
            elif self.strategy == ScheduleStrategy.SMART:
                # 智能调度：综合考虑优先级、预估时间、历史数据
                task = self._smart_select()
            
            elif self.strategy == ScheduleStrategy.ROUND_ROBIN:
                # Bug#70修复: 实现真正的轮询策略
                # ROUND_ROBIN 在不同优先级之间轮转，确保公平调度
                if not hasattr(self, '_rr_last_priority') or self._rr_last_priority is None:
                    self._rr_last_priority = -1
                
                # 找到下一个优先级（轮转）
                priorities_in_queue = sorted(set(t.priority for t in self._queue))
                if priorities_in_queue:
                    # 找到比上次高一级的优先级
                    next_priority = None
                    for p in priorities_in_queue:
                        if p > self._rr_last_priority:
                            next_priority = p
                            break
                    if next_priority is None:
                        # 回到最低优先级
                        next_priority = priorities_in_queue[0]
                    
                    self._rr_last_priority = next_priority
                    
                    # 从该优先级的任务中选最早入队的
                    for i, t in enumerate(self._queue):
                        if t.priority == next_priority:
                            # 交换到堆顶再弹出
                            self._queue[0], self._queue[i] = self._queue[i], self._queue[0]
                            task = heapq.heappop(self._queue)
                            break
                    else:
                        task = heapq.heappop(self._queue)
                else:
                    task = heapq.heappop(self._queue)
            
            else:
                task = heapq.heappop(self._queue)
            
            if task:
                # 检查依赖
                if not self._check_dependencies(task.task_id):
                    # 依赖未满足，放回队列末尾
                    heapq.heappush(self._queue, task)
                    return None
                
                # 记录运行中
                with self._running_lock:
                    self._running[task.task_id] = task
                
                # 计算等待时间
                wait_time = time.time() - task.created_time
                self._update_avg_wait_time(wait_time)
            
            return task
    
    def _smart_select(self) -> Optional[ScheduledTask]:
        """
        智能选择下一个任务
        
        考虑因素：
        1. 优先级
        2. 预估执行时间
        3. 历史成功率
        4. 依赖关系
        """
        if not self._queue:
            return None
        
        # 计算每个任务的得分
        best_task = None
        best_score = float('inf')
        best_index = 0
        
        for i, task in enumerate(self._queue):
            # 检查依赖
            if not self._check_dependencies(task.task_id):
                continue
            
            # 计算得分（越低越好）
            score = self._calculate_task_score(task)
            
            if score < best_score:
                best_score = score
                best_task = task
                best_index = i
        
        if best_task:
            self._queue.pop(best_index)
            heapq.heapify(self._queue)
            return best_task
        
        return None
    
    def _calculate_task_score(self, task: ScheduledTask) -> float:
        """
        计算任务得分
        
        得分 = 优先级权重 * 优先级 + 时间权重 * 预估时间 + 历史权重 * 历史得分
        """
        # 权重配置
        priority_weight = 0.5
        time_weight = 0.3
        history_weight = 0.2
        
        # 优先级得分（优先级值越小越好）
        priority_score = task.priority
        
        # 时间得分（归一化到0-3）
        time_score = min(task.estimated_duration / 300, 3)  # 5分钟为基准
        
        # 历史得分（基于相似任务的成功率）
        history_score = self._get_history_score(task)
        
        # 综合得分
        total_score = (
            priority_weight * priority_score +
            time_weight * time_score +
            history_weight * history_score
        )
        
        return total_score
    
    def _get_history_score(self, task: ScheduledTask) -> float:
        """获取历史得分"""
        task_type = task.task_data.get("task_type", "unknown")
        
        # 查找相似任务的历史
        similar_tasks = [
            h for h in self._task_history
            if h.get("task_type") == task_type
        ]
        
        if not similar_tasks:
            return 1.5  # 默认中等得分
        
        # 计算成功率
        successful = sum(1 for t in similar_tasks if t.get("success"))
        success_rate = successful / len(similar_tasks)
        
        # 转换为得分（成功率越高，得分越低）
        return (1 - success_rate) * 3
    
    def _check_dependencies(self, task_id: str) -> bool:
        """检查任务依赖是否满足"""
        if task_id not in self._dependencies:
            return True
        
        deps = self._dependencies[task_id]
        completed_ids = {t.get("task_id") for t in self._completed}
        # Bug#56修复: 依赖检查也应包含running中的任务（正在执行=已开始=依赖部分满足）
        # 如果依赖任务正在运行中，说明它还没完成，依赖仍未满足
        # 但我们可以提供一个选项：如果所有依赖都已完成或在运行中，允许执行
        # 这里保持严格语义：只有completed才算满足
        running_ids = set(self._running.keys())
        
        # 严格模式：依赖必须已完成
        return deps.issubset(completed_ids)
    
    def complete(
        self,
        task_id: str,
        success: bool,
        execution_time: float = 0,
        result: Optional[Dict[str, Any]] = None
    ):
        """
        标记任务完成
        
        Args:
            task_id: 任务ID
            success: 是否成功
            execution_time: 实际执行时间
            result: 执行结果
        """
        with self._running_lock:
            if task_id in self._running:
                task = self._running.pop(task_id)
                
                # 记录完成
                completion = {
                    "task_id": task_id,
                    "success": success,
                    "execution_time": execution_time,
                    "wait_time": time.time() - task.created_time - execution_time,
                    "completed_at": datetime.now().isoformat(),
                    "result": result
                }
                
                self._completed.append(completion)
                
                # Bug#49修复: 限制 _completed 列表大小，防止内存泄漏
                if len(self._completed) > 1000:
                    self._completed = self._completed[-500:]
                
                # 更新统计
                if success:
                    self._stats["total_completed"] += 1
                else:
                    self._stats["total_failed"] += 1
                
                self._update_avg_execution_time(execution_time)
                
                # 添加到历史
                self._task_history.append({
                    "task_id": task_id,
                    "task_type": task.task_data.get("task_type"),
                    "priority": task.priority,
                    "estimated_duration": task.estimated_duration,
                    "actual_duration": execution_time,
                    "success": success,
                    "timestamp": time.time()
                })
                
                # 定期保存
                if len(self._completed) % 10 == 0:
                    self._save_history()
                
                logger.info(f"任务 {task_id} 完成 (成功={success}, 耗时={execution_time:.1f}s)")
                
                if self._on_complete:
                    self._on_complete(task_id, success, result)
    
    def _update_avg_wait_time(self, wait_time: float):
        """更新平均等待时间"""
        total = self._stats["total_completed"] + self._stats["total_failed"]
        if total > 0:
            self._stats["avg_wait_time"] = (
                (self._stats["avg_wait_time"] * (total - 1) + wait_time) / total
            )
    
    def _update_avg_execution_time(self, exec_time: float):
        """更新平均执行时间"""
        total = self._stats["total_completed"] + self._stats["total_failed"]
        if total > 0:
            self._stats["avg_execution_time"] = (
                (self._stats["avg_execution_time"] * (total - 1) + exec_time) / total
            )
    
    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        with self._queue_lock:
            queue_size = len(self._queue)
        
        with self._running_lock:
            running_size = len(self._running)
        
        return {
            "strategy": self.strategy.value,
            "queue_size": queue_size,
            "running_tasks": running_size,
            "max_concurrent": self.max_concurrent,
            "completed_tasks": len(self._completed),
            "stats": self._stats
        }
    
    def get_queue_info(self) -> List[Dict[str, Any]]:
        """获取队列信息"""
        with self._queue_lock:
            return [
                {
                    "task_id": t.task_id,
                    "priority": t.priority,
                    "estimated_duration": t.estimated_duration,
                    "wait_time": time.time() - t.created_time
                }
                for t in sorted(self._queue)
            ]
    
    def reorder(self, task_id: str, new_priority: int) -> bool:
        """
        重新设置任务优先级
        
        Args:
            task_id: 任务ID
            new_priority: 新优先级
            
        Returns:
            是否成功
        """
        with self._queue_lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    self._queue[i].priority = new_priority
                    heapq.heapify(self._queue)
                    logger.info(f"任务 {task_id} 优先级更新为 {new_priority}")
                    return True
        
        return False
    
    def cancel(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功
        """
        with self._queue_lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    self._queue.pop(i)
                    heapq.heapify(self._queue)
                    logger.info(f"任务 {task_id} 已取消")
                    return True
        
        return False
    
    def clear_completed(self, keep_last: int = 100):
        """清理已完成任务记录"""
        if len(self._completed) > keep_last:
            self._completed = self._completed[-keep_last:]
    
    def set_callbacks(
        self,
        on_schedule: Optional[Callable] = None,
        on_complete: Optional[Callable] = None
    ):
        """设置回调函数"""
        self._on_schedule = on_schedule
        self._on_complete = on_complete
    
    def estimate_completion_time(self, task_id: str) -> Optional[float]:
        """
        预估任务完成时间
        
        Returns:
            预估完成时间戳，如果任务不在队列中返回None
        """
        with self._queue_lock:
            # 找到任务位置
            position = None
            task_estimated = 0
            
            for i, task in enumerate(sorted(self._queue)):
                if task.task_id == task_id:
                    position = i
                    task_estimated = task.estimated_duration
                    break
            
            if position is None:
                return None
            
            # 计算前面任务的预估时间
            wait_time = sum(
                t.estimated_duration for t in sorted(self._queue)[:position]
            )
            
            # 加上运行中任务的剩余时间
            with self._running_lock:
                running_time = sum(
                    t.estimated_duration for t in self._running.values()
                ) / max(len(self._running), 1)
            
            return time.time() + wait_time + running_time + task_estimated
