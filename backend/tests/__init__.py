"""TestForge 后端测试包。

分层：
    unit/    纯函数逻辑，无 IO、无外部依赖
    agents/  LangGraph 图与节点（默认 LLM_MOCK 模式）
    api/     HTTP 接口（TestClient + 临时 SQLite）
    e2e/     端到端全链路（可能依赖真实数据库/模型）
"""
