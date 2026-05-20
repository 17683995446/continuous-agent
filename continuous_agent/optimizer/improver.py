#!/usr/bin/env python3
"""
方法改进器
=========
负责改进工作方法和策略
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import re

logger = logging.getLogger("MethodImprover")


@dataclass
class MethodRecord:
    """方法记录"""
    method_id: str
    name: str
    description: str
    task_types: List[str]
    parameters: Dict[str, Any] = field(default_factory=dict)
    success_count: int = 0
    fail_count: int = 0
    total_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def avg_time(self) -> float:
        total = self.success_count + self.fail_count
        return self.total_time / total if total > 0 else 0.0


@dataclass
class Improvement:
    """改进建议"""
    improvement_id: str
    target_method: str
    improvement_type: str  # "parameter", "workflow", "fallback"
    description: str
    expected_benefit: str
    priority: int  # 1-5, 1最高
    status: str = "pending"  # pending, applied, rejected
    created_at: datetime = field(default_factory=datetime.now)


class MethodImprover:
    """
    方法改进器
    
    功能：
    - 跟踪方法效果
    - 识别改进机会
    - 生成改进建议
    - 应用方法优化
    """
    
    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        storage_path: str = "/data/user/work/method_improvements"
    ):
        self.knowledge_graph = knowledge_graph
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 方法库
        self.methods: Dict[str, MethodRecord] = {}
        
        # 改进建议
        self.improvements: List[Improvement] = []
        
        # 任务-方法映射
        self.task_method_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # 加载数据
        self._load()
    
    def _load(self):
        """加载数据"""
        methods_file = self.storage_path / "methods.json"
        improvements_file = self.storage_path / "improvements.json"
        
        if methods_file.exists():
            try:
                with open(methods_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for m in data:
                        record = MethodRecord(
                            method_id=m["method_id"],
                            name=m["name"],
                            description=m["description"],
                            task_types=m.get("task_types", []),
                            parameters=m.get("parameters", {}),
                            success_count=m.get("success_count", 0),
                            fail_count=m.get("fail_count", 0),
                            total_time=m.get("total_time", 0.0)
                        )
                        self.methods[record.method_id] = record
                logger.info(f"加载 {len(self.methods)} 个方法记录")
            except Exception as e:
                logger.warning(f"加载方法记录失败: {e}")
        
        if improvements_file.exists():
            try:
                with open(improvements_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for i in data:
                        improvement = Improvement(
                            improvement_id=i["improvement_id"],
                            target_method=i["target_method"],
                            improvement_type=i["improvement_type"],
                            description=i["description"],
                            expected_benefit=i["expected_benefit"],
                            priority=i["priority"],
                            status=i.get("status", "pending")
                        )
                        self.improvements.append(improvement)
                logger.info(f"加载 {len(self.improvements)} 个改进建议")
            except Exception as e:
                logger.warning(f"加载改进建议失败: {e}")
    
    def _save(self):
        """保存数据"""
        methods_file = self.storage_path / "methods.json"
        improvements_file = self.storage_path / "improvements.json"
        
        try:
            with open(methods_file, 'w', encoding='utf-8') as f:
                json.dump([
                    {
                        "method_id": m.method_id,
                        "name": m.name,
                        "description": m.description,
                        "task_types": m.task_types,
                        "parameters": m.parameters,
                        "success_count": m.success_count,
                        "fail_count": m.fail_count,
                        "total_time": m.total_time
                    }
                    for m in self.methods.values()
                ], f, ensure_ascii=False, indent=2)
            
            with open(improvements_file, 'w', encoding='utf-8') as f:
                json.dump([
                    {
                        "improvement_id": i.improvement_id,
                        "target_method": i.target_method,
                        "improvement_type": i.improvement_type,
                        "description": i.description,
                        "expected_benefit": i.expected_benefit,
                        "priority": i.priority,
                        "status": i.status
                    }
                    for i in self.improvements
                ], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
    
    def register_method(
        self,
        name: str,
        description: str,
        task_types: List[str],
        parameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        注册新方法
        
        Args:
            name: 方法名称
            description: 方法描述
            task_types: 适用的任务类型
            parameters: 方法参数
            
        Returns:
            方法ID
        """
        method_id = f"method_{int(time.time() * 1000)}"
        
        record = MethodRecord(
            method_id=method_id,
            name=name,
            description=description,
            task_types=task_types,
            parameters=parameters or {}
        )
        
        self.methods[method_id] = record
        self._save()
        
        logger.info(f"注册方法 [{method_id}]: {name}")
        return method_id
    
    def record_method_usage(
        self,
        method_id: str,
        task_id: str,
        task_type: str,
        success: bool,
        execution_time: float,
        parameters_used: Optional[Dict[str, Any]] = None
    ):
        """
        记录方法使用情况
        
        Args:
            method_id: 方法ID
            task_id: 任务ID
            task_type: 任务类型
            success: 是否成功
            execution_time: 执行时间
            parameters_used: 使用的参数
        """
        if method_id not in self.methods:
            logger.warning(f"未知方法: {method_id}")
            return
        
        method = self.methods[method_id]
        
        if success:
            method.success_count += 1
        else:
            method.fail_count += 1
        
        method.total_time += execution_time
        method.updated_at = datetime.now()
        
        # 记录到历史
        self.task_method_history[task_type].append({
            "task_id": task_id,
            "method_id": method_id,
            "success": success,
            "execution_time": execution_time,
            "parameters": parameters_used,
            "timestamp": datetime.now().isoformat()
        })
        
        self._save()
    
    def get_best_method(
        self,
        task_type: str,
        criteria: str = "success_rate"  # success_rate, speed, balanced
    ) -> Optional[Tuple[str, MethodRecord]]:
        """
        获取最佳方法
        
        Args:
            task_type: 任务类型
            criteria: 选择标准
            
        Returns:
            (方法ID, 方法记录)
        """
        candidates = [
            (mid, m) for mid, m in self.methods.items()
            if task_type in m.task_types
        ]
        
        if not candidates:
            return None
        
        # 根据标准排序
        if criteria == "success_rate":
            candidates.sort(key=lambda x: x[1].success_rate, reverse=True)
        elif criteria == "speed":
            candidates.sort(key=lambda x: x[1].avg_time)
        else:  # balanced
            candidates.sort(
                key=lambda x: x[1].success_rate * 0.7 - x[1].avg_time / 300 * 0.3,
                reverse=True
            )
        
        return candidates[0]
    
    def analyze_improvements(self) -> List[Improvement]:
        """
        分析并生成改进建议
        
        Returns:
            改进建议列表
        """
        new_improvements = []
        
        for method_id, method in self.methods.items():
            # 检查成功率
            if method.success_rate < 0.7 and (method.success_count + method.fail_count) >= 5:
                improvement = Improvement(
                    improvement_id=f"imp_{int(time.time() * 1000)}",
                    target_method=method_id,
                    improvement_type="fallback",
                    description=f"方法 [{method.name}] 成功率较低({method.success_rate*100:.1f}%)，建议添加备用方案",
                    expected_benefit="提高任务成功率",
                    priority=2
                )
                new_improvements.append(improvement)
            
            # 检查执行时间
            if method.avg_time > 180 and method.success_count >= 3:
                improvement = Improvement(
                    improvement_id=f"imp_{int(time.time() * 1000) + 1}",
                    target_method=method_id,
                    improvement_type="workflow",
                    description=f"方法 [{method.name}] 平均执行时间较长({method.avg_time:.1f}s)，建议优化流程",
                    expected_benefit="减少执行时间",
                    priority=3
                )
                new_improvements.append(improvement)
            
            # 检查参数优化机会
            history = self.task_method_history.get(method_id, [])
            if len(history) >= 10:
                param_improvement = self._analyze_parameters(method, history)
                if param_improvement:
                    new_improvements.append(param_improvement)
        
        self.improvements.extend(new_improvements)
        
        # 限制改进建议数量，防止无限增长
        if len(self.improvements) > 500:
            self.improvements = self.improvements[-300:]
        
        self._save()
        
        return new_improvements
    
    def _analyze_parameters(
        self,
        method: MethodRecord,
        history: List[Dict[str, Any]]
    ) -> Optional[Improvement]:
        """分析参数优化机会"""
        # 找出成功和失败的参数模式
        success_params = []
        fail_params = []
        
        for record in history:
            params = record.get("parameters", {})
            if record["success"]:
                success_params.append(params)
            else:
                fail_params.append(params)
        
        if not success_params or not fail_params:
            return None
        
        # 简单分析：找出成功案例中常见的参数值
        # 这里可以扩展为更复杂的分析
        
        return None
    
    def apply_improvement(
        self,
        improvement_id: str,
        action: str = "apply"  # apply, reject
    ) -> bool:
        """
        应用或拒绝改进建议
        
        Args:
            improvement_id: 改进ID
            action: 操作类型
            
        Returns:
            是否成功
        """
        for improvement in self.improvements:
            if improvement.improvement_id == improvement_id:
                if action == "apply":
                    improvement.status = "applied"
                    
                    # 如果有知识图谱，存储改进经验
                    if self.knowledge_graph:
                        self.knowledge_graph.add_experience(
                            content=improvement.description,
                            task_type="method_improvement",
                            experience_type="solution",
                            context={
                                "target_method": improvement.target_method,
                                "improvement_type": improvement.improvement_type
                            }
                        )
                    
                    logger.info(f"应用改进: {improvement.description}")
                else:
                    improvement.status = "rejected"
                
                self._save()
                return True
        
        return False
    
    def get_pending_improvements(self) -> List[Improvement]:
        """获取待处理的改进建议"""
        return [i for i in self.improvements if i.status == "pending"]
    
    def get_method_stats(self, method_id: str) -> Dict[str, Any]:
        """获取方法统计"""
        if method_id not in self.methods:
            return {}
        
        method = self.methods[method_id]
        
        return {
            "method_id": method.method_id,
            "name": method.name,
            "success_rate": method.success_rate,
            "avg_time": method.avg_time,
            "total_uses": method.success_count + method.fail_count,
            "task_types": method.task_types
        }
    
    def get_all_methods(self) -> List[Dict[str, Any]]:
        """获取所有方法"""
        return [
            {
                "method_id": m.method_id,
                "name": m.name,
                "description": m.description,
                "success_rate": m.success_rate,
                "avg_time": m.avg_time,
                "task_types": m.task_types
            }
            for m in self.methods.values()
        ]
    
    def suggest_method_for_task(
        self,
        task_type: str,
        task_description: str
    ) -> Dict[str, Any]:
        """
        为任务推荐方法
        
        Args:
            task_type: 任务类型
            task_description: 任务描述
            
        Returns:
            推荐结果
        """
        best = self.get_best_method(task_type)
        
        if best:
            method_id, method = best
            return {
                "recommended_method": method_id,
                "method_name": method.name,
                "description": method.description,
                "parameters": method.parameters,
                "confidence": method.success_rate,
                "estimated_time": method.avg_time
            }
        
        # 没有找到匹配的方法，尝试从知识图谱获取
        if self.knowledge_graph:
            similar = self.knowledge_graph.query_relevant(
                query=task_description,
                task_type=task_type,
                limit=3
            )
            
            if similar:
                return {
                    "recommended_method": None,
                    "suggested_from_knowledge": similar[0]["content"],
                    "confidence": similar[0].get("success_rate", 0.5)
                }
        
        return {
            "recommended_method": None,
            "suggestion": "暂无推荐方法，将使用默认策略"
        }
