# GeoAnalysis Agent 🏙️

> **悉尼 109 个行政区的空间资源分析对话式 AI Agent**
>
> 底层：PostgreSQL + PostGIS 硬数据底座（纯 SQL 可复现评分）
> 上层：smolagents CodeAgent（自然语言→空间分析→建议）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库连接
cp config.yaml config.local.yaml
# 编辑 config.local.yaml，填入你的 PostgreSQL + PostGIS 连接信息

# 3. 导入数据（参考 notebooks/Final-DATA2001+assignment.ipynb）
python data_warehouse/setup.py  # 一键建表 + 索引 + 视图

# 4. 启动对话界面
python dashboard/gradio_app.py
# 打开浏览器 http://localhost:7860
```

## 项目结构

```
geoanalysis-agent/
│
├── data_warehouse/              # ═══ 硬数据底座 ═══
│   ├── schema.sql               # 11 张表 DDL
│   ├── views.sql                # Z-Score + Sigmoid RAI 评分视图
│   ├── indexes.sql              # GiST 空间索引
│   ├── connection.py            # SQLAlchemy 连接管理
│   └── loaders/                 # 8 类数据源 ETL
│
├── src/                         # ═══ Agent 层 ═══
│   ├── agent.py                 # CodeAgent 组装入口
│   ├── config.py                # 配置加载器
│   ├── tools/                   # @tool 业务 Skill
│   │   ├── resource_gap_detector.py
│   │   ├── spatial_accessibility.py
│   │   ├── recommendation_generator.py
│   │   └── search_suburb_report.py
│   ├── rag/                     # 知识库与检索
│   │   ├── report_generator.py  # 区域报告自动生成
│   │   ├── chunker.py           # "区域+维度"切分
│   │   ├── vector_store.py      # ChromaDB 操作
│   │   ├── retriever.py         # 语义+空间增强检索
│   │   └── query_rewriter.py    # 同义词扩展
│   ├── mcp/
│   │   └── postgis_server.py    # PostGIS MCP Server
│   ├── session/
│   │   └── session_manager.py   # 多轮对话管理
│   ├── eval/
│   │   ├── evaluator.py         # LLM-as-Eval
│   │   └── final_answer_checks.py
│   └── app.py                   # FastAPI 后端
│
├── dashboard/
│   └── gradio_app.py            # Gradio 对话界面
│
├── notebooks/
│   └── Final-DATA2001+assignment.ipynb  # 数据分析原始 Notebook
│
├── tests/
│   └── test_core.py
│
├── config.yaml                  # 全局配置
├── requirements.txt
└── README.md
```

## 架构

```
用户自然语言
    │
    ▼
┌─ GradioUI / FastAPI ─────────────────────────────┐
│                                                   │
│  ┌─ CodeAgent (smolagents) ────────────────────┐ │
│  │  ReAct Loop: Think → Generate Code → Execute │ │
│  │                                              │ │
│  │  @tool 工具集:                               │ │
│  │  ├─ resource_gap_detector   (读 RAI 评分)    │ │
│  │  ├─ spatial_accessibility   (缓冲区查询)     │ │
│  │  ├─ recommendation_generator (规则+润色)     │ │
│  │  ├─ search_suburb_report    (RAG 检索)       │ │
│  │  └─ [MCP] PostGIS 空间原语                   │ │
│  │                                              │ │
│  │  执行环境: E2B / Docker 沙箱                 │ │
│  └──────────────────────────────────────────────┘ │
│                                                   │
│  ┌─ SessionManager ─────────────────────────────┐ │
│  │  多轮对话 | 指代消解 | 上下文注入              │ │
│  └──────────────────────────────────────────────┘ │
└────────────────────┬──────────────────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │                                 │
    ▼                                 ▼
┌────────────┐              ┌─────────────────┐
│ ChromaDB   │              │ PostgreSQL       │
│ 436 chunk  │              │ + PostGIS        │
│ 知识库     │              │ 11 表 + 评分视图  │
└────────────┘              └─────────────────┘
```

## 模型切换

```python
# 一行配置切换模型
model = LiteLLMModel(model_id="anthropic/claude-sonnet-4-6")   # Claude
model = LiteLLMModel(model_id="deepseek/deepseek-chat")         # DeepSeek (1/10 成本)
model = LiteLLMModel(model_id="openai/gpt-4o")                 # OpenAI
model = LiteLLMModel(model_id="ollama_chat/qwen2.5:7b",        # 本地免费
                     api_base="http://localhost:11434")
```

## 迭代开发

| Iter | 内容 | 状态 |
|------|------|------|
| 0 | 数据底座 + RAI 评分（Notebook） | ✅ |
| 1 | 知识库 + RAG 空间增强检索 | ✅ |
| 2 | CodeAgent + MCP + 业务 Skill | ✅ |
| 3 | 多轮对话 + 幻觉控制 + 歧义处理 | ✅ |
| 4 | GradioUI + 多模型 + LLM-as-Eval | ✅ |

## 许可

MIT
