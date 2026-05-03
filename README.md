# 基于 RAG 与 Agent 工作流的物流供应链知识库问答系统

## 项目简介

本项目面向物流、仓储、供应链业务场景，基于 Dify 构建 RAG 知识库问答与 Agent 工作流系统。系统支持物流业务文档问答、订单状态查询、异常订单处理建议生成，并通过自建测试集对问答效果进行评估。

项目首版聚焦业务落地与工程可复现性，重点展示以下能力：

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
├── AGENTS.md
├── README.md
├── docs/
├── order_api/
├── prompts/
├── evaluation/
├── dify/
├── screenshots/
└── 基于RAG与Agent工作流的物流供应链知识库问答系统_开发文档.md
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
- `GET /orders/{order_id}`
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

- [workflow_design.md](/D:/简历项目/dify/workflow_design.md)
- [dify_config_notes.md](/D:/简历项目/dify/dify_config_notes.md)
- [chatflow_setup_checklist.md](/D:/简历项目/dify/chatflow_setup_checklist.md)

## 评测方法

仓库提供：

- `evaluation/test_questions.csv`：基础测试问题集
- `evaluation/rag_eval.py`：调用 Dify API 的评测脚本

运行方式：

```powershell
$env:DIFY_API_KEY="你的 Dify API Key"
cd evaluation
python rag_eval.py
```

评测结果默认输出到 `evaluation/eval_result.csv`。

## 截图清单

建议至少准备以下 6 张截图用于 GitHub 展示与简历说明：

- `01_knowledge_base.png`：Dify 知识库上传页面
- `02_chatflow_canvas.png`：Dify Chatflow 工作流画布
- `03_rag_answer_with_citation.png`：知识库问答与引用来源
- `04_order_api_call.png`：订单查询结果
- `05_exception_solution.png`：异常处理建议
- `06_eval_result.png`：评测输出或结果表

## 后续联调建议

- Dify Cloud 不能直接访问本机 `127.0.0.1`，本地联调建议使用临时公网隧道。
- 临时隧道地址只用于开发调试，不要写入仓库长期文档的正式接口地址位置。
- 每次在 Dify UI 中调整 Prompt、检索参数或节点结构后，记得同步回写到仓库。
