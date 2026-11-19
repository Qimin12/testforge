# 测试目录说明

> 这个目录只放测试代码。业务代码在 `../app/`。

## 目录

| 目录 | 内容 | 依赖 |
|---|---|---|
| `unit/` | 纯逻辑：密码、JWT、配置解析、状态 reducer | 无 |
| `agents/` | LangGraph 图与节点（路由、mock 生成、执行器、全图跑通、中断恢复） | 无网络 |
| `api/` | HTTP 接口：注册/登录/API Key/图运行 | 临时 SQLite |
| `e2e/` | 端到端全链路 | 临时 SQLite + 假 API |

假 API 由 `conftest.py` 里的 `httpx.MockTransport` 提供，**测试不需要联网**，
也不需要开虚拟机里的 PostgreSQL/Redis。

## 跑测试

```bash
cd /mnt/e/MyProject/testforge/backend
conda activate testforge

pytest                          # 全部
pytest tests/unit -m unit       # 只跑纯逻辑
pytest tests/agents -m agents    # 只跑图
pytest tests/api -m api          # 只跑接口
pytest tests/e2e -m e2e          # 只跑端到端
pytest -k "review"              # 按名字挑
pytest --cov=app --cov-report=term-missing   # 覆盖率
```

## 约定

1. **测试自己控制环境**：`conftest.py` 顶部固定了 `LLM_MOCK=true`、
   `LANGGRAPH_CHECKPOINTER=memory`、临时 SQLite 路径。不要在测试里连真实
   数据库或真实模型。
2. **要测真实模型**：单独放 `tests/e2e/test_llm_live.py` 并标 `@pytest.mark.e2e`，
   把 `LLM_MOCK` 覆盖为 false，用 `pytest -m e2e` 手动跑，别混进默认套件。
3. **要测真实 Postgres 检查点**：把 `LANGGRAPH_CHECKPOINTER` 覆盖成 `postgres`
   并配 `CHECKPOINT_DB_URL`，同样标 `e2e`。
4. 新增节点时，同步加一条 `tests/agents/test_<node>.py`，用 mock 模式断言
   输入输出结构，不要断言模型文案。
