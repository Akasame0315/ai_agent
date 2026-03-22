"""
RAG（Retrieval-Augmented Generation）知識庫系統
路徑：core/rag.py

功能：
- 支援匯入 .txt / .md / .pdf 文件
- 自動切段、向量化、存入 ChromaDB
- 查詢時搜尋最相關的段落注入 prompt
"""
import os
import re
import hashlib
import datetime
import chromadb # type: ignore
from chromadb.utils import embedding_functions # type: ignore

# ── 初始化 ChromaDB（和記憶系統分開，存在 rag_db 資料夾）────────────
_client = chromadb.PersistentClient(path="rag_db")
_ef     = embedding_functions.DefaultEmbeddingFunction()

_collection = _client.get_or_create_collection(
    name="knowledge_base",
    embedding_function=_ef,
    metadata={"hnsw:space": "cosine"}
)

CHUNK_SIZE    = 300   # 每個段落的字元數
CHUNK_OVERLAP = 50    # 段落間重疊字元數（避免切斷重要資訊）


# ══════════════════════════════════════════════════════════════════════
# 文件處理
# ══════════════════════════════════════════════════════════════════════

def _chunk_text(text: str) -> list[str]:
    """把長文字切成有重疊的小段落"""
    text   = re.sub(r'\n{3,}', '\n\n', text).strip()
    chunks = []
    start  = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if len(c.strip()) > 20]


def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_pdf(path: str) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except ImportError:
        return "❌ 讀取 PDF 需要安裝：pip install pypdf"
    except Exception as e:
        return f"❌ PDF 讀取失敗：{e}"


def add_document(file_path: str, source_name: str = "") -> str:
    """
    把文件加入知識庫。
    支援 .txt / .md / .pdf
    file_path 可以是絕對路徑或相對路徑。
    """
    if not os.path.exists(file_path):
        return f"❌ 找不到檔案：{file_path}"

    ext  = os.path.splitext(file_path)[1].lower()
    name = source_name or os.path.basename(file_path)

    # 讀取文字內容
    if ext in (".txt", ".md"):
        text = _read_txt(file_path)
    elif ext == ".pdf":
        text = _read_pdf(file_path)
        if text.startswith("❌"):
            return text
    else:
        return f"❌ 不支援的格式：{ext}（支援 .txt / .md / .pdf）"

    if not text.strip():
        return f"❌ 檔案是空的：{name}"

    # 切段落
    chunks = _chunk_text(text)

    # 存入 ChromaDB
    today    = datetime.datetime.now().strftime("%Y-%m-%d")
    added    = 0
    skipped  = 0

    for i, chunk in enumerate(chunks):
        # 用內容 hash 當 ID，避免重複匯入
        chunk_id = hashlib.md5(f"{name}_{chunk}".encode()).hexdigest()

        try:
            # 嘗試查是否已存在
            existing = _collection.get(ids=[chunk_id])
            if existing["ids"]:
                skipped += 1
                continue

            _collection.add(
                documents=[chunk],
                ids=[chunk_id],
                metadatas=[{
                    "source": name,
                    "date":   today,
                    "chunk":  i
                }]
            )
            added += 1
        except Exception as e:
            print(f"[RAG] 段落 {i} 存入失敗：{e}")

    return (
        f"✅ 已匯入文件：{name}\n"
        f"   共 {len(chunks)} 個段落，新增 {added} 個，跳過重複 {skipped} 個"
    )


def add_text(content: str, source_name: str) -> str:
    """
    直接把一段文字加入知識庫（不需要檔案）。
    適合從網頁複製的內容、手動輸入的資料。
    """
    if not content.strip():
        return "❌ 內容是空的"

    chunks   = _chunk_text(content)
    today    = datetime.datetime.now().strftime("%Y-%m-%d")
    added    = 0
    skipped  = 0

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{source_name}_{chunk}".encode()).hexdigest()
        try:
            existing = _collection.get(ids=[chunk_id])
            if existing["ids"]:
                skipped += 1
                continue
            _collection.add(
                documents=[chunk],
                ids=[chunk_id],
                metadatas=[{"source": source_name, "date": today, "chunk": i}]
            )
            added += 1
        except Exception as e:
            print(f"[RAG] 存入失敗：{e}")

    return (
        f"✅ 已加入知識庫：{source_name}\n"
        f"   共 {len(chunks)} 個段落，新增 {added} 個，跳過重複 {skipped} 個"
    )


# ══════════════════════════════════════════════════════════════════════
# 查詢
# ══════════════════════════════════════════════════════════════════════

def search_knowledge(query: str, n_results: int = 3) -> str:
    """
    搜尋知識庫，回傳最相關的段落（格式化字串供注入 prompt）。
    找不到相關內容時回傳空字串。
    """
    count = _collection.count()
    if count == 0:
        return ""

    try:
        results = _collection.query(
            query_texts=[query],
            n_results=min(n_results, count)
        )
        docs      = results.get("documents", [[]])[0]
        metas     = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        # 只保留相似度夠高的結果（distance < 0.8）
        relevant = [
            (doc, meta) for doc, meta, dist
            in zip(docs, metas, distances)
            if dist < 0.8
        ]

        if not relevant:
            return ""

        lines = ["📚 知識庫相關內容："]
        for doc, meta in relevant:
            source = meta.get("source", "未知來源")
            lines.append(f"  【{source}】{doc[:200]}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[RAG] 搜尋失敗：{e}")
        return ""


def list_documents() -> str:
    """列出知識庫裡有哪些文件來源"""
    count = _collection.count()
    if count == 0:
        return "📭 知識庫是空的，還沒有匯入任何文件"

    try:
        results = _collection.get()
        metas   = results.get("metadatas", [])

        # 統計每個來源的段落數
        sources: dict[str, int] = {}
        for meta in metas:
            src = meta.get("source", "未知")
            sources[src] = sources.get(src, 0) + 1

        lines = [f"📚 知識庫共有 {count} 個段落，來自 {len(sources)} 個文件：\n"]
        for src, cnt in sorted(sources.items()):
            lines.append(f"  • {src}（{cnt} 個段落）")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ 查詢失敗：{e}"


def delete_document(source_name: str) -> str:
    """從知識庫刪除指定來源的所有段落"""
    try:
        results = _collection.get(where={"source": source_name})
        ids     = results.get("ids", [])

        if not ids:
            return f"❌ 知識庫裡找不到來源：{source_name}"

        _collection.delete(ids=ids)
        return f"✅ 已刪除「{source_name}」的 {len(ids)} 個段落"

    except Exception as e:
        return f"❌ 刪除失敗：{e}"
