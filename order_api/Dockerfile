FROM node:24-alpine AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-fund --no-audit
COPY web ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY order_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY order_api /app/order_api
COPY docs /app/docs
COPY --from=frontend /web/dist /app/web/dist
RUN mkdir -p /app/order_api/data
ENV PORT=8018 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8018
CMD ["python", "-m", "order_api.serve"]
