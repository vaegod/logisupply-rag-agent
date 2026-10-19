"""Initialize only this project's local Dify, register tools and publish its DSL.

No requests are sent to Dify Cloud or Railway. Model credentials are read from
private local configuration and stored through the local Dify console API.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import httpx
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dify.build_agent import build

PRIVATE = ROOT / "dify/local/selfhost"
CONSOLE = "http://127.0.0.1:8088/console/api"
TOOL_BASE = "http://logisupply-api:8018"


def items(value, names=("plugins", "data", "list")):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in names:
            if key in value:
                found = items(value[key], names)
                if found:
                    return found
    return []


def write_env(path, values):
    path.write_text("\n".join(k + "=" + str(v or "") for k, v in values.items()) + "\n", encoding="utf-8")


def main():
    config_path = PRIVATE / "local-admin.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    app_env_path = PRIVATE / "local-app.env"
    app_env = dotenv_values(app_env_path)
    private_source = dotenv_values(ROOT / ".env")

    with httpx.Client(base_url=CONSOLE, timeout=120, headers={"Origin": "http://127.0.0.1:8088"}) as client:
        def request(method, path, **kwargs):
            token = next((v for k, v in client.cookies.items() if k.endswith("csrf_token")), None)
            if token:
                client.headers["X-CSRF-Token"] = token
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                # Full diagnostics may contain credentials; retain them only in
                # the ignored directory and print just endpoint/status.
                (PRIVATE / "last-console-error.json").write_text(response.text, encoding="utf-8")
                raise RuntimeError(f"Local Dify console {method} {path}: HTTP {response.status_code}; see private diagnostics")
            return response.json() if response.content else {}

        if request("GET", "/setup").get("step") == "not_started":
            request("POST", "/setup", json={key: config[key] for key in ("email", "name", "password")})
            print("Local Dify administrator initialized.", flush=True)
        request("POST", "/login", json={"email": config["email"],
                "password": base64.b64encode(config["password"].encode()).decode(), "remember_me": True})

        plugin_ids = ["langgenius/agent", "langgenius/siliconflow"]
        installations = items(request("POST", "/workspaces/current/plugin/list/installations/ids", json={"plugin_ids": plugin_ids}))
        installed_ids = {x.get("plugin_id"): x.get("plugin_unique_identifier") for x in installations}
        missing_ids = [x for x in plugin_ids if not installed_ids.get(x)]
        versions = (request("POST", "/workspaces/current/plugin/list/latest-versions",
                            json={"plugin_ids": missing_ids}).get("versions", {}) if missing_ids else {})
        required = {}
        for plugin in plugin_ids:
            version = installed_ids.get(plugin) or (versions.get(plugin) or {}).get("unique_identifier")
            if not version:
                raise RuntimeError("Official plugin version not available: " + plugin)
            required[plugin] = version
        missing = [required[x] for x in plugin_ids if not installed_ids.get(x)]
        if missing:
            request("POST", "/workspaces/current/plugin/install/marketplace", json={"plugin_unique_identifiers": missing})
            print("Installing official Agent and SiliconFlow plugins…", flush=True)
            for _ in range(100):
                data = items(request("POST", "/workspaces/current/plugin/list/installations/ids", json={"plugin_ids": plugin_ids}))
                installed_ids = {x.get("plugin_id"): x.get("plugin_unique_identifier") for x in data}
                if all(installed_ids.get(x) for x in plugin_ids):
                    break
                time.sleep(3)
            else:
                raise RuntimeError("Local Dify plugin installation did not finish; inspect plugin daemon logs")

        provider = "langgenius/siliconflow/siliconflow"
        providers = items(request("GET", "/workspaces/current/model-providers"))
        silicon = next((x for x in providers if x.get("provider") == provider), None)
        if silicon is None:
            (PRIVATE / "provider-diagnostics.json").write_text(json.dumps(providers, ensure_ascii=False), encoding="utf-8")
            raise RuntimeError("SiliconFlow provider not visible after plugin installation")
        if not config.get("model_credential_configured"):
            key = private_source.get("LLM_API_KEY") or private_source.get("EMBEDDING_API_KEY")
            if not key:
                raise RuntimeError("Configure LLM_API_KEY or EMBEDDING_API_KEY in the private .env")
            request("POST", f"/workspaces/current/model-providers/{provider}/credentials",
                    json={"credentials": {"api_key": key}, "name": "Local project API"})
            config["model_credential_configured"] = True
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        tool_name = "LogiSupply Local Tools"
        tools = items(request("GET", "/workspaces/current/tool-providers", params={"type": "api"}))
        existing = next((x for x in tools if x.get("id") == config.get("tool_provider_id") or
                         x.get("name") == tool_name or x.get("provider") == tool_name), None)
        api_spec = httpx.get("http://127.0.0.1:8020/agent-openapi.json", timeout=15).json()
        api_spec["servers"] = [{"url": TOOL_BASE}]
        if existing is None:
            request("POST", "/workspaces/current/tool-provider/api/add", json={"provider": tool_name,
                    "schema_type": "openapi", "schema": json.dumps(api_spec, ensure_ascii=False),
                    "credentials": {"auth_type": "api_key_header", "api_key_header": "X-API-Key", "api_key_value": config["tool_key"]},
                    "icon": {"content": "🚚", "background": "#E4FBCC"}})
            tools = items(request("GET", "/workspaces/current/tool-providers", params={"type": "api"}))
            existing = next((x for x in tools if x.get("name") == tool_name or x.get("provider") == tool_name), None)
        if not existing:
            (PRIVATE / "tool-diagnostics.json").write_text(json.dumps(tools, ensure_ascii=False), encoding="utf-8")
            raise RuntimeError("Local tool provider could not be located")
        tool_id = existing["id"]
        config["tool_provider_id"] = tool_id
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        dsl, _ = build(tool_id, provider, "Qwen/Qwen3-14B", required["langgenius/agent"], TOOL_BASE)
        dsl["app"]["name"] = "物流异常处理智能助手"
        for variable in dsl["workflow"]["environment_variables"]:
            if variable["name"] == "LOGISUPPLY_TOOL_API_KEY":
                variable["value"] = config["tool_key"]
        content = yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)
        (PRIVATE / "local-agent.dify.yml").write_text(content, encoding="utf-8")
        payload = {"mode": "yaml-content", "yaml_content": content}
        if config.get("app_id"):
            payload["app_id"] = config["app_id"]
        result = request("POST", "/apps/imports", json=payload)
        if result.get("status") == "pending":
            result = request("POST", f"/apps/imports/{result['id']}/confirm", json={})
        app_id = result.get("app_id")
        if not app_id:
            (PRIVATE / "import-diagnostics.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            raise RuntimeError("Local workflow import did not return an app ID")
        config["app_id"] = app_id
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        request("POST", f"/apps/{app_id}/workflows/publish", json={"marked_name": "local-milvus"})
        if not app_env.get("DIFY_API_KEY") or config.get("app_api_key_app_id") != app_id:
            key = request("POST", f"/apps/{app_id}/api-keys", json={})["token"]
            app_env["DIFY_API_KEY"] = key
            write_env(app_env_path, app_env)
            config["app_api_key_app_id"] = app_id
        config.update(app_id=app_id, tool_provider_id=tool_id, plugins=required)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print("Local Dify workflow published; application key saved privately. Restart only the local app to load it.")


if __name__ == "__main__":
    main()
