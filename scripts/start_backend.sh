#!/usr/bin/env bash
# AI档案室 — 本地启动后端
# 用法: bash scripts/start_backend.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"

# 首次安装依赖
if [ ! -d .venv ]; then
  echo "==> 创建虚拟环境"
  python3 -m venv .venv
fi

echo "==> 安装/校验依赖"
./.venv/bin/pip install -q -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

echo "==> 检查 .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  已生成 .env，请填写 LLM_API_KEY / EMBEDDING_API_KEY 后重启"
fi

echo "==> 启动 FastAPI (http://127.0.0.1:8000)"
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
