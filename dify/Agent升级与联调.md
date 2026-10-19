# 物流智能体 V2：配置、运行与验收

V1 `logisupply_chatflow.dify.yml` 是原预定义工作流，保留作对照。V2 `logisupply_agent.dify.yml` 使用 Dify 经典 Agent / Function Calling，前端继续使用 Dify 自带聊天页面。模板中的模型、API 工具 provider ID 和地址需要工作区绑定，不表示已完成云端联调。

## 本地运行

在仓库根目录执行：

```powershell
python -m pip install -r requirements-dev.txt
python -m order_api.run_demo
```

服务默认监听 `127.0.0.1:8018`。首次运行在 `dify/local/runtime.json` 生成不同的工具密钥与操作员密钥；该目录被 Git 忽略。数据库位于 `order_api/data/logisupply.db`，已启用 WAL。启动时只补充缺失的演示数据，不覆盖数据库中已有订单和工单。

`http://127.0.0.1:8018/health` 检查健康状态，`/docs` 可查看接口，`/agent-openapi.json` 只导出工具接口，不包含操作员接口。V2 启动器不暴露 V1 无鉴权的订单路由。

订单沿用原四条历史模拟数据，轨迹只保存原来已知的节点快照，不伪造承运商轨迹或延迟原因。Agent 必须明确数据为历史演示快照。

## 工具与数据库

| 工具 | 行为 |
|---|---|
| query_order | 从 SQLite 获取订单事实 |
| query_tracking | 从 SQLite 获取已知轨迹事件 |
| search_sop | 在原十份 SOP 上做文档级 BM25，返回内容与文件名 |
| prepare_ticket | 生成草稿、30分钟有效期和一次确认短语；有未关闭工单则返回原工单 |
| query_ticket | 按用户和订单/工单号查询进度及事件 |
| create_ticket | 只由顶层确认分支调用，不加入 Agent 工具列表 |

V2 的 SOP 工具采用本地 BM25，方便工具独立运行和无密钥回归；不等同于 V1 Dify Knowledge 的混合检索。后续可将 search_sop 替换成 Knowledge Retrieval Workflow 工具，Agent 其他工具无需改变。

数据库包含 orders、tracking、proposals、tickets 和 ticket_events。SQL 参数化执行；建单使用 `BEGIN IMMEDIATE`、草稿唯一约束及同用户同订单的未关闭工单唯一索引，重复请求和并发确认不会重复建单。

## 为什么确认分支独立

普通问题进入 Agent，模型根据结果自主选工具和决定是否继续。用户请求建单时，Agent 只能生成并展示草稿。

用户下一条消息必须是服务返回的完整短语，例如 `确认创建工单 P-0123456789abcdef`。顶层 Code 节点只检查当前 `sys.query`，符合格式才通过 HTTP 请求提交原文、草稿号、`sys.user_id` 和 `sys.conversation_id`。后端再次检查草稿所属用户、会话和有效期。

`create_ticket` 不出现在 Agent 工具列表中，模型输出、历史消息或泛泛的“好的”不会触发写入。原文确认重放只返回已有工单。**鉴权信任边界是后端与已授权的 Dify 服务，用户/会话字段由顶层流程固定传递；此演示并未接入企业用户身份和订单访问权限系统。**

## 在现有 Dify 应用上升级

1. 导出现有应用 DSL 保存备份。原应用可继续保留已发布版本，在草稿中升级。
2. 将后端部署到 Dify Cloud 可访问的 HTTPS 地址。本机 `127.0.0.1` 不能供 Dify Cloud 访问；临时隧道和稳定服务器是不同部署选择。
3. 集成 → 工具 → Swagger API 作为工具，导入 `agent_tools.openapi.json`。将 `servers[0].url` 替换为实际后端地址。鉴权选择请求头 / Custom，键为 `X-API-Key`，值为工具密钥。不要给 Dify 操作员密钥。
4. 安装官方 Agent 策略，选择经典 Agent / FunctionCalling。使用已有支持工具调用的模型；原工作区模型 provider 可从备份 DSL 查看。
5. 在现有画布空白处右键 → 导入应用 → 选择 V2 DSL → 覆盖并导入。这会更新当前应用草稿，继续使用原应用 ID；先保存原备份，验证后再发布。
6. 模板 provider ID 为占位符。直接在 Agent 中重新添加刚才创建的 query_order、query_tracking、search_sop、prepare_ticket 和 query_ticket 五个工具，核对参数绑定；不要添加 create_ticket。
7. user_id、conversation_id 关闭自动生成，分别用变量选择器绑定 `sys.user_id`、`sys.conversation_id`；其余参数开启自动生成。设置最大迭代8次，历史窗口20轮。不要用字符串占位符冒充变量。
8. 环境变量 `ORDER_API_BASE` 填后端地址，`LOGISUPPLY_TOOL_API_KEY` 类型为 secret，填工具密钥。确认 HTTP 节点直接使用 gate.body，没有 LLM 参数重写。
9. 预览核对下面的验收场景；确认通过后发布，继续使用原 Dify Web App。

本地可通过生成器一次填好工作区标识，输出留在不提交的 `dify/local/`：

```powershell
python dify/build_agent.py --provider-id '<API工具provider ID>' --model-provider '<模型provider>' --model '<模型名>' --agent-plugin-id '<官方策略完整插件标识>' --api-base 'https://<工具后端地址>'
```

生成器不会嵌入密钥；导入后仍须在 Dify 填入 secret 环境变量。模型/插件/provider ID 均可通过界面配置后导出 DSL 获取。

节点 ID 使用字母、数字和下划线。Dify 模板变量不能使用带连字符的节点 ID，否则可能把 `{{#node-name.text#}}` 当普通文本输出。本地模板回归检查和真实 Dify 预览均验证此项。

## 工单闭环演示

1. 聊天：“JD2026002 延迟了怎么处理？帮我准备异常工单。”
2. 核对 Agent 实际查询了订单与 SOP，展示了草稿和确认短语，没有声称已建单。
3. 发送完整确认短语，返回新工单号和 open 状态。
4. 操作员在仓库根目录执行（替换实际工单号）：

```powershell
python -m order_api.operator T-<实际ID> --expected open --status processing --note '运营开始核实延迟节点'
python -m order_api.operator T-<实际ID> --expected processing --status resolved --note '已核实节点并通知客户处理结果'
python -m order_api.operator T-<实际ID> --expected resolved --status closed --note '客户确认收到结果，关闭工单'
```

每一步之后在原聊天中问工单进度，Agent 调用 query_ticket 获取真实数据库记录。支持 resolved → processing 重新处理；closed 为终态，不能任意跳步。重新处理时清除旧解决说明，历史说明仍保留在事件中。

操作员接口仅接受独立 `X-Admin-Key`。CLI 默认本机地址，可读取本地密钥文件；远程操作必须显式设置操作员环境变量。演示命令只记录模拟处理结果，不表示真的联系承运商或客户。

## 部署

服务工厂读取 `LOGISUPPLY_DB_PATH`、`LOGISUPPLY_TOOL_API_KEY`、`LOGISUPPLY_ADMIN_API_KEY` 和 `LOGISUPPLY_PUBLIC_URL`。工具与操作员密钥必须不同；未设置时相应接口返回503。

```powershell
docker build -f order_api/Dockerfile -t logisupply-agent:local .
docker run --rm -p 8018:8018 -v logisupply-data:/data -e LOGISUPPLY_DB_PATH=/data/logisupply.db -e LOGISUPPLY_TOOL_API_KEY -e LOGISUPPLY_ADMIN_API_KEY -e LOGISUPPLY_PUBLIC_URL logisupply-agent:local
```

先在启动终端设置上述环境变量。TLS/域名由服务器反向代理提供。数据库必须挂载持久卷，不能把容器文件层当作持久存储。服务不自动加载 `.env`。

云端托管配置和实际 Dify 验收顺序见 [云端部署说明](../docs/云端部署说明.md)。

## 验收与证据

本地运行 `python -m pytest -q` 和 `python evaluation/offline_eval.py --check`。测试覆盖订单存储、SOP来源、草稿确认、过期/跨会话拒绝、并发幂等、完整状态流转、重启保留、角色接口分离，以及确认分支不会使用模型文本。

在线手工场景见 `evaluation/agent_cases.json`。通过 Dify 预览的执行日志确认模型实际选择的工具、参数、返回结果及迭代次数，不能用本地接口测试替代 Agent 效果证据。尚未执行的场景须保持 pending。

启动本地演示服务后，可运行 `python evaluation/agent_local_acceptance.py`，经真实 HTTP 调用完成查询、草稿、拒绝模糊确认、正式确认、幂等和操作员关闭流程，报告写入 `evaluation/results/agent_local_acceptance.json`。该脚本会创建并关闭一条明确标注的模拟工单，不调用模型，也不代表 Dify 联调结果。
