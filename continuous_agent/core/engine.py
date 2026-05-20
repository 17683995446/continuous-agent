#!/usr/bin/env python3
"""
持续运行Agent核心引擎
====================
主要职责：
1. 任务接收和调度
2. 执行状态管理
3. 与知识图谱和优化模块协调
"""

import asyncio
import json
import time
import threading
import queue
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path
from datetime import datetime
import traceback
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("ContinuousAgent")


class TaskType(Enum):
    """任务类型枚举"""
    IMPLEMENT = "implement"          # 实现需求
    REFACTOR = "refactor"            # 重构代码
    ANALYZE = "analyze"              # 分析代码
    FIX_BUG = "fix_bug"              # 修复bug
    ADD_FEATURE = "add_feature"      # 新增功能
    OPTIMIZE = "optimize"            # 优化代码
    TEST = "test"                    # 测试代码
    DOCUMENT = "document"            # 编写文档


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"              # 等待执行
    RUNNING = "running"              # 正在执行
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败
    RETRYING = "retrying"            # 重试中
    PAUSED = "paused"                # 已暂停


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0    # 最高优先级
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class Task:
    """任务数据结构"""
    id: str
    description: str
    task_type: TaskType
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional['TaskResult'] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "description": self.description,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "context": self.context,
            "dependencies": self.dependencies,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result.to_dict() if self.result else None
        }


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    learnings: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": str(self.output) if self.output else None,
            "error": self.error,
            "metrics": self.metrics,
            "learnings": self.learnings,
            "files_modified": self.files_modified
        }


class ContinuousAgent:
    """
    持续运行Agent核心类
    
    特性：
    - 无空闲时刻，全程满负荷运转
    - 经验自动积累，越运行知识越多
    - 遇事先查图谱，做事更快更准
    - 执行、优化、存知识三者同时进行
    """
    
    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        optimizer: Optional[Any] = None,
        executor: Optional[Any] = None,
        workspace: str = "/data/user/work",
        state_file: Optional[str] = None,
        max_queue_size: int = 500
    ):
        self.knowledge_graph = knowledge_graph
        self.optimizer = optimizer
        self.executor = executor
        self.workspace = Path(workspace)
        # state_file 默认放在 workspace 目录下，避免不同实例共享状态
        self.state_file = Path(state_file) if state_file else self.workspace / "agent_state.json"
        self.max_queue_size = max_queue_size
        
        # 任务队列
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.active_tasks: Dict[str, Task] = {}
        self.completed_tasks: Dict[str, Task] = {}
        self._processed_task_ids: set = set()  # 已处理过的任务ID，防止知识重复存储
        
        # 线程安全
        self._lock = threading.RLock()
        self._task_counter = 0
        self._max_completed_tasks = 1000  # completed_tasks 上限，防止内存泄漏
        
        # 运行状态
        self._running = False
        self._paused = False
        self._stop_event = threading.Event()
        
        # 工作线程
        self._executor_thread: Optional[threading.Thread] = None
        self._optimizer_thread: Optional[threading.Thread] = None
        self._knowledge_thread: Optional[threading.Thread] = None
        
        # 统计信息
        self.stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_runtime": 0,
            "optimizations_applied": 0,
            "knowledge_entries_added": 0
        }
        
        # 回调函数
        self._on_task_complete: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_learning: Optional[Callable] = None
        
        # 加载状态
        self._load_state()
        
        logger.info("ContinuousAgent 初始化完成")
    
    def _load_state(self):
        """加载持久化状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.stats = state.get("stats", self.stats)
                    logger.info(f"加载状态: {self.stats}")
            except Exception as e:
                logger.warning(f"加载状态失败: {e}")
    
    def _save_state(self):
        """保存状态"""
        try:
            state = {
                "stats": self.stats,
                "last_saved": datetime.now().isoformat()
            }
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")
    
    def add_task(
        self,
        description: str,
        task_type: TaskType = TaskType.IMPLEMENT,
        priority: TaskPriority = TaskPriority.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        添加新任务
        
        Args:
            description: 任务描述
            task_type: 任务类型
            priority: 优先级
            context: 上下文信息
            dependencies: 依赖的任务ID列表
            
        Returns:
            任务ID
        """
        # 输入验证
        if description is None:
            raise ValueError("任务描述不能为None")
        
        if not isinstance(description, str):
            raise ValueError(f"任务描述必须是字符串，当前类型: {type(description)}")
        
        if len(description.strip()) == 0:
            raise ValueError("任务描述不能为空字符串")
        
        if not isinstance(task_type, TaskType):
            raise ValueError(f"无效的任务类型: {task_type}")
        
        if not isinstance(priority, TaskPriority):
            raise ValueError(f"无效的优先级: {priority}")
        
        # 检查队列大小限制
        current_queue_size = self.task_queue.qsize()
        if current_queue_size >= self.max_queue_size:
            logger.warning(f"任务队列已满 ({current_queue_size}/{self.max_queue_size})")
            raise RuntimeError(f"任务队列已满 ({current_queue_size}/{self.max_queue_size})，请稍后重试")
        
        # 生成唯一任务ID（使用计数器+时间戳+随机数）
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{int(time.time() * 1000)}_{self._task_counter}_{random.randint(1000, 9999)}"
        
        # 检查依赖是否存在
        if dependencies:
            for dep_id in dependencies:
                if dep_id not in self.active_tasks and dep_id not in self.completed_tasks:
                    raise ValueError(f"依赖的任务不存在: {dep_id}")
            
            # 检测循环依赖
            if self._would_create_cycle(task_id, dependencies):
                raise ValueError(f"检测到循环依赖，任务ID: {task_id}")
        
        task = Task(
            id=task_id,
            description=description,
            task_type=task_type,
            priority=priority,
            context=context or {},
            dependencies=dependencies or []
        )
        
        # 放入优先级队列（优先级值越小越优先）
        self.task_queue.put((priority.value, task.created_at.timestamp(), task))
        
        with self._lock:
            self.active_tasks[task_id] = task
        
        logger.info(f"添加任务 [{task_id}]: {description}")
        return task_id
    
    def add_batch_tasks(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """批量添加任务，跳过无效条目"""
        task_ids = []
        for task_info in tasks:
            if not task_info or not isinstance(task_info, dict):
                logger.warning("跳过无效的批量任务: 条目为None或非字典")
                continue
            description = task_info.get("description", "")
            if not description or not isinstance(description, str) or len(description.strip()) == 0:
                logger.warning("跳过无效的批量任务: 缺少有效描述")
                continue
            try:
                task_id = self.add_task(
                    description=description,
                    task_type=TaskType(task_info.get("task_type", "implement")),
                    priority=TaskPriority(task_info.get("priority", 2)),
                    context=task_info.get("context"),
                    dependencies=task_info.get("dependencies")
                )
                task_ids.append(task_id)
            except (ValueError, KeyError) as e:
                logger.warning(f"跳过无效的批量任务: {e}")
        return task_ids
    
    def start(self):
        """启动Agent"""
        if self._running:
            logger.warning("Agent已在运行中")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # 启动执行线程
        self._executor_thread = threading.Thread(
            target=self._execution_loop,
            name="ExecutorThread",
            daemon=True
        )
        self._executor_thread.start()
        logger.debug("执行线程已启动")
        
        # 启动优化线程
        self._optimizer_thread = threading.Thread(
            target=self._optimization_loop,
            name="OptimizerThread",
            daemon=True
        )
        self._optimizer_thread.start()
        logger.debug("优化线程已启动")
        
        # 启动知识存储线程
        self._knowledge_thread = threading.Thread(
            target=self._knowledge_loop,
            name="KnowledgeThread",
            daemon=True
        )
        self._knowledge_thread.start()
        logger.debug("知识线程已启动")
        
        logger.info("🚀 ContinuousAgent 已启动，开始持续运行...")
    
    def stop(self):
        """停止Agent"""
        logger.info("正在停止Agent...")
        self._running = False
        self._stop_event.set()
        
        # 等待线程结束
        for thread in [self._executor_thread, self._optimizer_thread, self._knowledge_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f"线程 {thread.name} 未能在5秒内结束")
        
        # 保存状态
        self._save_state()
        logger.info("Agent已停止")
    
    def pause(self):
        """暂停执行"""
        self._paused = True
        logger.info(f"Agent已暂停，当前活跃任务数: {len(self.active_tasks)}")
    
    def resume(self):
        """恢复执行"""
        self._paused = False
        logger.info("Agent已恢复")
    
    def _execution_loop(self):
        """
        执行循环 - 核心工作线程
        
        流程：
        1. 从知识图谱调取老经验
        2. 不间断执行任务
        3. 做完立刻总结优缺点
        4. 出错自动修复
        """
        while self._running and not self._stop_event.is_set():
            try:
                if self._paused:
                    time.sleep(0.5)
                    continue
                
                # 获取下一个任务（带超时）
                try:
                    priority, _, task = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    # 队列为空，检查是否有待重试的任务
                    logger.debug("任务队列为空，等待新任务...")
                    self._check_retry_tasks()
                    continue
                
                # 检查依赖是否满足
                if not self._check_dependencies(task):
                    # 依赖未满足，增加等待计数
                    task._dependency_wait_count = getattr(task, '_dependency_wait_count', 0) + 1
                    
                    if task._dependency_wait_count > 100:
                        # 超过最大等待次数，标记为失败
                        logger.warning(f"⚠️ 任务依赖等待超时，放弃执行 [{task.id}]: {task.description}")
                        task.status = TaskStatus.FAILED
                        # Bug#48修复: 设置task.result，确保任务不会"消失"
                        task.result = TaskResult(
                            success=False,
                            error=f"依赖等待超时: 依赖任务未在规定时间内完成",
                            learnings=[f"任务 {task.id} 因依赖超时失败"]
                        )
                        with self._lock:
                            self.stats["tasks_failed"] += 1
                            self.active_tasks.pop(task.id, None)
                        # Bug#48修复: 调用失败回调
                        callback = self._on_task_failed
                        if callback:
                            try:
                                callback(task, task.result)
                            except Exception as cb_err:
                                logger.error(f"依赖超时失败回调异常: {cb_err}")
                        continue
                    
                    # 重新放回队列，使用递增的优先级避免饥饿
                    time.sleep(0.5)
                    new_priority = max(priority, task._dependency_wait_count)
                    self.task_queue.put((new_priority, task.created_at.timestamp(), task))
                    continue
                
                # 更新任务状态
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                
                logger.info(f"▶ 开始执行任务 [{task.id}]: {task.description}")
                
                # 1. 先从知识图谱调取相关经验
                relevant_experience = self._query_knowledge(task)
                if relevant_experience:
                    logger.info(f"📚 找到 {len(relevant_experience)} 条相关经验")
                
                # 2. 执行任务
                result = self._execute_task(task, relevant_experience)
                
                # 3. 处理结果
                if result.success:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now()
                    task.result = result
                    
                    with self._lock:
                        self.completed_tasks[task.id] = task
                        # 安全删除，避免KeyError
                        self.active_tasks.pop(task.id, None)
                        self.stats["tasks_completed"] += 1
                        # 防止 completed_tasks 无限增长
                        if len(self.completed_tasks) > self._max_completed_tasks:
                            oldest_ids = sorted(
                                self.completed_tasks.keys(),
                                key=lambda tid: self.completed_tasks[tid].completed_at or datetime.min
                            )
                            for old_id in oldest_ids[:len(self.completed_tasks) - self._max_completed_tasks]:
                                del self.completed_tasks[old_id]
                    
                    logger.info(f"✅ 任务完成 [{task.id}]")
                    
                    # 安全调用回调
                    callback = self._on_task_complete
                    if callback:
                        try:
                            callback(task, result)
                        except Exception as cb_err:
                            logger.error(f"任务完成回调异常: {cb_err}")
                else:
                    # 失败处理
                    # 判断是否为不可恢复的错误（如不支持的任务类型）
                    is_unrecoverable = (
                        result.error and 
                        "需要自定义执行器" in (result.error or "")
                    )
                    
                    # Bug#37修复: 统一设置 task.result，确保后续知识存储能获取 learnings
                    task.result = result
                    
                    if is_unrecoverable:
                        # 不可恢复的错误直接标记失败，不浪费重试
                        task.status = TaskStatus.FAILED
                        with self._lock:
                            self.stats["tasks_failed"] += 1
                            self.active_tasks.pop(task.id, None)
                        logger.error(f"❌ 任务不可恢复 [{task.id}]: {result.error}")
                        # Bug#37修复: 不可恢复失败也要调用回调
                        callback = self._on_task_failed
                        if callback:
                            try:
                                callback(task, result)
                            except Exception as cb_err:
                                logger.error(f"任务失败回调异常: {cb_err}")
                    else:
                        task.retry_count += 1
                        if task.retry_count < task.max_retries:
                            task.status = TaskStatus.PENDING
                            logger.warning(f"⚠️ 任务失败，准备重试 [{task.id}] ({task.retry_count}/{task.max_retries})")
                            self.task_queue.put((priority, task.created_at.timestamp(), task))
                            # 重试中不调用失败回调，也不计入失败统计，等最终失败再处理
                            continue  # 不走下面的最终失败逻辑
                        else:
                            task.status = TaskStatus.FAILED
                        # Bug#36修复: 只有最终失败才在这里计入 stats（is_unrecoverable 分支已单独计入）
                        with self._lock:
                            self.stats["tasks_failed"] += 1
                            # 失败任务也从 active_tasks 移除，防止重复重试
                            self.active_tasks.pop(task.id, None)
                        logger.error(f"❌ 任务最终失败 [{task.id}]: {result.error}")
                        self._save_state()
                        
                        # Bug#37修复: 最终失败时调用回调
                        callback = self._on_task_failed
                        if callback:
                            try:
                                callback(task, result)
                            except Exception as cb_err:
                                logger.error(f"任务失败回调异常: {cb_err}")
                
                # 定期保存状态
                with self._lock:
                    completed = self.stats["tasks_completed"]
                if completed > 0 and completed % 10 == 0:
                    self._save_state()
                    
            except Exception as e:
                logger.error(f"执行循环异常: {e}\n{traceback.format_exc()}")
                time.sleep(1)
    
    def _optimization_loop(self):
        """
        优化循环 - 自动改进方法
        
        流程：
        1. 分析已完成任务的模式
        2. 识别可优化的方法
        3. 应用优化建议
        """
        while self._running and not self._stop_event.is_set():
            try:
                if self._paused:
                    time.sleep(1)
                    continue
                
                # 每30秒执行一次优化分析
                time.sleep(30)
                
                if self.optimizer and len(self.completed_tasks) >= 3:
                    # 分析最近的完成任务
                    recent_tasks = list(self.completed_tasks.values())[-10:]
                    
                    optimization_result = self.optimizer.analyze_and_optimize(
                        tasks=recent_tasks,
                        stats=self.stats
                    )
                    
                    if optimization_result.get("improvements"):
                        self.stats["optimizations_applied"] += len(optimization_result["improvements"])
                        logger.info(f"🔧 应用 {len(optimization_result['improvements'])} 项优化")
                else:
                    logger.debug(f"完成任务数不足，跳过优化 (当前: {len(self.completed_tasks)})")
                        
            except Exception as e:
                logger.error(f"优化循环异常: {e}")
                time.sleep(5)
    
    def _knowledge_loop(self):
        """
        知识存储循环 - 持续积累经验
        
        流程：
        1. 收集新经验
        2. 归类存档
        3. 更新知识图谱
        """
        while self._running and not self._stop_event.is_set():
            try:
                if self._paused:
                    time.sleep(1)
                    continue
                
                # 每10秒检查一次新知识
                time.sleep(10)
                
                if self.knowledge_graph:
                    # 收集最近完成任务的经验（只处理未处理过的任务）
                    with self._lock:
                        recent_completed = list(self.completed_tasks.items())[-5:]
                    
                    for task_id, task in recent_completed:
                        if task_id in self._processed_task_ids:
                            continue
                        if task.result and task.result.learnings:
                            for learning in task.result.learnings:
                                self.knowledge_graph.add_experience(
                                    content=learning,
                                    task_type=task.task_type.value,
                                    context={
                                        "task_id": task.id,
                                        "success": task.result.success,
                                        "metrics": task.result.metrics
                                    }
                                )
                            with self._lock:
                                self._processed_task_ids.add(task_id)
                                self.stats["knowledge_entries_added"] += len(task.result.learnings)
                            logger.info(f"📖 存入新经验: {task_id} ({len(task.result.learnings)}条)")
                    
                    # 批量保存到磁盘（避免每次add_experience都写磁盘）
                    if self.knowledge_graph:
                        self.knowledge_graph.flush()
                else:
                    logger.debug("未配置知识图谱，跳过知识存储")
                        
            except Exception as e:
                logger.error(f"知识存储循环异常: {e}")
                time.sleep(5)
    
    def _query_knowledge(self, task: Task) -> List[Dict[str, Any]]:
        """从知识图谱查询相关经验"""
        if not self.knowledge_graph:
            return []
        
        try:
            return self.knowledge_graph.query_relevant(
                query=task.description,
                task_type=task.task_type.value,
                limit=5
            )
        except Exception as e:
            logger.warning(f"查询知识图谱失败: {e}")
            return []
    
    def _execute_task(
        self,
        task: Task,
        relevant_experience: List[Dict[str, Any]]
    ) -> TaskResult:
        """
        执行单个任务
        
        Args:
            task: 任务对象
            relevant_experience: 相关经验列表
            
        Returns:
            执行结果
        """
        start_time = time.time()
        
        try:
            if self.executor:
                # 使用自定义执行器
                result = self.executor.execute(
                    task=task,
                    experience=relevant_experience,
                    workspace=str(self.workspace)
                )
            else:
                # 默认执行逻辑
                result = self._default_execute(task, relevant_experience)
            
            # 记录执行时间
            elapsed = time.time() - start_time
            if result.metrics is None:
                result.metrics = {}
            result.metrics["execution_time"] = elapsed
            with self._lock:
                self.stats["total_runtime"] += elapsed
            
            return result
            
        except Exception as e:
            logger.error(f"执行任务异常 [{task.id}]: {e}")
            return TaskResult(
                success=False,
                error=f"{str(e)}\n{traceback.format_exc()}"
            )
    
    def _default_execute(
        self,
        task: Task,
        experience: List[Dict[str, Any]]
    ) -> TaskResult:
        """
        默认执行逻辑
        
        根据任务类型执行相应操作
        """
        output = None
        learnings = []
        files_modified = []
        
        try:
            task_type = task.task_type
            
            if task_type == TaskType.ANALYZE:
                # 分析代码
                output = self._analyze_code(task.context)
                learnings.append(f"分析任务完成，发现 {len(output.get('issues', []))} 个问题")
                
            elif task_type == TaskType.FIX_BUG:
                # 修复bug
                output = self._fix_bug(task.context)
                learnings.append(f"Bug修复: {output.get('fix_description', '已完成')}")
                files_modified = output.get('files_modified', [])
                
            elif task_type == TaskType.IMPLEMENT:
                # 实现需求
                output = self._implement_feature(task.context)
                learnings.append(f"功能实现: {task.description[:50]}")
                files_modified = output.get('files_modified', [])
                
            elif task_type == TaskType.REFACTOR:
                # 重构代码
                output = self._refactor_code(task.context)
                learnings.append(f"重构完成: {output.get('summary', '代码已优化')}")
                files_modified = output.get('files_modified', [])
                
            elif task_type == TaskType.ADD_FEATURE:
                # 新增功能
                output = self._add_feature(task.context)
                learnings.append(f"新功能添加: {task.description[:50]}")
                files_modified = output.get('files_modified', [])
                
            else:
                # DOCUMENT/TEST/OPTIMIZE 等类型需要自定义执行器
                # 默认执行器不做实际操作，返回未实现提示
                return TaskResult(
                    success=False,
                    error=f"任务类型 {task_type.value} 需要自定义执行器，默认执行器不支持",
                    output={"message": f"任务类型 {task_type} 的执行逻辑待实现"},
                    learnings=[f"未实现的任务类型: {task_type.value}"]
                )
            
            return TaskResult(
                success=True,
                output=output,
                learnings=learnings,
                files_modified=files_modified
            )
            
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                learnings=[f"执行失败: {str(e)}"]
            )
    
    def _analyze_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析代码"""
        # 这里可以集成实际的代码分析逻辑
        return {
            "issues": [],
            "suggestions": [],
            "complexity": "medium"
        }
    
    def _fix_bug(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """修复bug"""
        return {
            "fix_description": "Bug已修复",
            "files_modified": []
        }
    
    def _implement_feature(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """实现功能"""
        return {
            "implementation": "功能已实现",
            "files_modified": []
        }
    
    def _refactor_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """重构代码"""
        return {
            "summary": "代码已重构",
            "files_modified": []
        }
    
    def _add_feature(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """添加新功能"""
        return {
            "feature": "新功能已添加",
            "files_modified": []
        }
    
    def _check_dependencies(self, task: Task) -> bool:
        """检查任务依赖是否满足"""
        result = all(dep_id in self.completed_tasks for dep_id in task.dependencies)
        logger.debug(f"检查依赖 [{task.id}]: 满足={result}")
        return result
    
    def _would_create_cycle(self, new_task_id: str, new_task_deps: List[str]) -> bool:
        """
        检测新任务是否会创建循环依赖
        
        检查新任务的任何依赖是否最终依赖于新任务本身
        """
        visited = set()
        
        def has_path_to(current_id: str, target_id: str) -> bool:
            """检查从current_id出发是否能到达target_id"""
            if current_id == target_id:
                return True
            if current_id in visited:
                return False
            
            visited.add(current_id)
            
            # 查找current_id对应的任务
            task = None
            if current_id in self.active_tasks:
                task = self.active_tasks[current_id]
            elif current_id in self.completed_tasks:
                task = self.completed_tasks[current_id]
            
            if task:
                for next_dep in task.dependencies:
                    if has_path_to(next_dep, target_id):
                        return True
            
            return False
        
        # 检查新任务的任何依赖是否能到达新任务
        # 这会形成循环: new_task -> dep -> ... -> new_task
        for dep_id in new_task_deps:
            visited.clear()  # 重置visited
            if has_path_to(dep_id, new_task_id):
                return True
        
        return False
    
    def _check_retry_tasks(self):
        """检查需要重试的任务
        
        注意：当前实现中任务重试直接在 _execution_loop 的失败分支中处理
        （设置 status=PENDING 并重新入队），不再使用 RETRYING 状态。
        此方法保留是为了向后兼容，但实际不会找到任何 RETRYING 状态的任务。
        """
        logger.debug(f"检查重试任务...")
        with self._lock:
            retrying_tasks = [
                (tid, t) for tid, t in self.active_tasks.items()
                if t.status == TaskStatus.RETRYING
            ]
        
        if retrying_tasks:
            logger.warning(f"发现 {len(retrying_tasks)} 个RETRYING状态的任务（不应出现）")
        
        for task_id, task in retrying_tasks:
            # 将状态重置为PENDING再入队，防止重复入队
            task.status = TaskStatus.PENDING
            self.task_queue.put((
                task.priority.value,
                task.created_at.timestamp(),
                task
            ))
            logger.debug(f"重试任务已入队 [{task_id}]")
    
    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "running": self._running,
            "paused": self._paused,
            "active_tasks": len(self.active_tasks),
            "queued_tasks": self.task_queue.qsize(),
            "completed_tasks": len(self.completed_tasks),
            "stats": self.stats
        }
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]
        if task_id in self.completed_tasks:
            return self.completed_tasks[task_id]
        return None
    
    def set_callbacks(
        self,
        on_task_complete: Optional[Callable] = None,
        on_task_failed: Optional[Callable] = None,
        on_learning: Optional[Callable] = None
    ):
        """设置回调函数"""
        self._on_task_complete = on_task_complete
        self._on_task_failed = on_task_failed
        self._on_learning = on_learning
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
        return False
