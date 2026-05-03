# 基于 RAG 与 Agent 工作流的物流供应链知识库问答系统开发文档

## 0. 项目定位

**项目名称：** 基于 RAG 与 Agent 工作流的物流供应链知识库问答系统  
**英文名：** LogiSupply-RAG-Agent  
**项目目标：** 面向物流、仓储、供应链业务场景，构建一个能回答业务知识、查询订单状态、生成异常处理建议的大模型应用系统。

本项目不追求复杂算法，而是重点展示大模型应用实习岗位常见关键词：

- Dify
- RAG
- 知识库
- Agent
- Workflow
- HTTP Request
- FastAPI
- Prompt Engineering
- 模型评测
- 业务落地

---

## 1. 最小可完成版本

先完成 V1，不要一开始做得太复杂。

### 1.1 V1 功能范围

| 功能 | 用户问题示例 | 技术点 |
|---|---|---|
| 物流知识库问答 | 冷链运输温度异常怎么办？ | Dify Knowledge + RAG |
| 订单状态查询 | 订单 JD2026001 到哪了？ | Dify HTTP Request + FastAPI |
| 异常处理建议 | 订单 JD2026002 延迟了，怎么处理？ | RAG + API 工具调用 + LLM 总结 |
| 效果评测 | 用 50 条问题测试准确率 | Python 脚本 + CSV |

做到这 4 个功能，就够写进实习简历。

---

## 2. 系统架构

```text
用户输入问题
   ↓
Dify Chatflow / Workflow
   ↓
问题分类节点 Question Classifier
   ├── 知识类问题
   │      ↓
   │   Knowledge Retrieval 检索物流知识库
   │      ↓
   │   LLM 根据知识库内容生成答案
   │      ↓
   │   返回答案 + 引用来源
   │
   ├── 订单查询类问题
   │      ↓
   │   Parameter Extractor 提取订单号
   │      ↓
   │   HTTP Request 调用 FastAPI 订单接口
   │      ↓
   │   LLM 整理订单状态
   │      ↓
   │   返回订单状态
   │
   └── 异常处理类问题
          ↓
       提取订单号
          ↓
       调用订单接口获取异常信息
          ↓
       检索异常处理 SOP 知识库
          ↓
       LLM 生成处理建议
          ↓
       返回处理步骤
```

---

## 3. 技术栈

| 模块 | 技术 |
|---|---|
| 大模型应用平台 | Dify |
| 工作流 | Dify Chatflow |
| 知识库 | Dify Knowledge |
| 大模型 | DeepSeek / Qwen / GLM / OpenAI-compatible 模型均可 |
| 后端工具接口 | Python + FastAPI |
| 数据存储 | JSON 模拟订单数据 |
| 文档格式 | Markdown / PDF |
| 部署 | Dify Cloud 或本地 Docker |
| 评测 | Python + CSV |

### 3.1 为什么用 Chatflow

本项目需要多轮对话和分支逻辑，因此建议选择 Dify 的 **Chatflow**，而不是普通 Chatbot。

Chatflow 更适合完成：

- 问题分类
- 知识库检索
- 参数提取
- HTTP 接口调用
- 异常处理分支
- 最终答案生成

---

## 4. 开发方式选择

### 4.1 方案 A：Dify Cloud + FastAPI 公网接口

这是最简单的方式。

你需要完成：

1. 注册并登录 Dify；
2. 在 Dify 中创建知识库；
3. 在 Dify 中搭建 Chatflow；
4. 将 FastAPI 订单接口部署到一个公网地址；
5. 在 Dify 的 HTTP Request 节点里调用公网接口。

适合当前阶段快速完成项目。

### 4.2 方案 B：本地 Docker 部署 Dify

本地部署更像工程项目，但会增加 Docker、端口、网络等问题。

本地部署命令示例：

```bash
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```

然后访问：

```text
http://localhost/install
```

注意：如果 Dify 在 Docker 中运行，Dify 容器不能直接使用 `127.0.0.1` 访问宿主机上的 FastAPI 服务。可以使用宿主机局域网 IP，例如：

```text
http://192.168.x.x:8000
```

如果使用 Dify Cloud，则本地接口不能直接被访问，建议把 FastAPI 部署到公网。

---

## 5. 项目仓库结构

建议 GitHub 仓库名称：

```text
logisupply-rag-agent
```

目录结构：

```text
logisupply-rag-agent/
├── README.md
├── docs/
│   ├── 01_仓储入库流程.md
│   ├── 02_仓储出库流程.md
│   ├── 03_冷链运输规范.md
│   ├── 04_订单延迟处理SOP.md
│   ├── 05_货物破损处理SOP.md
│   ├── 06_退换货处理规则.md
│   ├── 07_客户投诉处理规则.md
│   ├── 08_运输费用计算规则.md
│   ├── 09_库存盘点规范.md
│   └── 10_异常工单升级规则.md
│
├── order_api/
│   ├── main.py
│   ├── orders.json
│   ├── requirements.txt
│   └── README.md
│
├── prompts/
│   ├── rag_system_prompt.md
│   ├── order_query_prompt.md
│   └── exception_solution_prompt.md
│
├── evaluation/
│   ├── test_questions.csv
│   ├── rag_eval.py
│   └── eval_result.csv
│
├── dify/
│   ├── workflow_design.md
│   └── dify_config_notes.md
│
└── screenshots/
    ├── 01_knowledge_base.png
    ├── 02_chatflow_canvas.png
    ├── 03_rag_answer_with_citation.png
    ├── 04_order_api_call.png
    ├── 05_exception_solution.png
    └── 06_eval_result.png
```

---

## 6. 准备物流知识库文档

你不需要使用真实企业内部文档，可以自己整理模拟业务文档。每份文档控制在 **500 到 1500 字**。

### 6.1 文档清单

| 文件名 | 内容 |
|---|---|
| 01_仓储入库流程.md | 预约、到货、验收、质检、上架 |
| 02_仓储出库流程.md | 拣货、复核、打包、交接、出库 |
| 03_冷链运输规范.md | 温控、异常报警、交接记录 |
| 04_订单延迟处理SOP.md | 延迟原因、通知客户、补偿规则 |
| 05_货物破损处理SOP.md | 拍照、登记、赔付、责任判定 |
| 06_退换货处理规则.md | 退货条件、换货流程、时效 |
| 07_客户投诉处理规则.md | 投诉分级、响应时效、升级机制 |
| 08_运输费用计算规则.md | 首重、续重、特殊货物费用 |
| 09_库存盘点规范.md | 盘点周期、差异处理、复盘 |
| 10_异常工单升级规则.md | 普通异常、严重异常、人工升级 |

### 6.2 示例文档：04_订单延迟处理SOP.md

```markdown
# 订单延迟处理SOP

## 1. 适用范围

本规则适用于仓储出库、干线运输、末端配送等环节导致的订单延迟问题。

## 2. 常见延迟原因

订单延迟通常包括以下几类原因：

1. 仓库拣货积压；
2. 商品缺货或库存不一致；
3. 干线运输车辆晚点；
4. 分拨中心分拣异常；
5. 天气、交通管制等不可抗力；
6. 客户地址错误或联系方式异常。

## 3. 处理流程

当订单出现延迟时，客服或运营人员应按照以下流程处理：

1. 查询订单当前物流节点；
2. 判断延迟发生在哪个环节；
3. 预估新的送达时间；
4. 主动通知客户延迟原因和预计送达时间；
5. 如果超过承诺时效，应根据规则判断是否需要补偿；
6. 对严重延迟订单创建异常工单；
7. 必要时升级给人工运营处理。

## 4. 客户沟通话术

建议话术：

您好，经查询您的订单当前处于运输延迟状态，主要原因是干线运输节点出现异常。我们已为您跟进处理，预计新的送达时间为系统显示时间。如给您带来不便，我们深感抱歉。

## 5. 升级规则

如果订单延迟超过 24 小时，应创建普通异常工单。

如果订单延迟超过 48 小时，或客户连续投诉两次以上，应升级为严重异常工单。

如果订单涉及生鲜、冷链、医药等特殊品类，应优先升级处理。
```

---

## 7. FastAPI 订单查询接口开发

这个接口是本项目中最重要的代码贡献。Dify 自己做 RAG 比较容易，但加入 FastAPI 工具接口后，项目更像真实业务系统。

### 7.1 创建目录

```bash
mkdir -p logisupply-rag-agent/order_api
cd logisupply-rag-agent/order_api
```

### 7.2 requirements.txt

```txt
fastapi
uvicorn
pydantic
```

### 7.3 orders.json

```json
[
  {
    "order_id": "JD2026001",
    "customer_name": "张三",
    "status": "运输中",
    "current_node": "北京通州分拨中心",
    "expected_arrival": "2026-05-06",
    "exception_type": "无异常",
    "product_type": "普通商品",
    "last_update": "2026-05-03 10:30:00"
  },
  {
    "order_id": "JD2026002",
    "customer_name": "李四",
    "status": "延迟",
    "current_node": "华北干线运输节点",
    "expected_arrival": "2026-05-07",
    "exception_type": "干线运输延迟",
    "product_type": "普通商品",
    "last_update": "2026-05-03 09:15:00"
  },
  {
    "order_id": "JD2026003",
    "customer_name": "王五",
    "status": "异常",
    "current_node": "冷链仓储中心",
    "expected_arrival": "2026-05-04",
    "exception_type": "温度异常报警",
    "product_type": "冷链商品",
    "last_update": "2026-05-03 11:20:00"
  },
  {
    "order_id": "JD2026004",
    "customer_name": "赵六",
    "status": "异常",
    "current_node": "末端配送站",
    "expected_arrival": "2026-05-05",
    "exception_type": "货物外包装破损",
    "product_type": "电子产品",
    "last_update": "2026-05-03 12:00:00"
  }
]
```

### 7.4 main.py

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json

app = FastAPI(
    title="LogiSupply Order API",
    description="用于 Dify Agent 工作流调用的模拟物流订单查询接口",
    version="1.0.0"
)

DATA_FILE = Path(__file__).parent / "orders.json"


def load_orders():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "logisupply-order-api"
    }


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    orders = load_orders()
    for order in orders:
        if order["order_id"].upper() == order_id.upper():
            return {
                "found": True,
                "order": order
            }

    raise HTTPException(
        status_code=404,
        detail={
            "found": False,
            "message": f"未找到订单：{order_id}"
        }
    )


class ExceptionRequest(BaseModel):
    order_id: str
    user_problem: str | None = None


@app.post("/orders/analyze")
def analyze_order_exception(req: ExceptionRequest):
    orders = load_orders()
    target_order = None

    for order in orders:
        if order["order_id"].upper() == req.order_id.upper():
            target_order = order
            break

    if target_order is None:
        raise HTTPException(
            status_code=404,
            detail={
                "found": False,
                "message": f"未找到订单：{req.order_id}"
            }
        )

    exception_type = target_order["exception_type"]

    if exception_type == "无异常":
        risk_level = "低"
        suggestion = "订单当前无异常，建议告知客户订单正在正常流转。"
    elif "延迟" in exception_type:
        risk_level = "中"
        suggestion = "建议查询延迟节点，预估新的送达时间，并主动通知客户。"
    elif "温度" in exception_type:
        risk_level = "高"
        suggestion = "冷链订单出现温度异常，建议立即升级人工处理，并核查温控记录。"
    elif "破损" in exception_type:
        risk_level = "高"
        suggestion = "建议要求站点上传破损照片，登记异常工单，并根据规则判断赔付责任。"
    else:
        risk_level = "中"
        suggestion = "建议创建异常工单，并交由运营人员进一步处理。"

    return {
        "found": True,
        "order": target_order,
        "risk_level": risk_level,
        "suggestion": suggestion,
        "user_problem": req.user_problem
    }
```

### 7.5 启动接口

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

测试：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/orders/JD2026001
```

浏览器也可以访问：

```text
http://127.0.0.1:8000/docs
```

---

## 8. Dify 知识库配置

### 8.1 创建知识库

在 Dify 中进入：

```text
Knowledge → Create Knowledge → Upload local files
```

上传 `docs/` 目录中的 Markdown 文档。

### 8.2 推荐知识库名称

```text
物流供应链业务知识库
```

### 8.3 Chunk 设置建议

| 配置项 | 建议 |
|---|---|
| Chunk 模式 | General |
| Chunk 长度 | 500-800 tokens |
| Chunk overlap | 50-100 tokens |
| 分隔符 | Markdown 标题、换行 |
| 是否启用自动摘要 | V1 可不启用 |

### 8.4 Index Method 设置

建议选择：

```text
High Quality
```

原因：High Quality 会使用 embedding model 把内容片段转换成向量，更适合语义检索。

### 8.5 Retrieval 设置建议

| 配置项 | 建议值 |
|---|---|
| Retrieval Method | Hybrid Search |
| Top K | 3 或 5 |
| Score Threshold | 0.4-0.5 |
| Rerank | 先不用外部 Rerank，后续再加 |

---

## 9. Dify Chatflow 工作流设计

创建应用：

```text
Studio → Create Application → Chatflow
```

应用名称：

```text
物流供应链智能助手
```

### 9.1 总体节点图

```text
Start
  ↓
Question Classifier
  ├── 知识库问答
  │      ↓
  │   Knowledge Retrieval
  │      ↓
  │   LLM_知识问答
  │      ↓
  │   Answer
  │
  ├── 订单状态查询
  │      ↓
  │   Parameter Extractor_订单号
  │      ↓
  │   HTTP Request_查询订单
  │      ↓
  │   LLM_整理订单状态
  │      ↓
  │   Answer
  │
  ├── 异常处理建议
  │      ↓
  │   Parameter Extractor_订单号
  │      ↓
  │   HTTP Request_分析订单异常
  │      ↓
  │   Knowledge Retrieval_异常SOP
  │      ↓
  │   LLM_生成处理建议
  │      ↓
  │   Answer
  │
  └── 其他问题
         ↓
      LLM_兜底回复
         ↓
      Answer
```

---

## 10. 节点详细配置

### 10.1 Start 节点

默认即可。

用户输入变量通常是：

```text
sys.query
```

---

### 10.2 Question Classifier 节点

节点名称：

```text
问题分类
```

输入变量：

```text
sys.query
```

#### 分类 1：知识库问答

描述：

```text
用户询问物流、仓储、供应链、冷链、退换货、运输费用、投诉处理、库存盘点等业务规则或流程，不涉及具体订单号。
```

示例：

```text
仓储入库流程是什么？
冷链运输温度异常怎么办？
客户投诉物流超时如何处理？
退货需要满足什么条件？
```

#### 分类 2：订单状态查询

描述：

```text
用户想查询某个具体订单的状态、当前位置、预计送达时间，通常包含订单号。
```

示例：

```text
订单 JD2026001 到哪了？
帮我查一下 JD2026002 的状态。
JD2026003 什么时候送达？
```

#### 分类 3：异常处理建议

描述：

```text
用户询问具体订单出现延迟、破损、温控异常、投诉等情况时应该如何处理，通常包含订单号或异常描述。
```

示例：

```text
订单 JD2026002 延迟了怎么处理？
JD2026003 出现温度异常怎么办？
客户投诉 JD2026004 包装破损，应该怎么处理？
```

#### 分类 4：其他问题

描述：

```text
与物流供应链业务无关，或者问题信息不足，无法判断用户意图。
```

---

### 10.3 知识库问答分支

#### 节点 1：Knowledge Retrieval

节点名称：

```text
检索物流知识库
```

配置：

| 配置 | 值 |
|---|---|
| Query | `sys.query` |
| Knowledge | 物流供应链业务知识库 |
| Top K | 3 |
| Score Threshold | 0.4 |

#### 节点 2：LLM_知识问答

System Prompt：

```text
你是一个物流供应链业务助手，负责根据知识库内容回答用户问题。

回答要求：
1. 只能依据提供的知识库上下文回答，不要编造制度、流程或数字。
2. 如果知识库没有相关内容，直接说明“知识库中没有找到明确依据”。
3. 回答要结构化，优先使用条目形式。
4. 如果问题涉及操作流程，请按步骤回答。
5. 如果问题涉及异常处理，请说明处理原因、处理步骤和注意事项。
6. 回答最后加一句：以上内容基于当前知识库资料整理。
```

User Prompt：

```text
用户问题：
{{sys.query}}

请根据知识库上下文回答。
```

Context 选择：

```text
检索物流知识库.result
```

#### 节点 3：Answer

输出：

```text
{{LLM_知识问答.text}}
```

---

### 10.4 订单状态查询分支

#### 节点 1：Parameter Extractor_订单号

节点名称：

```text
提取订单号
```

输入变量：

```text
sys.query
```

参数定义：

| 参数名 | 类型 | 是否必填 | 描述 |
|---|---|---|---|
| order_id | string | 是 | 用户问题中的订单号，例如 JD2026001 |

#### 节点 2：HTTP Request_查询订单

节点名称：

```text
查询订单接口
```

Method：

```text
GET
```

URL：

```text
https://你的公网订单接口域名/orders/{{提取订单号.order_id}}
```

如果是本地开发，URL 可能是：

```text
http://你的局域网IP:8000/orders/{{提取订单号.order_id}}
```

#### 节点 3：LLM_整理订单状态

System Prompt：

```text
你是物流订单客服助手。请根据订单接口返回的 JSON 信息，给用户整理订单状态。

回答要求：
1. 说明订单号、当前状态、当前位置、预计送达时间。
2. 如果 exception_type 是“无异常”，告诉用户订单正常流转。
3. 如果存在异常，提醒用户异常类型，并建议继续查看异常处理建议。
4. 不要编造接口中不存在的信息。
```

User Prompt：

```text
用户问题：
{{sys.query}}

订单接口返回：
{{查询订单接口.body}}

请整理成用户容易理解的中文回复。
```

#### 节点 4：Answer

输出：

```text
{{LLM_整理订单状态.text}}
```

---

### 10.5 异常处理建议分支

这个分支是项目里最能体现 **RAG + Agent 工作流** 的地方。

#### 节点 1：Parameter Extractor_订单号

提取参数：

```text
order_id
```

#### 节点 2：HTTP Request_分析订单异常

Method：

```text
POST
```

URL：

```text
https://你的公网订单接口域名/orders/analyze
```

Headers：

```json
{
  "Content-Type": "application/json"
}
```

Body：

```json
{
  "order_id": "{{提取订单号.order_id}}",
  "user_problem": "{{sys.query}}"
}
```

#### 节点 3：Knowledge Retrieval_异常SOP

节点名称：

```text
检索异常处理SOP
```

Query：

```text
{{sys.query}}
```

Knowledge：

```text
物流供应链业务知识库
```

Retrieval 设置：

| 配置 | 值 |
|---|---|
| Top K | 5 |
| Score Threshold | 0.35 |

#### 节点 4：LLM_生成异常处理建议

System Prompt：

```text
你是物流供应链异常处理助手，负责根据订单接口信息和知识库 SOP 给出处理建议。

回答必须遵守：
1. 先总结订单当前状态和异常类型。
2. 再根据知识库 SOP 给出处理步骤。
3. 如果订单接口信息与知识库 SOP 都不足，必须明确说明信息不足。
4. 不要编造赔付金额、内部系统名称或不存在的规则。
5. 输出格式必须包含：
   - 订单概况
   - 异常判断
   - 建议处理步骤
   - 客户沟通话术
   - 是否需要人工升级
```

User Prompt：

```text
用户问题：
{{sys.query}}

订单接口返回：
{{分析订单异常.body}}

知识库检索结果：
{{检索异常处理SOP.result}}

请生成处理建议。
```

输出示例：

```text
## 订单概况

订单 JD2026002 当前状态为延迟，当前位置为华北干线运输节点，预计送达时间为 2026-05-07。

## 异常判断

该订单异常类型为干线运输延迟，属于中等风险异常。

## 建议处理步骤

1. 查询订单当前物流节点，确认延迟发生在干线运输环节。
2. 预估新的送达时间。
3. 主动通知客户延迟原因和预计送达时间。
4. 如果延迟超过 24 小时，创建普通异常工单。
5. 如果延迟超过 48 小时或客户重复投诉，应升级为严重异常工单。

## 客户沟通话术

您好，经查询您的订单当前处于运输延迟状态，主要原因是干线运输节点出现异常。我们已为您跟进处理，预计新的送达时间为 2026-05-07。如给您带来不便，我们深感抱歉。

## 是否需要人工升级

当前建议先创建普通异常工单；如果超过 48 小时仍未送达，建议升级人工运营处理。
```

---

## 11. Dify 应用设置

### 11.1 开启引用来源

在应用设置里开启：

```text
Citation and Attribution
```

这样回答中会展示知识库来源，有利于体现 RAG 项目效果。

### 11.2 发布应用

完成调试后：

```text
Publish → Web App
```

需要截图：

1. Web App 首页；
2. 用户问知识库问题；
3. 回答带引用来源；
4. 用户查询订单；
5. 用户询问异常处理建议。

---

## 12. 评测集设计

一定要做评测，否则项目容易被认为只是简单搭了一个 Dify 应用。

### 12.1 test_questions.csv

路径：

```text
evaluation/test_questions.csv
```

内容示例：

```csv
id,question,type,expected_keyword
1,仓储入库流程包括哪些步骤？,knowledge,预约 到货 验收 上架
2,冷链运输温度异常怎么办？,knowledge,温度异常 升级 温控记录
3,订单JD2026001当前状态是什么？,order,运输中 北京通州分拨中心
4,订单JD2026002延迟了怎么处理？,exception,干线运输延迟 通知客户 异常工单
5,客户投诉物流超时应该怎么处理？,knowledge,投诉 响应 升级
6,JD2026003出现温度异常如何处理？,exception,冷链 温度异常 人工升级
```

建议准备 50 条：

| 类型 | 数量 |
|---|---:|
| 知识库问答 | 25 |
| 订单查询 | 10 |
| 异常处理 | 15 |

### 12.2 rag_eval.py

这个脚本用于调用 Dify API 做简单评测。

```python
import os
import csv
import time
import requests

DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")

if not DIFY_API_KEY:
    raise RuntimeError("请先设置环境变量 DIFY_API_KEY")

INPUT_FILE = "test_questions.csv"
OUTPUT_FILE = "eval_result.csv"


def ask_dify(question: str) -> str:
    url = f"{DIFY_API_BASE}/chat-messages"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": {},
        "query": question,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "eval-user-001"
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    return data.get("answer", "")


def keyword_hit(answer: str, expected_keyword: str) -> float:
    keywords = [kw.strip() for kw in expected_keyword.split() if kw.strip()]
    if not keywords:
        return 0.0

    hit_count = sum(1 for kw in keywords if kw in answer)
    return hit_count / len(keywords)


def main():
    results = []

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            question = row["question"]
            expected_keyword = row["expected_keyword"]

            print(f"正在评测：{question}")

            try:
                answer = ask_dify(question)
                score = keyword_hit(answer, expected_keyword)
                passed = "是" if score >= 0.5 else "否"
            except Exception as e:
                answer = f"ERROR: {e}"
                score = 0.0
                passed = "否"

            results.append({
                "id": row["id"],
                "question": question,
                "type": row["type"],
                "expected_keyword": expected_keyword,
                "answer": answer.replace("\n", " "),
                "keyword_score": round(score, 2),
                "passed": passed
            })

            time.sleep(1)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "id",
            "question",
            "type",
            "expected_keyword",
            "answer",
            "keyword_score",
            "passed"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    passed_count = sum(1 for r in results if r["passed"] == "是")
    total = len(results)
    print(f"评测完成：{passed_count}/{total} 通过，通过率 {passed_count / total:.2%}")


if __name__ == "__main__":
    main()
```

运行：

```bash
cd evaluation
export DIFY_API_KEY="你的Dify应用APIKey"
python rag_eval.py
```

Windows PowerShell：

```powershell
$env:DIFY_API_KEY="你的Dify应用APIKey"
python rag_eval.py
```

README 中可以写：

```text
构建 50 条物流业务问答测试集，从关键词命中、回答完整性、引用正确性三个维度评估系统效果。初版通过率约 70%，通过调整 TopK、Score Threshold 和 Prompt 模板后，通过率提升到 80% 以上。
```

注意：具体数字必须使用自己实际跑出来的结果，不要乱写。

---

## 13. README 模板

可以直接放到仓库根目录的 README.md 中。

```markdown
# 基于 RAG 与 Agent 工作流的物流供应链知识库问答系统

## 项目简介

本项目面向物流、仓储、供应链业务场景，基于 Dify 构建 RAG 知识库问答与 Agent 工作流系统。系统支持物流业务文档问答、订单状态查询、异常订单处理建议生成，并通过自建测试集对问答效果进行评估。

## 核心功能

- 物流供应链知识库问答
- 知识库答案来源引用
- 订单状态查询工具调用
- 订单异常处理建议生成
- RAG 问答效果评测

## 技术栈

Dify、RAG、Chatflow、Knowledge Retrieval、HTTP Request、FastAPI、Python、Prompt Engineering、CSV 评测

## 系统架构

用户问题进入 Dify Chatflow 后，首先由 Question Classifier 判断问题类型：

- 知识类问题走 Knowledge Retrieval；
- 订单查询类问题调用 FastAPI 订单接口；
- 异常处理类问题同时调用订单接口和知识库 SOP，再由 LLM 生成处理建议。

## 项目目录

见仓库目录结构。

## FastAPI 订单接口

启动方式：

```bash
cd order_api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

接口：

- GET /health
- GET /orders/{order_id}
- POST /orders/analyze

## Dify 工作流

工作流包含以下节点：

- Question Classifier
- Parameter Extractor
- HTTP Request
- Knowledge Retrieval
- LLM
- Answer

## 评测方法

使用 50 条物流业务问题进行测试，统计关键词命中率和回答通过率。

## 项目截图

见 screenshots 目录。
```

---

## 14. 截图清单

简历项目一定要有截图，至少准备 6 张。

| 截图文件名 | 内容 |
|---|---|
| 01_knowledge_base.png | Dify 知识库上传文档页面 |
| 02_chatflow_canvas.png | Dify Chatflow 工作流画布 |
| 03_rag_answer_with_citation.png | 知识库问答 + 引用来源 |
| 04_order_api_call.png | 查询订单状态结果 |
| 05_exception_solution.png | 异常处理建议 |
| 06_eval_result.png | 评测结果 CSV 或终端输出 |

---

## 15. 项目完成标准

| 项目要求 | 是否必须 |
|---|---|
| Dify 知识库能正常检索 | 必须 |
| 用户问流程问题能回答 | 必须 |
| 回答能显示引用来源 | 必须 |
| FastAPI 订单接口能跑 | 必须 |
| Dify 能调用订单接口 | 必须 |
| 能处理订单异常问题 | 必须 |
| 有 50 条评测问题 | 必须 |
| 有 README 和截图 | 必须 |
| 有 Docker 部署 | 可选 |
| 有前端页面 | 不需要 |
| 有模型微调 | 不需要 |
| 有本地大模型部署 | 不需要 |

---

## 16. 开发计划

### 第 1 天：搭建基础环境

完成：

- 注册/登录 Dify；
- 新建 GitHub 仓库；
- 创建项目目录；
- 写 5 份 Markdown 业务文档；
- 写 FastAPI 订单接口。

验收：

```text
FastAPI /health 能返回 ok
/orders/JD2026001 能返回订单信息
```

### 第 2 天：完成知识库

完成：

- 补齐 10 份文档；
- 上传到 Dify Knowledge；
- 设置 High Quality；
- 测试知识库检索。

验收：

```text
问“订单延迟处理流程是什么？”
Dify 能检索到 04_订单延迟处理SOP.md
```

### 第 3 天：完成 Dify Chatflow 主流程

完成：

- 创建 Chatflow；
- 配置 Question Classifier；
- 配置知识库问答分支；
- 配置订单查询分支；
- 配置异常处理分支。

验收：

```text
问“订单JD2026001到哪了？”
系统能调用订单接口并返回状态。
```

### 第 4 天：优化 Prompt 和异常处理

完成：

- 优化知识库问答 Prompt；
- 优化异常处理 Prompt；
- 调整 TopK 和 Score Threshold；
- 开启 Citation and Attribution。

验收：

```text
问“JD2026002延迟了怎么处理？”
系统能结合订单接口和 SOP 输出处理步骤。
```

### 第 5 天：做评测

完成：

- 写 50 条测试问题；
- 跑 rag_eval.py；
- 生成 eval_result.csv；
- 根据错误样例调整 Prompt 和检索参数。

验收：

```text
有评测结果，通过率达到 70% 以上即可。
```

### 第 6 天：整理 GitHub 和截图

完成：

- 写 README；
- 上传截图；
- 整理 prompts；
- 整理 dify/workflow_design.md。

验收：

```text
别人打开你的 GitHub，能看懂项目背景、架构、功能和运行方式。
```

### 第 7 天：写进简历

完成：

- 生成简历项目描述；
- 准备面试讲解稿；
- 准备 3 个演示问题。

---

## 17. 简历写法

### 17.1 项目名称

**基于 RAG 与 Agent 工作流的物流供应链知识库问答系统**

### 17.2 项目描述

面向物流仓储与供应链业务场景，基于 Dify 构建 RAG 知识库问答与 Agent 工作流系统，支持业务文档问答、答案来源引用、订单状态查询和异常订单处理建议生成。使用 FastAPI 实现模拟订单查询接口，并通过自建测试集评估系统问答效果。

### 17.3 技术栈

```text
Dify、RAG、Chatflow、Knowledge Retrieval、HTTP Request、FastAPI、Python、Prompt Engineering、CSV 评测
```

### 17.4 简历 bullet

- 基于 Dify 搭建物流供应链知识库问答系统，上传并结构化处理 10+ 份仓储、运输、冷链、退换货、异常处理 SOP 文档，实现基于 RAG 的业务问答与来源引用。
- 设计 Dify Chatflow 工作流，使用 Question Classifier 区分知识问答、订单查询和异常处理等用户意图，并路由到不同处理分支。
- 使用 FastAPI 开发模拟订单查询接口，并通过 Dify HTTP Request 节点接入工作流，实现订单状态查询和异常订单分析。
- 设计异常处理 Prompt，使系统能够结合订单接口返回信息和知识库 SOP，生成订单延迟、冷链温度异常、货物破损等场景的处理建议。
- 构建 50 条物流业务测试集，对系统回答的关键词命中率、答案完整性和引用准确性进行评估，并根据 badcase 调整 TopK、Score Threshold 和 Prompt 模板。

---

## 18. 面试讲解稿

可以这样讲：

```text
我这个项目是一个物流供应链场景的大模型应用，主要用 Dify 做 RAG 和 Agent 工作流。

用户问题进入系统后，先通过 Question Classifier 判断是知识库问题、订单查询问题还是异常处理问题。

如果是知识类问题，就走 Knowledge Retrieval，从物流业务文档中检索相关片段，再交给 LLM 生成回答，并展示引用来源。

如果是订单查询问题，系统会用 Parameter Extractor 提取订单号，然后通过 HTTP Request 调用我用 FastAPI 写的订单查询接口。

如果是异常处理问题，系统会先查订单状态，再检索异常处理 SOP，最后由 LLM 生成处理步骤和客户沟通话术。

我还做了 50 条测试问题，对回答结果做了简单评测，用来优化 Prompt 和检索参数。
```

---

## 19. 常见问题处理

### 19.1 Dify 调不到本地 FastAPI

原因：

- Dify Cloud 不能访问你电脑上的 `127.0.0.1`；
- 本地 Docker 版 Dify 也不能直接用 `127.0.0.1` 访问宿主机服务。

解决：

- 最简单：把 FastAPI 部署到公网；
- 本地自测：使用宿主机局域网 IP；
- 实在不行：先用 Dify Code 节点模拟订单数据，后面再补 HTTP Request。

### 19.2 知识库回答不准

解决：

- 文档标题写清楚；
- 每份文档不要太长；
- Chunk 控制在 500-800 tokens；
- TopK 从 3 调到 5；
- Score Threshold 从 0.5 降到 0.35；
- Prompt 里明确要求“只根据知识库回答”。

### 19.3 分类错误

解决：

- Question Classifier 的每个分类描述写得更具体；
- 每个分类加 3-5 个示例；
- “异常处理建议”和“订单状态查询”要区分清楚。

### 19.4 简历项目看起来像套壳

解决：强调自己做了以下部分：

1. 整理物流业务文档；
2. 设计 Dify 工作流；
3. 开发 FastAPI 订单接口；
4. 设计 Prompt；
5. 构建评测集；
6. 根据 badcase 优化检索参数。

---

## 20. 最终交付物清单

做完后应该有：

- GitHub 仓库
- Dify Web App 链接
- FastAPI 订单接口代码
- 10+ 份物流知识库文档
- Dify 工作流截图
- RAG 问答截图
- 订单查询截图
- 异常处理截图
- 50 条评测问题
- eval_result.csv
- README.md
- 简历项目描述

---

## 21. 推荐演示问题

### 21.1 知识库问答

```text
仓储入库流程包括哪些步骤？
```

```text
冷链运输出现温度异常时应该怎么处理？
```

### 21.2 订单查询

```text
订单 JD2026001 当前到哪里了？
```

### 21.3 异常处理

```text
订单 JD2026002 延迟了，应该怎么处理？
```

```text
JD2026003 出现温度异常，应该如何处理？
```

---

## 22. 项目注意事项

1. 不要把项目写成“调用大模型 API 的聊天机器人”。
2. 一定要强调 RAG、知识库、Agent 工作流、HTTP 工具调用和评测。
3. 不要写自己没有实现的功能，比如模型微调、本地部署大模型、多模态识别等。
4. 简历里的数字要基于实际结果，例如文档数量、测试集数量、通过率等。
5. 面试时要能讲清楚：问题如何分类、RAG 如何检索、订单接口如何调用、异常处理如何生成。

---

## 23. 最终建议

你的第一版不要追求完美，先按这个文档做出能演示的版本。

这个项目比“简单调 API 聊天机器人”更适合写进实习简历，因为它能对应以下岗位：

- 大模型应用开发实习生
- RAG 开发实习生
- AI Agent 开发实习生
- 知识库产品实习生
- 大模型评测实习生
- AI 产品测试实习生

推荐完成路线：

```text
Dify 知识库问答
→ FastAPI 订单接口
→ Dify HTTP Request 调用接口
→ 异常处理工作流
→ 50 条问题评测
→ README + 截图 + 简历项目描述
```
