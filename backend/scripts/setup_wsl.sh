#!/usr/bin/env bash
# =============================================================================
# TestForge 后端环境初始化（在 WSL 里执行）
#
#   cd /mnt/e/MyProject/testforge/backend
#   bash scripts/setup_wsl.sh
#
# 幂等：重复执行只会补齐缺失的依赖/配置。
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

MIRROR="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
ENV_NAME="${CONDA_ENV_NAME:-testforge}"

info()  { printf '\033[36m[setup]\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[warn ]\033[0m %s\n' "$*"; }
fail()  { printf '\033[31m[fail ]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. 检查 conda
# ---------------------------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
  fail "找不到 conda。请先初始化 miniconda（source ~/miniconda3/bin/activate）再运行本脚本。"
fi

# ---------------------------------------------------------------------------
# 2. 创建 / 复用 conda 环境
# ---------------------------------------------------------------------------
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  info "复用已有 conda 环境: $ENV_NAME"
else
  info "创建 conda 环境: $ENV_NAME (python=3.12)"
  conda create -n "$ENV_NAME" python=3.12 -y
fi

# 让后续命令跑在该环境里
eval "$(conda shell.bash hook)"
conda activate "$ENV_NAME"

PY_VER="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
info "Python 版本: $PY_VER"
case "$PY_VER" in
  3.11|3.12|3.13) ;;
  *) fail "需要 Python 3.11+（LangChain 1.x 要求），当前 $PY_VER" ;;
esac

# ---------------------------------------------------------------------------
# 3. 安装依赖
# ---------------------------------------------------------------------------
python -m pip install --upgrade pip -i "$MIRROR"
info "安装 requirements.txt（首次约 1~3 分钟）"
python -m pip install -r requirements.txt -i "$MIRROR"

# ---------------------------------------------------------------------------
# 4. 生成 .env
# ---------------------------------------------------------------------------
if [ -f .env ]; then
  info ".env 已存在，保留不动"
else
  cp .env.example .env
  info "已从 .env.example 生成 .env —— 请手动填 LLM_API_KEY / 数据库地址"
fi

# ---------------------------------------------------------------------------
# 5. 自检：关键模块能否导入
# ---------------------------------------------------------------------------
info "导入自检..."
python - <<'PY'
import importlib, sys

checks = [
    "langgraph",
    "langgraph.checkpoint.memory",
    "langgraph.checkpoint.postgres.aio",
    "langgraph.checkpoint.sqlite.aio",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langsmith",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "celery",
    "redis",
    "psycopg",
    "psycopg_pool",
    "httpx",
    "jwt",
    "bcrypt",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "app.main",
]
failed = []
for name in checks:
    try:
        importlib.import_module(name)
        print(f"  ok   {name}")
    except Exception as exc:
        failed.append((name, exc))
        print(f"  FAIL {name}: {type(exc).__name__}: {exc}")

if failed:
    print(f"\n{len(failed)} 个模块导入失败")
    sys.exit(1)
print("\n全部模块导入成功")
PY

# ---------------------------------------------------------------------------
# 6. 打印后续命令
# ---------------------------------------------------------------------------
cat <<'EOF'

-------------------------------------------------------------
环境就绪。常用命令（都在 backend/ 目录下执行）：

  conda activate testforge
  cp .env.example .env            # 首次；然后填 LLM_API_KEY

  # 启动服务
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  # 打开 http://localhost:8000/docs

  # 跑测试
  pytest
  pytest tests/unit -m unit
  pytest tests/agents -m agents

  # 建表迁移（生产用它替代 AUTO_CREATE_TABLES）
  alembic revision --autogenerate -m "init"
  alembic upgrade head
-------------------------------------------------------------
EOF
