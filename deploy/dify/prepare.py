"""Prepare a pinned local Dify classic-Agent stack and private runtime config.

The public Compose is derived from Dify 1.17.1's official service definitions.
Credentials are only written below the gitignored dify/local directory.
"""
from __future__ import annotations
import copy
import json
import secrets
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIVATE = ROOT / "dify/local/selfhost"
VERSION = "1.17.1"
UPSTREAM = PRIVATE / f"dify-{VERSION}/docker"
RAW = f"https://raw.githubusercontent.com/langgenius/dify/{VERSION}/docker/"


def fetch(relative):
    local = UPSTREAM / relative
    if local.exists():
        return local.read_text(encoding="utf-8")
    response = httpx.get(RAW + relative, timeout=45, follow_redirects=True)
    response.raise_for_status()
    return response.text


def env_text(values):
    # Generated tokens/URLs have no newlines. Existing API credentials are
    # copied verbatim to a private dotenv, never interpolated into shell code.
    if any("\n" in str(value) or "\r" in str(value) for value in values.values()):
        raise ValueError("Environment values must be single-line")
    return "\n".join(key + "=" + str(value) for key, value in values.items()) + "\n"


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    config_path = PRIVATE / "local-admin.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {key: secrets.token_urlsafe(36) for key in (
            "secret", "db_password", "redis_password", "sandbox_key", "plugin_key", "inner_key",
            "tool_key", "admin_key", "operator_password")}
        config.update(email="admin@example.com", name="LogiSupply local", password="Local9!" + secrets.token_urlsafe(18))
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    text = fetch(".env.example")
    values = {key: value for key, value in dotenv_values(stream=__import__("io").StringIO(text), interpolate=False).items() if value is not None}
    values.update(COMPOSE_PROFILES="postgresql", SECRET_KEY=config["secret"], INIT_PASSWORD="",
                  DB_PASSWORD=config["db_password"], REDIS_PASSWORD=config["redis_password"],
                  CELERY_BROKER_URL="redis://:" + config["redis_password"] + "@redis:6379/1",
                  SANDBOX_API_KEY=config["sandbox_key"], CODE_EXECUTION_API_KEY=config["sandbox_key"],
                  PLUGIN_DAEMON_KEY=config["plugin_key"],
                  PLUGIN_DIFY_INNER_API_KEY=config["inner_key"],
                  CONSOLE_API_URL="http://127.0.0.1:8088", CONSOLE_WEB_URL="http://127.0.0.1:8088",
                  SERVICE_API_URL="http://127.0.0.1:8088", APP_API_URL="http://127.0.0.1:8088",
                  APP_WEB_URL="http://127.0.0.1:8088", FILES_URL="http://127.0.0.1:8088",
                  INTERNAL_FILES_URL="http://api:5001", ENABLE_COLLABORATION_MODE="false",
                  CELERY_WORKER_AMOUNT="1", SERVER_WORKER_AMOUNT="1", SERVER_WORKER_CONNECTIONS="10",
                  VECTOR_STORE="milvus", MILVUS_URI="http://milvus-rag:19530", MILVUS_TOKEN="",
                  SSRF_PROXY_ALLOW_PRIVATE_IPS="172.29.240.0/24", SANDBOX_ENABLE_NETWORK="true",
                  PIP_MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple")
    (PRIVATE / "local-dify.env").write_text(env_text(values), encoding="utf-8")
    source = dotenv_values(ROOT / ".env")
    app_env_path = PRIVATE / "local-app.env"
    existing = dotenv_values(app_env_path) if app_env_path.exists() else {}
    app_values = {"PORT": "8018", "LOGISUPPLY_DB_PATH": "/data/local-logisupply.db",
                  "LOGISUPPLY_PUBLIC_URL": "http://127.0.0.1:8020",
                  "LOGISUPPLY_TOOL_API_KEY": config["tool_key"], "LOGISUPPLY_ADMIN_API_KEY": config["admin_key"],
                  "LOGISUPPLY_WEB_OPERATOR_PASSWORD": config["operator_password"],
                  "DIFY_API_BASE": "http://nginx/v1", "DIFY_API_KEY": existing.get("DIFY_API_KEY", ""),
                  "LOGISUPPLY_ALLOW_LOCAL_DIFY_HTTP": "true", "DIFY_CONSOLE_URL": "http://127.0.0.1:8088",
                  "RAG_MODE": "hybrid", "LOGISUPPLY_MILVUS_URI": "http://milvus-rag:19530",
                  "EMBEDDING_BASE_URL": source.get("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1"),
                  "EMBEDDING_MODEL": source.get("EMBEDDING_MODEL", "BAAI/bge-m3"), "EMBEDDING_DIMENSIONS": "1024",
                  "EMBEDDING_API_KEY": source.get("EMBEDDING_API_KEY", "")}
    app_env_path.write_text(env_text(app_values), encoding="utf-8")
    (PRIVATE / "本机访问说明.txt").write_text(
        "工作台：http://127.0.0.1:8020\n操作员：http://127.0.0.1:8020/operator\n"
        "操作员口令：" + config["operator_password"] + "\n\n"
        "Dify：http://127.0.0.1:8088\n账号：" + config["email"] + "\n密码：" + config["password"]
        + "\n\n此文件只保存在本机，不要提交到 GitHub 或放入截图。\n", encoding="utf-8")
    services = yaml.safe_load(fetch("docker-compose.yaml"))["services"]
    selected = ["init_permissions", "api", "worker", "worker_beat", "web", "db_postgres", "redis", "sandbox", "plugin_daemon", "ssrf_proxy", "nginx"]
    result = {}
    volume_maps = {"/app/api/storage": "app_storage", "/var/lib/postgresql/data": "postgres_data",
                   "/data": "redis_data", "/app/storage": "plugin_data", "/dependencies": "sandbox_dependencies"}
    limits = {"api": "1100m", "worker": "900m", "worker_beat": "500m", "web": "700m",
              "db_postgres": "256m", "redis": "128m", "sandbox": "256m", "plugin_daemon": "800m",
              "ssrf_proxy": "128m", "nginx": "64m"}
    volumes = {}
    for name in selected:
        item = copy.deepcopy(services[name])
        item.pop("profiles", None)
        item.pop("ports", None)
        item["networks"] = ["default"]
        if "env_file" in item:
            item["env_file"] = ["../../dify/local/selfhost/local-dify.env"]
        dependencies = item.get("depends_on", {})
        if isinstance(dependencies, dict):
            item["depends_on"] = {k: v for k, v in dependencies.items() if k in selected}
        elif dependencies:
            item["depends_on"] = [k for k in dependencies if k in selected]
        new_volumes = []
        for value in item.get("volumes", []):
            target = value.split(":")[1]
            if target in volume_maps:
                volume = volume_maps[target]
                volumes[volume] = {}
                new_volumes.append(volume + ":" + target)
            elif name == "ssrf_proxy":
                file = value.split(":")[0].split("/")[-1]
                new_volumes.append("./ssrf_proxy/" + file + ":" + target + ":ro")
        item["volumes"] = new_volumes
        if name in limits:
            item["mem_limit"] = limits[name]
        if name == "nginx":
            item.pop("entrypoint", None)
            item["volumes"] = ["./nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
            item["ports"] = ["127.0.0.1:8088:80"]
        result[name] = item
    volumes["business_data"] = {"name": "logisupply-dify_business_data", "external": True}
    result["logisupply-api"] = {"build": {"context": "../..", "dockerfile": "order_api/Dockerfile",
                                            "args": {"PIP_INDEX_URL": "https://pypi.tuna.tsinghua.edu.cn/simple"}},
        "image": "logisupply-api:local", "env_file": ["../../dify/local/selfhost/local-app.env"],
        "ports": ["127.0.0.1:8020:8018"], "volumes": ["business_data:/data"],
        "networks": ["default"], "mem_limit": "800m", "restart": "unless-stopped"}
    compose = {"services": result, "volumes": volumes,
               "networks": {"default": {"name": "logisupply-local", "ipam": {"config": [{"subnet": "172.29.240.0/24"}]}}}}
    (HERE / "compose.yml").write_text("# Derived from official Dify 1.17.1; classic Agent services only.\n" + yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")
    proxy = HERE / "ssrf_proxy"
    proxy.mkdir(exist_ok=True)
    for file in ("squid.conf.template", "squid-common.conf.template", "docker-entrypoint.sh"):
        (proxy / file).write_text(fetch("ssrf_proxy/" + file), encoding="utf-8")
    print("Prepared local Dify 1.17.1 and app config; credentials saved privately, not displayed.")


if __name__ == "__main__":
    main()
