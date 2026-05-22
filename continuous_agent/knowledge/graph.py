#!/usr/bin/env python3
"""
知识图谱核心实现
===============
负责经验的存储、关联和检索
"""

import json
import time
import hashlib
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import logging
import re

logger = logging.getLogger("KnowledgeGraph")


class ExperienceType(Enum):
    """经验类型"""
    SOLUTION = "solution"           # 解决方案
    PATTERN = "pattern"             # 代码模式
    ERROR_FIX = "error_fix"         # 错误修复
    BEST_PRACTICE = "best_practice" # 最佳实践
    ANTI_PATTERN = "anti_pattern"   # 反模式（避免的做法）
    LEARNING = "learning"           # 学习心得
    CONTEXT = "context"             # 上下文信息


@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    content: str
    experience_type: ExperienceType
    task_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    related_entries: List[str] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "experience_type": self.experience_type.value,
            "task_type": self.task_type,
            "tags": self.tags,
            "context": self.context,
            "related_entries": self.related_entries,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeEntry':
        """从字典创建"""
        return cls(
            id=data["id"],
            content=data["content"],
            experience_type=ExperienceType(data["experience_type"]),
            task_type=data.get("task_type"),
            tags=data.get("tags", []),
            context=data.get("context", {}),
            related_entries=data.get("related_entries", []),
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.5


@dataclass
class KnowledgeRelation:
    """知识关系"""
    source_id: str
    target_id: str
    relation_type: str  # "relates_to", "solves", "causes", "follows"
    strength: float = 1.0  # 关系强度 0-1
    created_at: datetime = field(default_factory=datetime.now)


class KnowledgeGraph:
    """
    知识图谱
    
    功能：
    - 存储和检索经验
    - 建立知识关联
    - 智能推荐相关经验
    - 支持向量化检索
    """
    
    def __init__(
        self,
        storage_path: str = "/data/user/work/knowledge_graph",
        max_entries: int = 10000
    ):
        self.storage_path = Path(storage_path)
        self.max_entries = max_entries
        self._dirty = False  # 延迟保存标志
        self._auto_flush_threshold = 10  # Bug#79: 自动flush阈值
        self._auto_flush_count = 0
        
        # 存储结构
        self.entries: Dict[str, KnowledgeEntry] = {}
        self.relations: List[KnowledgeRelation] = []
        self.tag_index: Dict[str, Set[str]] = {}  # tag -> entry_ids
        self.task_type_index: Dict[str, Set[str]] = {}  # task_type -> entry_ids
        
        # 锁
        self._lock = threading.RLock()
        
        # 统计
        self._stats = {
            "total_entries": 0,
            "total_relations": 0,
            "queries": 0,
            "cache_hits": 0
        }
        
        # 加载已有数据
        self._load()
        
        logger.info(f"知识图谱初始化完成，当前条目数: {len(self.entries)}")
    
    def _load(self):
        """加载存储的数据"""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        entries_file = self.storage_path / "entries.json"
        relations_file = self.storage_path / "relations.json"
        
        if entries_file.exists():
            try:
                with open(entries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for entry_data in data:
                        entry = KnowledgeEntry.from_dict(entry_data)
                        self.entries[entry.id] = entry
                        self._update_indices(entry)
                logger.info(f"加载 {len(self.entries)} 条知识条目")
            except Exception as e:
                logger.error(f"加载知识条目失败: {e}")
        else:
            logger.debug("知识条目文件不存在，使用空图谱")
        
        if relations_file.exists():
            try:
                with open(relations_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for rel_data in data:
                        self.relations.append(KnowledgeRelation(
                            source_id=rel_data["source_id"],
                            target_id=rel_data["target_id"],
                            relation_type=rel_data["relation_type"],
                            strength=rel_data.get("strength", 1.0)
                        ))
                logger.info(f"加载 {len(self.relations)} 条关系")
            except Exception as e:
                logger.error(f"加载关系失败: {e}")
    
    def _save(self):
        """保存数据"""
        try:
            entries_file = self.storage_path / "entries.json"
            relations_file = self.storage_path / "relations.json"
            
            with open(entries_file, 'w', encoding='utf-8') as f:
                json.dump([e.to_dict() for e in self.entries.values()], f, ensure_ascii=False, indent=2)
            
            with open(relations_file, 'w', encoding='utf-8') as f:
                json.dump([
                    {
                        "source_id": r.source_id,
                        "target_id": r.target_id,
                        "relation_type": r.relation_type,
                        "strength": r.strength
                    }
                    for r in self.relations
                ], f, ensure_ascii=False, indent=2)
            
            logger.debug(f"知识图谱数据已保存 ({len(self.entries)} 条目)")
        except Exception as e:
            logger.error(f"保存知识图谱失败: {e}")
    
    def _update_indices(self, entry: KnowledgeEntry):
        """更新索引"""
        # 更新标签索引
        for tag in entry.tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = set()
            self.tag_index[tag].add(entry.id)
        
        # 更新任务类型索引
        if entry.task_type:
            if entry.task_type not in self.task_type_index:
                self.task_type_index[entry.task_type] = set()
            self.task_type_index[entry.task_type].add(entry.id)
    
    def _remove_from_indices(self, entry: KnowledgeEntry):
        """从索引中移除"""
        for tag in entry.tags:
            if tag in self.tag_index:
                self.tag_index[tag].discard(entry.id)
        
        if entry.task_type and entry.task_type in self.task_type_index:
            self.task_type_index[entry.task_type].discard(entry.id)
    
    def add_experience(
        self,
        content: str,
        task_type: str,
        experience_type: ExperienceType = ExperienceType.SOLUTION,
        tags: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        related_to: Optional[List[str]] = None
    ) -> str:
        """
        添加经验
        
        Args:
            content: 经验内容
            task_type: 任务类型
            experience_type: 经验类型
            tags: 标签
            context: 上下文
            related_to: 相关条目ID列表
            
        Returns:
            条目ID
        """
        with self._lock:
            # 参数校验：空内容不允许添加
            if not content or not content.strip():
                logger.warning("拒绝添加空内容经验")
                return ""
            
            # 生成ID
            entry_id = self._generate_id(content)
            
            # 检查是否已存在相似条目（使用高阈值避免误判）
            # Bug#75修复: 去重阈值从0.9提高到0.99，避免只有末尾数字不同的内容被误判为重复
            similar = self._find_similar(content, threshold=0.99)
            if similar:
                # 更新已有条目
                existing = self.entries[similar[0]]
                existing.success_count += 1
                existing.updated_at = datetime.now()
                logger.debug(f"更新已有经验: {entry_id}")
                return existing.id
            
            # 创建新条目
            entry = KnowledgeEntry(
                id=entry_id,
                content=content,
                experience_type=experience_type,
                task_type=task_type,
                tags=tags or [],
                context=context or {},
                success_count=1
            )
            
            # 添加到存储
            self.entries[entry_id] = entry
            self._update_indices(entry)
            
            # 添加关系
            if related_to:
                for related_id in related_to:
                    if related_id in self.entries:
                        self._add_relation(entry_id, related_id, "relates_to")
            
            # 自动关联相似条目
            similar_entries = self._find_similar(content, threshold=0.6, limit=3)
            for similar_id in similar_entries:
                if similar_id != entry_id:
                    self._add_relation(entry_id, similar_id, "relates_to", strength=0.5)
            
            # 更新统计
            self._stats["total_entries"] = len(self.entries)
            
            # 检查容量
            if len(self.entries) > self.max_entries:
                self._prune_old_entries()
            
            # Bug#79修复: 自动flush机制，防止崩溃数据丢失
            self._dirty = True
            self._auto_flush_count += 1
            if self._auto_flush_count >= self._auto_flush_threshold:
                self.flush()
                self._auto_flush_count = 0
            
            logger.info(f"添加新经验 [{entry_id}]: {content[:50]}...")
            return entry_id
    
    def _generate_id(self, content: str) -> str:
        """生成条目ID"""
        hash_input = f"{content}{time.time()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def _find_similar(
        self,
        content: str,
        threshold: float = 0.8,
        limit: int = 5
    ) -> List[str]:
        """
        查找相似条目
        
        使用简单的文本相似度（实际应用中可替换为向量相似度）
        """
        similar = []
        content_words = set(self._tokenize(content))
        
        for entry_id, entry in self.entries.items():
            entry_words = set(self._tokenize(entry.content))
            
            # Jaccard 相似度
            intersection = len(content_words & entry_words)
            union = len(content_words | entry_words)
            similarity = intersection / union if union > 0 else 0
            
            if similarity >= threshold:
                similar.append((entry_id, similarity))
        
        # 按相似度排序
        similar.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in similar[:limit]]
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        # 简单分词（可替换为更复杂的分词器）
        text = text.lower()
        words = re.findall(r'\b\w+\b', text)
        # Bug#75修复: 只过滤单个字母，保留数字（数字对区分内容很重要）
        return [w for w in words if not (len(w) == 1 and w.isalpha())]
    
    def _add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        strength: float = 1.0
    ):
        """添加关系"""
        # 检查是否已存在
        for rel in self.relations:
            if (rel.source_id == source_id and 
                rel.target_id == target_id and 
                rel.relation_type == relation_type):
                rel.strength = max(rel.strength, strength)
                return
        
        relation = KnowledgeRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=strength
        )
        self.relations.append(relation)
        
        # 更新条目的关联列表
        if source_id in self.entries:
            if target_id not in self.entries[source_id].related_entries:
                self.entries[source_id].related_entries.append(target_id)
        
        self._stats["total_relations"] = len(self.relations)
    
    def _prune_old_entries(self):
        """清理旧条目"""
        # 按成功率和最后更新时间排序
        entries_list = list(self.entries.values())
        entries_list.sort(key=lambda e: (e.success_rate, e.updated_at))
        
        # 移除最不成功的条目
        to_remove = entries_list[:len(entries_list) - self.max_entries]
        for entry in to_remove:
            del self.entries[entry.id]
            self._remove_from_indices(entry)
        
        logger.info(f"清理了 {len(to_remove)} 条旧经验")
    
    def query_relevant(
        self,
        query: str,
        task_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        查询相关经验
        
        Args:
            query: 查询文本
            task_type: 任务类型过滤
            tags: 标签过滤
            limit: 返回数量限制
            
        Returns:
            相关经验列表
        """
        with self._lock:
            self._stats["queries"] += 1
            logger.debug(f"查询相关经验: query='{query[:30]}' limit={limit}")
            
            # 获取候选条目
            candidates = set(self.entries.keys())
            
            # 按任务类型过滤
            if task_type and task_type in self.task_type_index:
                candidates &= self.task_type_index[task_type]
            
            # 按标签过滤
            if tags:
                tag_candidates = set()
                for tag in tags:
                    if tag in self.tag_index:
                        tag_candidates |= self.tag_index[tag]
                candidates &= tag_candidates
            
            # 计算相关性得分
            query_words = set(self._tokenize(query))
            scored = []
            
            for entry_id in candidates:
                entry = self.entries[entry_id]
                entry_words = set(self._tokenize(entry.content))
                
                # 文本相似度
                intersection = len(query_words & entry_words)
                text_score = intersection / max(len(query_words), 1)
                
                # 综合得分（考虑成功率）
                total_score = text_score * 0.7 + entry.success_rate * 0.3
                
                scored.append((entry_id, total_score))
            
            # 排序
            scored.sort(key=lambda x: x[1], reverse=True)
            
            # 构建结果
            results = []
            for entry_id, score in scored[:limit]:
                entry = self.entries[entry_id]
                results.append({
                    "id": entry.id,
                    "content": entry.content,
                    "experience_type": entry.experience_type.value,
                    "task_type": entry.task_type,
                    "tags": entry.tags,
                    "context": entry.context,
                    "success_rate": entry.success_rate,
                    "relevance_score": score
                })
            
            if results:
                self._stats["cache_hits"] += 1
            
            return results
    
    def get_entry(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """获取条目"""
        return self.entries.get(entry_id)
    
    def get_related(self, entry_id: str, depth: int = 1) -> List[KnowledgeEntry]:
        """
        获取相关条目
        
        Args:
            entry_id: 条目ID
            depth: 关系深度
            
        Returns:
            相关条目列表
        """
        visited = set()
        result = []
        
        def _traverse(current_id: str, current_depth: int):
            if current_depth > depth or current_id in visited:
                return
            
            visited.add(current_id)
            
            # 查找相关条目
            for rel in self.relations:
                related_id = None
                if rel.source_id == current_id:
                    related_id = rel.target_id
                elif rel.target_id == current_id:
                    related_id = rel.source_id
                
                if related_id and related_id not in visited:
                    if related_id in self.entries:
                        result.append(self.entries[related_id])
                        _traverse(related_id, current_depth + 1)
        
        _traverse(entry_id, 1)
        return result
    
    def update_success(self, entry_id: str, success: bool):
        """更新条目成功率"""
        logger.debug(f"更新经验 [{entry_id}] success={success}")
        with self._lock:
            if entry_id in self.entries:
                entry = self.entries[entry_id]
                if success:
                    entry.success_count += 1
                else:
                    entry.fail_count += 1
                entry.updated_at = datetime.now()
                self._dirty = True
            else:
                logger.warning(f"尝试更新不存在的经验条目: {entry_id}")
    
    def flush(self):
        """将脏数据保存到磁盘"""
        if self._dirty:
            logger.debug("flush: 检测到脏数据，保存到磁盘")
            self._save()
            self._dirty = False
        else:
            logger.debug("flush: 无脏数据，跳过保存")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "entries_by_type": {
                exp_type.value: sum(
                    1 for e in self.entries.values() 
                    if e.experience_type == exp_type
                )
                for exp_type in ExperienceType
            },
            "entries_by_task_type": {
                task_type: len(ids)
                for task_type, ids in self.task_type_index.items()
            }
        }
    
    def export(self, format: str = "json") -> str:
        """导出知识图谱"""
        if format == "json":
            data = {
                "entries": [e.to_dict() for e in self.entries.values()],
                "relations": [
                    {
                        "source_id": r.source_id,
                        "target_id": r.target_id,
                        "relation_type": r.relation_type,
                        "strength": r.strength
                    }
                    for r in self.relations
                ],
                "stats": self.get_stats()
            }
            return json.dumps(data, ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
    
    def import_data(self, data: str, format: str = "json"):
        """导入知识图谱"""
        if format == "json":
            parsed = json.loads(data)
            
            for entry_data in parsed.get("entries", []):
                entry = KnowledgeEntry.from_dict(entry_data)
                self.entries[entry.id] = entry
                self._update_indices(entry)
            
            for rel_data in parsed.get("relations", []):
                self.relations.append(KnowledgeRelation(
                    source_id=rel_data["source_id"],
                    target_id=rel_data["target_id"],
                    relation_type=rel_data["relation_type"],
                    strength=rel_data.get("strength", 1.0)
                ))
            
            self._save()
            logger.info(f"导入 {len(self.entries)} 条条目和 {len(self.relations)} 条关系")
        else:
            raise ValueError(f"不支持的导入格式: {format}")
    
    def clear(self):
        """清空知识图谱"""
        with self._lock:
            self.entries.clear()
            self.relations.clear()
            self.tag_index.clear()
            self.task_type_index.clear()
            self._save()
            logger.info("知识图谱已清空")
