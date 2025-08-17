import os
import json
import sqlite3
import time
from typing import List, Dict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

SCHEMA = {
    "sessions": """
        CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY,
            name TEXT,
            role_id TEXT,
            book_id TEXT,
            created_at INTEGER
        );
    """,
    "messages": """
        CREATE TABLE IF NOT EXISTS messages(
            session_id TEXT,
            idx INTEGER,
            role TEXT,
            content TEXT,
            created_at INTEGER
        );
    """,
    "ltm": """
        CREATE TABLE IF NOT EXISTS ltm(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role_id TEXT,
            fact TEXT,
            created_at INTEGER
        );
    """,
}

def ensure_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        for ddl in SCHEMA.values():
            cur.execute(ddl)
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_sid ON messages(session_id, idx);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ltm_sid ON ltm(session_id, role_id, created_at);")
        conn.commit()

class SessionStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
    def create_session(self, name: str, role_id: str,book_id: str) -> str:
        sid = str(int(time.time()*1000))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO sessions(id,name,role_id,created_at) VALUES(?,?,?,?)",
                         (sid, name, role_id, int(time.time())))
            conn.commit()
        return sid
    def list_sessions(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT id,name,role_id,created_at FROM sessions ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [ {"id": r[0], "name": r[1], "role_id": r[2], "created_at": r[3]}
                     for r in rows
                ]

    def load_history(self, session_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY idx ASC", (session_id,))
            return [ {"role": r[0], "content": r[1]} for r in cur.fetchall() ]
    def append_message(self, session_id: str, role: str, content: str):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COALESCE(MAX(idx), -1) FROM messages WHERE session_id=?", (session_id,))
            max_idx = cur.fetchone()[0]
            conn.execute("INSERT INTO messages(session_id,idx,role,content,created_at) VALUES(?,?,?,?,?)",
                         (session_id, max_idx+1, role, content, int(time.time())))
            conn.commit()
    def clear_history(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.commit()
    def delete_session(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM ltm WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            conn.commit()
    def export_json(self, session_id: str) -> str:
        data = {"session": None, "messages": self.load_history(session_id), "ltm": []}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT id,name,role_id,created_at FROM sessions WHERE id=?", (session_id,))
            row = cur.fetchone()
            if row:
                data["session"] = {"id": row[0], "name": row[1], "role_id": row[2], "book_id": row[3],"created_at": row[4]}
            cur = conn.execute("SELECT fact,created_at FROM ltm WHERE session_id=? ORDER BY created_at DESC", (session_id,))
            data["ltm"] = [ {"fact": r[0], "created_at": r[1]} for r in cur.fetchall() ]
        path = os.path.join("data", "sessions", f"session_{session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

class LTMStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
    def insert(self, session_id: str, role_id: str, fact: str):
        if not fact.strip():
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO ltm(session_id,role_id,fact,created_at) VALUES(?,?,?,?)",
                         (session_id, role_id, fact.strip(), int(time.time())))
            conn.commit()

    def retrieve(self, session_id: str, role_id: str, query: str, top_k: int = 3) -> List[str]:
        terms = [t for t in query.split() if len(t) >= 2][:5]
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT fact,created_at FROM ltm WHERE session_id=? AND role_id=? ORDER BY created_at DESC",
                               (session_id, role_id))
            rows = cur.fetchall()
        scored = []
        for fact, ts in rows:
            score = sum(1 for t in terms if t in fact)
            scored.append((score, ts, fact))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [f for _,__,f in scored[:top_k]]

def extract_facts(llm, role_name: str, history: List[Dict], user_text: str, reply: str) -> List[str]:
    prompt = f"""
请基于以下对话，提取1-3条**简短、稳定**的事实（用于长期记忆）。
要求：
- 不包含具体对话措辞；
- 只保留与关系/身份/目标/承诺/立场相关的陈述句；
- 15~50字/条；
- 若无可用事实则返回空。

[角色]{role_name}
[用户提问]{user_text}
[角色回复]{reply}
输出JSON数组，如：["事实1","事实2"]
""".strip()
    try:
        content = llm.invoke([{"role": "user", "content": prompt}]).content
        data = json.loads(content)
        if isinstance(data, list):
            return [str(x) for x in data][:3]
    except Exception:
        pass
    return []
