#!/usr/bin/env bash
# AI档案室 — 本地 PostgreSQL + pgvector 一键安装（需要 sudo）
# 用法: sudo bash scripts/setup_db.sh
set -euo pipefail

echo "==> 安装 PostgreSQL 16 + pgvector"
apt-get update -qq
apt-get install -y postgresql-16 postgresql-16-pgvector

echo "==> 启动服务"
service postgresql start || pg_ctlcluster 16 main start || true

echo "==> 创建用户与数据库"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='aiarchive'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER aiarchive WITH PASSWORD 'aiarchive_dev_pw';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='aiarchive'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE aiarchive OWNER aiarchive;"

echo "==> 开启 vector 扩展"
sudo -u postgres psql -d aiarchive -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "==> 验证"
sudo -u postgres psql -d aiarchive -c "SELECT extversion FROM pg_extension WHERE extname='vector';"

echo "✅ 完成！DATABASE_URL=postgresql+psycopg2://aiarchive:aiarchive_dev_pw@localhost:5432/aiarchive"
