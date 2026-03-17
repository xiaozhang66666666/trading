# Frontend（T1-01）

## 作用
提供 `T1-01` 的操作界面：
- 搜索 QQQ/TQQQ/ETH
- 加入/删除自选
- 展示市场类型（美股/Crypto）
- 展示数据状态与会话信息
- 展示数据源状态

## 启动
```bash
cd frontend
npm install
npm run dev
```

可选环境变量：
- `VITE_API_BASE`，默认 `/api`
- `VITE_BACKEND_TARGET`，仅本地 dev 代理使用，默认 `http://127.0.0.1:8000`

## Docker
```bash
docker build -t multi-asset-frontend ./frontend
docker run --rm -p 8080:80 multi-asset-frontend
```
