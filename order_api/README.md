# Order API

本目录提供给 Dify Chatflow 调用的模拟物流订单接口。

## 启动方式

```powershell
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 接口

- `GET /health`
- `GET /orders?order_id=JD2026001`
- `GET /orders/{order_id}`
- `POST /orders/query`
- `POST /orders/analyze`

## 本地测试

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/orders/JD2026001
curl "http://127.0.0.1:8000/orders?order_id=JD2026001"
curl -Method POST -Uri http://127.0.0.1:8000/orders/query -ContentType application/json -Body '{"order_id":"JD2026001"}'
```

联调 Dify Cloud 时，请通过临时公网隧道把本地 `8000` 端口暴露出去，并在 Dify 的 HTTP Request 节点中替换占位 URL。
