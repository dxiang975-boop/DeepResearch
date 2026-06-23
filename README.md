# DeepResearch Multi-Agent Assistant

## 运行前准备

### 1. 安装 Python

```powershell
conda create -n deepresearch python=3.11 -y
conda activate deepresearch
```

### 2. 安装 Node.js

```text
Node.js ^20.19.0 或 >=22.12.0
```

## 配置环境变量
最小可运行配置如下：

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

REDIS_URL=
POSTGRES_DSN=
MILVUS_HOST=
MILVUS_PORT=19530
MILVUS_COLLECTION=mult_agent_memory
```

## 安装后端依赖

```powershell
conda activate deepresearch
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 启动后端
在项目根目录执行：

```powershell
conda activate deepresearch
python app\app_main.py
```

## 安装并启动前端

进入前端目录deep_research\deep_research\front\agent_front：

```powershell
deep_research\deep_research\front\agent_front
npm install
npm run dev
```

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

### PostgreSQL

```powershell
docker run -d --name deepresearch-postgres `
  -p 5432:5432 `
  -e POSTGRES_USER=root `
  -e POSTGRES_PASSWORD=RootPass123 `
  -e POSTGRES_DB=deepresearch `
  -v deepresearch-postgres-data:/var/lib/postgresql/data `
  postgres:16
```

### Redis

Redis 是可选项。如果使用 PostgreSQL 做 checkpointer 和记忆存储，可以先不启 Redis。

```powershell
docker run -d --name deepresearch-redis `
  -p 6379:6379 `
  redis:7 redis-server --requirepass RedisPass123
```

`.env` 示例：

```env
REDIS_URL=redis://:RedisPass123@127.0.0.1:6379
```

### Milvus

Milvus 用于本地知识库向量检索。启动 Milvus 后设置：

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
