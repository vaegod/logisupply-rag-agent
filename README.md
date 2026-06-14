# 基于 RAG 与 Agent 工作流的物流供应链知识库问答系统

## 项目简介

本项目面向物流、仓储、供应链业务场景，基于 Dify 构建 RAG 知识库问答与 Agent 工作流系统。系统支持物流业务文档问答、订单状态查询、异常订单处理建议生成，并通过自建测试集对问答效果进行评估。

项目聚焦业务落地与工程可复现性，重点展示以下能力：

- 物流供应链知识库问答
- 知识库答案引用来源展示
- 订单状态查询工具调用
- 异常订单处理建议生成
- 基于测试集的评测与优化

## 核心功能

### 1. 物流知识库问答

用户可以直接询问仓储、运输、冷链、退换货、盘点、异常工单升级等业务规则，系统从 Dify Knowledge 检索相关文档片段，再由大模型整理成结构化答复。

### 2. 订单状态查询

当问题中包含订单号时，Dify Chatflow 会提取订单号，调用 `FastAPI` 订单接口，并将接口返回的 JSON 整理成客服可直接使用的中文回复。

### 3. 异常处理建议

当订单出现延迟、温度异常、破损等问题时，系统会结合订单接口结果与知识库中的 SOP 文档，生成处理步骤、客户沟通话术和是否需要人工升级的建议。

### 4. 问答效果评测

仓库提供测试问题集和评测脚本，用于批量调用 Dify API，统计关键词命中和通过率，辅助优化 Prompt 与检索参数。

## 技术栈

- Dify
- RAG / Knowledge Retrieval
- Dify Chatflow / Agent Workflow
- FastAPI
- Python
- Markdown 知识库
- CSV 测试集与评测脚本

## 系统架构

```text
用户输入问题
   ↓
Dify Chatflow
   ↓
Question Classifier
   ├── 知识库问答 → Knowledge Retrieval → LLM → Answer
   ├── 订单状态查询 → 参数提取 → HTTP Request → LLM → Answer
   ├── 异常处理建议 → 参数提取 → HTTP Request → Knowledge Retrieval → LLM → Answer
   └── 其他问题 → LLM 兜底 → Answer
```

## 项目目录

```text
.
├── README.md
├── docs/          # 物流业务知识库与项目展示文档
├── order_api/     # FastAPI 订单工具接口
├── prompts/       # Dify LLM 节点 Prompt
├── evaluation/    # 测试集与评测脚本
├── dify/          # Dify 工作流配置说明
└── screenshots/   # 项目展示截图
```

## FastAPI 订单接口

本地启动：

```powershell
cd order_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

接口列表：

- `GET /health`
- `GET /orders?order_id=...`
- `GET /orders/{order_id}`
- `POST /orders/query`
- `POST /orders/analyze`

启动后可访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Dify 工作流

建议在 Dify 中创建 `Chatflow` 应用，包含以下节点：

- `Question Classifier`
- `Knowledge Retrieval`
- `Parameter Extractor`
- `HTTP Request`
- `LLM`
- `Answer`

详细节点说明、Prompt 配置和联调替换项见：

- [workflow_design.md](dify/workflow_design.md)
- [dify_config_notes.md](dify/dify_config_notes.md)
- [chatflow_setup_checklist.md](dify/chatflow_setup_checklist.md)

推荐配置与已验证结果：

- 知识库问答分支：`Hybrid Search`、`Top K = 5`、`Score Threshold = 0.35`
- 异常处理建议分支：`Hybrid Search`、`Top K = 5`、`Score Threshold = 0.35`、`Rerank = Qwen/Qwen3-Reranker-8B`
- 订单查询与异常处理分支通过 Dify `HTTP Request` 节点调用 `FastAPI` 订单接口
- 订单查询分支最终推荐使用 `POST /orders/query` + JSON Body，避免 Dify 在 GET URL 路径/查询参数拼接时出现兼容问题

已验证通过的问题：

- `冷链运输温度异常怎么办？`
- `订单 JD2026001 到哪了？`
- `订单 JD2026002 延迟了怎么处理？`

## 评测方法

仓库提供：

- `evaluation/test_questions.csv`：基础测试问题集
- `evaluation/rag_eval.py`：调用 Dify API 的评测脚本

运行方式：

```powershell
$env:DIFY_API_KEY="<DIFY_API_KEY>"
cd evaluation
python rag_eval.py
```

评测结果默认输出到 `evaluation/eval_result.csv`。

说明：

- 仓库不保存 `DIFY_API_KEY`，运行前需通过环境变量注入。
- 运行 `rag_eval.py` 前，请先在 Dify 中发布当前 Chatflow 应用；未发布状态下，Dify API 会返回 `Workflow not published`。
- 当 Dify Prompt 或检索参数调整后，建议重新跑一次小样本验证，再批量执行 `rag_eval.py`。

## 部署与联调说明

- Dify Cloud 不能直接访问本机 `127.0.0.1`，订单接口需要使用 Dify 可访问的 HTTP 地址。
- 本地开发可通过临时隧道暴露 `order_api` 的 `8000` 端口；长期演示建议部署到稳定公网地址。
- 如接口域名变化，需要同时替换订单查询与异常处理分支中的两个 HTTP URL。
- Dify 在 HTTP URL、POST Body 和 LLM Prompt 中，优先使用变量插入器，不要依赖手写 `{{...}}` 模板字符串。
- 每次在 Dify UI 中调整 Prompt、检索参数或节点结构后，应同步回写到仓库。

## 项目展示文档

- [项目展示说明](docs/项目展示说明.md)
- [项目实现说明](docs/项目实现说明.md)
- [技术问答](docs/技术问答.md)
