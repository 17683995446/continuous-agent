#!/usr/bin/env python3
"""
极简全能持续运行Agent - 主入口
============================

使用方法：
    python -m continuous_agent run                    # 启动Agent
    python -m continuous_agent run --task "实现用户登录功能"  # 添加任务并启动
    python -m continuous_agent status                 # 查看状态
    python -m continuous_agent stop                   # 停止Agent
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from .core.engine import ContinuousAgent, TaskType, TaskPriority
from .core.executor import CodeExecutor
from .knowledge.graph import KnowledgeGraph
from .optimizer.learner import Optimizer
from .keeper.alive import KeepAlive, HealthStatus, HealthCheck

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("main")


def create_agent(
    workspace: str = "/data/user/work",
    knowledge_path: Optional[str] = None,
    enable_monitoring: bool = True
) -> ContinuousAgent:
    """
    创建配置好的Agent实例
    """
    # 确保工作目录存在
    os.makedirs(workspace, exist_ok=True)
    
    # 配置日志文件（使用workspace路径而非硬编码）
    file_handler = logging.FileHandler(
        os.path.join(workspace, "agent.log"), encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logging.getLogger().addHandler(file_handler)
    
    # 初始化知识图谱
    knowledge_graph = KnowledgeGraph(
        storage_path=knowledge_path or os.path.join(workspace, "knowledge_graph")
    )
    
    # 初始化优化器
    optimizer = Optimizer(
        knowledge_graph=knowledge_graph,
        history_file=os.path.join(workspace, "optimization_history.json")
    )
    
    # 初始化执行器
    executor = CodeExecutor(workspace=workspace)
    
    # 创建Agent
    agent = ContinuousAgent(
        knowledge_graph=knowledge_graph,
        optimizer=optimizer,
        executor=executor,
        workspace=workspace,
        state_file=os.path.join(workspace, "agent_state.json")
    )
    
    logger.info("Agent实例创建完成")
    return agent


def create_keepalive(
    agent: ContinuousAgent,
    workspace: str = "/data/user/work"
) -> KeepAlive:
    """
    创建保活模块
    
    Args:
        agent: Agent实例
        workspace: 工作目录
        
    Returns:
        KeepAlive实例
    """
    keepalive = KeepAlive(
        agent=agent,
        state_dir=os.path.join(workspace, "keepalive"),
        max_restart_attempts=3
    )
    
    # 注册健康检查
    def check_agent_health() -> HealthCheck:
        status = agent.get_status()
        if status["running"] and not status["paused"]:
            return HealthCheck(
                name="agent",
                status=HealthStatus.HEALTHY,
                message="Agent运行正常"
            )
        else:
            return HealthCheck(
                name="agent",
                status=HealthStatus.DEGRADED,
                message="Agent未运行或已暂停"
            )
    
    def check_queue_health() -> HealthCheck:
        status = agent.get_status()
        queue_size = status["queued_tasks"]
        
        if queue_size > 100:
            return HealthCheck(
                name="queue",
                status=HealthStatus.WARNING,
                message=f"任务队列过长: {queue_size}"
            )
        else:
            return HealthCheck(
                name="queue",
                status=HealthStatus.HEALTHY,
                message=f"任务队列正常: {queue_size}"
            )
    
    keepalive.register_health_check("agent", check_agent_health)
    keepalive.register_health_check("queue", check_queue_health)
    
    return keepalive


def run_interactive(agent: ContinuousAgent):
    """交互式运行"""
    print("\n" + "="*60)
    print("  极简全能持续运行Agent")
    print("  输入 'help' 查看命令，'quit' 退出")
    print("="*60 + "\n")
    
    while True:
        try:
            cmd = input("agent> ").strip()
            
            if not cmd:
                continue
            
            if cmd.lower() in ['quit', 'exit', 'q']:
                print("正在停止Agent...")
                agent.stop()
                print("再见！")
                break
            
            elif cmd.lower() == 'help':
                print("""
可用命令：
  help                    显示帮助
  status                  查看Agent状态
  add <任务描述>          添加任务
  add type=<类型> <描述>  添加指定类型任务
  list                    列出任务队列
  pause                   暂停执行
  resume                  恢复执行
  stats                   查看统计信息
  knowledge               查看知识图谱统计
  optimize                执行优化分析
  quit                    退出程序

任务类型：
  implement, refactor, analyze, fix_bug, add_feature, optimize, test
""")
            
            elif cmd.lower() == 'status':
                status = agent.get_status()
                print(f"""
Agent状态：
  运行中: {status['running']}
  已暂停: {status['paused']}
  活动任务: {status['active_tasks']}
  队列任务: {status['queued_tasks']}
  已完成任务: {status['completed_tasks']}
""")
            
            elif cmd.lower().startswith('add '):
                parts = cmd[4:].strip()
                
                # 解析任务类型
                task_type = TaskType.IMPLEMENT
                if parts.startswith('type='):
                    type_end = parts.find(' ')
                    if type_end > 0:
                        type_str = parts[5:type_end]
                        try:
                            task_type = TaskType(type_str)
                            parts = parts[type_end+1:]
                        except ValueError:
                            print(f"未知的任务类型: {type_str}")
                            continue
                
                task_id = agent.add_task(
                    description=parts,
                    task_type=task_type
                )
                print(f"已添加任务: {task_id}")
            
            elif cmd.lower() == 'list':
                print("\n活动任务:")
                for task_id, task in agent.active_tasks.items():
                    print(f"  [{task_id}] {task.description[:50]}... ({task.status.value})")
            
            elif cmd.lower() == 'pause':
                agent.pause()
                print("Agent已暂停")
            
            elif cmd.lower() == 'resume':
                agent.resume()
                print("Agent已恢复")
            
            elif cmd.lower() == 'stats':
                status = agent.get_status()
                stats = status['stats']
                print(f"""
统计信息：
  已完成任务: {stats['tasks_completed']}
  失败任务: {stats['tasks_failed']}
  总运行时间: {stats['total_runtime']:.1f}s
  优化次数: {stats['optimizations_applied']}
  知识条目: {stats['knowledge_entries_added']}
""")
            
            elif cmd.lower() == 'knowledge':
                if agent.knowledge_graph:
                    kg_stats = agent.knowledge_graph.get_stats()
                    print(f"""
知识图谱：
  总条目: {kg_stats['total_entries']}
  总关系: {kg_stats['total_relations']}
  查询次数: {kg_stats['queries']}
""")
                else:
                    print("知识图谱未初始化")
            
            elif cmd.lower() == 'optimize':
                if agent.optimizer:
                    result = agent.optimizer.analyze_and_optimize()
                    print(f"""
优化分析：
  改进项: {len(result['improvements'])}
""")
                    for imp in result['improvements']:
                        print(f"  - {imp.get('description', '')}")
                else:
                    print("优化器未初始化")
            
            else:
                # 作为任务添加
                task_id = agent.add_task(description=cmd)
                print(f"已添加任务: {task_id}")
        
        except KeyboardInterrupt:
            print("\n使用 'quit' 命令退出")
        
        except Exception as e:
            print(f"错误: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="极简全能持续运行Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s run                           # 启动Agent
  %(prog)s run --task "实现用户登录"      # 添加任务并启动
  %(prog)s run --daemon                  # 后台运行
  %(prog)s status                        # 查看状态
"""
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # run 命令
    run_parser = subparsers.add_parser("run", help="启动Agent")
    run_parser.add_argument(
        "--workspace", "-w",
        default="/data/user/work",
        help="工作目录"
    )
    run_parser.add_argument(
        "--task", "-t",
        help="初始任务"
    )
    run_parser.add_argument(
        "--type",
        default="implement",
        choices=["implement", "refactor", "analyze", "fix_bug", "add_feature", "optimize", "test"],
        help="任务类型"
    )
    run_parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="后台运行"
    )
    run_parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="交互模式"
    )
    run_parser.add_argument(
        "--no-keepalive",
        action="store_true",
        help="禁用保活模块"
    )
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="查看状态")
    status_parser.add_argument(
        "--workspace", "-w",
        default="/data/user/work",
        help="工作目录"
    )
    
    # stop 命令
    stop_parser = subparsers.add_parser("stop", help="停止Agent")
    stop_parser.add_argument(
        "--workspace", "-w",
        default="/data/user/work",
        help="工作目录"
    )
    
    # add 命令
    add_parser = subparsers.add_parser("add", help="添加任务")
    add_parser.add_argument("description", help="任务描述")
    add_parser.add_argument(
        "--type",
        default="implement",
        help="任务类型"
    )
    add_parser.add_argument(
        "--priority",
        type=int,
        default=2,
        help="优先级 (0-3)"
    )
    
    args = parser.parse_args()
    
    if args.command == "run":
        # 创建Agent
        agent = create_agent(workspace=args.workspace)
        
        # 添加初始任务
        if args.task:
            task_type = TaskType(args.type)
            agent.add_task(
                description=args.task,
                task_type=task_type
            )
            logger.info(f"添加初始任务: {args.task}")
        
        if args.daemon:
            # 后台运行模式
            keepalive = create_keepalive(agent, args.workspace)
            logger.info("启动后台运行模式...")
            keepalive.run_forever()
        
        elif args.interactive:
            # 交互模式
            agent.start()
            run_interactive(agent)
        
        else:
            # 前台运行
            if not args.no_keepalive:
                keepalive = create_keepalive(agent, args.workspace)
                keepalive.run_forever()
            else:
                agent.start()
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    agent.stop()
    
    elif args.command == "status":
        state_file = Path(args.workspace) / "agent_state.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                state = json.load(f)
            print(json.dumps(state, indent=2, ensure_ascii=False))
        else:
            print("Agent未运行或状态文件不存在")
    
    elif args.command == "stop":
        # 发送停止信号
        pid_file = Path(args.workspace) / "agent.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 15)  # SIGTERM
            print(f"已发送停止信号到进程 {pid}")
        else:
            print("未找到运行中的Agent")
    
    elif args.command == "add":
        # 添加任务到队列（需要Agent运行中）
        print("此功能需要Agent运行中，请使用交互模式添加任务")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
