#!/usr/bin/env python3
"""
知识存储后端
==========
支持多种存储方式
"""

import json
import pickle
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import time

logger = logging.getLogger("StorageBackend")


class StorageBackend(ABC):
    """存储后端抽象基类"""
    
    @abstractmethod
    def save(self, key: str, value: Any) -> bool:
        """保存数据"""
        pass
    
    @abstractmethod
    def load(self, key: str) -> Optional[Any]:
        """加载数据"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查是否存在"""
        pass
    
    @abstractmethod
    def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        """列出所有键"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """清空存储"""
        pass


class MemoryStorage(StorageBackend):
    """内存存储"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._access_time: Dict[str, float] = {}
    
    def save(self, key: str, value: Any) -> bool:
        with self._lock:
            if len(self._data) >= self.max_size and key not in self._data:
                # LRU 淘汰
                oldest = min(self._access_time.items(), key=lambda x: x[1])
                del self._data[oldest[0]]
                del self._access_time[oldest[0]]
            
            self._data[key] = value
            self._access_time[key] = time.time()
            return True
    
    def load(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._data:
                self._access_time[key] = time.time()
                return self._data[key]
            return None
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                del self._access_time[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        return key in self._data
    
    def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        with self._lock:
            keys = list(self._data.keys())
            if pattern:
                import fnmatch
                keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
            return keys
    
    def clear(self) -> bool:
        with self._lock:
            self._data.clear()
            self._access_time.clear()
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_items": len(self._data),
                "max_size": self.max_size,
                "usage_percent": len(self._data) / self.max_size * 100
            }


class FileStorage(StorageBackend):
    """文件存储"""
    
    def __init__(
        self,
        storage_dir: str = "/data/user/work/storage",
        format: str = "json"  # json, pickle
    ):
        self.storage_dir = Path(storage_dir)
        self.format = format
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
    
    def _get_path(self, key: str) -> Path:
        """获取文件路径"""
        # 安全处理key
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.storage_dir / f"{safe_key}.{self.format}"
    
    def save(self, key: str, value: Any) -> bool:
        with self._lock:
            try:
                path = self._get_path(key)
                
                if self.format == "json":
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(value, f, ensure_ascii=False, indent=2)
                else:  # pickle
                    with open(path, 'wb') as f:
                        pickle.dump(value, f)
                
                return True
            except Exception as e:
                logger.error(f"保存失败 [{key}]: {e}")
                return False
    
    def load(self, key: str) -> Optional[Any]:
        with self._lock:
            try:
                path = self._get_path(key)
                
                if not path.exists():
                    return None
                
                if self.format == "json":
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:  # pickle
                    with open(path, 'rb') as f:
                        return pickle.load(f)
            except Exception as e:
                logger.error(f"加载失败 [{key}]: {e}")
                return None
    
    def delete(self, key: str) -> bool:
        with self._lock:
            try:
                path = self._get_path(key)
                if path.exists():
                    path.unlink()
                    return True
                return False
            except Exception as e:
                logger.error(f"删除失败 [{key}]: {e}")
                return False
    
    def exists(self, key: str) -> bool:
        return self._get_path(key).exists()
    
    def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        keys = []
        for path in self.storage_dir.glob(f"*.{self.format}"):
            key = path.stem
            if pattern:
                import fnmatch
                if fnmatch.fnmatch(key, pattern):
                    keys.append(key)
            else:
                keys.append(key)
        return keys
    
    def clear(self) -> bool:
        with self._lock:
            try:
                for path in self.storage_dir.glob(f"*.{self.format}"):
                    path.unlink()
                return True
            except Exception as e:
                logger.error(f"清空失败: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        files = list(self.storage_dir.glob(f"*.{self.format}"))
        total_size = sum(f.stat().st_size for f in files)
        
        return {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "storage_dir": str(self.storage_dir),
            "format": self.format
        }


class SQLiteStorage(StorageBackend):
    """SQLite存储"""
    
    def __init__(self, db_path: str = "/data/user/work/storage.db"):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS storage (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def save(self, key: str, value: Any) -> bool:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    value_str = json.dumps(value, ensure_ascii=False)
                    conn.execute("""
                        INSERT OR REPLACE INTO storage (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (key, value_str))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"保存失败 [{key}]: {e}")
                return False
    
    def load(self, key: str) -> Optional[Any]:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    row = conn.execute(
                        "SELECT value FROM storage WHERE key = ?", (key,)
                    ).fetchone()
                    
                    if row:
                        return json.loads(row["value"])
                    return None
            except Exception as e:
                logger.error(f"加载失败 [{key}]: {e}")
                return None
    
    def delete(self, key: str) -> bool:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM storage WHERE key = ?", (key,))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"删除失败 [{key}]: {e}")
                return False
    
    def exists(self, key: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM storage WHERE key = ?", (key,)
                ).fetchone()
                return row is not None
    
    def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        with self._lock:
            with self._get_connection() as conn:
                if pattern:
                    # SQLite LIKE 模式
                    sql_pattern = pattern.replace("*", "%").replace("?", "_")
                    rows = conn.execute(
                        "SELECT key FROM storage WHERE key LIKE ?", (sql_pattern,)
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT key FROM storage").fetchall()
                
                return [row["key"] for row in rows]
    
    def clear(self) -> bool:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM storage")
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"清空失败: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            with self._get_connection() as conn:
                count = conn.execute("SELECT COUNT(*) as count FROM storage").fetchone()["count"]
                
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                return {
                    "total_records": count,
                    "db_size_bytes": db_size,
                    "db_path": str(self.db_path)
                }


class HybridStorage(StorageBackend):
    """
    混合存储
    
    结合内存缓存和持久化存储
    """
    
    def __init__(
        self,
        persistent_storage: StorageBackend,
        cache_size: int = 1000
    ):
        self.persistent = persistent_storage
        self.cache = MemoryStorage(max_size=cache_size)
        self._lock = threading.RLock()
    
    def save(self, key: str, value: Any) -> bool:
        with self._lock:
            # 先保存到持久化存储
            if self.persistent.save(key, value):
                # 再更新缓存
                self.cache.save(key, value)
                return True
            return False
    
    def load(self, key: str) -> Optional[Any]:
        with self._lock:
            # 先查缓存
            value = self.cache.load(key)
            if value is not None:
                return value
            
            # 缓存未命中，从持久化存储加载
            value = self.persistent.load(key)
            if value is not None:
                # 更新缓存
                self.cache.save(key, value)
            
            return value
    
    def delete(self, key: str) -> bool:
        with self._lock:
            self.cache.delete(key)
            return self.persistent.delete(key)
    
    def exists(self, key: str) -> bool:
        return self.cache.exists(key) or self.persistent.exists(key)
    
    def list_keys(self, pattern: Optional[str] = None) -> List[str]:
        return self.persistent.list_keys(pattern)
    
    def clear(self) -> bool:
        with self._lock:
            self.cache.clear()
            return self.persistent.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "cache": self.cache.get_stats(),
            "persistent": self.persistent.get_stats() if hasattr(self.persistent, 'get_stats') else {}
        }
