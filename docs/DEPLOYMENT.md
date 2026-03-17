# 部署说明（Docker Compose）

## 1. 前置条件
- Docker >= 24
- Docker Compose Plugin >= 2.20

## 2. 环境变量准备
```bash
cp .env.example .env
```

如需调整端口，可修改 `.env`：
- `BACKEND_PORT`：后端对外端口（默认 `8000`）
- `FRONTEND_PORT`：前端对外端口（默认 `8080`）

## 3. 启动服务
```bash
docker compose up -d --build
```

## 4. 验证
- 前端页面：`http://127.0.0.1:${FRONTEND_PORT}`
- 后端健康检查：`http://127.0.0.1:${BACKEND_PORT}/health`

可查看容器日志：
```bash
docker compose logs -f backend frontend
```

## 5. 停止与清理
```bash
docker compose down
```

如需连同镜像清理：
```bash
docker compose down --rmi local
```

## 6. 本地开发（非容器）
### 后端
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

本地开发默认通过 Vite 代理 `/api` 到 `VITE_BACKEND_TARGET`（默认 `http://127.0.0.1:8000`）。
