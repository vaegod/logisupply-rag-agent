# 项目协作指南

## 项目概览

本项目用于实现“基于 RAG 与 Agent 工作流的物流供应链知识库问答系统”首版，重点展示 Dify、RAG、Knowledge、Chatflow、HTTP Request、FastAPI、Prompt Engineering 和评测能力。

V1 范围固定为四项能力：

- 物流供应链知识库问答
- 订单状态查询
- 异常处理建议生成
- 基于测试集的问答评测

当前仓库不做前端页面、不做模型微调、不做本地大模型部署。

## 目录约定

- `docs/`：物流业务知识库文档，作为 Dify Knowledge 的上传源
- `order_api/`：FastAPI 模拟订单接口
- `prompts/`：Chatflow 中使用的 Prompt 配置源
- `evaluation/`：测试问题、评测脚本与评测结果输出目录
- `dify/`：知识库参数、工作流拓扑、节点配置与联调说明
- `screenshots/`：项目展示截图

新增文件时，优先放入上述目录，不要在根目录随意堆放业务材料。

## 运行命令

本地开发默认使用 Python 3.13+。

创建虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

启动订单接口：

```powershell
cd order_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

运行评测脚本：

```powershell
$env:DIFY_API_KEY="你的 Dify API Key"
cd evaluation
python rag_eval.py
```

## Dify 配置规则

- 不要把 Dify API Key、模型密钥、隧道 token 等敏感信息提交到仓库。
- 不要在文档、Prompt 或代码里写死临时公网隧道地址。
- Dify Cloud 联调时，只在 `dify/dify_config_notes.md` 中使用占位 URL，并在实际配置时替换。
- Dify UI 中的 Prompt、节点参数和检索阈值一旦调整，必须同步回写到 `prompts/` 或 `dify/` 文档。

## 文档与 Prompt 维护

- `docs/` 下文件名使用 `序号_主题.md` 形式，便于知识库排序与检索。
- 每份业务文档尽量围绕一个主题展开，避免把多个 SOP 混写在一个文件里。
- `prompts/` 中每个 Prompt 文件都要说明适用节点、输入变量和回答约束。
- 如果 Dify 节点的最终版本与仓库中的 Prompt 不一致，以仓库回写后的版本为准。

## 评测与截图

- `evaluation/test_questions.csv` 用于维护测试集，优先扩充真实业务表达方式，而不是只写标准问法。
- `evaluation/eval_result.csv` 是本地输出文件，不纳入版本控制。
- `screenshots/` 至少保留知识库、Chatflow、RAG 回答、订单查询、异常处理、评测结果 6 类截图。

## 提交规范

- 提交信息建议使用简洁中文动词短语，例如：`初始化项目骨架`、`补充订单接口`、`完善 Dify 配置说明`。
- 每次提交尽量围绕单一主题，避免把文档、代码和截图的大量不相关改动混在一起。
- 提交前确认没有把密钥、个人账号信息、临时隧道地址和无关缓存文件带入仓库。

