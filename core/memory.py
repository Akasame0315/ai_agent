"""
記憶系統：使用 ChromaDB 向量資料庫
- 每次對話結束後自動萃取重要資訊存入記憶
- 每次對話開始前自動搜尋相關記憶注入 prompt
- 記憶永久保存，重啟後依然存在
"""
import json
import datetime
import chromadb # type: ignore
from chromadb.utils import embedding_functions # type: ignore


# ── 初始化 ChromaDB（資料存在本機 memory_db 資料夾）─────────────────
_client = chromadb.PersistentClient(path="memory_db")
_ef     = embedding_functions.DefaultEmbeddingFunction()  # 使用內建的向量模型

_collection = _client.get_or_create_collection(
    name="agent_memory",
    embedding_function=_ef,
    metadata={"hnsw:space": "cosine"}
)


# ══════════════════════════════════════════════════════════════════════
# 公開 API
# ══════════════════════════════════════════════════════════════════════

def search_memory(query: str, n_results: int = 3) -> str:
    """
    搜尋和 query 最相關的記憶，回傳格式化字串供注入 prompt。
    沒有記憶或搜尋不到時回傳空字串。
    """
    count = _collection.count()
    if count == 0:
        return ""

    try:
        results = _collection.query(
            query_texts=[query],
            n_results=min(n_results, count)
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return ""

        lines = ["📝 相關記憶："]
        for doc, meta in zip(docs, metas):
            date = meta.get("date", "")
            lines.append(f"  • [{date}] {doc}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[Memory] 搜尋失敗：{e}")
        return ""


def save_memory(user_message: str, agent_reply: str) -> None:
    """
    從一輪對話中萃取值得記住的資訊並存入記憶庫。
    使用簡單的規則判斷，不需要額外的 LLM 呼叫。
    """
    memories_to_save = []

    # ── 規則一：使用者說「我是/我叫/我在/我有/我喜歡/我不喜歡...」─────
    import re
    user_patterns = [
        r"我(?:是|叫|在|住|有|喜歡|不喜歡|討厭|想要|需要|正在|使用|工作|讀).{2,30}",
        r"我的(?:名字|工作|習慣|偏好|電腦|手機).{2,20}",
        r"(?:請|幫我)?記住.{2,30}",
        r"我(?:平常|通常|都|一直).{2,30}",
    ]
    for pattern in user_patterns:
        matches = re.findall(pattern, user_message)
        for m in matches:
            memories_to_save.append(f"用戶資訊：{m.strip()}")

    # ── 規則二：對話裡提到的具體偏好 ─────────────────────────────────
    preference_keywords = ["喜歡", "不喜歡", "討厭", "偏好", "習慣", "慣用"]
    if any(kw in user_message for kw in preference_keywords):
        # 把整句話存下來作為偏好記憶
        clean = user_message.strip()
        if len(clean) > 5 and clean not in [m.split("：")[-1] for m in memories_to_save]:
            memories_to_save.append(f"用戶偏好：{clean[:100]}")

    # ── 存入 ChromaDB ─────────────────────────────────────────────────
    if memories_to_save:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        for i, mem in enumerate(memories_to_save):
            mem_id = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
            try:
                # 檢查是否已有相似記憶（避免重複）
                existing = _collection.query(
                    query_texts=[mem],
                    n_results=1
                )
                existing_docs = existing.get("documents", [[]])[0]
                if existing_docs:
                    # 計算相似度，太相似就跳過
                    existing_distances = existing.get("distances", [[1.0]])[0]
                    if existing_distances and existing_distances[0] < 0.1:
                        continue  # 太相似，跳過

                _collection.add(
                    documents=[mem],
                    ids=[mem_id],
                    metadatas=[{"date": today, "source": "conversation"}]
                )
                print(f"[Memory] 已儲存記憶：{mem[:50]}...")
            except Exception as e:
                print(f"[Memory] 儲存失敗：{e}")


def list_all_memories() -> str:
    """列出所有記憶（給使用者查看用）"""
    count = _collection.count()
    if count == 0:
        return "📭 目前沒有任何記憶"

    try:
        results = _collection.get()
        docs    = results.get("documents", [])
        metas   = results.get("metadatas", [])

        lines = [f"🧠 共有 {count} 條記憶：\n"]
        for doc, meta in zip(docs, metas):
            date = meta.get("date", "")
            lines.append(f"  [{date}] {doc}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 讀取記憶失敗：{e}"


def clear_memories() -> str:
    """清除所有記憶"""
    try:
        _client.delete_collection("agent_memory")
        # 重新建立空的 collection
        global _collection
        _collection = _client.get_or_create_collection(
            name="agent_memory",
            embedding_function=_ef,
            metadata={"hnsw:space": "cosine"}
        )
        return "🗑️ 所有記憶已清除"
    except Exception as e:
        return f"❌ 清除失敗：{e}"
