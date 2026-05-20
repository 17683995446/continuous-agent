#!/usr/bin/env python3
"""
性能分析器
=========
分析任务执行性能和模式
"""

import json
import statistics
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import time

logger = logging.getLogger("PerformanceAnalyzer")


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    """分析报告"""
    period_start: datetime
    period_end: datetime
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    avg_execution_time: float
    success_rate: float
    throughput: float  # tasks per hour
    bottlenecks: List[Dict[str, Any]]
    recommendations: List[str]
    trends: Dict[str, Any]


class PerformanceAnalyzer:
    """
    性能分析器
    
    功能：
    - 收集性能指标
    - 分析性能趋势
    - 识别瓶颈
    - 生成优化建议
    """
    
    def __init__(
        self,
        metrics_file: Optional[str] = None,
        retention_days: int = 30
    ):
        self.metrics_file = Path(metrics_file) if metrics_file else None
        self.retention_days = retention_days
        
        # 指标存储
        self._metrics: Dict[str, List[PerformanceMetric]] = defaultdict(list)
        self._task_history: List[Dict[str, Any]] = []
        
        # 分析缓存
        self._last_analysis: Optional[AnalysisReport] = None
        self._last_analysis_time: Optional[datetime] = None
    
    def record_metric(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """
        记录指标
        
        Args:
            name: 指标名称
            value: 指标值
            tags: 标签
        """
        metric = PerformanceMetric(
            name=name,
            value=value,
            tags=tags or {}
        )
        
        self._metrics[name].append(metric)
        
        # 清理过期数据
        self._cleanup_old_metrics()
    
    def record_task(
        self,
        task_id: str,
        task_type: str,
        success: bool,
        execution_time: float,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录任务执行
        
        Args:
            task_id: 任务ID
            task_type: 任务类型
            success: 是否成功
            execution_time: 执行时间
            error: 错误信息
            metadata: 元数据
        """
        record = {
            "task_id": task_id,
            "task_type": task_type,
            "success": success,
            "execution_time": execution_time,
            "error": error,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        
        self._task_history.append(record)
        
        # 记录相关指标
        self.record_metric("task_execution_time", execution_time, {"task_type": task_type})
        self.record_metric("task_success", 1.0 if success else 0.0, {"task_type": task_type})
    
    def _cleanup_old_metrics(self):
        """清理过期指标"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        
        for name in self._metrics:
            self._metrics[name] = [
                m for m in self._metrics[name]
                if m.timestamp > cutoff
            ]
        
        # 清理任务历史
        cutoff_str = cutoff.isoformat()
        self._task_history = [
            t for t in self._task_history
            if t["timestamp"] > cutoff_str
        ]
    
    def analyze(
        self,
        period_hours: int = 24,
        force: bool = False
    ) -> AnalysisReport:
        """
        分析性能
        
        Args:
            period_hours: 分析周期（小时）
            force: 是否强制重新分析
            
        Returns:
            分析报告
        """
        # 检查缓存
        if not force and self._last_analysis and self._last_analysis_time:
            cache_age = datetime.now() - self._last_analysis_time
            if cache_age < timedelta(minutes=5):
                return self._last_analysis
        
        now = datetime.now()
        period_start = now - timedelta(hours=period_hours)
        
        # 过滤周期内的任务
        period_tasks = [
            t for t in self._task_history
            if datetime.fromisoformat(t["timestamp"]) > period_start
        ]
        
        # 基本统计
        total_tasks = len(period_tasks)
        successful_tasks = sum(1 for t in period_tasks if t["success"])
        failed_tasks = total_tasks - successful_tasks
        
        execution_times = [t["execution_time"] for t in period_tasks]
        avg_execution_time = statistics.mean(execution_times) if execution_times else 0
        
        success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0
        throughput = total_tasks / period_hours if period_hours > 0 else 0
        
        # 识别瓶颈
        bottlenecks = self._identify_bottlenecks(period_tasks)
        
        # 生成建议
        recommendations = self._generate_recommendations(
            success_rate, avg_execution_time, bottlenecks
        )
        
        # 分析趋势
        trends = self._analyze_trends(period_tasks)
        
        # 创建报告
        report = AnalysisReport(
            period_start=period_start,
            period_end=now,
            total_tasks=total_tasks,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
            avg_execution_time=avg_execution_time,
            success_rate=success_rate,
            throughput=throughput,
            bottlenecks=bottlenecks,
            recommendations=recommendations,
            trends=trends
        )
        
        self._last_analysis = report
        self._last_analysis_time = now
        
        return report
    
    def _identify_bottlenecks(
        self,
        tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """识别瓶颈"""
        bottlenecks = []
        
        # 按任务类型分组
        by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for task in tasks:
            by_type[task["task_type"]].append(task)
        
        # 分析每种类型
        for task_type, type_tasks in by_type.items():
            times = [t["execution_time"] for t in type_tasks]
            failures = sum(1 for t in type_tasks if not t["success"])
            
            avg_time = statistics.mean(times) if times else 0
            failure_rate = failures / len(type_tasks) if type_tasks else 0
            
            # 判断是否是瓶颈
            is_bottleneck = False
            reason = ""
            
            if avg_time > 300:  # 超过5分钟
                is_bottleneck = True
                reason = f"平均执行时间过长: {avg_time:.1f}s"
            elif failure_rate > 0.3:  # 失败率超过30%
                is_bottleneck = True
                reason = f"失败率过高: {failure_rate*100:.1f}%"
            
            if is_bottleneck:
                bottlenecks.append({
                    "task_type": task_type,
                    "avg_time": avg_time,
                    "failure_rate": failure_rate,
                    "count": len(type_tasks),
                    "reason": reason
                })
        
        return sorted(bottlenecks, key=lambda x: x["avg_time"], reverse=True)
    
    def _generate_recommendations(
        self,
        success_rate: float,
        avg_execution_time: float,
        bottlenecks: List[Dict[str, Any]]
    ) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if success_rate < 0.8:
            recommendations.append(
                f"成功率偏低({success_rate*100:.1f}%)，建议检查常见错误模式并优化"
            )
        
        if avg_execution_time > 120:
            recommendations.append(
                f"平均执行时间较长({avg_execution_time:.1f}s)，考虑并行化或优化算法"
            )
        
        for bottleneck in bottlenecks[:3]:
            recommendations.append(
                f"瓶颈任务 [{bottleneck['task_type']}]: {bottleneck['reason']}"
            )
        
        if not recommendations:
            recommendations.append("性能表现良好，继续保持")
        
        return recommendations
    
    def _analyze_trends(
        self,
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析趋势"""
        if len(tasks) < 10:
            return {"status": "insufficient_data"}
        
        # 按时间排序
        sorted_tasks = sorted(tasks, key=lambda t: t["timestamp"])
        
        # 分成前后两半
        mid = len(sorted_tasks) // 2
        first_half = sorted_tasks[:mid]
        second_half = sorted_tasks[mid:]
        
        # 计算趋势
        first_success_rate = sum(1 for t in first_half if t["success"]) / len(first_half)
        second_success_rate = sum(1 for t in second_half if t["success"]) / len(second_half)
        
        first_avg_time = statistics.mean([t["execution_time"] for t in first_half])
        second_avg_time = statistics.mean([t["execution_time"] for t in second_half])
        
        success_trend = "improving" if second_success_rate > first_success_rate else "declining"
        time_trend = "improving" if second_avg_time < first_avg_time else "declining"
        
        return {
            "success_rate_trend": success_trend,
            "success_rate_change": (second_success_rate - first_success_rate) * 100,
            "execution_time_trend": time_trend,
            "execution_time_change": (second_avg_time - first_avg_time) / first_avg_time * 100 if first_avg_time > 0 else 0
        }
    
    def get_task_type_stats(
        self,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取任务类型统计"""
        if task_type:
            tasks = [t for t in self._task_history if t["task_type"] == task_type]
        else:
            tasks = self._task_history
        
        if not tasks:
            return {"count": 0}
        
        times = [t["execution_time"] for t in tasks]
        successes = sum(1 for t in tasks if t["success"])
        
        return {
            "count": len(tasks),
            "success_count": successes,
            "failure_count": len(tasks) - successes,
            "success_rate": successes / len(tasks),
            "avg_execution_time": statistics.mean(times),
            "min_execution_time": min(times),
            "max_execution_time": max(times),
            "p50_execution_time": statistics.median(times),
            "p95_execution_time": sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
        }
    
    def get_hourly_distribution(self) -> Dict[int, int]:
        """获取小时分布"""
        distribution = Counter()
        
        for task in self._task_history:
            hour = datetime.fromisoformat(task["timestamp"]).hour
            distribution[hour] += 1
        
        return dict(sorted(distribution.items()))
    
    def export_report(self, format: str = "json") -> str:
        """导出报告"""
        report = self.analyze()
        
        if format == "json":
            return json.dumps({
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "total_tasks": report.total_tasks,
                "successful_tasks": report.successful_tasks,
                "failed_tasks": report.failed_tasks,
                "avg_execution_time": report.avg_execution_time,
                "success_rate": report.success_rate,
                "throughput": report.throughput,
                "bottlenecks": report.bottlenecks,
                "recommendations": report.recommendations,
                "trends": report.trends
            }, ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def clear(self):
        """清空数据"""
        self._metrics.clear()
        self._task_history.clear()
        self._last_analysis = None
        self._last_analysis_time = None
