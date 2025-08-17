from __future__ import annotations
import os, time, random
from typing import List, Optional
from volcenginesdkarkruntime import Ark

# 可选：与 langchain 类型保持一致（不是硬性要求）
try:
    from langchain_core.embeddings import Embeddings  # type: ignore
except Exception:
    class Embeddings:  # 兜底，不强依赖
        pass

class ArkEmbeddings(Embeddings):
    """
    将火山 Ark SDK 封装为 LangChain 兼容的 Embeddings：
    - embed_documents(List[str]) -> List[List[float]]
    - embed_query(str) -> List[float]
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "doubao-embedding-large-text-240915",
        timeout: int = 30,
        batch_size: int = 32,
        encoding_format: str = "float",
        max_retries: int = 5,
        backoff_base: float = 0.5,
    ) -> None:
        api_key = api_key or os.getenv("ARK_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 ARK_API_KEY，请设置环境变量或在 ArkEmbeddings(api_key=...) 传入。")

        # volcenginesdkarkruntime 的 Ark 客户端
        self.client = Ark(api_key=api_key, timeout=timeout)
        self.model = model
        self.batch_size = max(1, batch_size)
        self.encoding_format = encoding_format
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    # ---- 内部统一请求，带重试 ---- #
    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        last_err: Optional[Exception] = None
        for retry in range(self.max_retries):
            try:
                resp = self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    encoding_format=self.encoding_format,
                )
                # Ark 返回对象：resp.data[i].embedding 即向量
                return [item.embedding for item in resp.data]
            except Exception as e:
                last_err = e
                # 指数退避 + 抖动
                sleep_s = self.backoff_base * (2 ** retry) + random.uniform(0, 0.2)
                time.sleep(sleep_s)
        # 重试仍失败
        raise RuntimeError(f"Ark embeddings 请求失败（已重试 {self.max_retries} 次）：{last_err}")

    # ---- LangChain 约定接口 ---- #
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i:i + self.batch_size]
            out.extend(self._embed_batch(chunk))
        return out

    def embed_query(self, text: str) -> List[float]:
        return self._embed_batch([text])[0]