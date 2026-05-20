# 极简全能持续运行Agent

一个能够持续运行、自动优化、积累经验的智能代码工程Agent系统。

## 核心特性

### 🔄 持续运行
- 开机就不停运转，全程满负荷工作
- 崩溃自动恢复，看门狗监控
- 无空闲时刻，持续执行任务

### 🧠 知识积累
- 经验自动存入知识图谱
- 遇事先查图谱，做事更快更准
- 越运行知识越多，能力越强

### ⚡ 自动优化
- 边做边调整方法，越做越好
- 分析执行模式，识别优化机会
- 学习最佳实践，持续改进

## 系统架构

```
continuous_agent/
├── core/                    # 核心引擎
│   ├── engine.py           # Agent主引擎
│   ├── executor.py         # 代码执行器
│   └── scheduler.py        # 任务调度器
├── knowledge/              # 知识图谱
│   ├── graph.py           # 知识图谱核心
│   ├── storage.py         # 存储后端
│   └── retriever.py       # 知识检索
├── optimizer/              # 优化模块
│   ├── learner.py         # 自学习优化器
│   ├── analyzer.py        # 性能分析器
│   └── improver.py        # 方法改进器
├── keeper/                 # 保活模块
│   ├── alive.py           # 保活核心
│   └── monitor.py         # 系统监控
└── main.py                 # 主入口
```

## 快速开始

### 安装

```bash
# 克隆项目
cd /workspace/continuous_agent

# 安装依赖（可选）
pip install psutil --break-system-packages
```

### 启动Agent

```bash
# 交互模式启动
python -m continuous_agent run -i

# 后台运行
python -m continuous_agent run --daemon

# 添加任务并启动
python -m continuous_agent run --task "实现用户登录功能" --type implement
```

### 交互命令

```
agent> help                    # 查看帮助
agent> status                  # 查看状态
agent> add 实现数据导出功能     # 添加任务
agent> list                    # 列出任务
agent> stats                   # 查看统计
agent> knowledge               # 查看知识图谱
agent> optimize                # 执行优化分析
agent> quit                    # 退出
```

## 使用示例

### Python API

```python
from continuous_agent import ContinuousAgent, KnowledgeGraph, Optimizer
from continuous_agent.core.engine import TaskType, TaskPriority

# 创建Agent
agent = ContinuousAgent(
    workspace="/data/user/work",
    knowledge_graph=KnowledgeGraph("/data/user/work/kg")
)

# 启动
agent.start()

# 添加任务
task_id = agent.add_task(
    description="重构用户认证模块",
    task_type=TaskType.REFACTOR,
    priority=TaskPriority.HIGH
)

# 查看状态
status = agent.get_status()
print(f"活动任务: {status['active_tasks']}")

# 停止
agent.stop()
```

### 批量添加任务

```python
tasks = [
    {"description": "分析代码复杂度", "task_type": "analyze", "priority": 2},
    {"description": "修复登录bug", "task_type": "fix_bug", "priority": 0},
    {"description": "添加日志功能", "task_type": "add_feature", "priority": 1}
]

task_ids = agent.add_batch_tasks(tasks)
```

## 任务类型

| 类型 | 说明 |
|------|------|
| `implement` | 实现新需求 |
| `refactor` | 重构代码 |
| `analyze` | 分析代码 |
| `fix_bug` | 修复bug |
| `add_feature` | 新增功能 |
| `optimize` | 优化代码 |
| `test` | 测试代码 |
| `document` | 编写文档 |

## 知识图谱

### 添加经验

```python
# 手动添加经验
agent.knowledge_graph.add_experience(
    content="使用工厂模式解耦对象创建",
    task_type="refactor",
    experience_type="pattern",
    tags=["design-pattern", "factory"]
)
```

### 查询经验

```python
# 查询相关经验
results = agent.knowledge_graph.query_relevant(
    query="如何重构代码提高可维护性",
    task_type="refactor",
    limit=5
)

for result in results:
    print(f"经验: {result['content']}")
    print(f"成功率: {result['success_rate']}")
```

## 优化器

### 记录任务完成

```python
# 记录任务执行结果
agent.optimizer.record_task_completion(
    task_type="implement",
    success=True,
    execution_time=45.0,
    method_used="tdd"
)
```

### 获取推荐

```python
# 获取方法推荐
recommendation = agent.optimizer.get_recommendation("implement")
print(f"推荐方法: {recommendation['recommended_method']}")
print(f"预估时间: {recommendation['estimated_time']}s")
```

## 保活模块

```python
from continuous_agent.keeper.alive import KeepAlive

# 创建保活模块
keepalive = KeepAlive(
    agent=agent,
    max_restart_attempts=3
)

# 注册健康检查
def check_health():
    from continuous_agent.keeper.alive import HealthCheck, HealthStatus
    return HealthCheck(
        name="custom",
        status=HealthStatus.HEALTHY,
        message="自定义检查通过"
    )

keepalive.register_health_check("custom", check_health)

# 启动（崩溃自动恢复）
keepalive.run_forever()
```

## 运行测试

```bash
python -m continuous_agent.tests.test_integration
```

## 配置选项

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGENT_WORKSPACE` | 工作目录 | `/data/user/work` |
| `AGENT_LOG_LEVEL` | 日志级别 | `INFO` |
| `AGENT_MAX_TASKS` | 最大任务数 | `10000` |

### 调度策略

- `FIFO` - 先进先出
- `PRIORITY` - 优先级优先
- `SHORTEST_FIRST` - 最短任务优先
- `SMART` - 智能调度（默认）

## 运转流程

```
┌─────────────────────────────────────────────────────────────┐
│                    持续运行循环                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ 知识图谱 │───▶│ 执行任务 │───▶│ 总结经验 │              │
│  │ 调取经验 │    │ 完成工作 │    │ 存入图谱 │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│       ▲                                │                    │
│       │                                ▼                    │
│       │         ┌──────────┐    ┌──────────┐               │
│       │         │ 优化方法 │◀───│ 分析结果 │               │
│       │         │ 改进策略 │    │ 识别模式 │               │
│       │         └──────────┘    └──────────┘               │
│       │               │                                     │
│       └───────────────┴─────────────────────┘              │
│                   无限循环                                   │
└─────────────────────────────────────────────────────────────┘
```

## 核心逻辑

> **一直干活 → 越干越会干 → 把学会的全部存起来 → 下次直接调取使用**

1. **先查图谱** - 遇到任务先从知识图谱查找相关经验
2. **执行任务** - 使用最佳方法完成任务
3. **总结经验** - 分析执行过程，提取学习点
4. **存入图谱** - 将新经验归类存档
5. **优化方法** - 根据执行结果改进工作方式
6. **继续循环** - 无限重复以上步骤

## 许可证

MIT License
