from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from .character_card import load_character, render_system_prompt
from backend.retriever import DemoRetriever
from backend.memory import SessionStore, LTMStore, extract_facts
import os
from typing import Generator
MAX_HISTORY_ROUNDS = 8
api_key=os.getenv("OPENAI_API_KEY")
# 新增：后端统一控制默认值，可用环境变量覆盖
DEFAULT_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.8"))
DEFAULT_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

def build_history_aware_query(history: List[Dict], user_text: str) -> str:
    last_users = [m["content"] for m in history if m["role"] == "user"]
    tail = last_users[-2:] if len(last_users) >= 2 else last_users
    joined = " \n".join(tail + [user_text]) if tail else user_text
    return joined[:800]

class RoleChatEngine:
    def __init__(self, card_id: str, book_id:str,session_store: SessionStore, ltm_store: LTMStore,
                 temperature: float = 0.5, top_k: int = 5):
        self.card_id = card_id
        self.card = load_character(card_id)
        self.book_id = book_id
        self.retriever = DemoRetriever(book_id=book_id, k=top_k or DEFAULT_TOP_K)
        self.llm = ChatOpenAI(
                     base_url="https://jy.ai666.net/v1",
                     api_key=api_key,
                     temperature=temperature or DEFAULT_TEMPERATURE,
                     model = "gpt-4o",
                     )
        self.sessions = session_store
        self.ltm = ltm_store
    def _clip_history(self, history: List[Dict]) -> List[Dict]:
        return history[-MAX_HISTORY_ROUNDS * 2 :]

    def chat(self, session_id: str, history: List[Dict], user_text: str, use_ltm: bool = True) -> str:
        history = self._clip_history(history)
        query_for_retrieval = build_history_aware_query(history, user_text)
        hidden_ctx = self.retriever.fetch_hidden_context(query_for_retrieval)

        # 只有开启时才检索长期记忆
        if use_ltm:
            ltm_snippets = self.ltm.retrieve(session_id=session_id, role_id=self.card_id, query=user_text, top_k=3)
            if ltm_snippets:
                hidden_ctx += "\n\n【长期记忆】\n" + "\n".join(ltm_snippets)

        sys_prompt = render_system_prompt(self.card, hidden_ctx)
        messages = [SystemMessage(content=sys_prompt)]
        for m in history:
            if m["role"] == "user":
                messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                messages.append(AIMessage(content=m["content"]))
        messages.append(HumanMessage(content=user_text))

        resp = self.llm.invoke(messages)
        reply = resp.content
        # 入库
        self.sessions.append_message(session_id, role="user", content=user_text)
        self.sessions.append_message(session_id, role="assistant", content=reply)

        # 只有开启时才写入长期记忆
        if use_ltm:
            facts = extract_facts(self.llm, self.card.display_name, history, user_text, reply)
            for f in facts:
                self.ltm.insert(session_id=session_id, role_id=self.card_id, fact=f)

        return reply

    # —— [NEW] 流式输出：逐块产出，结束后入库 + 抽取 —— #
    def chat_stream(
            self,
            session_id: str,
            history: List[Dict],
            user_text: str,
            use_ltm: bool = True,
    ) -> Generator[str, None, str]:
        history_clipped = self._clip_history(history)
        query_for_retrieval = build_history_aware_query(history_clipped, user_text)
        hidden_ctx = self.retriever.fetch_hidden_context(query_for_retrieval)
        if use_ltm:
            ltm_snippets = self.ltm.retrieve(session_id=session_id, role_id=self.card_id, query=user_text, top_k=3)
            if ltm_snippets:
                hidden_ctx += "\n\n【长期记忆】\n" + "\n".join(ltm_snippets)
        sys_prompt = render_system_prompt(self.card, hidden_ctx)
        messages = [SystemMessage(content=sys_prompt)]
        for m in history_clipped:
            if m["role"] == "user":
                messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                messages.append(AIMessage(content=m["content"]))
        messages.append(HumanMessage(content=user_text))

        chunks = []
        for delta in self.llm.stream(messages):  # [NEW] 使用流式接口
            piece = getattr(delta, "content", None)
            if piece:
                chunks.append(piece)
                yield piece
        full = "".join(chunks)

        # 入库
        self.sessions.append_message(session_id, role="user", content=user_text)
        self.sessions.append_message(session_id, role="assistant", content=full)
        # 长期记忆抽取
        if use_ltm:
            facts = extract_facts(self.llm, self.card.display_name, history_clipped, user_text, full)
            for f in facts:
                self.ltm.insert(session_id=session_id, role_id=self.card_id, fact=f)
        return full
