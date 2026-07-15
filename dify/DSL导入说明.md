# Dify DSL 导入说明

## 文件

`logisupply_chatflow.dify.yml` 使用 Dify App DSL `0.3.1` 结构，包含以下完整节点和连线：

- Start
- Question Classifier
- 两个 Knowledge Retrieval
- 两个 Parameter Extractor
- 两个 HTTP Request
- 四个业务 LLM 节点
- 四个 Answer 节点

## 导入后必须完成的配置

DSL 不保存工作区凭证、模型配置和知识库内部 ID。导入后按顺序完成：

1. 为问题分类、参数提取和四个 LLM 节点选择当前工作区可用的模型。
2. 在两个 Knowledge Retrieval 节点中选择由 `docs/` 十份 SOP 创建的知识库。
3. 将两个 HTTP Request 节点中的 `https://replace-me.example.com` 替换为 Dify 可访问的订单 API 地址。
4. 分别调试知识问答、订单查询、异常建议和兜底四条分支。
5. 发布 Chatflow 后再运行 `evaluation/rag_eval.py`。

## 兼容边界

该文件依据 Dify 官方仓库当前 `0.3.1` Chatflow 测试夹具和节点字段生成，并通过本仓库 YAML 与图结构测试。由于本地没有用户的 Dify 工作区、模型插件和知识库 ID，不能声称已在目标工作区完成导入验证；如果 Dify Cloud 升级后提示字段迁移，请在界面导入后重新保存一次 DSL。
