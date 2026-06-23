# DeepResearch Multi-Agent Assistant

DeepResearch 是一个基于 FastAPI、LangGraph、LangChain、Qwen 和 Vue3 的多 Agent 深度研究助手。项目支持简单问题直接回答，也支持复杂问题自动完成任务规划、网络检索、本地 RAG 检索、证据裁判、分析归纳、反思补搜和最终报告生成。

## 技术栈

- 后端：Python、FastAPI、Uvicorn、Pydantic
- Agent 编排：LangGraph、LangChain
- 大模型：DashScope / 通义千问 Qwen
- 网络检索：Bocha Web Search
- RAG：DashScope Embedding、Milvus
- 记忆与状态：PostgreSQL、Redis、LangGraph Checkpointer
- 前端：Vue3、TypeScript、Vite

## 运行前准备

推荐环境：

- Python 3.10 或 3.11
- Node.js `^20.19.0` 或 `>=22.12.0`
- Git
- Docker Desktop，完整记忆/RAG 模式才需要

## 配置环境变量

复制模板：

```powershell
copy .env.example .env
```

最小可运行配置：

```env
DASHSCOPE_API_KEY=你的DashScopeKey
MODEL=qwen-plus
BOCHA_API_KEY=你的BochaKey

THREAD_ID=default
USER_ID=default_user
TENANT_ID=default_tenant
MAX_ITERATIONS=2

ENABLE_MEMORY=false
ENABLE_MILVUS=false
CHECKPOINTER_BACKEND=memory
```

说明：

- `DASHSCOPE_API_KEY` 必填，用于调用 Qwen。
- `BOCHA_API_KEY` 用于联网搜索；不填也能启动后端，但网络证据为空。
- 初次运行建议保持 `ENABLE_MEMORY=false`、`ENABLE_MILVUS=false`，这样不依赖 Docker、PostgreSQL、Redis 和 Milvus。

如果页面报错 `Arrearage`，通常表示 DashScope 账号欠费、额度不足或未开通对应模型服务，需要到阿里云百炼/模型服务控制台处理账号状态。

## 安装后端依赖

使用 Conda 创建环境：

```powershell
conda create -n deepresearch python=3.11 -y
conda activate deepresearch
```

安装 Python 依赖：

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

验证依赖：

```powershell
python -m pip check
```

正常输出：

```text
No broken requirements found.
```

## 启动后端

在项目根目录执行：

```powershell
conda activate deepresearch
python app\app_main.py
```

默认后端地址：

```text
http://127.0.0.1:8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

正常返回：

```json
{
  "status": "ok",
  "service": "deepresearch-backend"
}
```

## 安装并启动前端

打开新的终端窗口：

```powershell
cd front\agent_front
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

前端已经在 `front/agent_front/vite.config.ts` 中配置代理：

```text
/api    -> http://127.0.0.1:8000
/health -> http://127.0.0.1:8000
```

因此需要先启动后端，再启动前端。

## 推荐启动顺序

最小版本：

```text
1. 配置 .env
2. 启动后端：python app\app_main.py
3. 启动前端：npm run dev
4. 浏览器打开 http://127.0.0.1:5173
```

完整版本：

```text
1. 启动 PostgreSQL / Redis / Milvus
2. 配置 .env 中的数据库和 Milvus 地址
3. 执行本地文档入库脚本
4. 启动后端
5. 启动前端
```

## 可选：开启完整记忆和本地 RAG

最小版本不需要 Docker。如果要体验完整功能，需要额外启动 PostgreSQL、Redis 和 Milvus。

PostgreSQL 示例：

```powershell
docker run -d --name deepresearch-postgres `
  -p 5432:5432 `
  -e POSTGRES_USER=root `
  -e POSTGRES_PASSWORD=RootPass123 `
  -e POSTGRES_DB=deepresearch `
  -v deepresearch-postgres-data:/var/lib/postgresql/data `
  postgres:16
```

`.env` 示例：

```env
ENABLE_MEMORY=true
CHECKPOINTER_BACKEND=postgres
SHORT_TERM_BACKEND=postgres
LONG_TERM_BACKEND=postgres
POSTGRES_DSN=postgresql://root:RootPass123@127.0.0.1:5432/deepresearch
```

Redis 示例：

```powershell
docker run -d --name deepresearch-redis `
  -p 6379:6379 `
  redis:7 redis-server --requirepass RedisPass123
```

`.env` 示例：

```env
REDIS_URL=redis://:RedisPass123@127.0.0.1:6379
```

Milvus 启动后设置：

```env
ENABLE_MILVUS=true
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=mult_agent_memory
```

本地文档入库脚本：

```text
app/mult_agents/rag/ingest.py
```

运行前需要把脚本中的 `INPUT_PATH` 改成你的本地文档路径，然后执行：

```powershell
python app\mult_agents\rag\ingest.py
```

## 主要接口

```text
GET  /health
POST /api/v1/research/run
POST /api/v1/research/stream
```
