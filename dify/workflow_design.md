# Dify Chatflow 工作流设计

## 应用建议

- 应用类型：`Chatflow`
- 应用名称：`物流供应链智能助手`

## 总体节点图

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
  │   LLM_生成异常处理建议
  │      ↓
  │   Answer
  │
  └── 其他问题
         ↓
      LLM_兜底回复
         ↓
      Answer
```

## 节点说明

### Start

- 默认输入变量：`sys.query`

### Question Classifier

建议配置 4 个分类：

1. 知识库问答
2. 订单状态查询
3. 异常处理建议
4. 其他问题

分类描述与示例可直接参考 `dify_config_notes.md`。

### 知识库问答分支

- `Knowledge Retrieval`
  - Query：`sys.query`
  - Knowledge：`物流供应链业务知识库`
  - Top K：`5`
  - Score Threshold：`0.35`
- `LLM_知识问答`
  - Prompt 来源：`prompts/rag_system_prompt.md`
  - 如果当前 Dify 版本未暴露 `result` 字段，直接在提示词中插入 `上下文`

### 订单状态查询分支

- `Parameter Extractor_订单号`
  - 必填参数：`order_id`
- `HTTP Request_查询订单`
  - Method：`POST`
  - URL：`https://<order-api-domain>/orders/query`
  - Body：JSON + 变量插入器传入 `order_id`
- `LLM_整理订单状态`
  - Prompt 来源：`prompts/order_query_prompt.md`

### 异常处理建议分支

- `Parameter Extractor_订单号`
  - 必填参数：`order_id`
- `HTTP Request_分析订单异常`
  - Method：`POST`
  - URL：`https://<order-api-domain>/orders/analyze`
  - Body 使用 JSON + 变量插入器传入 `order_id` 和 `user_problem`
- `Knowledge Retrieval_异常SOP`
  - Query：`sys.query`
  - Knowledge：`物流供应链业务知识库`
  - Top K：`5`
  - Score Threshold：`0.35`
- `LLM_生成异常处理建议`
  - Prompt 来源：`prompts/exception_solution_prompt.md`
  - 知识检索输出如显示为 `上下文`，直接引用该变量

### 其他问题分支

可以使用简短兜底 Prompt，例如：

```text
你是物流供应链助手。如果用户问题与物流业务无关，或者缺少必要信息，请礼貌说明当前系统仅支持物流知识问答、订单查询和异常处理建议，并提示用户补充订单号或问题背景。
```

## Answer 节点输出

- 知识库问答：`{{LLM_知识问答.text}}`
- 订单状态查询：`{{LLM_整理订单状态.text}}`
- 异常处理建议：`{{LLM_生成异常处理建议.text}}`
- 其他问题：`{{LLM_兜底回复.text}}`
