# AI档案室 🗂️

> 把自己的文档变成 24 小时在线的 AI 助手：上传即问，回答必带出处。

微信小程序 · 私人知识库问答（RAG）· 免费 + 广告变现

---

## 📁 目录结构

```
H:\AI\AI档案室\
├── README.md            # 本文件
├── docs/                # 📄 文档（PRD 唯一权威：docs/PRD.md）
├── backend/             # 🐍 FastAPI 后端
│   ├── app/             #   主代码（config/db/models/schemas/auth）
│   │   ├── routers/     #   API 路由（docs/chat/quota）
│   │   └── services/    #   核心服务（parser/chunker/embedding/retrieval/llm/processor）
│   ├── tests/           #   测试（parser/chunker/api）
│   ├── requirements.txt #   依赖
│   ├── docker-compose.yml # 可选：容器化 PG（镜像源问题，建议用本地 apt 装）
│   └── .env.example     #   环境变量模板
├── miniprogram/         # 📱 微信小程序前端（8 页面）
│   └── pages/           #   chat(会话/对话) + docs(文档库/详情/上传) + mine(我的/额度/隐私)
├── scripts/             # 🔧 脚本（setup_db / start_backend）
└── data/                # 💾 运行数据（不入 git）
```

## 🚀 本地启动（开发环境）

```bash
# 1. 安装数据库（需要 sudo，只需一次）
sudo bash scripts/setup_db.sh

# 2. 配置密钥
cd backend && cp .env.example .env
#    编辑 .env 填入 LLM_API_KEY（DeepSeek）和 EMBEDDING_API_KEY（硅基流动 BGE-M3）

# 3. 启动后端
bash scripts/start_backend.sh        # → http://127.0.0.1:8000 （/health 验证）

# 4. 跑测试
cd backend && ./.venv/bin/python -m pytest tests/ -v

# 5. 小程序
#    用微信开发者工具导入 miniprogram/ 目录（已关闭域名校验，可直连本机后端）
```

## 🧪 当前状态（2026-08-09 晚，M1 进行中）

| 模块 | 状态 |
|------|:---:|
| PRD v1.0 | ✅ 定稿 |
| 后端代码（上传/解析/分块/向量化/混合检索/SSE 流式问答） | ✅ 已写 |
| 小程序前端 8 页面 | ✅ 已写 |
| 单元测试（parser/chunker） | ✅ 已写 |
| API 集成测试 | ✅ 已写 |
| 依赖安装 | ⏳ 进行中 |
| PostgreSQL + pgvector | ⏳ 待执行 setup_db.sh |
| 端到端验证（需 API key） | ⏳ 待 Tom 提供 key |

## 🔑 关键决策（详见 PRD §0）

- 后端：自建 FastAPI ｜ 向量库：PostgreSQL + pgvector ｜ 模型：DeepSeek + BGE-M3
- 流式输出：必须（SSE）｜ 知识库：v1 单库 ｜ 额度：10 文档/100MB/20 轮每天
- 合规：工具类目上架，AI 内容打标，多租户数据隔离
