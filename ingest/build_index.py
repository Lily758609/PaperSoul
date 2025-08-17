# 新增：多书支持
import argparse
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import os
from ingest.ark_embeddings import ArkEmbeddings

BASE = Path(__file__).resolve().parents[1]
NOVELS_DIR = BASE / "data" / "novels"
INDEXES_DIR = BASE / "data" / "indexes"

def build_index_for(book_id: str):
    book_dir = NOVELS_DIR / book_id
    assert book_dir.exists(), f"not found: {book_dir}"
    docs = []
    for p in book_dir.glob("*.txt"):
        docs.extend(TextLoader(str(p), encoding="utf-8").load())
    splits = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=120).split_documents(docs)
    ark_model = os.getenv("ARK_EMBED_MODEL", "doubao-embedding-large-text-240915")
    emb = ArkEmbeddings(model=ark_model, batch_size=32)  # [CHANGED]

    # [ADDED] 小型探活，避免大批量构建时才失败
    emb.embed_documents(["health check"])

    vs = FAISS.from_documents(splits,emb)
    out = INDEXES_DIR / book_id
    out.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(out))
    print(f"✅ index saved to {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="book_id, e.g. num1_cxs")
    args = ap.parse_args()
    build_index_for(args.book)
