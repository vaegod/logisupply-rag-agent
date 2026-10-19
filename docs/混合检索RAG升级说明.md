> 2026-10-19 本机部署更新：当前使用本机 Dify 1.17.1、React/FastAPI、SQLite 与 Milvus 3.0.2，模型继续调用 API。根目录 `start-local.ps1` 启动完整项目，入口 http://127.0.0.1:8020；[本地运行说明](本地运行说明.md)。79项后端与3项前端测试和构建通过，真实本地 Dify 工单全流程见 `evaluation/results/local_acceptance.json`。下文旧云端部署、旧接口启动或迁移首轮数字按历史范围保留。

# 物流混合检索RAG（当前Milvus版）

2026-10-19。当前主库为Milvus，完整运行、配置、字段设计和验证步骤见[Milvus迁移说明](Milvus迁移说明.md)。先前Qdrant版本留作[历史对照](历史版本/Qdrant混合检索说明_20261019.md)，不再作为当前启动方式。

当前链路：十份SOP按章节切成53片→BAAI/bge-m3生成1024维向量→Milvus显式Schema存储；问题同时做BM25与向量召回→RRF融合→返回正文、文件和章节。业务订单、轨迹、草稿与工单仍在SQLite，Agent与确认边界保持原样。

当前索引为FLAT＋COSINE，采用Strong一致性查询核对完整性；文档、模型、维度、切分与存储版本共同隔离集合。向量服务异常时明确降级到章节BM25，不在用户请求中隐式全库重建。

验证：74项Python回归、3项前端流测试与构建通过；真实Embedding与Milvus的35题固定开发集Top-1来源命中33/35，Top-3为35/35。原整篇BM25分别为28/35、35/35；Milvus与迁移前Qdrant结果一致，这不是跨库性能收益。新模型验收与服务重启结果分别看hybrid_acceptance.json、milvus_server_acceptance.json。

固定开发题不是独立盲测，来源命中不是答案准确率；普通词仍可能召回与用户意图无关的片段，生成层需要核对依据。原模型失败历史保留在qdrant_baseline_20261019与hybrid_failure_history.json。新增RAG当前只在本地验证，原Railway/Dify未重新发布。
