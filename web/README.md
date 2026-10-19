> 2026-10-19 本机部署更新：当前使用本机 Dify 1.17.1、React/FastAPI、SQLite 与 Milvus 3.0.2，模型继续调用 API。根目录 `start-local.ps1` 启动完整项目，入口 http://127.0.0.1:8020；[本地运行说明](../docs/本地运行说明.md)。79项后端与3项前端测试和构建通过，真实本地 Dify 工单全流程见 `evaluation/results/local_acceptance.json`。下文旧云端部署、旧接口启动或迁移首轮数字按历史范围保留。

# 物流异常处理智能助手 · React 前端

React 19 + TypeScript + Vite；FastAPI 同源提供静态资源和浏览器网关。复用已发布 Dify Chatflow、工单数据库及操作员状态机。

## 功能

- `/`：SSE 流式聊天、恢复会话、演示订单上下文、数据库校验的草稿确认卡片。
- `/tickets`：当前浏览器会话创建的工单、进度、解决说明、事件时间线，每 5 秒更新。
- `/operator`：独立口令登录、状态统计、搜索/筛选/分页、状态推进、退回处理、退出登录。
- 加载、空列表、输入校验、模型超时、未完成流、状态冲突和移动端导航均有对应界面。

## 本地开发

```powershell
cd web
npm ci
npm run build
npm test
cd ..
$env:LOGISUPPLY_DB_PATH = "$PWD/order_api/data/logisupply.db"
$env:LOGISUPPLY_TOOL_API_KEY = "<工具服务密钥>"
$env:LOGISUPPLY_ADMIN_API_KEY = "<独立操作员API密钥>"
$env:DIFY_API_KEY = "<已发布应用的API密钥>"
$env:LOGISUPPLY_WEB_OPERATOR_PASSWORD = "<独立随机口令，至少24字符>"
$env:LOGISUPPLY_PUBLIC_URL = "http://127.0.0.1:8018"
python -m order_api.serve
```

访问 http://127.0.0.1:8018 。需要热更新时另开终端运行 `cd web; npm run dev`（默认端口 5173；网关对写请求做来源校验，开发时应通过同源入口，或将 PUBLIC_URL 配置为实际 Vite 地址）。

**真实 Dify 联调时，网关必须与 Dify 工具所连接的后端使用同一个工单数据库。** 本地新数据库无法看到云端 Dify 写入的草稿。可以本地构建/运行测试；完整业务验收使用 Railway 同源部署，或为独立本地 Dify 环境单独配置工具服务。

## 部署

`order_api/Dockerfile` 先构建 React，再把 dist 放入 Python 镜像。沿用原 Railway 服务、8018 端口与 `/data` 持久卷，新增 `DIFY_API_KEY` 与 `LOGISUPPLY_WEB_OPERATOR_PASSWORD` 两个服务端变量。已有 API 路径与 V2 Dify 聊天页继续可用。不要设置 VITE_DIFY_API_KEY 或将任何服务密钥放入前端环境变量。

## 调用链与身份

浏览器 → 同源 `/web/chat` → Dify 已发布 `/chat-messages` SSE → Agent/确认分支 → 原有 `/tools/*` → SQLite。

网关生成随机匿名浏览器会话，Cookie 为 HttpOnly / SameSite=Strict（云端 Secure），服务端只保存 Token 哈希。浏览器传本地会话 ID；网关校验归属后才使用自己保存的 Dify conversation_id，绝不信任浏览器传 user_id。

Dify API 的 `user` 外部标识与 `sys.user_id` 内部标识不同。网关按上游返回、由当前会话发起的 Dify conversation_id 关联 proposals/tickets，从数据库获取实际草稿，不从模型文本正则提取一张可写入的卡片。确认按钮把完整确认短语作为用户的新消息发送，沿用既有确定性建单分支和数据库事务。重复确认仍返回原工单。

操作员使用单独口令换取 8 小时 Cookie，服务端核对角色后调用同一 Tickets.transition。原 X-Admin-Key 仅供原有操作员 API/CLI，浏览器不持有。退出使服务端 Token 失效。状态冲突返回 409，页面刷新后要求操作员核对并重新提交，不静默覆盖。

会话、聊天记录与关联持久化在原 SQLite 中新增 web_* 表；已有业务表不迁移、不覆盖。当前浏览器可恢复自己的历史；原 Dify 页面和其他浏览器的工单不会被自动归入此访客。清理 Cookie 会失去匿名身份；这不是账号系统，也不提供企业级订单 ACL。

## 限制

订单仍是历史演示快照；处理动作是模拟业务。单副本 SQLite，无生产 SLA。访客聊天每会话 10 分钟 15 次、全站 24 小时 300 次，同时最多 4 个流式请求；操作员口令失败 5 次后限流 10 分钟。限流用于控制演示成本，不代表完整防滥用体系。

程序测试对 Dify 使用可控 MockTransport 验证身份差异和故障分支；实际云端与浏览器验收另外记录，不能互相替代。

## V3 首轮部署验收（2026-10-19）

- 在线入口：https://logisupply-api-production.up.railway.app/ ，操作员页为 `/operator`。
- 首轮运行代码固定在 `688d6cb07eb47f460920c2a52f84cd9f549e8ed4`；后续提交仅补充验收材料与注释。
- 49 项 Python 测试、3 项前端流式解析测试、TypeScript 与 Vite 构建通过。
- `evaluation/results/web_cloud_acceptance.json`：真实网关 → Dify → 工单库，重复确认、权限隔离、处理至关闭、旧状态冲突、退出登录均验证；API 验收工单 `T-836e162027693427`。
- `evaluation/results/web_browser_acceptance.json`：实际 React 页面聊天、点击确认、操作员登录/搜索/处理、用户进度同步；工单 `T-2a94b5da13f1814c` 已关闭，4 条事件。处理中经过一次新部署，访客/操作员会话与工单均恢复成功。
- `evaluation/results/web_cloud_acceptance_initial.json` 保留首轮验收记录：脚本错误地假设 V2 持久化探针仍处于 processing，而该工单此前收尾已关闭。核实旧工单和 4 条事件仍完整后修正验收参照，首轮生成的模拟工单也已关闭。
- `evaluation/results/web_layout_acceptance.json`：1440px / 390px 的静态 React DOM 渲染均无横向溢出，已检查截图；移动端交互未单独进行真实设备验收。
- 截图 `screenshots/10_*`、`12_*` 至 `15_*` 来自实际云端页面；`11_*` 是响应式静态渲染检查。

本机操作员访问口令位于 git 忽略目录 `dify/local/操作员访问说明.txt`，不随仓库发布。正式服务的 Dify 密钥仅存在服务端环境变量中。


## 当前视觉版本（2026-10-19）

根据用户反馈重新设计业务工作台，运行代码为 `dbbd5fc2536bf7a624dae66601c3379a9403a013`。采用浅色导航、蓝色操作按钮、统一的字号与状态标签；聊天页增加演示订单快捷填入，窄屏可打开订单信息抽屉；操作员详情在窄屏以抽屉展示，支持遮罩与 Escape 关闭。原工具、确认建单、数据库和鉴权逻辑保持原有行为。

构建与 3 项前端流式测试通过。已在云端验证实际聊天查询、快捷填入与订单信息同步、操作员登录/查看工单/关闭详情/退出，以及原有工单与 4 条事件保留。静态 1440×900 与 390×844 渲染均无横向溢出，输入框保持可见；移动端交互未单独做真实设备验证。报告为 `evaluation/results/redesign_delivery.json`，截图为 `screenshots/16_*` 至 `21_*`，其中 `17_*` 仅为本地静态渲染。
