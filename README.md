# TestForge

> AI 驱动的全链路自动化测试平台

TestForge 把 **AI 生成测试用例、自动执行、失败分析、缺陷定位、报告导出** 串成一条完整的自动化链路：导入 OpenAPI/Swagger 即可生成接口测试用例，执行失败后由大模型自动分析根因并生成缺陷记录与修复建议，最终产出可下载的质量报告，并可作为**质量门禁**接入 CI/CD 流水线。

平台由 `backend`（FastAPI + LangGraph 多 Agent）与 `frontend`（Next.js 15）两部分组成。

---

## ✨ 核心特性

- **AI 用例生成**：从 OpenAPI/Swagger 文档自动生成接口测试用例
- **全链路编排**：基于 LangGraph 的状态图，一条链接「生成 → 审核 → 执行 → 分析 → 缺陷 → 报告」
- **失败自动分析**：只对失败用例调用模型，输出失败原因、根因定位与修复建议
- **缺陷自动分类**：按功能 / 性能 / 安全自动分类缺陷，记录严重级别
- **报告与导出**：支持 JSON / Markdown / CSV / XLSX 多种格式导出
- **覆盖率上报**：支持 pytest-cov 等工具的覆盖率上报与历史趋势
- **CI/CD 质量门禁**：`X-API-Key` 鉴权 + 门禁结论（通过率、缺陷数），GitHub Actions / GitLab CI 开箱即用
- **定时调度**：基于 Celery beat，按项目配置的间隔自动执行
- **成本可观测**：按 Agent 节点的 Token 用量统计、月度预算与超支告警
- **多 LLM 供应商**：硅基流动（默认）/ DeepSeek / 通义千问，均走 OpenAI 兼容协议
- **开发零依赖**：无 Key / 无数据库 / 无 Redis 也能跑通全图（LLM Mock + SQLite + 同步执行）

---

## 🧱 技术栈

### 后端 [`backend/`](backend)

| 分类 | 选型 | 版本 |
|---|---|---|
| 语言 | Python | ≥ 3.11（推荐 3.12） |
| Web 框架 | FastAPI + Uvicorn | 0.163.2 / 0.54.0 |
| AI 编排 | LangGraph + LangChain | 1.2.22 / 1.5.0 |
| LLM 适配 | langchain-openai（OpenAI 兼容协议） | 1.8.1 |
| ORM / 迁移 | SQLAlchemy 2（async）+ Alembic | 2.1.9 / 1.20.1 |
| 数据库 | PostgreSQL（生产）/ SQLite（开发兜底） | — |
| 任务队列 | Celery + Redis | 5.7.0 / 8.1.0 |
| 认证 | PyJWT + bcrypt（JWT + API Key） | 2.15.1 / 5.0.0 |
| 校验 | Pydantic / Pydantic-Settings | 2.14.3 / 2.16.3 |
| 日志 | structlog | 26.1.0 |

### 前端 [`frontend/`](frontend)

| 分类 | 选型 |
|---|---|
| 框架 | Next.js 15（App Router）+ React 19 |
| 语言 | TypeScript 5.7 |
| 样式 | Tailwind CSS 3.4 |
| 数据请求 | @tanstack/react-query 5 |
| 包管理 | pnpm |

---

## 🏗️ 架构总览

整个测试流程由 LangGraph 状态图驱动，[graph.py](backend/app/agents/graph.py) 定义节点与路由：

```
                     ┌─(execute_only)─────────────▶ executor ─┐
START ─┬─(full/generate)─▶ case_gen ─▶ review ⏸ ─▶ executor ─┤
       └─(analyze_only)──────────▶ analyzer ─▶ defect ─▶ report ─▶ END
       └─(report_only)───────────────────────────▶ report ─▶ END

执行后：
  executor ─(有失败)─▶ analyzer ─▶ defect_classifier ─▶ report ─▶ END
  executor ─(全通过)───────────────────────────────────▶ report ─▶ END
```

| 节点 | 职责 |
|---|---|
| `case_gen` | 依据 OpenAPI/Swagger 生成测试用例 |
| `review` | 人工审核（`REQUIRE_REVIEW=true` 时在此中断，等待恢复） |
| `executor` | 并发执行用例（`EXECUTOR_CONCURRENCY` 控制并发上限） |
| `analyzer` | 分析失败用例的根因，给出修复建议（无失败不调用，省 Token） |
| `defect_classifier` | 将失败归类为缺陷并自动分类/定级 |
| `report` | 汇总执行结果、生成报告与 Token 用量 |

**运行模式**（`mode`）：`full`（生成 + 执行）/ `execute_only`（只执行已有用例）/ `analyze_only` / `report_only`。

### 开发期降级策略

不依赖任何外部服务即可开发调试，四种能力均可独立切换：

| 能力 | 生产 / 联调 | 开发兜底（无需外部服务） | 配置项 |
|---|---|---|---|
| 关系库 | PostgreSQL 16 | SQLite（本地文件） | `DATABASE_URL` |
| LangGraph 检查点 | PostgresSaver | MemorySaver / SQLiteSaver | `LANGGRAPH_CHECKPOINTER` |
| Celery broker | Redis | 同步执行（eager） | `CELERY_EAGER=true` |
| LLM | 硅基流动真实调用 | 确定性 Mock 桩 | `LLM_MOCK=true` |

---

## 📁 目录结构

```
testforge/
├── backend/                  # FastAPI 后端（Python）
│   ├── app/
│   │   ├── agents/           # LangGraph 多 Agent（状态图、节点、Prompt、LLM 工厂）
│   │   │   └── nodes/        #   生成 / 审核 / 执行 / 分析 / 缺陷 / 报告 节点
│   │   ├── api/v1/           # REST 接口（auth / projects / cases / executions / defects / graph / ci / usage）
│   │   ├── core/             # 配置、安全、日志
│   │   ├── db/models/        # SQLAlchemy 数据模型（项目 / 用例 / 执行 / 缺陷 / 覆盖率 / 用户）
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── services/         # 业务逻辑（执行编排、报告、覆盖率、用量统计）
│   │   └── workers/          # Celery worker / beat 定时调度
│   ├── alembic/              # 数据库迁移
│   ├── tests/                # pytest（unit / agents / api / e2e）
│   │   ├── unit/             #   纯逻辑单元测试
│   │   ├── agents/           #   LangGraph 图与节点测试
│   │   ├── api/              #   接口测试
│   │   └── e2e/              #   端到端全链路测试
│   ├── scripts/              # WSL 环境初始化脚本
│   ├── requirements.txt      # 后端依赖（精确锁定）
│   └── pyproject.toml        # pytest / ruff / mypy 配置
├── frontend/                 # Next.js 15 前端（TypeScript）
│   └── app/                  # 页面：概览 / 项目 / 用例 / 执行 / 缺陷 / 设置
├── docs/                     # 方案与集成文档
│   ├── 00-技术栈方案-V1.md
│   ├── 02-接口清单.md
│   └── 03-CICD集成.md
├── scripts/ci/               # CI 质量门禁脚本（testforge-gate.sh）
└── .github/workflows/        # 本仓库自己的 CI
```

---

## 🚀 快速开始

### 环境要求

- Python ≥ 3.11（推荐 3.12）
- Node.js ≥ 22 与 pnpm ≥ 9
- （可选）PostgreSQL 16 / Redis 7 —— 开发期可不启动，见「开发降级策略」

### 1. 启动后端

```bash
cd backend

# 方式 A：WSL/conda 一键初始化脚本（自动建环境、装依赖、生成 .env、自检）
bash scripts/setup_wsl.sh

# 方式 B：手动安装
conda create -n testforge python=3.12 -y
conda activate testforge
pip install -r requirements.txt
cp .env.example .env         # 按需填写 LLM_API_KEY 等

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> 没有 LLM API Key 也没关系：`.env` 默认 `LLM_MOCK=true`，会走确定性桩数据，全图依然可以跑通。

### 2. 启动前端

```bash
cd frontend
cp .env.example .env.local   # 默认已指向 http://localhost:8000/api/v1
pnpm install
pnpm dev                     # 访问 http://localhost:3000
```

### 3. 访问

| 入口 | 地址 |
|---|---|
| 前端界面 | http://localhost:3000 |
| Swagger 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

---

## ⚙️ 配置说明

所有后端配置均通过环境变量 / `.env` 注入，代码中不出现任何字面量地址，模板见 [backend/.env.example](backend/.env.example)。关键配置：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | 关系库 DSN（`postgresql+asyncpg://` 或 `sqlite+aiosqlite://`） | SQLite |
| `LANGGRAPH_CHECKPOINTER` | 检查点类型：`memory` / `sqlite` / `postgres` | `sqlite` |
| `LLM_PROVIDER` / `LLM_BASE_URL` | LLM 供应商与端点（OpenAI 兼容） | 硅基流动 |
| `LLM_API_KEY` | LLM 密钥（留空自动进入 Mock 模式） | — |
| `LLM_MODEL_LARGE` / `LLM_MODEL_SMALL` | 大/小模型分级（复杂任务走 `large`） | DeepSeek-V3 / Qwen2.5-7B |
| `LLM_MOCK` | 是否启用确定性 Mock 桩 | `true` |
| `CELERY_EAGER` | Celery 同步执行（免 Redis） | `true` |
| `REQUIRE_REVIEW` | 用例生成后是否暂停等待人工审核 | `false` |
| `EXECUTOR_CONCURRENCY` | 用例并发执行上限 | `5` |
| `TOKEN_BUDGET_MONTHLY` / `LLM_RATE_LIMIT_PER_PROJECT` | 月度 Token 预算与单项目限流 | — |

前端配置见 [frontend/.env.example](frontend/.env.example)（`NEXT_PUBLIC_API_BASE`）。

---

## 🧪 测试

后端使用 pytest，测试默认 Mock LLM、使用内存检查点与临时 SQLite，**无需联网**（假 API 由 `httpx.MockTransport` 提供）：

```bash
cd backend
conda activate testforge

pytest                         # 全部测试
pytest tests/unit -m unit      # 纯逻辑
pytest tests/agents -m agents  # LangGraph 图与节点
pytest tests/api -m api        # HTTP 接口
pytest tests/e2e -m e2e        # 端到端全链路
pytest --cov=app --cov-report=term-missing   # 覆盖率
```

代码质量检查（配置见 `pyproject.toml`）：

```bash
ruff check app tests alembic
mypy app
```

> 测试目录约定详见 [backend/tests/README.md](backend/tests/README.md)。

---

## 🔗 CI/CD 集成

TestForge 可作为质量门禁接入你的流水线：测试不通过即构建失败。

1. 在平台创建项目并导入 OpenAPI 文档；
2. 在「设置 → API Key」创建 CI Key（以 `tfg_` 开头，`X-API-Key` 鉴权，无需用户名密码）；
3. 在流水线中调用脚本 [`scripts/ci/testforge-gate.sh`](scripts/ci/testforge-gate.sh)：

```bash
curl -X POST "$TESTFORGE_URL/ci/run" \
  -H "X-API-Key: $TESTFORGE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"<ID>","mode":"execute_only","min_pass_rate":100}' | jq '.gate'
```

支持 `min_pass_rate`（通过率门禁）、`fail_on_defects`（有缺陷即失败）、`mode`（`full` / `execute_only`）等参数。

GitHub Actions / GitLab CI 的完整接入示例见 [docs/03-CICD集成.md](docs/03-CICD集成.md)。

---

## 📚 文档

| 文档 | 说明 |
|---|---|
| [后端接口清单](docs/02-接口清单.md) | 全部 REST 接口说明与五分钟跑通示例 |
| [CI/CD 集成指南](docs/03-CICD集成.md) | 质量门禁接入 GitHub Actions / GitLab CI |
| [技术栈方案 V1](docs/00-技术栈方案-V1.md) | 技术选型与决策记录 |

后端接口交互式文档：启动后访问 `http://localhost:8000/docs`。