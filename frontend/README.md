# TestForge 前端

Next.js 15（App Router）+ React 19 + TailwindCSS 的测试平台界面。

> 后端接口清单见 [../docs/02-接口清单.md](../docs/02-接口清单.md)

## 启动

```bash
cd /mnt/e/MyProject/testforge/frontend

cp .env.example .env.local      # 后端地址，默认 http://localhost:8000/api/v1
pnpm install                    # 或 npm install
pnpm dev                        # http://localhost:3000
```

后端要先起：

```bash
cd ../backend && conda activate testforge
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> 后端 `CORS_ORIGINS` 默认已包含 `http://localhost:3000`。若前端跑在别的端口，
> 记得在 `backend/.env` 里加上。

## 页面

| 路由 | 内容 |
|---|---|
| `/login`、`/register` | 登录 / 注册（注册即自动登录） |
| `/dashboard` | 概览：项目数、执行次数、平均通过率、未修复缺陷、最近执行 |
| `/projects` | 项目列表 + 新建（名称、描述、被测地址） |
| `/projects/[id]` | 项目详情：用例 / 执行记录 / 概览三个页签；导入 OpenAPI、运行、设置、归档 |
| `/executions` | 执行记录列表，支持按项目与状态筛选 |
| `/executions/[id]` | 执行详情：报告、逐条结果（可展开错误）、缺陷、审核恢复、导出 JSON |
| `/defects` | 缺陷列表，支持筛选与改状态 |
| `/settings` | 个人资料、API Key、运行环境（读 `/health`） |

## 关键实现说明

| 事情 | 在哪 |
|---|---|
| HTTP 客户端 / 自动刷新 token / 401 跳登录 | `lib/api.ts` |
| 登录态与用户信息 | `lib/auth.tsx` |
| 所有数据请求（React Query hooks） | `lib/queries.ts` |
| 后端类型定义（与 Pydantic 对齐） | `lib/types.ts` |
| 基础组件（Button/Card/Badge/Table 等） | `components/ui/` |
| 图标（内联 SVG，无第三方图标库） | `components/icons.tsx` |

**为什么依赖这么少**：只有 `next`、`react`、`@tanstack/react-query`、`clsx`、`tailwind-merge`。
没有 shadcn CLI、没有组件库、没有图表库——样式直接写 Tailwind，
图标手写 SVG。这样 `pnpm install` 快，也不会被某个包的 breaking change 卡住。

## 交互细节

- **长任务提示**：运行一个 `full` 模式会调用大模型，可能 1~3 分钟。
  点「开始执行」后按钮进入 loading 并提示不要关页面。
- **人工审核**：后端 `REQUIRE_REVIEW=true` 时，执行会停在审核节点，
  执行详情页顶部会出现「确认并继续 / 驳回」。
- **API Key**：完整值只在创建后显示一次，页面提供了复制按钮。
- **请求失败**：所有错误都通过 toast 展示后端返回的 `detail`，不会静默。

## 已知限制

- 没有 SSR 数据预取：所有数据在客户端拉取（登录态存在 localStorage，最简单可靠）。
- 报告目前只能导出 JSON（后端还没做 PDF/Excel）。
- 用例编辑只覆盖名称、方法、路径、期望码、断言；headers/params/body
  会原样保留但暂不支持在界面上改。
