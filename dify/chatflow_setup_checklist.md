# Dify Chatflow 搭建清单

本清单面向首版联调，默认使用 `Dify Cloud + 本地 FastAPI + 临时公网隧道` 方案。建议边搭边截图，后续可以直接放进 `screenshots/`。

## 1. 创建知识库

进入：

```text
Knowledge → Create Knowledge → Upload local files
```

执行步骤：

1. 新建知识库，名称填写 `物流供应链业务知识库`。
2. 上传 `docs/` 目录下的 10 份 Markdown 文档。
3. `Index Method` 选择 `High Quality`。
4. `Chunk Mode` 选择 `General`。
5. `Chunk Length` 先设置为 `500-800 tokens`。
6. `Chunk Overlap` 先设置为 `50-100 tokens`。
7. 完成后先测试一次检索，确认能够命中 `04_订单延迟处理SOP.md`、`03_冷链运输规范.md` 等文档。

建议截图：

- 知识库创建完成页
- 文档上传成功页

## 2. 创建 Chatflow 应用

进入：

```text
Studio → Create Application → Chatflow
```

建议应用名：

```text
物流供应链智能助手
```

创建后先不要急着发布，先把所有节点连起来再逐个调试。

## 3. 配置 Start 节点

`Start` 节点保持默认即可。

关键点：

- 输入变量默认使用 `sys.query`
- 不需要额外添加用户输入字段

## 4. 配置 Question Classifier

节点命名建议：

```text
问题分类
```

输入变量：

```text
sys.query
```

创建 4 个分类：

### 分类 1：知识库问答

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

### 分类 2：订单状态查询

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

### 分类 3：异常处理建议

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

### 分类 4：其他问题

描述：

```text
与物流供应链业务无关，或者问题信息不足，无法判断用户意图。
```

## 5. 搭建知识库问答分支

按顺序新增：

```text
Knowledge Retrieval → LLM → Answer
```

### Knowledge Retrieval

- 节点名：`检索物流知识库`
- Query：`sys.query`
- Knowledge：`物流供应链业务知识库`
- Top K：`3`
- Score Threshold：`0.4`
- Retrieval Method：`Hybrid Search`

### LLM_知识问答

- Prompt 来源：`prompts/rag_system_prompt.md`
- Context 选择：`检索物流知识库.result`

### Answer

输出：

```text
{{LLM_知识问答.text}}
```

联调问题：

```text
冷链运输温度异常怎么办？
仓储入库流程包括哪些步骤？
```

## 6. 搭建订单状态查询分支

按顺序新增：

```text
Parameter Extractor → HTTP Request → LLM → Answer
```

### Parameter Extractor_订单号

- 节点名：`提取订单号`
- 输入变量：`sys.query`
- 参数名：`order_id`
- 类型：`string`
- 是否必填：`是`
- 描述：`用户问题中的订单号，例如 JD2026001`

### HTTP Request_查询订单

- 节点名：`查询订单接口`
- Method：`GET`
- URL：

```text
https://你的临时隧道域名/orders/{{提取订单号.order_id}}
```

说明：

- 先在本地启动 `order_api`
- 再用临时隧道把 `8000` 端口映射到公网
- 只在 Dify UI 中替换地址，不把真实隧道域名写回仓库

### LLM_整理订单状态

- Prompt 来源：`prompts/order_query_prompt.md`

### Answer

输出：

```text
{{LLM_整理订单状态.text}}
```

联调问题：

```text
订单 JD2026001 到哪了？
JD2026002 预计什么时候送达？
```

## 7. 搭建异常处理建议分支

按顺序新增：

```text
Parameter Extractor → HTTP Request → Knowledge Retrieval → LLM → Answer
```

### Parameter Extractor_订单号

- 直接复用订单查询分支的 `order_id` 提取逻辑

### HTTP Request_分析订单异常

- Method：`POST`
- URL：

```text
https://你的临时隧道域名/orders/analyze
```

- Headers：

```json
{
  "Content-Type": "application/json"
}
```

- Body：

```json
{
  "order_id": "{{提取订单号.order_id}}",
  "user_problem": "{{sys.query}}"
}
```

### Knowledge Retrieval_异常SOP

- 节点名：`检索异常处理SOP`
- Query：`sys.query`
- Knowledge：`物流供应链业务知识库`
- Top K：`5`
- Score Threshold：`0.35`
- Retrieval Method：`Hybrid Search`

### LLM_生成异常处理建议

- Prompt 来源：`prompts/exception_solution_prompt.md`

### Answer

输出：

```text
{{LLM_生成异常处理建议.text}}
```

联调问题：

```text
订单 JD2026002 延迟了怎么处理？
JD2026003 出现温度异常怎么办？
客户投诉 JD2026004 包装破损，应该怎么处理？
```

## 8. 搭建其他问题分支

新增一个普通 `LLM` 节点作为兜底回复。

System Prompt 可使用：

```text
你是物流供应链助手。如果用户问题与物流业务无关，或者缺少必要信息，请礼貌说明当前系统仅支持物流知识问答、订单查询和异常处理建议，并提示用户补充订单号或问题背景。
```

测试问题：

```text
今天天气怎么样？
帮我看看这个订单。
```

第二个问题的重点是检查它是否会提醒用户补充订单号。

## 9. 应用设置与发布前检查

发布前建议确认：

1. 已开启引用来源展示。
2. 知识问答分支能返回引用片段。
3. 订单查询分支能正常访问临时隧道地址。
4. 异常处理分支能同时使用接口结果和 SOP 检索结果。
5. 所有 Prompt 最新版本都已经同步回仓库。

## 10. 推荐截图顺序

建议按以下顺序保存截图：

1. `01_knowledge_base.png`
2. `02_chatflow_canvas.png`
3. `03_rag_answer_with_citation.png`
4. `04_order_api_call.png`
5. `05_exception_solution.png`
6. `06_eval_result.png`

