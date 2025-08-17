from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import os
from ingest.ark_embeddings import ArkEmbeddings
BASE = Path(__file__).resolve().parents[1]
NOVELS_DIR = BASE / "data" / "novels"
INDEXES_DIR = BASE / "data" / "indexes"

# 合并两个检索结果列表，打分
def rrf_merge(vec_docs, bm_docs, k=5):
    scores = {}
    for rank, d in enumerate(vec_docs): # 打分
        scores[d.page_content] = scores.get(d.page_content, 0) + 1.0 / (50 + rank)
    for rank, d in enumerate(bm_docs):
        scores[d.page_content] = scores.get(d.page_content, 0) + 1.0 / (60 + rank)
    unique = {}
    for d in vec_docs + bm_docs:
        if d.page_content not in unique:
            unique[d.page_content] = d
    ranked = sorted(unique.values(), key=lambda d: scores[d.page_content], reverse=True)
    return ranked[:k]

class DemoRetriever:
    def __init__(self, book_id:str,k: int = 5):
        self.book_id = book_id
        self.k = k
        ark_model = os.getenv("ARK_EMBED_MODEL", "doubao-embedding-large-text-240915")  # [ADDED]
        embeddings = ArkEmbeddings(model=ark_model, batch_size=32)
        # [ADDED] 友好检查：索引是否存在（避免路径/模型不一致时的隐晦报错）
        out_dir = INDEXES_DIR / book_id  # [ADDED]
        faiss_path = out_dir / "index.faiss"  # [ADDED]
        pkl_path = out_dir / "index.pkl"  # [ADDED]
        if not faiss_path.exists() or not pkl_path.exists():  # [ADDED]
            raise FileNotFoundError(
                f"未找到向量索引：{faiss_path} / {pkl_path}\n"
                f"请先构建：python -m ingest.build_index --book {book_id} "
                f"--ark_model {ark_model}"
            )

        self.vs = FAISS.load_local(str(out_dir), embeddings, allow_dangerous_deserialization=True)
        docs = []
        for p in (NOVELS_DIR / book_id).glob("*.txt"):
            docs.extend(TextLoader(str(p), encoding="utf-8").load())
        chunks = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=120).split_documents(docs)
        self.bm25 = BM25Retriever.from_documents(chunks)
        self.bm25.k = max(k, 5)

    def fetch_hidden_context(self, query: str) -> str:
        vec_docs = self.vs.similarity_search(query, k=self.k)
        bm_docs = self.bm25.invoke(query)
        merged = rrf_merge(vec_docs, bm_docs, k=self.k)
        return "\n\n".join(d.page_content.strip() for d in merged)