#!/usr/bin/env python3
"""
系统监控模块
==========
负责监控系统状态和发送告警
"""

import json
import os
import platform
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger("SystemMonitor")


@dataclass
class MetricSnapshot:
    """指标快照"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    task_queue_size: int
    active_tasks: int
    completed_tasks: int


@dataclass
class Alert:
    """告警"""
    alert_id: str
    level: str  # info, warning, error, critical
    source: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class SystemMonitor:
    """
    系统监控器
    
    功能：
    - 系统资源监控
    - 性能指标收集
    - 阈值告警
    - 历史数据记录
    """
    
    def __init__(
        self,
        history_size: int = 1000,
        collection_interval: int = 60,
        storage_path: Optional[str] = None
    ):
        self.history_size = history_size
        self.collection_interval = collection_interval
        self.storage_path = Path(storage_path) if storage_path else None
        
        # 指标历史
        self._metrics_history: deque = deque(maxlen=history_size)
        
        # 阈值配置
        self._thresholds = {
            "cpu_percent": {"warning": 80, "critical": 95},
            "memory_percent": {"warning": 80, "critical": 95},
            "disk_percent": {"warning": 85, "critical": 95},
            "task_queue_size": {"warning": 100, "critical": 500},
            "error_rate": {"warning": 0.1, "critical": 0.3}
        }
        
        # 运行状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 告警
        self._alerts: List[Alert] = []
        self._alert_callbacks: List[Callable] = []
        
        # 统计
        self._stats = {
            "collections": 0,
            "alerts_generated": 0
        }
    
    def start(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
        
        logger.info("系统监控已启动")
    
    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        
        logger.info("系统监控已停止")
    
    def _collection_loop(self):
        """收集循环"""
        while self._running:
            try:
                self.collect_metrics()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"收集指标失败: {e}")
    
    def collect_metrics(self) -> MetricSnapshot:
        """收集指标"""
        # 获取系统指标
        cpu_percent = self._get_cpu_percent()
        memory_percent = self._get_memory_percent()
        disk_percent = self._get_disk_percent()
        
        # 创建快照
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            task_queue_size=0,  # 由外部更新
            active_tasks=0,
            completed_tasks=0
        )
        
        self._metrics_history.append(snapshot)
        self._stats["collections"] += 1
        
        # 检查阈值
        self._check_thresholds(snapshot)
        
        return snapshot
    
    def _get_cpu_percent(self) -> float:
        """获取CPU使用率"""
        try:
            import psutil
            return psutil.cpu_percent(interval=1)
        except ImportError:
            # 如果没有psutil，返回模拟值
            return 50.0
    
    def _get_memory_percent(self) -> float:
        """获取内存使用率"""
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return 50.0
    
    def _get_disk_percent(self) -> float:
        """获取磁盘使用率"""
        try:
            import psutil
            return psutil.disk_usage('/').percent
        except ImportError:
            return 50.0
    
    def _check_thresholds(self, snapshot: MetricSnapshot):
        """检查阈值"""
        # CPU
        if snapshot.cpu_percent >= self._thresholds["cpu_percent"]["critical"]:
            self._create_alert(
                level="critical",
                source="cpu",
                message=f"CPU使用率过高: {snapshot.cpu_percent:.1f}%"
            )
        elif snapshot.cpu_percent >= self._thresholds["cpu_percent"]["warning"]:
            self._create_alert(
                level="warning",
                source="cpu",
                message=f"CPU使用率较高: {snapshot.cpu_percent:.1f}%"
            )
        
        # 内存
        if snapshot.memory_percent >= self._thresholds["memory_percent"]["critical"]:
            self._create_alert(
                level="critical",
                source="memory",
                message=f"内存使用率过高: {snapshot.memory_percent:.1f}%"
            )
        elif snapshot.memory_percent >= self._thresholds["memory_percent"]["warning"]:
            self._create_alert(
                level="warning",
                source="memory",
                message=f"内存使用率较高: {snapshot.memory_percent:.1f}%"
            )
        
        # 磁盘
        if snapshot.disk_percent >= self._thresholds["disk_percent"]["critical"]:
            self._create_alert(
                level="critical",
                source="disk",
                message=f"磁盘使用率过高: {snapshot.disk_percent:.1f}%"
            )
    
    def _create_alert(
        self,
        level: str,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """创建告警"""
        alert = Alert(
            alert_id=f"alert_{int(time.time() * 1000)}",
            level=level,
            source=source,
            message=message,
            details=details or {}
        )
        
        self._alerts.append(alert)
        self._stats["alerts_generated"] += 1
        
        # 限制告警列表大小，防止内存泄漏
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]
        
        # 触发回调
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"告警回调失败: {e}")
        
        logger.log(
            logging.ERROR if level in ["error", "critical"] else logging.WARNING,
            f"[{level.upper()}] {source}: {message}"
        )
    
    def update_task_metrics(
        self,
        queue_size: int,
        active_tasks: int,
        completed_tasks: int
    ):
        """更新任务指标"""
        if self._metrics_history:
            latest = self._metrics_history[-1]
            latest.task_queue_size = queue_size
            latest.active_tasks = active_tasks
            latest.completed_tasks = completed_tasks
            
            # 检查队列阈值
            if queue_size >= self._thresholds["task_queue_size"]["critical"]:
                self._create_alert(
                    level="critical",
                    source="task_queue",
                    message=f"任务队列过长: {queue_size}"
                )
    
    def set_threshold(self, metric: str, level: str, value: float):
        """设置阈值"""
        if metric in self._thresholds:
            self._thresholds[metric][level] = value
            logger.info(f"设置阈值: {metric}.{level} = {value}")
    
    def add_alert_callback(self, callback: Callable):
        """添加告警回调"""
        self._alert_callbacks.append(callback)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        if not self._metrics_history:
            return {}
        
        latest = self._metrics_history[-1]
        
        return {
            "timestamp": latest.timestamp.isoformat(),
            "cpu_percent": latest.cpu_percent,
            "memory_percent": latest.memory_percent,
            "disk_percent": latest.disk_percent,
            "task_queue_size": latest.task_queue_size,
            "active_tasks": latest.active_tasks,
            "completed_tasks": latest.completed_tasks
        }
    
    def get_metrics_history(
        self,
        duration_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """获取历史指标"""
        cutoff = datetime.now() - timedelta(minutes=duration_minutes)
        
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "disk_percent": m.disk_percent
            }
            for m in self._metrics_history
            if m.timestamp > cutoff
        ]
    
    def get_alerts(
        self,
        level: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取告警"""
        alerts = self._alerts
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return [
            {
                "alert_id": a.alert_id,
                "level": a.level,
                "source": a.source,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "acknowledged": a.acknowledged
            }
            for a in alerts[-limit:]
        ]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def clear_alerts(self):
        """清空告警"""
        self._alerts.clear()
        logger.info("告警已清空")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            **self._stats,
            "history_size": len(self._metrics_history),
            "alerts_count": len(self._alerts),
            "thresholds": self._thresholds
        }


class AlertManager:
    """
    告警管理器
    
    功能：
    - 告警聚合
    - 告警通知
    - 告警升级
    """
    
    def __init__(
        self,
        aggregation_window: int = 300,  # 5分钟
        escalation_threshold: int = 3
    ):
        self.aggregation_window = aggregation_window
        self.escalation_threshold = escalation_threshold
        
        # 告警存储
        self._alerts: Dict[str, List[Alert]] = {}
        
        # 通知处理器
        self._handlers: List[Callable] = []
        
        # 升级规则
        self._escalation_rules: Dict[str, Callable] = {}
    
    def add_handler(self, handler: Callable):
        """添加通知处理器"""
        self._handlers.append(handler)
    
    def process_alert(self, alert: Alert):
        """处理告警"""
        # 聚合
        key = f"{alert.source}:{alert.level}"
        
        if key not in self._alerts:
            self._alerts[key] = []
        
        self._alerts[key].append(alert)
        
        # 检查是否需要升级
        recent_count = self._count_recent_alerts(key)
        
        if recent_count >= self.escalation_threshold:
            self._escalate(alert, recent_count)
        
        # 发送通知
        self._notify(alert)
    
    def _count_recent_alerts(self, key: str) -> int:
        """统计最近告警数量"""
        cutoff = datetime.now() - timedelta(seconds=self.aggregation_window)
        
        return sum(
            1 for a in self._alerts.get(key, [])
            if a.timestamp > cutoff
        )
    
    def _escalate(self, alert: Alert, count: int):
        """升级告警"""
        logger.warning(f"告警升级: {alert.source} 在短时间内触发 {count} 次")
        
        # 调用升级规则
        if alert.source in self._escalation_rules:
            try:
                self._escalation_rules[alert.source](alert, count)
            except Exception as e:
                logger.error(f"升级规则执行失败: {e}")
    
    def _notify(self, alert: Alert):
        """发送通知"""
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"通知处理失败: {e}")
    
    def add_escalation_rule(self, source: str, rule: Callable):
        """添加升级规则"""
        self._escalation_rules[source] = rule
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警摘要"""
        summary = {
            "total_alerts": sum(len(a) for a in self._alerts.values()),
            "by_level": {},
            "by_source": {}
        }
        
        for alerts in self._alerts.values():
            for alert in alerts:
                # 按级别统计
                if alert.level not in summary["by_level"]:
                    summary["by_level"][alert.level] = 0
                summary["by_level"][alert.level] += 1
                
                # 按来源统计
                if alert.source not in summary["by_source"]:
                    summary["by_source"][alert.source] = 0
                summary["by_source"][alert.source] += 1
        
        return summary
    
    def clear_old_alerts(self, max_age_hours: int = 24):
        """清理旧告警"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        for key in self._alerts:
            self._alerts[key] = [
                a for a in self._alerts[key]
                if a.timestamp > cutoff
            ]
