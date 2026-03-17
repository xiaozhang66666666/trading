# Backend（T1-01）

## 作用
提供 `T1-01 标的管理与数据源接入` 所需 API：
- 标的搜索
- 添加/删除自选
- 数据源状态
- 市场会话信息（盘前/正常盘/盘后/休市，Crypto 7x24）

## 启动
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker
```bash
docker build -t multi-asset-backend ./backend
docker run --rm -p 8000:8000 multi-asset-backend
```

## 关键接口
- `GET /api/v1/symbols/search?q=QQQ`
- `GET /api/v1/watchlist`
- `POST /api/v1/watchlist` body: `{ "symbol": "ETH" }`
- `DELETE /api/v1/watchlist/ETH`
- `GET /api/v1/data-sources/status`
