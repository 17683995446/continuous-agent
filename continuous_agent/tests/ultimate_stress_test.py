#!/usr/bin/env python3
"""
极限压力测试 - 慢工出细活
========================
更长时间、更大规模、更复杂、更混乱的真实实践
"""

import sys
import time
import threading
import random
import gc
import os
import signal
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, '/workspace')

from continuous_agent.core.engine import ContinuousAgent, TaskType, TaskPriority, TaskStatus
from continuous_agent.knowledge.graph import KnowledgeGraph
from continuous_agent.optimizer.learner import Optimizer


class UltimateStressTest:
    """极限压力测试"""
    
    def __init__(self):
        self.base = Path("/data/user/work/ultimate_stress")
        self.base.mkdir(parents=True, exist_ok=True)
        self.issues = []
        self.metrics = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'errors': [],
            'memory_peaks': []
        }
    
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {msg}")
    
    def issue(self, desc):
        self.issues.append(desc)
        self.log(f"⚠️ {desc}")
    
    def test_1_mega_marathon(self):
        """
        测试1: 超级马拉松 - 30分钟持续运行，1000+任务
        """
        print("\n[测试1] 超级马拉松 (30分钟，1000+任务)")
        
        agent = ContinuousAgent(
            workspace=str(self.base / "mega"),
            max_queue_size=500
        )
        
        agent.start()
        start_time = time.time()
        
        task_id = 0
        while time.time() - start_time < 1800:  # 30分钟
            # 每10秒添加一批任务
            for _ in range(random.randint(5, 15)):
                try:
                    agent.add_task(
                        f"超级任务{task_id}",
                        task_type=random.choice(list(TaskType)),
                        priority=random.choice(list(TaskPriority))
                    )
                    self.metrics['tasks_submitted'] += 1
                    task_id += 1
                except RuntimeError:
                    pass  # 队列满
            
            # 每2分钟报告一次
            elapsed = int(time.time() - start_time)
            if elapsed % 120 == 0:
                status = agent.get_status()
                self.log(f"T+{elapsed//60}min: "
                        f"提交{self.metrics['tasks_submitted']} "
                        f"完成{status['stats']['tasks_completed']} "
                        f"失败{status['stats']['tasks_failed']}")
                
                # 检查异常
                if status['stats']['tasks_failed'] > 50:
                    self.issue(f"T+{elapsed//60}min 失败任务过多: {status['stats']['tasks_failed']}")
            
            time.sleep(10)
        
        agent.stop()
        
        final = agent.get_status()
        self.metrics['tasks_completed'] = final['stats']['tasks_completed']
        self.metrics['tasks_failed'] = final['stats']['tasks_failed']
        
        success_rate = self.metrics['tasks_completed'] / max(self.metrics['tasks_submitted'], 1)
        self.log(f"结论: 提交{self.metrics['tasks_submitted']}，完成{self.metrics['tasks_completed']}，"
                f"成功率{success_rate:.1%}")
        
        return success_rate > 0.8  # 80%以上成功率算通过
    
    def test_2_massive_dependency_web(self):
        """
        测试2: 大规模依赖网 - 复杂依赖关系
        """
        print("\n[测试2] 大规模依赖网 (100个任务，复杂依赖)")
        
        agent = ContinuousAgent(
            workspace=str(self.base / "dep_web"),
            max_queue_size=200
        )
        
        # 创建100个任务，形成复杂依赖网
        task_ids = []
        
        # 第一层：基础任务（无依赖）
        for i in range(20):
            tid = agent.add_task(f"基础任务{i}", priority=TaskPriority.HIGH)
            task_ids.append(tid)
        
        # 第二层：依赖1-2个基础任务
        for i in range(30):
            deps = random.sample(task_ids[:20], random.randint(1, 2))
            tid = agent.add_task(f"中间任务{i}", dependencies=deps)
            task_ids.append(tid)
        
        # 第三层：依赖多个中间任务
        for i in range(50):
            deps = random.sample(task_ids[20:50], random.randint(1, 3))
            tid = agent.add_task(f"顶层任务{i}", dependencies=deps)
            task_ids.append(tid)
        
        self.log(f"创建了{len(task_ids)}个任务，形成依赖网")
        
        agent.start()
        
        # 观察直到完成或超时
        for minute in range(10):
            status = agent.get_status()
            completed = len(agent.completed_tasks)
            self.log(f"M{minute+1}: 完成{completed}/{len(task_ids)}")
            
            if completed == len(task_ids):
                self.log("所有任务完成！")
                break
            
            time.sleep(60)
        
        agent.stop()
        
        final_completed = len(agent.completed_tasks)
        success = final_completed >= len(task_ids) * 0.9
        self.log(f"结论: 完成{final_completed}/{len(task_ids)}")
        
        return success
    
    def test_3_chaos_monkey(self):
        """
        测试3: 混沌猴子 - 随机破坏和干扰
        """
        print("\n[测试3] 混沌猴子 (随机干扰)")
        
        ws = self.base / "chaos_monkey"
        ws.mkdir(exist_ok=True)
        
        agent = ContinuousAgent(
            workspace=str(ws),
            max_queue_size=100
        )
        
        # 启动Agent
        agent.start()
        
        # 添加初始任务
        for i in range(50):
            agent.add_task(f"混沌任务{i}")
        
        # 混沌猴子线程
        stop_chaos = threading.Event()
        chaos_errors = []
        
        def chaos_monkey():
            """随机搞破坏"""
            while not stop_chaos.is_set():
                try:
                    action = random.choice([
                        'delete_state',
                        'corrupt_file',
                        'create_large_file',
                        'modify_permission'
                    ])
                    
                    if action == 'delete_state':
                        sf = ws / "agent_state.json"
                        if sf.exists():
                            sf.unlink()
                            self.log("混沌猴子: 删除了状态文件")
                    
                    elif action == 'corrupt_file':
                        cf = ws / "corrupted.txt"
                        cf.write_bytes(b'\x00\xff\x00\xff' * 1000)
                        self.log("混沌猴子: 创建了损坏文件")
                    
                    elif action == 'create_large_file':
                        lf = ws / "large_file.tmp"
                        lf.write_bytes(b'x' * (1024 * 1024))  # 1MB
                        self.log("混沌猴子: 创建了大文件")
                    
                    time.sleep(random.uniform(5, 15))
                    
                except Exception as e:
                    chaos_errors.append(str(e))
        
        chaos_thread = threading.Thread(target=chaos_monkey)
        chaos_thread.start()
        
        # 主线程继续添加任务
        for i in range(50, 100):
            try:
                agent.add_task(f"混沌任务{i}")
            except Exception as e:
                chaos_errors.append(f"add-{i}: {e}")
            time.sleep(2)
        
        # 停止混沌猴子
        stop_chaos.set()
        chaos_thread.join()
        
        time.sleep(10)
        agent.stop()
        
        status = agent.get_status()
        self.log(f"结论: 完成{status['stats']['tasks_completed']}个，混沌错误{len(chaos_errors)}个")
        
        # 只要系统没崩溃就算成功
        return status['stats']['tasks_completed'] > 0
    
    def test_4_memory_pressure_cooker(self):
        """
        测试4: 内存压力锅 - 持续高内存压力
        """
        print("\n[测试4] 内存压力锅 (持续高负载)")
        
        # 创建多个Agent同时运行
        agents = []
        errors = []
        
        def run_agent_instance(idx):
            try:
                a = ContinuousAgent(
                    workspace=str(self.base / f"mem_pressure_{idx}"),
                    max_queue_size=50
                )
                agents.append(a)
                
                for i in range(30):
                    a.add_task(f"Agent{idx}任务{i}")
                
                a.start()
                time.sleep(120)  # 运行2分钟
                a.stop()
                
            except Exception as e:
                errors.append(f"Agent{idx}: {e}")
        
        # 同时运行5个Agent
        threads = [threading.Thread(target=run_agent_instance, args=(i,)) for i in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        total_completed = sum(
            a.get_status()['stats']['tasks_completed'] 
            for a in agents if hasattr(a, 'get_status')
        )
        
        self.log(f"结论: 5个Agent共完成{total_completed}个任务，错误{len(errors)}个")
        
        return len(errors) == 0 and total_completed > 100
    
    def test_5_time_travel(self):
        """
        测试5: 时间旅行 - 系统时间变化的影响
        """
        print("\n[测试5] 时间旅行 (模拟时间变化)")
        
        # 注意：我们不能真正改变系统时间，但可以通过其他方式测试
        agent = ContinuousAgent(
            workspace=str(self.base / "time_travel"),
            max_queue_size=50
        )
        
        # 添加任务并记录时间戳
        tasks_with_time = []
        for i in range(20):
            tid = agent.add_task(f"时间任务{i}")
            tasks_with_time.append((tid, datetime.now()))
        
        agent.start()
        time.sleep(10)
        agent.stop()
        
        # 检查任务时间戳是否合理
        status = agent.get_status()
        
        # 验证：完成的任务时间应该晚于创建时间
        time_valid = True
        for tid, create_time in tasks_with_time:
            if tid in agent.completed_tasks:
                # 这里我们假设completed_at会被设置
                task = agent.completed_tasks[tid]
                if hasattr(task, 'completed_at') and task.completed_at:
                    if task.completed_at < create_time:
                        time_valid = False
                        self.issue(f"任务{tid}完成时间早于创建时间")
        
        self.log(f"结论: 完成{status['stats']['tasks_completed']}个，时间一致性{time_valid}")
        
        return time_valid
    
    def run_all(self):
        """运行所有测试"""
        print("="*70)
        print("  极限压力测试 - 慢工出细活")
        print("="*70)
        
        results = []
        
        # 选择性运行（这些测试非常耗时）
        # results.append(("超级马拉松", self.test_1_mega_marathon()))
        results.append(("大规模依赖网", self.test_2_massive_dependency_web()))
        results.append(("混沌猴子", self.test_3_chaos_monkey()))
        results.append(("内存压力锅", self.test_4_memory_pressure_cooker()))
        results.append(("时间旅行", self.test_5_time_travel()))
        
        passed = sum(1 for _, r in results if r)
        failed = len(results) - passed
        
        print("\n" + "="*70)
        print(f"  结果: {passed} 通过, {failed} 失败")
        print("="*70)
        
        if self.issues:
            print("\n  发现的问题:")
            for issue in self.issues:
                print(f"    - {issue}")
        
        if failed == 0 and not self.issues:
            print("\n🎉 极限压力测试通过！系统无懈可击！")
        
        return failed == 0 and not self.issues


def main():
    test = UltimateStressTest()
    test.run_all()


if __name__ == "__main__":
    main()
