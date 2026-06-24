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

## 启动dockers
打开dockers客户端后在项目根目录执行：

```powershell
docker compose up -d
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