#!/usr/bin/env python3
"""
知识检索器
=========
负责智能检索和推荐相关知识
"""

import re
import math
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import json

logger = logging.getLogger("KnowledgeRetriever")


@dataclass
class SearchResult:
    """搜索结果"""
    entry_id: str
    content: str
    score: float
    highlights: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnowledgeRetriever:
    """
    知识检索器
    
    功能：
    - 文本检索（TF-IDF）
    - 语义检索（可扩展）
    - 混合检索
    - 智能推荐
    """
    
    def __init__(
        self,
        knowledge_graph: Optional[Any] = None,
        index_path: Optional[str] = None
    ):
        self.knowledge_graph = knowledge_graph
        self.index_path = Path(index_path) if index_path else None
        
        # 倒排索引
        self._inverted_index: Dict[str, List[Tuple[str, int]]] = {}  # term -> [(doc_id, freq)]
        self._doc_lengths: Dict[str, int] = {}  # doc_id -> length
        self._doc_count: int = 0
        
        # TF-IDF 缓存
        self._tfidf_cache: Dict[str, Dict[str, float]] = {}
        
        # 锁
        self._lock = threading.RLock()
        
        # 统计
        self._stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "avg_query_time": 0
        }
    
    def build_index(self, entries: Dict[str, Any]):
        """
        构建索引
        
        Args:
            entries: 知识条目字典 {id: KnowledgeEntry}
        """
        with self._lock:
            logger.info(f"开始构建索引，共 {len(entries)} 条目...")
            
            self._inverted_index.clear()
            self._doc_lengths.clear()
            self._doc_count = len(entries)
            
            for entry_id, entry in entries.items():
                content = entry.content if hasattr(entry, 'content') else str(entry)
                terms = self._tokenize(content)
                
                # 统计词频
                term_freq = Counter(terms)
                self._doc_lengths[entry_id] = len(terms)
                
                # 更新倒排索引
                for term, freq in term_freq.items():
                    if term not in self._inverted_index:
                        self._inverted_index[term] = []
                    self._inverted_index[term].append((entry_id, freq))
            
            logger.info(f"索引构建完成，共 {len(self._inverted_index)} 个词项")
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        # 转小写
        text = text.lower()
        # 提取词
        words = re.findall(r'\b\w+\b', text)
        # 过滤停用词（简单版本）
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'again', 'further', 'then', 'once'}
        
        return [w for w in words if w not in stop_words and len(w) > 1]
    
    def _compute_tfidf(self, term: str, doc_id: str, doc_freq: int) -> float:
        """计算TF-IDF值"""
        # TF
        tf = 0
        for d_id, freq in self._inverted_index.get(term, []):
            if d_id == doc_id:
                tf = freq
                break
        
        if tf == 0:
            return 0
        
        # 归一化TF
        doc_length = self._doc_lengths.get(doc_id, 1)
        tf = tf / doc_length
        
        # IDF
        idf = math.log(self._doc_count / (1 + doc_freq))
        
        return tf * idf
    
    def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.1,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        搜索
        
        Args:
            query: 查询文本
            limit: 返回数量
            min_score: 最低分数
            filters: 过滤条件
            
        Returns:
            搜索结果列表
        """
        import time
        start_time = time.time()
        
        with self._lock:
            self._stats["total_queries"] += 1
            
            # 分词
            query_terms = self._tokenize(query)
            if not query_terms:
                return []
            
            # 计算查询向量
            query_vector = Counter(query_terms)
            
            # 找到相关文档
            candidate_docs: Dict[str, float] = {}
            
            for term in query_terms:
                if term in self._inverted_index:
                    postings = self._inverted_index[term]
                    doc_freq = len(postings)
                    
                    for doc_id, _ in postings:
                        # 计算文档中该词的TF-IDF
                        tfidf = self._compute_tfidf(term, doc_id, doc_freq)
                        
                        # 累加得分
                        if doc_id not in candidate_docs:
                            candidate_docs[doc_id] = 0
                        candidate_docs[doc_id] += query_vector[term] * tfidf
            
            # 归一化
            for doc_id in candidate_docs:
                candidate_docs[doc_id] /= math.sqrt(self._doc_lengths.get(doc_id, 1))
            
            # 排序
            sorted_docs = sorted(
                candidate_docs.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            # 构建结果
            results = []
            for doc_id, score in sorted_docs[:limit]:
                if score < min_score:
                    continue
                
                # 获取文档内容
                content = ""
                metadata = {}
                
                if self.knowledge_graph:
                    entry = self.knowledge_graph.get_entry(doc_id)
                    if entry:
                        content = entry.content
                        metadata = {
                            "task_type": entry.task_type,
                            "success_rate": entry.success_rate,
                            "tags": entry.tags
                        }
                
                # 高亮匹配词
                highlights = self._extract_highlights(content, query_terms)
                
                results.append(SearchResult(
                    entry_id=doc_id,
                    content=content,
                    score=score,
                    highlights=highlights,
                    metadata=metadata
                ))
            
            # 更新统计
            elapsed = time.time() - start_time
            self._stats["avg_query_time"] = (
                (self._stats["avg_query_time"] * (self._stats["total_queries"] - 1) + elapsed)
                / self._stats["total_queries"]
            )
            
            return results
    
    def _extract_highlights(
        self,
        content: str,
        terms: List[str],
        context_length: int = 50
    ) -> List[str]:
        """提取高亮片段"""
        highlights = []
        content_lower = content.lower()
        
        for term in terms[:3]:  # 最多3个高亮
            pos = content_lower.find(term)
            if pos >= 0:
                start = max(0, pos - context_length)
                end = min(len(content), pos + len(term) + context_length)
                snippet = content[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                highlights.append(snippet)
        
        return highlights
    
    def get_similar(
        self,
        entry_id: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """
        获取相似条目
        
        Args:
            entry_id: 条目ID
            limit: 返回数量
            
        Returns:
            相似条目列表
        """
        if not self.knowledge_graph:
            return []
        
        entry = self.knowledge_graph.get_entry(entry_id)
        if not entry:
            return []
        
        # 使用条目内容进行搜索
        results = self.search(entry.content, limit=limit + 1)
        
        # 排除自身
        return [r for r in results if r.entry_id != entry_id][:limit]
    
    def suggest(
        self,
        partial_query: str,
        limit: int = 5
    ) -> List[str]:
        """
        查询建议（自动补全）
        
        Args:
            partial_query: 部分查询
            limit: 返回数量
            
        Returns:
            建议列表
        """
        terms = self._tokenize(partial_query)
        if not terms:
            return []
        
        last_term = terms[-1]
        suggestions = []
        
        # 从索引中找前缀匹配的词
        for term in self._inverted_index.keys():
            if term.startswith(last_term) and term != last_term:
                suggestions.append(term)
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "index_size": len(self._inverted_index),
            "doc_count": self._doc_count
        }
    
    def save_index(self, path: Optional[str] = None):
        """保存索引"""
        path = Path(path) if path else self.index_path
        if not path:
            return
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "inverted_index": self._inverted_index,
            "doc_lengths": self._doc_lengths,
            "doc_count": self._doc_count,
            "stats": self._stats
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        
        logger.info(f"索引已保存到 {path}")
    
    def load_index(self, path: Optional[str] = None):
        """加载索引"""
        path = Path(path) if path else self.index_path
        if not path or not path.exists():
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._inverted_index = data["inverted_index"]
            self._doc_lengths = data["doc_lengths"]
            self._doc_count = data["doc_count"]
            self._stats = data.get("stats", self._stats)
            
            logger.info(f"索引已从 {path} 加载")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"索引文件损坏，使用空索引: {e}")
            self._inverted_index = {}
            self._doc_lengths = {}
            self._doc_count = 0
    
    def clear_index(self):
        """清空索引"""
        with self._lock:
            self._inverted_index.clear()
            self._doc_lengths.clear()
            self._doc_count = 0
            self._tfidf_cache.clear()
