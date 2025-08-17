## 项目名称
PaperSoul（Python + LangChain + ChatGPT + ArkSKD）

## 项目简介
这是一个基于 Python + LangChain + ChatGPT + ArkSKD 的 AI 聊天应用，支持基于原著小说角色进行对话。应用在不展示原文的情况下使用隐式 RAG 技术检索相关剧情，并结合短期和长期记忆，保持角色设定和剧情一致性。

## 功能特点
- **固定角色选择**：用户选择预设角色卡。
- **隐式检索增强（RAG）**：结合 FAISS 向量检索与 BM25 关键词检索，RRF 融合结果作为上下文隐式注入。
- **角色一致性**：基于角色原文相关剧情，以及角色卡的人设、口癖、关系、世界观、安全边界进行严格约束。
- **短期记忆**：会话窗口保留最近 N 轮对话（默认 8 轮）。
- **长期记忆**：从对话中提取稳定事实存储到 SQLite，并在后续召回注入上下文。
- **会话管理**：支持新建、加载、删除、清空、导出会话（JSON 格式）。
- **参数可调**：侧边栏调整 temperature 与检索 top_k。

## 技术栈
- Python
- LangChain
- OpenAI ChatGPT API
- FAISS（向量检索）
- BM25（关键词检索）
- SQLite（长期记忆与会话存档）
- Streamlit（前端 UI）

## 运行步骤
1. 设置环境变量 `OPENAI_API_KEY`
2. 构建索引：`python ingest/build_index.py`
3. 启动应用：`streamlit run gradio_app.py`

## 适用场景
- 原著角色互动体验
- 长期剧情互动与记忆保持