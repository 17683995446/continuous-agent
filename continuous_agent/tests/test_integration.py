#!/usr/bin/env python3
"""
集成测试
=======
测试各模块协同工作
"""

import os
import sys
import time
import unittest
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from continuous_agent.core.engine import (
    ContinuousAgent, Task, TaskType, TaskStatus, TaskPriority, TaskResult
)
from continuous_agent.core.executor import CodeExecutor
from continuous_agent.core.scheduler import TaskScheduler, ScheduleStrategy
from continuous_agent.knowledge.graph import KnowledgeGraph, ExperienceType
from continuous_agent.knowledge.storage import MemoryStorage, FileStorage
from continuous_agent.knowledge.retriever import KnowledgeRetriever
from continuous_agent.optimizer.learner import Optimizer
from continuous_agent.optimizer.analyzer import PerformanceAnalyzer
from continuous_agent.keeper.alive import KeepAlive, HealthStatus


class TestCoreEngine(unittest.TestCase):
    """测试核心引擎"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = Path("/data/user/work/test_agent")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.agent = ContinuousAgent(
            workspace=str(self.test_dir),
            state_file=str(self.test_dir / "state.json")
        )
    
    def tearDown(self):
        """测试后清理"""
        self.agent.stop()
    
    def test_add_task(self):
        """测试添加任务"""
        task_id = self.agent.add_task(
            description="测试任务",
            task_type=TaskType.IMPLEMENT
        )
        
        self.assertIsNotNone(task_id)
        self.assertIn(task_id, self.agent.active_tasks)
        
        task = self.agent.get_task(task_id)
        self.assertEqual(task.description, "测试任务")
        self.assertEqual(task.task_type, TaskType.IMPLEMENT)
    
    def test_task_priority(self):
        """测试任务优先级"""
        import time
        # 添加不同优先级的任务（添加延迟避免ID冲突）
        low_id = self.agent.add_task(
            description="低优先级任务",
            task_type=TaskType.IMPLEMENT,
            priority=TaskPriority.LOW
        )
        time.sleep(0.01)  # 避免时间戳冲突
        
        high_id = self.agent.add_task(
            description="高优先级任务",
            task_type=TaskType.IMPLEMENT,
            priority=TaskPriority.HIGH
        )
        time.sleep(0.01)
        
        critical_id = self.agent.add_task(
            description="紧急任务",
            task_type=TaskType.FIX_BUG,
            priority=TaskPriority.CRITICAL
        )
        
        # 验证任务已添加
        self.assertEqual(len(self.agent.active_tasks), 3)
        # 验证ID不同
        self.assertNotEqual(low_id, high_id)
        self.assertNotEqual(high_id, critical_id)
    
    def test_agent_status(self):
        """测试状态获取"""
        status = self.agent.get_status()
        
        self.assertIn("running", status)
        self.assertIn("paused", status)
        self.assertIn("active_tasks", status)
        self.assertIn("stats", status)


class TestKnowledgeGraph(unittest.TestCase):
    """测试知识图谱"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = Path("/data/user/work/test_knowledge")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.kg = KnowledgeGraph(
            storage_path=str(self.test_dir / "kg")
        )
    
    def tearDown(self):
        """测试后清理"""
        self.kg.clear()
    
    def test_add_experience(self):
        """测试添加经验"""
        entry_id = self.kg.add_experience(
            content="使用工厂模式可以解耦对象创建",
            task_type="refactor",
            experience_type=ExperienceType.PATTERN,
            tags=["design-pattern", "factory"]
        )
        
        self.assertIsNotNone(entry_id)
        self.assertIn(entry_id, self.kg.entries)
    
    def test_query_relevant(self):
        """测试查询相关经验"""
        # 添加一些经验
        self.kg.add_experience(
            content="Python中使用try-except处理异常",
            task_type="fix_bug",
            experience_type=ExperienceType.SOLUTION
        )
        
        self.kg.add_experience(
            content="使用日志记录异常信息便于调试",
            task_type="fix_bug",
            experience_type=ExperienceType.BEST_PRACTICE
        )
        
        # 查询
        results = self.kg.query_relevant(
            query="如何处理Python异常",
            task_type="fix_bug"
        )
        
        self.assertGreater(len(results), 0)
    
    def test_update_success_rate(self):
        """测试更新成功率"""
        entry_id = self.kg.add_experience(
            content="测试经验",
            task_type="test"
        )
        
        # 获取初始值（add_experience会自动+1）
        entry = self.kg.get_entry(entry_id)
        initial_count = entry.success_count
        
        # 更新成功
        self.kg.update_success(entry_id, True)
        entry = self.kg.get_entry(entry_id)
        self.assertEqual(entry.success_count, initial_count + 1)
        
        # 更新失败
        self.kg.update_success(entry_id, False)
        entry = self.kg.get_entry(entry_id)
        self.assertEqual(entry.fail_count, 1)


class TestOptimizer(unittest.TestCase):
    """测试优化器"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = Path("/data/user/work/test_optimizer")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.optimizer = Optimizer(
            history_file=str(self.test_dir / "opt_history.json")
        )
    
    def test_record_task_completion(self):
        """测试记录任务完成"""
        # 记录成功的任务
        self.optimizer.record_task_completion(
            task_type="implement",
            success=True,
            execution_time=30.0,
            method_used="default"
        )
        
        # 记录失败的任务
        self.optimizer.record_task_completion(
            task_type="implement",
            success=False,
            execution_time=60.0,
            error="TimeoutError"
        )
        
        # 验证指标
        self.assertEqual(len(self.optimizer.metrics["execution_time"]), 2)
    
    def test_get_recommendation(self):
        """测试获取推荐"""
        # 记录一些任务
        for i in range(5):
            self.optimizer.record_task_completion(
                task_type="analyze",
                success=True,
                execution_time=20.0 + i * 5,
                method_used="static_analysis"
            )
        
        recommendation = self.optimizer.get_recommendation("analyze")
        
        self.assertEqual(recommendation["task_type"], "analyze")
        self.assertIsNotNone(recommendation["estimated_time"])
    
    def test_analyze_and_optimize(self):
        """测试分析和优化"""
        # 记录一些任务
        for i in range(20):
            self.optimizer.record_task_completion(
                task_type="test",
                success=i % 3 != 0,  # 2/3成功率
                execution_time=10.0 + i
            )
        
        result = self.optimizer.analyze_and_optimize()
        
        self.assertIn("improvements", result)
        self.assertIn("patterns", result)


class TestScheduler(unittest.TestCase):
    """测试任务调度器"""
    
    def setUp(self):
        """测试前准备"""
        self.scheduler = TaskScheduler(
            strategy=ScheduleStrategy.SMART
        )
    
    def test_schedule_task(self):
        """测试调度任务"""
        success = self.scheduler.schedule(
            task_id="task_001",
            priority=1,
            estimated_duration=60.0,
            task_data={"type": "implement"}
        )
        
        self.assertTrue(success)
    
    def test_get_next(self):
        """测试获取下一个任务"""
        # 调度多个任务
        self.scheduler.schedule("task_001", priority=2)
        self.scheduler.schedule("task_002", priority=0)  # 最高优先级
        self.scheduler.schedule("task_003", priority=1)
        
        # 获取下一个
        next_task = self.scheduler.get_next()
        
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.task_id, "task_002")
    
    def test_complete_task(self):
        """测试完成任务"""
        self.scheduler.schedule("task_001", priority=1)
        task = self.scheduler.get_next()
        
        self.scheduler.complete(
            task_id="task_001",
            success=True,
            execution_time=30.0
        )
        
        status = self.scheduler.get_status()
        self.assertEqual(status["completed_tasks"], 1)


class TestKeepAlive(unittest.TestCase):
    """测试保活模块"""
    
    def test_health_check(self):
        """测试健康检查"""
        keepalive = KeepAlive()
        
        # 注册健康检查
        def check_test() -> 'HealthCheck':
            from continuous_agent.keeper.alive import HealthCheck
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="测试正常"
            )
        
        keepalive.register_health_check("test", check_test)
        
        # 运行检查
        results = keepalive.run_health_checks()
        
        self.assertIn("test", results)
        self.assertEqual(results["test"].status, HealthStatus.HEALTHY)
    
    def test_watchdog(self):
        """测试看门狗"""
        from continuous_agent.keeper.alive import Watchdog
        
        watchdog = Watchdog(timeout_seconds=5, check_interval=1)
        
        timeout_called = []
        
        def on_timeout():
            timeout_called.append(True)
        
        watchdog.set_timeout_callback(on_timeout)
        watchdog.start()
        
        # 发送心跳
        watchdog.heartbeat()
        time.sleep(2)
        
        # 检查状态
        status = watchdog.get_status()
        self.assertEqual(status["status"], "ok")
        
        watchdog.stop()


class TestCodeExecutor(unittest.TestCase):
    """测试代码执行器"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = Path("/data/user/work/test_executor")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.executor = CodeExecutor(workspace=str(self.test_dir))
    
    def test_detect_language(self):
        """测试语言检测"""
        self.assertEqual(self.executor._detect_language(".py"), "python")
        self.assertEqual(self.executor._detect_language(".js"), "javascript")
        self.assertEqual(self.executor._detect_language(".ts"), "typescript")
    
    def test_analyze_python(self):
        """测试Python代码分析"""
        code = '''
def hello():
    print("Hello, World!")

class Greeter:
    def greet(self, name):
        return f"Hello, {name}!"
'''
        
        issues, metrics = self.executor._analyze_python(code)
        
        self.assertEqual(metrics["functions"], 2)
        self.assertEqual(metrics["classes"], 1)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        test_dir = Path("/data/user/work/test_integration")
        test_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 创建知识图谱
        kg = KnowledgeGraph(
            storage_path=str(test_dir / "kg")
        )
        
        # 2. 添加初始经验
        kg.add_experience(
            content="使用类型注解提高代码可读性",
            task_type="refactor",
            experience_type=ExperienceType.BEST_PRACTICE
        )
        
        # 3. 创建优化器
        optimizer = Optimizer(
            knowledge_graph=kg,
            history_file=str(test_dir / "opt.json")
        )
        
        # 4. 创建Agent
        agent = ContinuousAgent(
            knowledge_graph=kg,
            optimizer=optimizer,
            workspace=str(test_dir)
        )
        
        # 5. 添加任务
        task_id = agent.add_task(
            description="重构用户服务代码",
            task_type=TaskType.REFACTOR
        )
        
        self.assertIsNotNone(task_id)
        
        # 6. 记录优化数据
        optimizer.record_task_completion(
            task_type="refactor",
            success=True,
            execution_time=45.0
        )
        
        # 7. 验证知识积累
        self.assertGreater(len(kg.entries), 0)
        
        # 清理
        agent.stop()
        kg.clear()


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestCoreEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestKnowledgeGraph))
    suite.addTests(loader.loadTestsFromTestCase(TestOptimizer))
    suite.addTests(loader.loadTestsFromTestCase(TestScheduler))
    suite.addTests(loader.loadTestsFromTestCase(TestKeepAlive))
    suite.addTests(loader.loadTestsFromTestCase(TestCodeExecutor))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
