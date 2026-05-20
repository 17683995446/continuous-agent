#!/usr/bin/env python3
"""
自学习优化器
==========
负责分析任务执行情况，自动优化工作方法
"""

import json
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging
import statistics

from ..knowledge.graph import ExperienceType

logger = logging.getLogger("Optimizer")


class OptimizationType(Enum):
    """优化类型"""
    EXECUTION_TIME = "execution_time"      # 执行时间优化
    SUCCESS_RATE = "success_rate"          # 成功率优化
    ERROR_PATTERN = "error_pattern"        # 错误模式优化
    METHOD_IMPROVEMENT = "method"          # 方法改进
    RESOURCE_USAGE = "resource"            # 资源使用优化
    PRIORITY_ADJUSTMENT = "priority"       # 优先级调整


@dataclass
class OptimizationRecord:
    """优化记录"""
    id: str
    optimization_type: OptimizationType
    description: str
    before_value: float
    after_value: float
    improvement_percent: float
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "optimization_type": self.optimization_type.value,
            "description": self.description,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "improvement_percent": self.improvement_percent,
            "context": self.context,
            "created_at": self.created_at.isoformat()
        }


class Optimizer:
    """
    自学习优化器
    
    功能：
    - 分析任务执行模式
    - 识别优化机会
    - 自动应用改进
    - 追踪优化效果
    """
    
    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        history_file: str = "/data/user/work/optimization_history.json",
        analysis_interval: int = 30  # 分析间隔（秒）
    ):
        self.knowledge_graph = knowledge_graph
        self.history_file = Path(history_file)
        self.analysis_interval = analysis_interval
        
        # 优化历史
        self.optimization_history: List[OptimizationRecord] = []
        
        # 性能指标
        self.metrics: Dict[str, List[float]] = defaultdict(list)
        self.task_metrics: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        
        # 学习到的模式
        self.learned_patterns: Dict[str, Any] = {
            "best_methods": {},       # 任务类型 -> 最佳方法
            "common_errors": {},      # 常见错误 -> 解决方案
            "time_estimates": {},     # 任务类型 -> 预估时间
            "success_factors": {}     # 成功因素
        }
        
        # 优化规则
        self.optimization_rules: List[Dict[str, Any]] = []
        
        # 锁
        self._lock = threading.RLock()
        
        # 统计
        self._stats = {
            "total_optimizations": 0,
            "successful_optimizations": 0,
            "total_improvement": 0.0
        }
        
        # 回调
        self._on_optimization: Optional[Callable] = None
        
        # 加载历史
        self._load_history()
        
        logger.info("优化器初始化完成")
    
    def _load_history(self):
        """加载历史数据"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    for record_data in data.get("history", []):
                        record = OptimizationRecord(
                            id=record_data["id"],
                            optimization_type=OptimizationType(record_data["optimization_type"]),
                            description=record_data["description"],
                            before_value=record_data["before_value"],
                            after_value=record_data["after_value"],
                            improvement_percent=record_data["improvement_percent"],
                            context=record_data.get("context", {}),
                            created_at=datetime.fromisoformat(record_data["created_at"])
                        )
                        self.optimization_history.append(record)
                    
                    self.learned_patterns = data.get("patterns", self.learned_patterns)
                    self._stats = data.get("stats", self._stats)
                    
                    logger.info(f"加载 {len(self.optimization_history)} 条优化记录")
            except Exception as e:
                logger.warning(f"加载优化历史失败: {e}")
    
    def _save_history(self):
        """保存历史数据"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "history": [r.to_dict() for r in self.optimization_history[-1000:]],
                "patterns": self.learned_patterns,
                "stats": self._stats
            }
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存优化历史失败: {e}")
    
    def record_task_completion(
        self,
        task_type: str,
        success: bool,
        execution_time: float,
        method_used: Optional[str] = None,
        error: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        记录任务完成情况
        
        Args:
            task_type: 任务类型
            success: 是否成功
            execution_time: 执行时间
            method_used: 使用的方法
            error: 错误信息（如果有）
            context: 上下文
        """
        with self._lock:
            logger.debug(f"记录任务完成: type={task_type} success={success} time={execution_time:.2f}s")
            # 记录全局指标
            self.metrics["execution_time"].append(execution_time)
            self.metrics["success"].append(1.0 if success else 0.0)
            
            # 记录任务类型指标
            self.task_metrics[task_type]["execution_time"].append(execution_time)
            self.task_metrics[task_type]["success"].append(1.0 if success else 0.0)
            
            # 记录方法使用情况
            if method_used:
                key = f"{task_type}:{method_used}"
                self.task_metrics[key]["execution_time"].append(execution_time)
                self.task_metrics[key]["success"].append(1.0 if success else 0.0)
            
            # 记录错误模式
            if error and not success:
                self._record_error_pattern(task_type, error, context)
            
            # 更新学习模式
            self._update_patterns(task_type, success, execution_time, method_used)
            
            # 限制历史长度
            for key in self.metrics:
                if len(self.metrics[key]) > 10000:
                    self.metrics[key] = self.metrics[key][-5000:]
            
            for task_type_key in self.task_metrics:
                for metric_key in self.task_metrics[task_type_key]:
                    if len(self.task_metrics[task_type_key][metric_key]) > 1000:
                        self.task_metrics[task_type_key][metric_key] = \
                            self.task_metrics[task_type_key][metric_key][-500:]
    
    def _record_error_pattern(
        self,
        task_type: str,
        error: str,
        context: Optional[Dict[str, Any]]
    ):
        """记录错误模式"""
        error_key = f"{task_type}:{error[:50]}"
        
        if error_key not in self.learned_patterns["common_errors"]:
            self.learned_patterns["common_errors"][error_key] = {
                "count": 0,
                "first_seen": datetime.now().isoformat(),
                "solutions": []
            }
        
        self.learned_patterns["common_errors"][error_key]["count"] += 1
        self.learned_patterns["common_errors"][error_key]["last_seen"] = datetime.now().isoformat()
    
    def _update_patterns(
        self,
        task_type: str,
        success: bool,
        execution_time: float,
        method_used: Optional[str]
    ):
        """更新学习模式"""
        logger.debug(f"更新模式: task_type={task_type} success={success}")
        # 更新时间预估
        if task_type not in self.learned_patterns["time_estimates"]:
            self.learned_patterns["time_estimates"][task_type] = {
                "samples": [],
                "average": 60.0,
                "std_dev": 30.0
            }
        
        samples = self.learned_patterns["time_estimates"][task_type]["samples"]
        samples.append(execution_time)
        
        # 只保留最近的样本
        if len(samples) > 100:
            samples = samples[-50:]
        
        self.learned_patterns["time_estimates"][task_type]["samples"] = samples
        self.learned_patterns["time_estimates"][task_type]["average"] = statistics.mean(samples)
        if len(samples) > 1:
            self.learned_patterns["time_estimates"][task_type]["std_dev"] = statistics.stdev(samples)
        
        # 更新最佳方法（无论成功失败都记录，才能正确计算成功率）
        if method_used:
            if task_type not in self.learned_patterns["best_methods"]:
                self.learned_patterns["best_methods"][task_type] = {}
            
            if method_used not in self.learned_patterns["best_methods"][task_type]:
                self.learned_patterns["best_methods"][task_type][method_used] = {
                    "success_count": 0,
                    "total_count": 0,
                    "avg_time": 0
                }
            
            method_stats = self.learned_patterns["best_methods"][task_type][method_used]
            method_stats["total_count"] += 1
            
            if success:
                method_stats["success_count"] += 1
                # 更新平均时间（只统计成功的）
                old_avg = method_stats["avg_time"]
                n = method_stats["success_count"]
                method_stats["avg_time"] = old_avg + (execution_time - old_avg) / n
    
    def analyze_and_optimize(
        self,
        tasks: Optional[List[Any]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        分析并应用优化
        
        Args:
            tasks: 最近的任务列表
            stats: 统计信息
            
        Returns:
            优化结果
        """
        with self._lock:
            logger.debug("开始优化分析...")
            optimizations = []
            
            # 1. 分析执行时间趋势
            time_optimization = self._analyze_execution_time()
            if time_optimization:
                optimizations.append(time_optimization)
            
            # 2. 分析成功率
            success_optimization = self._analyze_success_rate()
            if success_optimization:
                optimizations.append(success_optimization)
            
            # 3. 分析错误模式
            error_optimization = self._analyze_error_patterns()
            if error_optimization:
                optimizations.append(error_optimization)
            
            # 4. 分析最佳方法
            method_optimization = self._analyze_best_methods()
            if method_optimization:
                optimizations.append(method_optimization)
            
            # 应用优化
            applied = []
            for opt in optimizations:
                if self._apply_optimization(opt):
                    applied.append(opt)
                    self._stats["total_optimizations"] += 1
                    self._stats["successful_optimizations"] += 1
            
            # 保存
            if applied:
                self._save_history()
            
            return {
                "improvements": applied,
                "patterns": self.learned_patterns,
                "stats": self._stats
            }
    
    def _analyze_execution_time(self) -> Optional[Dict[str, Any]]:
        """分析执行时间"""
        times = self.metrics.get("execution_time", [])
        
        if len(times) < 10:
            return None
        
        # 计算趋势
        recent = times[-10:]
        older = times[-20:-10] if len(times) >= 20 else times[:-10]
        
        if not older:
            return None
        
        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)
        
        improvement = (older_avg - recent_avg) / older_avg * 100 if older_avg > 0 else 0
        
        if improvement > 5:  # 改进超过5%
            return {
                "type": OptimizationType.EXECUTION_TIME,
                "description": f"执行时间改善 {improvement:.1f}%",
                "before": older_avg,
                "after": recent_avg,
                "improvement_percent": improvement
            }
        elif improvement < -5:  # 退化超过5%
            logger.warning(f"执行时间退化: {improvement:.1f}%")
            return {
                "type": OptimizationType.EXECUTION_TIME,
                "description": f"执行时间退化 {-improvement:.1f}%，需要关注",
                "before": older_avg,
                "after": recent_avg,
                "improvement_percent": improvement,
                "needs_attention": True
            }
        
        return None
    
    def _analyze_success_rate(self) -> Optional[Dict[str, Any]]:
        """分析成功率"""
        successes = self.metrics.get("success", [])
        
        if len(successes) < 10:
            return None
        
        recent = successes[-10:]
        older = successes[-20:-10] if len(successes) >= 20 else successes[:-10]
        
        if not older:
            return None
        
        recent_rate = statistics.mean(recent)
        older_rate = statistics.mean(older)
        
        improvement = (recent_rate - older_rate) * 100
        
        if improvement > 5:  # 改进超过5%
            return {
                "type": OptimizationType.SUCCESS_RATE,
                "description": f"成功率提升 {improvement:.1f}%",
                "before": older_rate * 100,
                "after": recent_rate * 100,
                "improvement_percent": improvement
            }
        
        return None
    
    def _analyze_error_patterns(self) -> Optional[Dict[str, Any]]:
        """分析错误模式"""
        common_errors = self.learned_patterns.get("common_errors", {})
        
        # 找出高频错误
        high_freq_errors = [
            (key, data) for key, data in common_errors.items()
            if data.get("count", 0) >= 3
        ]
        
        if not high_freq_errors:
            return None
        
        # 按频率排序
        high_freq_errors.sort(key=lambda x: x[1]["count"], reverse=True)
        
        top_error = high_freq_errors[0]
        logger.warning(f"发现高频错误: {top_error[0][:50]}")
        
        return {
            "type": OptimizationType.ERROR_PATTERN,
            "description": f"发现高频错误: {top_error[0][:30]}...",
            "error_key": top_error[0],
            "count": top_error[1]["count"],
            "suggestion": "考虑添加预防措施或自动修复"
        }
    
    def _analyze_best_methods(self) -> Optional[Dict[str, Any]]:
        """分析最佳方法"""
        best_methods = self.learned_patterns.get("best_methods", {})
        
        recommendations = []
        
        for task_type, methods in best_methods.items():
            if len(methods) < 2:
                continue
            
            # 找出最佳方法
            best_method = None
            best_score = 0
            
            for method, stats in methods.items():
                if stats["total_count"] < 3:
                    continue
                
                success_rate = stats["success_count"] / stats["total_count"]
                # 综合得分：成功率权重高，时间权重低
                score = success_rate * 0.8 + (1 - stats["avg_time"] / 300) * 0.2
                
                if score > best_score:
                    best_score = score
                    best_method = method
            
            if best_method:
                recommendations.append({
                    "task_type": task_type,
                    "recommended_method": best_method,
                    "score": best_score
                })
        
        if recommendations:
            return {
                "type": OptimizationType.METHOD_IMPROVEMENT,
                "description": f"发现 {len(recommendations)} 个任务类型的最佳方法",
                "recommendations": recommendations
            }
        
        return None
    
    def _apply_optimization(self, optimization: Dict[str, Any]) -> bool:
        """应用优化"""
        try:
            # 处理optimization_type
            opt_type = optimization.get("type", OptimizationType.METHOD_IMPROVEMENT)
            if isinstance(opt_type, OptimizationType):
                opt_type_str = opt_type.value
            else:
                opt_type_str = str(opt_type)
            
            # 记录优化
            record = OptimizationRecord(
                id=f"opt_{int(time.time() * 1000)}",
                optimization_type=OptimizationType(opt_type_str),
                description=optimization.get("description", ""),
                before_value=optimization.get("before", 0),
                after_value=optimization.get("after", 0),
                improvement_percent=optimization.get("improvement_percent", 0),
                context=optimization
            )
            
            self.optimization_history.append(record)
            
            # 如果有知识图谱，存储优化经验
            if self.knowledge_graph:
                self.knowledge_graph.add_experience(
                    content=f"优化: {optimization.get('description', '')}",
                    task_type="optimization",
                    experience_type=ExperienceType.SOLUTION,
                    context=optimization
                )
            
            # 回调
            if self._on_optimization:
                self._on_optimization(optimization)
            
            logger.info(f"应用优化: {optimization.get('description', '')}")
            return True
            
        except Exception as e:
            logger.error(f"应用优化失败: {e}")
            return False
    
    def get_recommendation(self, task_type: str) -> Dict[str, Any]:
        """
        获取任务类型的方法推荐
        
        Args:
            task_type: 任务类型
            
        Returns:
            推荐信息
        """
        best_methods = self.learned_patterns.get("best_methods", {})
        time_estimates = self.learned_patterns.get("time_estimates", {})
        
        recommendation = {
            "task_type": task_type,
            "recommended_method": None,
            "estimated_time": 60.0,
            "confidence": 0.0
        }
        
        # 获取最佳方法
        if task_type in best_methods:
            methods = best_methods[task_type]
            best_method = None
            best_score = 0
            
            for method, stats in methods.items():
                if stats["total_count"] < 2:
                    continue
                
                success_rate = stats["success_count"] / stats["total_count"]
                score = success_rate
                
                if score > best_score:
                    best_score = score
                    best_method = method
            
            if best_method:
                recommendation["recommended_method"] = best_method
                recommendation["confidence"] = best_score
        
        # 获取时间预估
        if task_type in time_estimates:
            recommendation["estimated_time"] = time_estimates[task_type]["average"]
        
        return recommendation
    
    def get_time_estimate(self, task_type: str) -> Tuple[float, float]:
        """
        获取任务时间预估
        
        Returns:
            (预估时间, 标准差)
        """
        time_estimates = self.learned_patterns.get("time_estimates", {})
        
        if task_type in time_estimates:
            return (
                time_estimates[task_type]["average"],
                time_estimates[task_type]["std_dev"]
            )
        
        return (60.0, 30.0)  # 默认值
    
    def get_error_solutions(self, task_type: str) -> List[Dict[str, Any]]:
        """获取错误解决方案"""
        common_errors = self.learned_patterns.get("common_errors", {})
        
        solutions = []
        for error_key, data in common_errors.items():
            if error_key.startswith(task_type):
                solutions.append({
                    "error": error_key,
                    "count": data.get("count", 0),
                    "solutions": data.get("solutions", [])
                })
        
        return sorted(solutions, key=lambda x: x["count"], reverse=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "optimization_history_count": len(self.optimization_history),
            "learned_patterns": {
                "task_types": len(self.learned_patterns.get("best_methods", {})),
                "error_patterns": len(self.learned_patterns.get("common_errors", {})),
                "time_estimates": len(self.learned_patterns.get("time_estimates", {}))
            }
        }
    
    def set_callback(self, on_optimization: Optional[Callable] = None):
        """设置回调函数"""
        self._on_optimization = on_optimization
    
    def reset(self):
        """重置优化器"""
        with self._lock:
            self.optimization_history.clear()
            self.metrics.clear()
            self.task_metrics.clear()
            self.learned_patterns = {
                "best_methods": {},
                "common_errors": {},
                "time_estimates": {},
                "success_factors": {}
            }
            self._save_history()
            logger.info("优化器已重置")
