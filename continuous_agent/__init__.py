#!/usr/bin/env python3
"""
极简全能持续运行Agent
====================
核心特性：
1. 持续做事 - 不间断完成代码工程任务
2. 自动优化 - 边做边改进方法
3. 知识积累 - 经验自动存入知识图谱

架构：
- 保活模块：一直在线，崩溃自动重启
- 执行模块：专心完成任务
- 优化模块：改进做事方法
- 图谱模块：存经验、查资料、快速调取
"""

__version__ = "1.0.0"
__author__ = "Continuous Agent Team"

from .core.engine import ContinuousAgent
from .knowledge.graph import KnowledgeGraph
from .optimizer.learner import Optimizer
from .keeper.alive import KeepAlive

__all__ = [
    "ContinuousAgent",
    "KnowledgeGraph", 
    "Optimizer",
    "KeepAlive"
]
