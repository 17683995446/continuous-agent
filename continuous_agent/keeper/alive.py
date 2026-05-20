#!/usr/bin/env python3
"""
保活模块核心实现
==============
负责崩溃恢复、健康检查和持续运行
"""

import json
import os
import signal
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import logging
import subprocess

logger = logging.getLogger("KeepAlive")


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """健康检查记录"""
    name: str
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrashRecord:
    """崩溃记录"""
    crash_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    traceback: str
    recovery_action: str
    recovered: bool = False


class Watchdog:
    """
    看门狗
    
    监控系统是否响应，超时则触发恢复
    """
    
    def __init__(
        self,
        timeout_seconds: int = 60,
        check_interval: int = 10
    ):
        self.timeout = timeout_seconds
        self.check_interval = check_interval
        
        self._last_heartbeat = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_timeout: Optional[Callable] = None
        self._lock = threading.Lock()
    
    def start(self):
        """启动看门狗"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"看门狗已启动，超时时间: {self.timeout}s")
    
    def stop(self):
        """停止看门狗"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("看门狗已停止")
    
    def heartbeat(self):
        """发送心跳"""
        with self._lock:
            self._last_heartbeat = time.time()
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            time.sleep(self.check_interval)
            
            with self._lock:
                elapsed = time.time() - self._last_heartbeat
            
            if elapsed > self.timeout:
                logger.error(f"看门狗超时! 已经过 {elapsed:.1f}s 没有心跳")
                
                if self._on_timeout:
                    try:
                        self._on_timeout()
                    except Exception as e:
                        logger.error(f"超时回调失败: {e}")
    
    def set_timeout_callback(self, callback: Callable):
        """设置超时回调"""
        self._on_timeout = callback
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        with self._lock:
            elapsed = time.time() - self._last_heartbeat
        
        return {
            "running": self._running,
            "last_heartbeat": self._last_heartbeat,
            "seconds_since_heartbeat": elapsed,
            "timeout": self.timeout,
            "status": "ok" if elapsed < self.timeout else "timeout"
        }


class KeepAlive:
    """
    保活模块
    
    功能：
    - 崩溃自动恢复
    - 健康检查
    - 状态持久化
    - 优雅关闭
    """
    
    def __init__(
        self,
        agent: Optional[Any] = None,
        state_dir: str = "/data/user/work/keepalive",
        max_restart_attempts: int = 3,
        restart_cooldown: int = 30
    ):
        self.agent = agent
        self.state_dir = Path(state_dir)
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown
        
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # 看门狗
        self.watchdog = Watchdog(
            timeout_seconds=120,
            check_interval=15
        )
        
        # 健康检查器
        self._health_checks: Dict[str, Callable[[], HealthCheck]] = {}
        self._last_health_status: Dict[str, HealthCheck] = {}
        
        # 崩溃记录
        self._crash_records: List[CrashRecord] = []
        self._restart_attempts = 0
        self._last_restart_time: Optional[datetime] = None
        
        # 运行状态
        self._running = False
        self._shutdown_requested = False
        
        # 回调
        self._on_crash: Optional[Callable] = None
        self._on_recovery: Optional[Callable] = None
        
        # 加载状态
        self._load_state()
        
        # 注册信号处理
        self._setup_signal_handlers()
        
        logger.info("保活模块初始化完成")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def handle_shutdown(signum, frame):
            logger.info(f"收到信号 {signum}，准备优雅关闭...")
            self._shutdown_requested = True
            self.stop()
            sys.exit(0)
        
        # 注册信号
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
        
        # Windows 不支持 SIGUSR1
        if hasattr(signal, 'SIGUSR1'):
            signal.signal(signal.SIGUSR1, handle_shutdown)
    
    def _load_state(self):
        """加载状态"""
        state_file = self.state_dir / "state.json"
        
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    self._restart_attempts = data.get("restart_attempts", 0)
                    
                    for crash_data in data.get("crashes", []):
                        self._crash_records.append(CrashRecord(
                            crash_id=crash_data["crash_id"],
                            timestamp=datetime.fromisoformat(crash_data["timestamp"]),
                            error_type=crash_data["error_type"],
                            error_message=crash_data["error_message"],
                            traceback=crash_data["traceback"],
                            recovery_action=crash_data["recovery_action"],
                            recovered=crash_data.get("recovered", False)
                        ))
                    
                    logger.info(f"加载状态: {len(self._crash_records)} 条崩溃记录")
            except Exception as e:
                logger.warning(f"加载状态失败: {e}")
    
    def _save_state(self):
        """保存状态"""
        state_file = self.state_dir / "state.json"
        
        try:
            data = {
                "restart_attempts": self._restart_attempts,
                "last_restart": self._last_restart_time.isoformat() if self._last_restart_time else None,
                "crashes": [
                    {
                        "crash_id": c.crash_id,
                        "timestamp": c.timestamp.isoformat(),
                        "error_type": c.error_type,
                        "error_message": c.error_message,
                        "traceback": c.traceback,
                        "recovery_action": c.recovery_action,
                        "recovered": c.recovered
                    }
                    for c in self._crash_records[-100:]  # 只保留最近100条
                ]
            }
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")
    
    def register_health_check(
        self,
        name: str,
        check_func: Callable[[], HealthCheck]
    ):
        """
        注册健康检查
        
        Args:
            name: 检查名称
            check_func: 检查函数
        """
        self._health_checks[name] = check_func
        logger.info(f"注册健康检查: {name}")
    
    def run_health_checks(self) -> Dict[str, HealthCheck]:
        """运行所有健康检查"""
        results = {}
        
        for name, check_func in self._health_checks.items():
            try:
                result = check_func()
                results[name] = result
                self._last_health_status[name] = result
            except Exception as e:
                result = HealthCheck(
                    name=name,
                    status=HealthStatus.CRITICAL,
                    message=f"健康检查失败: {str(e)}"
                )
                results[name] = result
                self._last_health_status[name] = result
        
        return results
    
    def get_overall_health(self) -> HealthStatus:
        """获取整体健康状态"""
        if not self._last_health_status:
            return HealthStatus.UNKNOWN
        
        statuses = [h.status for h in self._last_health_status.values()]
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def start(self):
        """启动保活"""
        if self._running:
            logger.warning("保活模块已在运行")
            return
        
        self._running = True
        self._shutdown_requested = False
        
        # 启动看门狗
        self.watchdog.set_timeout_callback(self._handle_timeout)
        self.watchdog.start()
        
        # 启动Agent
        if self.agent:
            try:
                self.agent.start()
                logger.info("Agent已启动")
            except Exception as e:
                logger.error(f"Agent启动失败: {e}")
                self._record_crash(e, "启动失败")
        
        logger.info("🛡️ 保活模块已启动")
    
    def stop(self):
        """停止保活"""
        logger.info("正在停止保活模块...")
        
        self._running = False
        
        # 停止看门狗
        self.watchdog.stop()
        
        # 停止Agent
        if self.agent:
            try:
                self.agent.stop()
            except Exception as e:
                logger.error(f"Agent停止失败: {e}")
        
        # 保存状态
        self._save_state()
        
        logger.info("保活模块已停止")
    
    def run_forever(self):
        """
        永久运行
        
        包含崩溃恢复逻辑
        """
        logger.info("开始永久运行模式...")
        
        while not self._shutdown_requested:
            try:
                self.start()
                
                # 主循环
                while self._running and not self._shutdown_requested:
                    # 发送心跳
                    self.watchdog.heartbeat()
                    
                    # 运行健康检查
                    health = self.run_health_checks()
                    overall = self.get_overall_health()
                    
                    if overall != HealthStatus.HEALTHY:
                        logger.warning(f"健康状态: {overall.value}")
                    
                    # 保存状态
                    self._save_state()
                    
                    # 等待
                    time.sleep(30)
                
            except KeyboardInterrupt:
                logger.info("收到中断信号")
                self._shutdown_requested = True
                
            except Exception as e:
                logger.error(f"运行时错误: {e}\n{traceback.format_exc()}")
                
                # 记录崩溃
                self._record_crash(e, "运行时错误")
                
                # 尝试恢复
                if self._should_attempt_recovery():
                    self._attempt_recovery()
                else:
                    logger.critical("恢复尝试次数已达上限，停止运行")
                    break
        
        self.stop()
    
    def _handle_timeout(self):
        """处理超时"""
        logger.error("检测到超时，尝试恢复...")
        
        error = TimeoutError("看门狗超时")
        self._record_crash(error, "超时")
        
        if self._should_attempt_recovery():
            self._attempt_recovery()
    
    def _record_crash(self, error: Exception, context: str):
        """记录崩溃"""
        crash_id = f"crash_{int(time.time() * 1000)}"
        
        record = CrashRecord(
            crash_id=crash_id,
            timestamp=datetime.now(),
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            recovery_action="pending"
        )
        
        self._crash_records.append(record)
        
        # 回调
        if self._on_crash:
            self._on_crash(record)
        
        logger.error(f"记录崩溃 [{crash_id}]: {record.error_message}")
    
    def _should_attempt_recovery(self) -> bool:
        """是否应该尝试恢复"""
        # 检查重启次数
        if self._restart_attempts >= self.max_restart_attempts:
            return False
        
        # 检查冷却时间
        if self._last_restart_time:
            elapsed = datetime.now() - self._last_restart_time
            if elapsed < timedelta(seconds=self.restart_cooldown):
                return False
        
        return True
    
    def _attempt_recovery(self):
        """尝试恢复"""
        self._restart_attempts += 1
        self._last_restart_time = datetime.now()
        
        logger.info(f"尝试恢复 ({self._restart_attempts}/{self.max_restart_attempts})...")
        
        try:
            # 停止当前Agent
            if self.agent:
                try:
                    self.agent.stop()
                except Exception:
                    pass
            
            # 等待冷却
            time.sleep(5)
            
            # 重新启动
            self._running = False
            self.start()
            
            # 更新崩溃记录
            if self._crash_records:
                self._crash_records[-1].recovered = True
                self._crash_records[-1].recovery_action = "重启"
            
            # 回调
            if self._on_recovery:
                self._on_recovery()
            
            logger.info("恢复成功")
            
            # 重置重启计数（如果运行稳定）
            # 保存Timer引用防止被GC回收
            self._reset_timer = threading.Timer(
                300,  # 5分钟后重置
                self._reset_restart_attempts
            )
            self._reset_timer.start()
            
        except Exception as e:
            logger.error(f"恢复失败: {e}")
    
    def _reset_restart_attempts(self):
        """重置重启计数"""
        if self._running:
            self._restart_attempts = 0
            logger.info("运行稳定，重置重启计数")
    
    def set_callbacks(
        self,
        on_crash: Optional[Callable] = None,
        on_recovery: Optional[Callable] = None
    ):
        """设置回调函数"""
        self._on_crash = on_crash
        self._on_recovery = on_recovery
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "running": self._running,
            "shutdown_requested": self._shutdown_requested,
            "overall_health": self.get_overall_health().value,
            "restart_attempts": self._restart_attempts,
            "crash_count": len(self._crash_records),
            "watchdog": self.watchdog.get_status(),
            "health_checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message
                }
                for name, check in self._last_health_status.items()
            }
        }
    
    def get_crash_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取崩溃历史"""
        return [
            {
                "crash_id": c.crash_id,
                "timestamp": c.timestamp.isoformat(),
                "error_type": c.error_type,
                "error_message": c.error_message,
                "recovered": c.recovered
            }
            for c in self._crash_records[-limit:]
        ]
    
    def clear_crash_history(self):
        """清空崩溃历史"""
        self._crash_records.clear()
        self._restart_attempts = 0
        self._save_state()
        logger.info("崩溃历史已清空")
