import os
import uuid
import glob
import json
import gradio as gr

from backend.chat_engine import RoleChatEngine
from backend.memory import SessionStore, LTMStore, ensure_db

APP_TITLE = "PaperSoul-纸片人永远不死"
DB_PATH = os.path.join("data", "sessions", "chat.db")

# ========== 初始化数据库 ==========
ensure_db(DB_PATH)                        # [NEW] 内含 WAL/索引 加速
session_store = SessionStore(DB_PATH)
ltm_store = LTMStore(DB_PATH)

# ========== 角色卡自动发现 ==========
def load_all_cards():
    cards = []
    for p in glob.glob("data/lore/characters/*.json"):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        assert "id" in d and "display_name" in d and "book_id" in d, f"角色卡字段缺失：{p}"
        cards.append(d)
    return cards

CARDS = load_all_cards()
if not CARDS:
    raise RuntimeError("未找到任何角色卡。请在 data/lore/characters/ 放入 *.json，含 id/display_name/book_id。")

ROLE_LABELS = [f"{c['display_name']}（{c.get('book_title','') or c['book_id']}）" for c in CARDS]
ROLE_BY_LABEL = {ROLE_LABELS[i]: CARDS[i]["id"] for i in range(len(CARDS))}
BOOK_BY_ROLE = {c["id"]: c["book_id"] for c in CARDS}

# ========== 工具函数 ==========
def messages_to_pairs(messages):
    pairs = []
    u_buf = None
    for m in messages:
        if m["role"] == "user":
            if u_buf is not None:
                pairs.append((u_buf, None))
            u_buf = m["content"]
        else:
            if u_buf is None:
                pairs.append((None, m["content"]))
            else:
                pairs.append((u_buf, m["content"]))
                u_buf = None
    if u_buf is not None:
        pairs.append((u_buf, None))
    return pairs

def pairs_to_messages(pairs):
    msgs = []
    for u, a in pairs:
        if u:
            msgs.append({"role": "user", "content": u})
        if a:
            msgs.append({"role": "assistant", "content": a})
    return msgs

def list_session_options():
    existing = session_store.list_sessions()
    options = [f"{s['id']} · {s['name']}" for s in existing]
    return options, existing

# ========== 回调逻辑 ==========
def init_or_switch_role(role_label, use_ltm, state):
    role_id = ROLE_BY_LABEL[role_label]
    book_id = BOOK_BY_ROLE[role_id]
    engine = RoleChatEngine(                  # [NEW] 直接复用后端
        card_id=role_id,
        book_id=book_id,                      # [NEW] 角色 → 书 自动推导
        session_store=session_store,
        ltm_store=ltm_store,
    )
    session_id = state.get("session_id") or str(uuid.uuid4())
    state.update({
        "session_id": session_id,
        "role_id": role_id,
        "book_id": book_id,
        "engine": engine,
        "use_ltm": bool(use_ltm),
        "history": state.get("history") or [],
    })
    info = f"当前角色：{role_label}｜书ID：{book_id}"
    return info, state

def new_session(session_name, state, chatbot):
    if not state.get("role_id") or not state.get("book_id"):
        return gr.update(value="请先选择角色并初始化。"), state, chatbot
    sid = session_store.create_session(session_name or "Gradio会话", state["role_id"], state["book_id"])  # [CHANGED]
    state["session_id"] = sid
    state["history"] = []
    chatbot = gr.update(value=[])
    return f"已新建会话：{sid}", state, chatbot

def refresh_sessions():
    options, _ = list_session_options()
    if not options:
        return gr.update(choices=[], value=None), "暂无会话"
    return gr.update(choices=options, value=options[0]), "已刷新会话列表"

def load_session(select_label, state, chatbot):
    if not select_label:
        return "请选择一个会话", state, chatbot
    sid = select_label.split(" · ")[0]
    # 1) 加载历史
    msgs = session_store.load_history(sid)
    state["session_id"] = sid
    state["history"] = msgs[:]
    # 2) 从会话表取元信息，同步切换引擎到该会话的角色/书
    meta_list = session_store.list_sessions()
    meta = next((m for m in meta_list if m["id"] == sid), None)
    if meta and meta.get("role_id") and meta.get("book_id"):
        role_id = meta["role_id"]
        book_id = meta["book_id"]
        # 若与当前不同，则重建引擎
        if state.get("role_id") != role_id or state.get("book_id") != book_id:
            engine = RoleChatEngine(
                card_id=role_id,
                book_id=book_id,
                session_store=session_store,
                ltm_store=ltm_store,
            )
            state.update({"role_id": role_id, "book_id": book_id, "engine": engine})
        info = f"已加载会话：{sid}｜角色：{role_id}｜书：{book_id}"
    else:
        info = f"已加载会话：{sid}"

    return info, state, gr.update(value=msgs)

def delete_session(select_label, state, chatbot):
    if not select_label:
        return "请选择一个会话", state, chatbot
    sid = select_label.split(" · ")[0]
    session_store.delete_session(sid)
    if state.get("session_id") == sid:
        state["session_id"] = str(uuid.uuid4())
        state["history"] = []
        chatbot = gr.update(value=[])
    # 刷新下拉列表
    options, _ = list_session_options()
    sess_dd_update = gr.update(choices=options, value=(options[0] if options else None))
    return f"已删除会话：{sid}", state, chatbot, sess_dd_update

def clear_current_session(state, chatbot):
    sid = state.get("session_id")
    if not sid:
        return "未找到当前会话ID", state, chatbot
    session_store.clear_history(sid)
    state["history"] = []
    return "当前会话已清空", state, gr.update(value=[])

def export_current_session(state):
    sid = state.get("session_id")
    if not sid:
        return "未找到当前会话ID"
    path = session_store.export_json(sid)
    return f"已导出到：{path}"

def toggle_ltm(use_ltm, state):
    state["use_ltm"] = bool(use_ltm)
    return f"长期记忆：{'开启' if state['use_ltm'] else '关闭'}", state

# —— 流式发送（逐 token 推送） —— #
def send_message_stream(user_text, chatbot, state):
    user_text = (user_text or "").strip()
    if not user_text:
        yield chatbot, state, gr.update(value="")
        return
    if not state.get("engine"):
        yield chatbot, state, gr.update(value="", placeholder="请先选择角色并点击“初始化 / 切换角色”")
        return

    # 1) 先推用户消息 + 预留空的 bot 气泡
    msgs = list(state.get("history", []))  # [{'role', 'content'}, ...]
    msgs.append({"role": "user", "content": user_text})
    msgs.append({"role": "assistant", "content": ""})  # 预留一个空的助手气泡
    yield gr.update(value=msgs), state, gr.update(value="")

    # 2) 调用后端流式接口，逐步更新最后一条气泡
    acc = []
    stream = state["engine"].chat_stream(          # [NEW] 使用流式生成
        session_id=state["session_id"],
        history=state["history"],
        user_text=user_text,
        use_ltm=state.get("use_ltm", True),
    )
    for piece in stream:
        acc.append(piece)
        msgs[-1]["content"] = "".join(acc)      # [NEW] 实时更新最后一条
        yield gr.update(value=msgs), state, gr.update(value="")

    # 3) 收尾：更新本地历史（engine 内已入库）
    state["history"] = msgs
    yield gr.update(value=msgs), state, gr.update(value="")

# ========== UI ==========
with gr.Blocks(fill_height=True, theme="soft") as demo:
    state = gr.State({"history": [], "use_ltm": True})

    gr.Markdown(f"# {APP_TITLE}")
    gr.Markdown("选择你想进行对话的角色，一起搭建平行世界进行交互吧")

    with gr.Row():
        role_dd = gr.Dropdown(ROLE_LABELS, value=ROLE_LABELS[0], label="选择角色")
        ltm_ck = gr.Checkbox(value=True, label="开启长期记忆")
        init_btn = gr.Button("初始化 / 切换角色", variant="primary")
    info_md = gr.Markdown("未初始化")

    with gr.Row():
        name_tb = gr.Textbox(label="新建会话名称", value="演示对话", scale=2)
        new_btn = gr.Button("新建", scale=1)
        refresh_btn = gr.Button("刷新会话列表", scale=1)

    sess_dd = gr.Dropdown(choices=[], label="加载/删除会话（选择一项）", interactive=True)
    with gr.Row():
        load_btn = gr.Button("加载")
        del_btn = gr.Button("删除")
        clear_btn = gr.Button("清空当前会话")
        export_btn = gr.Button("导出JSON")

    chat = gr.Chatbot(type="messages",label="对话", height=520)
    with gr.Row():
        user_in = gr.Textbox(placeholder="对角色说点什么…", lines=2, scale=5)
        send_btn = gr.Button("发送", variant="primary", scale=1)

    # 事件绑定
    init_btn.click(init_or_switch_role, [role_dd, ltm_ck, state], [info_md, state], concurrency_limit=2)
    new_btn.click(new_session, [name_tb, state, chat], [info_md, state, chat], concurrency_limit=2)
    refresh_btn.click(refresh_sessions, [], [sess_dd, info_md], concurrency_limit=2)
    load_btn.click(load_session, [sess_dd, state, chat], [info_md, state, chat], concurrency_limit=2)
    del_btn.click(delete_session, [sess_dd, state, chat], [info_md, state, chat, sess_dd], concurrency_limit=2)
    clear_btn.click(clear_current_session, [state, chat], [info_md, state], concurrency_limit=2)
    export_btn.click(export_current_session, [state], [info_md], concurrency_limit=2)
    ltm_ck.change(toggle_ltm, [ltm_ck, state], [info_md, state], concurrency_limit=2)

    # —— 流式发送（通常最耗时，并发单独设高一点）—— #
    send_btn.click(send_message_stream, [user_in, chat, state], [chat, state, user_in], concurrency_limit=4)
    user_in.submit(send_message_stream, [user_in, chat, state], [chat, state, user_in], concurrency_limit=4)
if __name__ == "__main__":
    demo.queue( max_size=32)
    demo.launch(
        server_name="127.0.0.1",  # 或 0.0.0.0 便于手机/其它设备访问
        server_port=7860,
        max_threads=20,
        show_api=False  # 临时绕开 /info 的 schema 生成
        # share=True               # 如本机访问仍失败就打开它
    )