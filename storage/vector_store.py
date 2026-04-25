"""
Vector Store - ChromaDB RAG
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB 向量儲存"""
    
    def __init__(self, db_path: str = "./data/chroma", collection_name: str = "default"):
        self.db_path = db_path
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        
        # 建立目錄
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def connect(self):
        """連接向量資料庫"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self.client = chromadb.Client(Settings(
                persist_directory=self.db_path,
                anonymized_telemetry=False
            ))
            
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name
            )
            
            logger.info(f"已連接到 ChromaDB: {self.collection_name}")
            
        except ImportError:
            logger.warning("ChromaDB 未安裝，將使用記憶體模式")
            self._use_memory_mode()
        except Exception as e:
            logger.error(f"連接 ChromaDB 失敗: {e}")
            self._use_memory_mode()
    
    def _use_memory_mode(self):
        """使用記憶體模式（fallback）"""
        self.client = None
        self.collection = None
        self._memory_store: List[Dict] = []
        logger.info("使用記憶體模式")
    
    def add(
        self, 
        documents: List[str], 
        metadatas: List[Dict] = None, 
        ids: List[str] = None
    ):
        """新增文件"""
        if self.collection is None:
            # 記憶體模式
            for i, doc in enumerate(documents):
                self._memory_store.append({
                    "id": ids[i] if ids else f"doc_{i}",
                    "content": doc,
                    "metadata": metadatas[i] if metadatas else {}
                })
            return
        
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"新增 {len(documents)} 個文件")
    
    def search(
        self, 
        query: str, 
        n_results: int = 5, 
        where: Dict = None,
        where_document: Dict = None
    ) -> List[Dict]:
        """搜尋"""
        if self.collection is None:
            # 簡單的記憶體搜尋
            results = []
            for doc in self._memory_store:
                if query.lower() in doc["content"].lower():
                    results.append({
                        "id": doc["id"],
                        "content": doc["content"],
                        "metadata": doc["metadata"],
                        "distance": 0.0
                    })
            return results[:n_results]
        
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            where_document=where_document
        )
        
        # 格式化結果
        formatted = []
        if results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                formatted.append({
                    "id": results["ids"][0][i],
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0
                })
        
        return formatted
    
    def get(self, ids: List[str] = None, where: Dict = None, limit: int = None) -> List[Dict]:
        """取得文件"""
        if self.collection is None:
            if ids:
                return [d for d in self._memory_store if d["id"] in ids]
            return self._memory_store[:limit] if limit else self._memory_store
        
        results = self.collection.get(
            ids=ids,
            where=where,
            limit=limit
        )
        
        formatted = []
        if results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                formatted.append({
                    "id": results["ids"][i],
                    "content": doc,
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {}
                })
        
        return formatted
    
    def delete(self, ids: List[str] = None, where: Dict = None):
        """刪除文件"""
        if self.collection is None:
            if ids:
                self._memory_store = [d for d in self._memory_store if d["id"] not in ids]
            return
        
        self.collection.delete(
            ids=ids,
            where=where
        )
        logger.info(f"刪除文件: {ids or where}")
    
    def count(self) -> int:
        """取得文件數量"""
        if self.collection is None:
            return len(self._memory_store)
        
        return self.collection.count()
    
    def clear(self):
        """清除所有文件"""
        if self.collection is None:
            self._memory_store = []
            return
        
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(self.collection_name)
        logger.info("已清除所有文件")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # ChromaDB 不需要明確關閉