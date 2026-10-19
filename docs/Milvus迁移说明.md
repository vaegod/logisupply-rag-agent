> 2026-10-19 本机部署更新：当前使用本机 Dify 1.17.1、React/FastAPI、SQLite 与 Milvus 3.0.2，模型继续调用 API。根目录 `start-local.ps1` 启动完整项目，入口 http://127.0.0.1:8020；[本地运行说明](本地运行说明.md)。79项后端与3项前端测试和构建通过，真实本地 Dify 工单全流程见 `evaluation/results/local_acceptance.json`。下文旧云端部署、旧接口启动或迁移首轮数字按历史范围保留。

# 物流混合RAG：Qdrant迁移至Milvus

2026-10-19。此说明描述当前工作区的向量存储迁移；新增RAG仍未发布至原Railway/Dify。原Agent、查询接口、React页面、草稿确认、SQLite幂等与工单状态流程保留。

## 迁移范围

- 生产依赖从qdrant-client改为pymilvus 3.0.2，开发/测试额外使用milvus-lite 3.2.2。
- 章节切分、真实BAAI/bge-m3 Embedding（1024维）、BM25、每路12片候选和RRF参数60保持不变。
- Milvus显式定义id（VARCHAR主键）、vector（FLOAT_VECTOR）以及source、title、section、content、corpus_version、embedding_model字段。
- 当前只有53片，使用FLAT＋COSINE精确检索。没有宣称HNSW近似索引、大规模召回或性能提升。
- collection版本增加Milvus存储格式标识，当前文档/模型/维度变化仍形成新版本。相同完整索引可复用，旧Qdrant数据保留作回滚；不是把Qdrant磁盘文件直接挂给Milvus。
- 索引先完成并验证全部Embedding，再写入Milvus，flush后用Strong一致性查询核对count。统计接口可能不计growing segment，因此不将get_collection_stats当精确就绪判断。
- 查询使用MilvusClient.search，COSINE返回结果中的distance按相似度解释，应用保留原0.45最低分过滤。接口实际方式更新为hybrid_bm25_milvus_rrf；降级仍返回chunk_bm25并明确原因。

## 安装与本机配置

在仓库根目录执行，推荐使用隔离环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

开发测试包括真正的Milvus Lite数据库，二维确定性向量仅验证机制；真实语义评测另外调用Embedding API。服务端运行只需要order_api/requirements.txt，不强制安装Lite。

在被Git忽略的.env中设置Embedding配置，并选择以下一种方式：

```text
# 独立Milvus
LOGISUPPLY_MILVUS_URI=http://127.0.0.1:19530
LOGISUPPLY_MILVUS_TOKEN=

# 或本地Milvus Lite
# LOGISUPPLY_MILVUS_URI=order_api/data/milvus.db
```

不要将应用的本地.db路径写入SDK同名环境变量MILVUS_URI。SDK在导入时可能读取该变量并按HTTP服务地址校验；应用因此使用LOGISUPPLY_MILVUS_URI和LOGISUPPLY_MILVUS_TOKEN。不能将旧QDRANT_URL配置误认为已切换成功。

## 独立服务

compose.rag.yml参考官方Standalone部署方式，固定Milvus镜像3.0.2，嵌入etcd、本地数据存储与独立命名卷。仅映射本机19530和19091端口，未暴露etcd端口，也未新建付费云资源。

```powershell
docker compose -p logisupply-milvus -f compose.rag.yml up -d
# 本机引擎在WSL时：
wsl -d Ubuntu-24.04 -- docker compose -p logisupply-milvus -f /mnt/d/大数据开发面试准备_两会话整理/logisupply-rag-agent/compose.rag.yml up -d
.\.venv\Scripts\python.exe -m order_api.rag_index
.\.venv\Scripts\python.exe -m order_api.rag_index --check
```

只有向量服务启动且索引成功，才是语义检索已启用。错误时后端可能仍能返回BM25，必须检查retrieval_method和degraded字段，不能只看到HTTP 200就宣布迁移成功。

## 验证入口

```powershell
.\.venv\Scripts\python.exe -m pytest --junitxml=evaluation/results/milvus_tests.xml
.\.venv\Scripts\python.exe evaluation/hybrid_eval.py
.\.venv\Scripts\python.exe evaluation/hybrid_acceptance.py
# 如需复验真实生成模型，显式传入已有私有配置路径：
.\.venv\Scripts\python.exe evaluation/hybrid_acceptance.py --llm-env <私有配置文件> --model Qwen/Qwen3-14B
```

迁移前结果留在evaluation/results/qdrant_baseline_20261019，Milvus结果以新报告实际执行为准。比较题集仍为25个既有题＋10个改写题，指标为来源文档命中，不是回答准确率；换库本身没有自动提高问答正确率的保证。

原前台用户是匿名浏览器会话，客服是业务定位；操作员独立登录。当前没有企业员工身份或订单ACL。生成模型仍可能漏用工具或误引规则，原确认卡片与固定分支继续控制实际写入。

## 代码阅读顺序

1. RagSettings.from_env：应用配置与SDK变量边界。
2. HybridRetriever.index：定义Schema、FLAT索引、Upsert、Flush。
3. HybridRetriever.ready：加载集合、Strong聚合计数。
4. HybridRetriever.dense：Search、COSINE分数、最低分过滤。
5. HybridRetriever.search：与BM25融合、异常降级、章节来源。
6. tests/test_hybrid_rag.py：真实Lite重开、字段与维度、COSINE分数方向、并发和原工单闭环。

官方依据：[Standalone部署](https://milvus.io/docs/install_standalone-docker.md)、[Milvus Lite](https://milvus.io/docs/milvus_lite.md)、[向量检索](https://milvus.io/docs/single-vector-search.md)、[统计行数限制](https://milvus.io/api-reference/pymilvus/v2.6.x/MilvusClient/Collections/get_collection_stats.md)。
