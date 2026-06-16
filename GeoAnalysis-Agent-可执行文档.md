# GeoAnalysis Agent —— 可执行文档

> **版本**: v1.0 | **日期**: 2026-06-16 | **定位**: 面向城市规划的空间资源分析对话式 AI Agent

---

## 目录

1. [项目概述](#1-项目概述)
2. [需求分析](#2-需求分析)
3. [技术选型](#3-技术选型)
4. [架构设计](#4-架构设计)
5. [数据底座设计](#5-数据底座设计)
6. [核心模块详细设计](#6-核心模块详细设计)
7. [Agent 工作流](#7-agent-工作流)
8. [迭代计划](#8-迭代计划)
9. [风险评估与应对](#9-风险评估与应对)
10. [可交付成果](#10-可交付成果)
11. [技术问答预案](#11-技术问答预案)

---

## 1. 项目概述

### 1.1 解决的问题

悉尼 109 个行政区的医疗、教育、商业、交通等公共资源分配不均衡，规划决策长期依赖人工经验，且存在"高收入区域 = 高资源"的惯性假设。传统 GIS 分析门槛高，无法让非技术决策者自由探索数据。

### 1.2 产品定位

一个面向**城市规划分析师和地方政府决策者**的 AI Agent，用自然语言提问即可获得：

- 区域资源短板识别
- 空间可达性分析
- 可落地的差异化配置建议
- 交互式可视化看板

### 1.3 核心产品指标

| 指标 | 目标值 |
|------|--------|
| 响应时间 | < 15 秒（含空间查询） |
| 多轮对话 | 准确记住上下文，支持指代消解 |
| 数值可信 | 100% 可溯源，杜绝幻觉数字 |
| 模糊处理 | 支持澄清反问，不强行猜测 |

---

## 2. 需求分析

### 2.1 用户场景

```
场景 A（市规划局分析师）：
  "Parramatta 周边哪些区域交通可达性低于全市均值？"
  → Agent 自动检索 Parramatta 及相邻区域报告，
     调用空间可达性分析 Skill，返回排名和对比表，
     并高亮地图上的短板区域。

场景 B（议员/决策者）：
  "上次分析的那几个低资源区，教育资源具体差在哪里？"
  → Agent 从 session 记忆中还原"那几个区"的列表，
     调取教育覆盖维度数据，生成对比报告。

场景 C（社区代表）：
  "我们区诊所很少，能看看周边 2 公里内有多少吗？"
  → Agent 调用 MCP 空间缓冲区查询，
     返回精确数量和设施列表，并附来源说明。
```

### 2.2 功能需求

| 编号 | 需求 | 优先级 | 说明 |
|------|------|--------|------|
| F1 | 多源数据采集与空间数据仓库 | P0 | 7 类异构数据源 → PostgreSQL + PostGIS |
| F2 | 区域资源评价体系 | P0 | 四维指标 + Z-Score + Sigmoid → RAI |
| F3 | 自然语言报告生成与向量化 | P0 | 每区自动生成报告 → 按维度切分 chunk → ChromaDB |
| F4 | 语义检索 + 空间上下文增强 | P0 | 向量召回 top-5 + PostGIS 邻居扩展 |
| F5 | Tool Calling Agent | P0 | 3 个业务 Skill + MCP 空间查询原语 |
| F6 | 多轮对话记忆 | P1 | Session 上下文 + 指代消解 |
| F7 | 幻觉控制与溯源 | P0 | 所有数值来源可追溯 |
| F8 | 交互式看板 | P1 | Streamlit / Gradio |
| F9 | 多模型适配 | P2 | Claude / OpenAI / DeepSeek 可切换 |
| F10 | Agent 表现监控 | P2 | LLM-as-Eval 反馈闭环 |

### 2.3 非功能需求

| 编号 | 需求 | 目标值 |
|------|------|--------|
| NF1 | 空间查询性能 | 缓冲区查询 < 2s（GiST 索引） |
| NF2 | 模型无关 | LiteLLMModel 一行配置切换，Agent 业务代码零改动 |
| NF3 | 调用链路透明 | 每次 tool call 结构化日志记录 |
| NF4 | 本地可运行 | PostgreSQL + ChromaDB 均在本地 |

---

## 3. 技术选型

### 3.1 选型总览

```
┌──────────────────────────────────────────────────────────────┐
│                      技术栈全景图                              │
├──────────────────────────────────────────────────────────────┤
│  Agent 框架   │  🤗 smolagents (HuggingFace)                  │
│              │  CodeAgent 写 Python 代码调用工具               │
│              │  ~1,000 行核心逻辑，Apache 2.0 开源             │
├──────────────────────────────────────────────────────────────┤
│  LLM 后端     │  LiteLLMModel 统一接入                          │
│              │  Claude / OpenAI / DeepSeek / Ollama 一键切换   │
├──────────────────────────────────────────────────────────────┤
│  空间数据库   │  PostgreSQL 15 + PostGIS 3                    │
│              │  SRID 4283 (GDA94) │ GiST 空间索引             │
├──────────────────────────────────────────────────────────────┤
│  向量数据库   │  ChromaDB (嵌入式，Python 原生)                │
├──────────────────────────────────────────────────────────────┤
│  Embedding   │  sentence-transformers/all-MiniLM-L6-v2       │
├──────────────────────────────────────────────────────────────┤
│  MCP 协议    │  PostGIS MCP Server                           │
│              │  smolagents 原生支持 ToolCollection.from_mcp()  │
├──────────────────────────────────────────────────────────────┤
│  前端界面    │  GradioUI (smolagents 内置) + Folium (地图)     │
├──────────────────────────────────────────────────────────────┤
│  代码安全    │  E2B / Docker 沙箱 (smolagents 原生集成)        │
├──────────────────────────────────────────────────────────────┤
│  数据采集    │  Python 爬虫 + NSW POI API                     │
│  数据分析    │  pandas + numpy + scipy + geoalchemy2          │
│  可视化      │  matplotlib + seaborn + plotly + folium        │
│  数据验证    │  Pydantic (结构化输出 + 参数校验)               │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 关键选型理由

| 组件 | 候选方案 | 选择 | 理由 |
|------|---------|------|------|
| Agent 框架 | LangChain vs CrewAI vs 自研 | **smolagents** | HuggingFace 官方维护，核心仅 ~1,000 行，零黑盒；`CodeAgent` 生成 Python 代码调用工具（Benchmark 比 JSON Tool Calling 少 30% 步数）；原生 MCP 集成 + LiteLLM 多模型支持 |
| LLM 接入 | 自研 LLMClient vs 直接调用 | **LiteLLMModel** | smolagents 内置，100+ 模型一行配置切换；Claude / OpenAI / DeepSeek / Ollama 全部覆盖，无需维护适配器代码 |
| Agent 类型 | ToolCallingAgent vs CodeAgent | **CodeAgent** | 空间分析天然适合代码表达：循环检查多个区域、组合查询结果、做计算后再调用下一工具，JSON Tool Calling 做不到这些 |
| 空间数据库 | PostGIS vs GeoPandas 内存 | **PostGIS** | 13 万+ POI 数据量，GiST 空间索引保证查询性能；SQL 窗口函数实现 Z-Score 计算，可复现、可解释 |
| 向量数据库 | ChromaDB vs FAISS vs Pinecone | **ChromaDB** | 轻量、Python 原生；436+ chunk 规模完全不需要分布式方案 |
| 前端 | Streamlit vs Gradio vs React | **GradioUI** | smolagents 内置 `GradioUI`，一行代码启动对话界面 + Agent 思考过程可视化；自定义地图组件通过 Gradio 集成 |
| MCP | 自行对接 vs 框架内置 | **ToolCollection.from_mcp()** | smolagents 一行代码拉取 MCP Server 的所有工具，零手工编写 Schema |
| 代码安全 | subprocess vs Docker vs E2B | **E2B 云沙箱** | smolagents 原生支持 `executor_type="e2b"`，代码在隔离云端执行；本地开发用 Docker executor |

### 3.3 为什么选择 smolagents 而不是 LangChain / 自研？

**vs LangChain / CrewAI**:
1. LangChain Agent 抽象层太厚（`AgentExecutor`、`Tool`、`AgentAction`、`AgentFinish`……），调试困难，出了问题很难定位是哪一层
2. CrewAI 太黑盒，Role/Task 的编排逻辑不透明
3. smolagents 核心仅 ~1,000 行 —— 你可以读完整个框架源码再决定怎么用，而不是对着文档猜行为

**vs 自己从零写**:
1. 自研意味着要写 ReAct loop、tool 解析、错误重试、多模型适配、代码执行沙箱 —— 这些都是 smolagents 已解决的通用问题
2. 我们的差异化在**空间数据分析 Skill** 和 **RAG 空间上下文增强**，不在 Agent 调度基础设施
3. smolagents 的 `@tool` 装饰器 + `ToolCollection.from_mcp()` 让我们把精力集中在业务逻辑上

**smolagents 独有的杀手特性**:
| 特性 | 对本项目的价值 |
|------|---------------|
| `CodeAgent` 生成 Python 代码 | 一个 step 内组合多次工具调用 + pandas 计算，例如 `for area in neighbors: scores[area] = gap_detector(area)` |
| `ToolCollection.from_mcp()` | 一行代码接入 PostGIS MCP Server 的所有空间查询工具 |
| `LiteLLMModel` | 切换模型只需改 `model_id` 字符串，Claude → DeepSeek 一行配置 |
| `managed_agents` 多智能体 | 可以拆出一个专门的 `rag_agent` 负责检索，主 `manager_agent` 负责空间分析调度 |
| `agent.push_to_hub()` | 做完可以发布到 HuggingFace Hub 展示 |
| `GradioUI(agent).launch()` | 一行代码获得带思考过程可视化的对话界面 |
| E2B/Docker 沙箱 | `CodeAgent` 生成的代码在隔离环境执行，不影响宿主机 |

---

## 4. 架构设计

### 4.1 总体架构（基于 smolagents CodeAgent）

```
┌─────────────────────────────────────────────────────────────────────┐
│                     交互层 (Interface Layer)                         │
│            GradioUI (smolagents 内置)  │  Folium 地图  │  FastAPI    │
├─────────────────────────────────────────────────────────────────────┤
│                   Agent 核心层 (smolagents CodeAgent)                │
│                                                                     │
│   ┌───────────────────────────────────────────────────────────┐    │
│   │                  CodeAgent (ReAct Loop)                    │    │
│   │                                                           │    │
│   │   System Prompt (含 Tool 描述)                              │    │
│   │        │                                                   │    │
│   │        ▼                                                   │    │
│   │   ┌──────────┐    ┌──────────┐    ┌──────────────┐       │    │
│   │   │  Think   │───▶│   Act    │───▶│  Observe     │──┐    │    │
│   │   │ LLM 推理  │    │ 生成代码  │    │ 执行结果+日志  │   │    │    │
│   │   └──────────┘    └──────────┘    └──────────────┘   │    │    │
│   │        ▲                                               │    │    │
│   │        └───────────────────────────────────────────────┘    │    │
│   │                                                           │    │
│   │   终止条件: 调用 final_answer() 或 达到 max_steps            │    │
│   │   final_answer_checks: 自定义答案校验函数                    │    │
│   └───────────────────────────────────────────────────────────┘    │
│                              │                                       │
│   ┌──────────────────────────┴──────────────────────────────┐     │
│   │              LiteLLMModel (模型无关接入)                    │     │
│   │   anthropic/claude-sonnet  │  openai/gpt-4o              │     │
│   │   deepseek/deepseek-chat   │  ollama_chat/qwen2.5        │     │
│   └─────────────────────────────────────────────────────────┘     │
│                              │                                       │
│   ┌──────────────────────────┴──────────────────────────────┐     │
│   │             Session 管理层 (自研)                          │     │
│   │   SessionContext  │  指代消解  │  工具调用日志 (Mermaid)    │     │
│   └─────────────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────────────────┤
│                  Tool 层 (@tool 装饰器 + MCP)                       │
│                                                                     │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐           │
│   │ @tool          │ │ @tool         │ │ @tool         │           │
│   │ gap_detector   │ │ spatial_access│ │ recommend     │           │
│   │ 资源短板识别    │ │ 空间可达性     │ │ 建议生成      │           │
│   └───────┬───────┘ └───────┬───────┘ └───────┬───────┘           │
│           │                 │                 │                     │
│   ┌───────┴─────────────────┴─────────────────┴───────┐           │
│   │         ToolCollection.from_mcp(postgis_server)    │           │
│   │  query_buffer_poi │ nearest_n_poi │ service_area   │           │
│   └───────────────────────────────────────────────────┘           │
│                                                                     │
│   ┌───────────────────────────────────────────────────┐           │
│   │         RAG Tool (@tool)                           │           │
│   │  search_suburb_report(query) → 语义检索 + 空间扩展  │           │
│   └───────────────────────────────────────────────────┘           │
├─────────────────────────────────────────────────────────────────────┤
│                    数据层 (Data Layer)                               │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐   │
│   │ PostgreSQL │ │ ChromaDB   │ │ Session     │ │ Eval         │   │
│   │ + PostGIS  │ │ 向量存储    │ │ Store       │ │ Logs         │   │
│   │ 8 数据集    │ │ 436+ chunk │ │ 会话记忆     │ │ 评估日志      │   │
│   └────────────┘ └────────────┘ └────────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Agent 调用数据流（CodeAgent 代码生成模式）

与传统 JSON Tool Calling 的对比：smolagents `CodeAgent` 在一个 step 内生成**多行 Python 代码**，可以调用多个工具、用变量存中间结果、写循环和条件判断 —— 这在 JSON Tool Calling 需要多轮才能完成。

```
用户: "Parramatta 周边哪些区缺诊所？交通情况也帮我看看"
    │
    ▼
╔═══════════════════════════════════════════════════════════════╗
║ Step 1: CodeAgent 生成 Python 代码                              ║
╠═══════════════════════════════════════════════════════════════╣
║ # 同时查询资源短板 + 空间可达性                                   ║
║ parramatta_health = resource_gap_detector(                     ║
║     areas=["Parramatta"], dimension="公共服务"                  ║
║ )                                                              ║
║ parramatta_transport = resource_gap_detector(                  ║
║     areas=["Parramatta"], dimension="交通可达性"                 ║
║ )                                                              ║
║                                                                ║
║ # 找邻居区域并补查                                                ║
║ neighbors = search_suburb_report(                              ║
║     "Parramatta 周边 诊所 医疗设施", k=5                        ║
║ )                                                              ║
║ for n in neighbors['areas']:                                   ║
║     scores[n] = resource_gap_detector(                         ║
║         areas=[n], dimension="公共服务"                         ║
║     )                                                          ║
║                                                                ║
║ # 空间可达性查询                                                  ║
║ clinic_count = spatial_accessibility(                          ║
║     area="Parramatta", radius_meters=2000,                     ║
║     facility_type="clinic"                                     ║
║ )                                                              ║
║ final_answer({                                                 ║
║     "health_gaps": parramatta_health,                         ║
║     "transport": parramatta_transport,                        ║
║     "neighbor_gaps": scores,                                  ║
║     "nearby_clinics": clinic_count                            ║
║ })                                                             ║
╚═══════════════════════════════════════════════════════════════╝
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 在 E2B/Docker 沙箱中执行代码                                   │
│   → resource_gap_detector × N: 查询 well_resourced_scores    │
│   → search_suburb_report: ChromaDB 检索 + PostGIS 邻居扩展   │
│   → spatial_accessibility: 调用 MCP buffer_poi              │
│   → 执行日志注入 agent.logs                                   │
│   → 最终调用 final_answer() 返回结构化结果                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ CodeAgent 将 tool 输出交 LLM 整合为自然语言回答                 │
│   → 幻觉控制: system prompt 约束数字必须来自 tool 返回          │
│   → 来源追溯: 每个数字标注是哪个 tool 调用返回的                 │
└─────────────────────────────────────────────────────────────┘
```

**关键优势**：传统 JSON Tool Calling 需要 5-6 轮来回才能完成上述逻辑（一次一个 tool call），`CodeAgent` **一步完成**。对空间分析这种常常需要"查 A、再看 A 的邻居、再对比"的场景，步数减少意味着更快、更便宜、推理更连贯。

### 4.3 失败兜底决策树（smolagents ReAct Loop 版）

smolagents `CodeAgent` 的 ReAct Loop 自带错误处理：生成的 Python 代码如果有语法错误/异常，会被捕获并反馈给 Agent 让其修正。在此基础上，我们在 `@tool` 函数内部加入业务级兜底。

```
CodeAgent ReAct Loop ── Step N
    │
    ├── LLM 生成 Python 代码
    │      │
    │      ├── 语法/运行时错误
    │      │    → smolagents 自动捕获
    │      │    → 错误日志注入 agent.logs
    │      │    → Agent 在 Step N+1 看到错误并尝试修正
    │      │    → 同一错误重复 3 次 → Agent 调用 final_answer()
    │      │      告知用户: "此分析遇到技术问题，建议..."
    │      │
    │      └── 代码正常执行
    │           │
    │           └── @tool 函数内部
    │                │
    │                ├── 成功 → return 结构化 dict
    │                │
    │                └── 业务失败
    │                     │
    │                     ├── 参数错误 (区域名不存在)
    │                     │    → return {"error": "invalid_area",
    │                     │               "candidates": [模糊匹配列表]}
    │                     │    → Agent 读取 error 字段 → 修正参数 → 重试
    │                     │
    │                     └── 数据层错误 (DB 超时 / 网络)
    │                          → return {"error": "data_unavailable",
    │                                    "partial": 已完成的部分结果}
    │                          → Agent 决定:
    │                              - 有 partial 数据 → 先返回已有的
    │                              - 无任何数据 → 调用 search_suburb_report
    │                                降级为纯 RAG 回答
    │
    └── CodeAgent 达到 max_steps (默认 10)
         → 自动调用 final_answer() 总结当前已知信息
         → "分析未完全完成，以下是已获得的结果..."
```

**与传统 JSON Tool Calling 的关键差异**：传统模式每次失败需要框架层调度重试；smolagents 中 Agent 自己生成 try/except 代码来容错，这是 `CodeAgent` 在可靠性上的天然优势。

---

## 5. 数据底座设计

### 5.1 数据采集清单

共 8 类异构数据源，覆盖社会经济、交通、教育、公共安全、休闲设施等维度。

| # | 数据集 | 来源 | 粒度 | 规模 | 关键字段 | 采集方式 |
|---|--------|------|------|------|----------|----------|
| 1 | **Businesses.csv** | Australian Bureau of Statistics (ABS) | SA2 × 行业 | 12,198 条 (19 行业) | `industry_code`, `industry_name`, `sa2_code`, `total_businesses` | CSV 导入，按行业汇总营业额区间 |
| 2 | **Stops.txt** | Transport for NSW (GTFS 格式) | 经纬度点 | 114,718 个站点 | `stop_id`, `stop_lat`, `stop_lon`, `location_type`, `wheelchair_boarding` | CSV → PostGIS POINT，含公交/火车/轮渡所有站点 |
| 3 | **Population.csv** | ABS Census 2021 | SA2 × 19 年龄组 | 373 SA2 | `sa2_code`, 19 个年龄组列 (`0-4_people` ~ `85-and-over_people`) | CSV → PostgreSQL，计算 `total_population` 和 `youth_population` |
| 4 | **PollingPlaces.csv** | Australian Electoral Commission (2019 Federal Election) | 经纬度点 | 悉尼范围内的投票站 | 投票站名称、地址、经纬度 | CSV → PostGIS POINT，作为公共服务可达性参考 |
| 5 | **Catchments** (Shapefile) | NSW Department of Education | 学区多边形 | 2,128 个学区 (含 primary / secondary / future) | `USE_ID`, `CATCH_TYPE`, `USE_DESC`, `geometry` | Shapefile → PostGIS MULTIPOLYGON，用于计算学区覆盖率 |
| 6 | **Incomes** (Income.csv) | ABS Taxation Statistics | SA2 | 642 SA2 | `sa2_code21`, `median_income`, `mean_income`, `earners`, `median_age` | CSV 导入，含缺失值 (`np`) 清洗处理 |
| 7 | **Crimes** | Sydney Suburb Reviews | Suburb 名称 | 按 suburb 的犯罪率统计 | 犯罪类型、发生率 | CSV → 匹配 SA2 名称，作为社区安全维度 |
| 8 | **Playgrounds** | City of Sydney Open Data | 经纬度点 | 游乐场 & 健身站点列表 | 设施名称、类型、经纬度 | CSV/API → PostGIS POINT，作为休闲设施覆盖分析 |

> **空间统一**: 所有地理数据统一为 **SRID 4283** (GDA94)，与澳大利亚官方坐标系统一致。非空间数据通过 `sa2_code` 与 `sa2_regions` 表关联。

### 5.2 PostgreSQL + PostGIS 数据库设计

#### Schema 概览

```sql
-- 核心表结构 (8 张业务表 + 1 张边界主表)

-- [基础地理]
sa2_regions       -- 行政区边界 (MULTIPOLYGON, SRID 4283) — 主表
  ├── SA2_CODE21 (PK)
  ├── SA2_NAME21
  ├── SA4_NAME21
  └── geom (GiST INDEX)

-- [商业]
businesses        -- 企业数量 (按行业 × SA2) — 来源: Businesses.csv
  ├── industry_code, industry_name
  ├── sa2_code (FK → sa2_regions)
  └── total_businesses

-- [交通]
stopcount         -- 公交站点 (POINT, SRID 4283) — 来源: Stops.txt
  ├── stop_id
  └── geom (GiST INDEX)

-- [教育]
schoolcatch       -- 学校学区 (MULTIPOLYGON, SRID 4283) — 来源: Catchments
  ├── USE_ID, CATCH_TYPE, USE_DESC
  ├── geom (GiST INDEX)
  └── area_km2 (ST_Area 计算列)

-- [人口]
popall            -- 人口 (19 年龄组 × SA2) — 来源: Population.csv
  ├── sa2_code (FK → sa2_regions)
  ├── "0-4_people" ~ "85-and-over_people"
  └── total_population (计算列), youth_population (0-19)

-- [收入]
incomevalue       -- 收入 — 来源: Income.csv
  ├── sa2_code21 (FK → sa2_regions)
  ├── median_income, mean_income
  └── earners, median_age

-- [公共服务]
poi_counts        -- POI 计数 — 来源: NSW POI API
  ├── sa2_code (FK → sa2_regions)
  └── poi_count

pollingplaces     -- 投票站 (POINT, SRID 4283) — 来源: PollingPlaces.csv
  ├── place_id
  ├── place_name, address
  └── geom (GiST INDEX)

-- [安全]
crimes            -- 犯罪统计 — 来源: Sydney Suburb Reviews
  ├── suburb_name → 关联 sa2_regions
  ├── crime_type, crime_rate
  └── sa2_code (FK → sa2_regions)

-- [休闲]
playgrounds       -- 游乐场 & 健身站 (POINT, SRID 4283) — 来源: City of Sydney
  ├── facility_id
  ├── facility_name, facility_type (playground | fitness)
  └── geom (GiST INDEX)
```

> **设计原则**: 所有空间表统一 SRID 4283 + GiST 索引；所有业务表通过 `sa2_code` 与 `sa2_regions` 关联，确保任意维度的指标可按区域 JOIN。

#### 关键视图

```sql
-- 1. 人口汇总视图 (含计算列 total_population, youth_population)
pop_summary_view
  → popall ⋈ sa2_regions
  → 计算 total_population (19 年龄组求和)
  → 过滤 population >= 100

-- 2. 组合指标视图 (四维度数值)
combined_metrics_view
  → business_score_view   (制造业企业 / 千人)
  → stops_score_view      (公交站点 / 人)
  → schools_score_view    (学校 / 千青少年)
  → poi_score_view        (POI / 人)
  → total_pop_view

-- 3. 资源评分视图 (含 Z-Score + Sigmoid)
well_resourced_scores_view
  → 全城均值/标准差 (CROSS JOIN stats CTE)
  → z_business, z_stops, z_schools, z_poi
  → z_total = sum(z_*)
  → final_score = sigmoid(z_total)       -- 0-1 区间
  → 关联 incomevalue.median_income      -- 收入相关性分析
```

#### 空间索引策略

```sql
-- GiST 索引是空间查询性能的关键
CREATE INDEX idx_sa2_regions_geom    ON sa2_regions USING GIST(geom);
CREATE INDEX idx_schoolcatch_geom    ON schoolcatch USING GIST(geom);
CREATE INDEX idx_stopcount_geom      ON stopcount USING GIST(geom);
-- 缓冲区分析、最近邻查询均依赖 GiST 索引
```

### 5.3 资源评分算法 (四维 → 可扩展至六维)

```
对每个 SA2 区域:
  1. 计算四个核心维度的原始指标:
     - 商业活力:    businesses_per_1000  (制造业企业数 / 千人)
     - 交通可达性:  stops_per_capita      (公交站点数 / 人)
     - 教育覆盖:    schools_per_1000_youth (学校数 / 千青少年)
     - 公共服务:    poi_per_capita        (POI 数 / 人)

     [可扩展维度 — 数据已就绪，RAI v2 规划中]
     - 社区安全:    crime_rate_per_1000   (Crimes 表, 越低越好 → 反向 Z-Score)
     - 休闲设施:    playgrounds_per_1000  (Playgrounds 表)

  2. Z-Score 标准化 (与全城 109 区均值和标准差比较):
     z_i = (x_i - μ) / σ

  3. Sigmoid 映射到 0-1:
     final_score = 1 / (1 + e^(-Σz_i))

  4. 所有计算在 PostgreSQL 中用 SQL 窗口函数完成:
     - 可复现: 同一份 SQL, 同一结果
     - 可解释: 每个中间值可审计
     - 可追溯: 从 final_score 反向拆解到原始数据
```

---

## 6. 核心模块详细设计

### 6.1 模型接入 —— LiteLLMModel（零适配器代码）

smolagents 内置 `LiteLLMModel` 覆盖 100+ 模型，无需自研 LLMClient 抽象层：

```python
from smolagents import CodeAgent, LiteLLMModel

# Claude (原型首选，多步推理稳)
model = LiteLLMModel(model_id="anthropic/claude-sonnet-4-6")

# DeepSeek (成本降低一个数量级，中文强)
model = LiteLLMModel(model_id="deepseek/deepseek-chat")

# OpenAI
model = LiteLLMModel(model_id="openai/gpt-4o")

# Ollama 本地模型 (完全离线)
model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5:7b",
    api_base="http://localhost:11434",
    num_ctx=8192
)

# 切换模型只需改一行配置，上层 Agent 逻辑完全不变
```

### 6.2 Agent 核心 Skill 设计（@tool 装饰器）

每个业务 Skill 用 `@tool` 装饰器定义，类型提示 + docstring 自动生成 Tool Schema。

#### Skill 1: resource_gap_detector

```python
from smolagents import tool

@tool
def resource_gap_detector(
    areas: list[str] | None = None,
    dimension: str = "all",
    top_n: int = 5
) -> dict:
    """
    Identify resource gap areas based on the RAI four-dimension scoring system.
    Use this when the user asks about 'which areas lack resources',
    'resource shortages', 'gap analysis', or 'XX area's weaknesses'.

    Args:
        areas: List of SA2 area names, e.g. ['Parramatta', 'Auburn'].
               None or empty list means analyze all 109 areas.
        dimension: The resource dimension to check.
                   One of '商业活力', '交通可达性', '教育覆盖', '公共服务', or 'all'.
        top_n: Number of top gap areas to return. Default 5.
    """
    import psycopg2
    # 1. 参数校验: areas 非空 → 逐一验证存在于 109 区列表
    # 2. SQL 查询 well_resourced_scores 表
    # 3. 按维度 Z-Score 或 final_score 排序
    # 4. 返回结构化 dict
    return {
        "gaps": [
            {
                "suburb": "Wiley Park",
                "sa2_code": "...",
                "final_score": 0.08,
                "rank": 109,
                "z_scores": {
                    "商业活力": -1.2,
                    "交通可达性": 0.1,
                    "教育覆盖": -0.8,
                    "公共服务": -1.5
                }
            },
            ...
        ],
        "query_params": {"areas": areas, "dimension": dimension}
    }
```

#### Skill 2: spatial_accessibility_analyzer

```python
@tool
def spatial_accessibility_analyzer(
    area: str,
    radius_meters: int = 2000,
    facility_type: str = "all"
) -> dict:
    """
    Analyze spatial accessibility for a given area. Calculates how many
    facilities of a given type are reachable within a radius.
    Use this when the user asks 'how many X within Y km of Z',
    'walkable distance', 'nearby facilities'.

    Args:
        area: SA2 area name, e.g. 'Parramatta'.
        radius_meters: Search radius in meters. Default 2000 (2km).
        facility_type: Type of facility. One of 'clinic', 'school',
                       'transport', 'retail', 'community', 'all'.
    """
    # 1. 从 sa2_regions 获取区域质心 ST_Centroid(geom)
    # 2. 根据 facility_type 选择目标表 (stopcount / schoolcatch / poi_counts / playgrounds)
    # 3. ST_DWithin 缓冲区查询，利用 GiST 索引
    # 4. 返回可达设施列表 + 覆盖统计
    return {
        "area": area,
        "center": {"lat": -33.8150, "lng": 151.0011},
        "radius_m": radius_meters,
        "facility_type": facility_type,
        "count": 34,
        "facilities": [
            {"name": "Parramatta Medical Centre", "distance_m": 450, "type": "clinic"},
            ...
        ],
        "coverage_area_km2": 12.5
    }
```

#### Skill 3: recommendation_generator

```python
@tool
def recommendation_generator(
    gap_analysis: dict,
    focus: str = "all"
) -> dict:
    """
    Generate differentiated resource allocation recommendations based on
    gap analysis and spatial accessibility results.
    Use this when the user asks 'what should we do', 'recommendations',
    'how to improve', 'action plan'.

    Args:
        gap_analysis: Structured result from resource_gap_detector.
        focus: Recommendation focus area.
               One of '交通微循环', '公共服务优化', '商业活力触达', 'all'.
    """
    # 1. 规则模板匹配：根据短板类型选择预定义建议库
    # 2. LLM 润色：将模板与具体数据结合
    return {
        "recommendations": [
            {
                "priority": 1,
                "area": "Wiley Park",
                "action": "增设社区健康中心 + 移动诊所服务",
                "rationale": "公共服务 Z-Score = -1.5，远低于均值",
                "expected_impact": "服务覆盖率提升 40%"
            },
            ...
        ]
    }
```

#### RAG Tool: search_suburb_report

```python
@tool
def search_suburb_report(query: str, k: int = 5) -> dict:
    """
    Search the knowledge base for suburb analysis reports. Returns structured
    report chunks with suburb name, dimension, scores, and rankings.
    Use this when the user asks for information about specific areas,
    or when context about area characteristics is needed.

    Args:
        query: Natural language query about suburbs or resources.
        k: Number of top results to return. Default 5.
    """
    # 1. Query 改写 (同义词扩展)
    # 2. ChromaDB 语义检索 top-k
    # 3. PostGIS 邻居扩展 (ST_Touches / ST_Distance < 5km)
    # 4. 重排序: similarity * 0.7 + spatial_proximity * 0.3
    return {
        "chunks": [
            {
                "suburb_name": "Parramatta",
                "dimension": "公共服务",
                "score": 0.34,
                "rank": 87,
                "text": "Parramatta 的公共服务指数 0.34，低于悉尼均值 12%...",
                "metadata": {"sa2_code": "...", "sa4_name": "Sydney - Parramatta"}
            },
            ...
        ],
        "neighbor_areas": ["Auburn", "Granville", "Holroyd"],
        "retrieval_method": "semantic_vector + spatial_extension"
    }
```

### 6.3 Agent 组装 —— 一行代码注册所有工具

```python
from smolagents import CodeAgent, LiteLLMModel, ToolCollection

# 1. 选择模型
model = LiteLLMModel(model_id="anthropic/claude-sonnet-4-6")

# 2. 注册业务工具
custom_tools = [
    resource_gap_detector,
    spatial_accessibility_analyzer,
    recommendation_generator,
    search_suburb_report,
]

# 3. 一行代码接入 PostGIS MCP 工具
mcp_tools = ToolCollection.from_mcp("postgis_mcp_server")

# 4. 组装 Agent（含基础工具箱：DuckDuckGo 搜索 + Python 解释器）
agent = CodeAgent(
    tools=[*custom_tools, *mcp_tools],
    model=model,
    add_base_tools=True,                # 加 WebSearchTool + PythonInterpreterTool
    max_steps=10,                        # 最多 10 个 ReAct step
    executor_type="e2b",                 # 代码在 E2B 云沙箱安全执行
    # 或者本地: executor_type="docker"
    additional_authorized_imports=[      # 允许沙箱中的额外 import
        "psycopg2", "pandas", "numpy", "geoalchemy2"
    ],
)

# 5. 运行
result = agent.run(
    "Parramatta 周边哪些区缺诊所？交通也帮我看看"
)
```

### 6.4 MCP Server —— ToolCollection.from_mcp() 零代码接入

smolagents 原生支持 MCP，不需要手动写适配器。与 Agent 组装的集成方式已在 6.3 节展示，这里展示 PostGIS MCP Server 端暴露的工具定义：

# PostGIS MCP Server 暴露以下工具 (在 server 端定义):
# query_buffer_poi(center_lat, center_lng, radius_meters, poi_type)
# nearest_n_poi(center_lat, center_lng, n, poi_type)
# service_area_coverage(sa2_code, travel_mode, time_minutes)

# smolagents 端接入只需一行:
from smolagents import ToolCollection
postgis_tools = ToolCollection.from_mcp("postgis_mcp_server")
# 自动拉取所有工具的 name / description / input_schema / output_schema
# CodeAgent 的 system prompt 自动包含这些工具的 JSON Schema
```

### 6.5 多智能体分层（可选，Iter 3+）

当分析逻辑变复杂时，用 smolagents 的 `managed_agents` 拆分子智能体：

```python
# 子智能体: 专注 RAG 检索
rag_agent = CodeAgent(
    tools=[search_suburb_report],
    model=model,
    name="rag_agent",
    description="Retrieves suburb analysis reports from the knowledge base. "
                "Give it a natural language query about suburbs or resources."
)

# 子智能体: 专注空间分析
spatial_agent = CodeAgent(
    tools=[spatial_accessibility_analyzer, *postgis_tools],
    model=model,
    name="spatial_agent",
    description="Performs spatial accessibility analysis. "
                "Give it an area name and facility type."
)

# 主智能体: 调度 + 综合推理
manager_agent = CodeAgent(
    tools=[resource_gap_detector, recommendation_generator],
    model=model,
    managed_agents=[rag_agent, spatial_agent],
    max_steps=8
)

# 主智能体自动学会何时委派给子智能体
manager_agent.run("分析 Parramatta 的资源短板并给出交通优化建议")
```

### 6.6 多轮对话 Session 管理（结合 smolagents 内置能力）

smolagents 提供了两个关键能力让我们无需从零构建 session 管理：

- **`agent.run(user_request, reset=False)`**：不刷新 Agent 内存，保持前一轮的 tool 调用日志和推理链
- **`agent.write_memory_to_messages()`**：导出完整对话历史为 LLM 可读的 message list

在此基础上，我们维护一个轻量 SessionContext 来做**业务级**的上下文追踪（区域列表、偏好维度等）。

```python
from smolagents import CodeAgent

class SessionManager:
    """包装 smolagents CodeAgent，增加业务级 session 上下文"""

    def __init__(self, agent: CodeAgent):
        self.agent = agent
        self.analyzed_areas: list[str] = []
        self.last_skill_results: dict = {}
        self.user_preferences: dict = {
            "focused_dimensions": [],          # 用户关注的维度
            "favorite_areas": []               # 常问的区域
        }

    def chat(self, user_message: str, session_id: str) -> str:
        # 1. 将业务上下文注入用户消息
        context_prefix = ""
        if self.analyzed_areas:
            context_prefix = (
                f"[先前分析上下文]\n"
                f"已分析过的区域: {self.analyzed_areas}\n"
                f"用户关注维度: {self.user_preferences['focused_dimensions']}\n\n"
            )

        enriched_message = context_prefix + user_message

        # 2. 使用 reset=False 保留 smolagents 的内置记忆
        #    (agent.logs 中的 tool 调用历史不会清空)
        result = self.agent.run(enriched_message, reset=False)

        # 3. 更新业务上下文
        self._update_context(result)

        return result

    def _update_context(self, result):
        """从 agent.logs 中提取本次分析的区域列表和 skill 调用结果"""
        for step in self.agent.logs:
            # 提取 tool 调用涉及的 areas
            ...

# 指代消解示例:
# 用户: "上次那几个低资源区再分析一下交通"
# → context_prefix 中注入 "已分析过的区域: [Wiley Park, Lakemba, Parramatta]"
# → Agent 自动映射 "那几个" → 具体区域列表
# → Agent 生成代码: gap_detector(areas=["Wiley Park", "Lakemba", "Parramatta"], dimension="交通可达性")
```

### 6.7 幻觉控制机制（smolagents 增强版）

利用 smolagents 的 `final_answer_checks` + System Prompt 实现三层防护。

```python
# 层 1: CodeAgent 初始化时注入 System Prompt
from smolagents import CodeAgent

system_prompt_addition = """
你是 GeoAnalysis 城市规划分析助手。严格遵循以下规则：
1. 所有数值结论必须来自工具调用返回的结构化数据，禁止编造任何数字
2. 每条关键结论必须标注来源（区域报告 chunk ID 或工具调用 ID）
3. 遇到模糊指代（"东区"、"那几个区"），必须先追问澄清，不得猜测
4. 当检索或工具返回的数据不足时，明确告知用户，不得强行回答
5. 对于任何计算类问题，先用 Python 调用对应工具获取硬数据，再回答
"""

# 层 2: final_answer_checks —— 答案格式和完整性校验
def check_has_source_trace(final_answer: str, agent_memory=None) -> bool:
    """确保最终回答中包含数据来源标注"""
    has_source = any(marker in final_answer for marker in [
        "SA2:", "well_resourced_scores", "Z-Score", "数据来源"
    ])
    if not has_source and len(final_answer) > 50:
        # 短回答（如"请提供具体区域名"）不需要来源
        return False
    return True

def check_no_hallucinated_numbers(final_answer: str, agent_memory=None) -> bool:
    """检查回答中是否出现未经验证的数字（通过对比 tool 调用日志）"""
    # 提取 agent_memory 中所有 tool 返回的数值
    # 如果回答中出现不在该集合中的统计数字 → 标记为疑似幻觉
    # 详细实现略
    return True

agent = CodeAgent(
    tools=[...],
    model=model,
    system_prompt=system_prompt_addition,
    final_answer_checks=[check_has_source_trace, check_no_hallucinated_numbers],
    max_steps=10
)

# 层 3: @tool 函数内部的置信度边界
RETRIEVAL_THRESHOLD = 0.5

@tool
def search_suburb_report(query: str, k: int = 5) -> dict:
    ...
    if max_similarity < RETRIEVAL_THRESHOLD:
        return {
            "status": "low_confidence",
            "message": ("当前知识库中针对该问题的信息不足。"
                       f"建议联系数据团队补充相关数据。"),
            "chunks": []
        }
    ...
```

**三层兜底对比**：

| 层级 | 负责 | 失败行为 |
|------|------|---------|
| System Prompt | 控制 LLM 行为基调 | 违规时 Agent 仍可能偏离，但概率大幅降低 |
| `final_answer_checks` | 答案合规性自动校验 | 任意 check 返回 False → 继续运行，生成新的 final_answer |
| @tool 置信度边界 | 数据层质量保证 | 返回 low_confidence → Agent 诚实地告知用户 |

### 6.8 Agent 监控 —— LLM-as-Eval（结合 smolagents 日志）

```python
EVALUATION_DIMENSIONS = {
    "相关性": "回答是否切中用户问题？1-5 分",
    "数值准确性": "数字是否与数据库一致？（抽查与 hard source 对比）1-5 分",
    "引用完整性": "每个关键结论是否标注来源？1-5 分",
    "幻觉迹象": "是否存在编造事实或数字的痕迹？（有 = 0, 无 = 1）"
}

def evaluate_response(user_query, agent_response, tool_call_results):
    """使用低成本模型（如 DeepSeek/GPT-3.5）作为 evaluator"""
    eval_prompt = f"""
    你是 Agent 质量评估员。请对以下回答按维度评分:

    用户问题: {user_query}
    工具调用返回数据: {tool_call_results}
    Agent 回答: {agent_response}

    评估维度:
    {json.dumps(EVALUATION_DIMENSIONS, ensure_ascii=False)}

    返回 JSON: {{"dimension": score, ...}}
    """
    scores = call_evaluator_llm(eval_prompt)
    if any(s < 3 for s in scores.values()):
        trigger_human_review(user_query, agent_response, scores)
    return scores
```

---

## 7. Agent 工作流

### 7.1 完整 Tool Calling 序列

```
┌─ 用户: "Parramatta 2公里内有多少家诊所？交通和商业也帮我看看"
│
├─ [LLM 分析意图]
│   意图 1: 空间可达性查询 (spatial_accessibility_analyzer)
│   意图 2: 资源短板分析 (resource_gap_detector)
│   识别为可并行调用
│
├─ [Tool Call 1] → spatial_accessibility_analyzer
│   参数: {area: "Parramatta", radius_meters: 2000, poi_type: "clinic"}
│   结果: {poi_count: 34, poi_list: [...], coverage_area_km2: 12.5}
│
├─ [Tool Call 2] → resource_gap_detector  (并行)
│   参数: {areas: ["Parramatta"], dimension: "all"}
│   结果: {final_score: 0.38, z_scores: {...}, rank: 87/109}
│
├─ [Tool Call 3] → RAG 检索  (并行)
│   Query 改写: "Parramatta 诊所 医疗 交通 公交 商业 零售"
│   结果: top-5 chunk + 邻居扩展 (Auburn, Granville, Holroyd...)
│
├─ [LLM 整合]
│   → 自然语言回答 (基于 tool call 结果 + RAG context + session 历史)
│   → 标注所有数字来源
│   → 如果需要，调用 recommendation_generator 生成建议
│
└─ 返回用户 + 记录到 session 上下文
```

### 7.2 Query 改写与 RAG 优化流程

```
用户原始 Query: "查一下 Parramatta 周边缺诊所"
    │
    ▼
┌──────────────────────────────────┐
│ Step 1: 意图分类 (few-shot LLM)   │
│   识别: 医疗 + 空间邻近           │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Step 2: Query 改写 + 同义词扩展   │
│   "Parramatta 诊所 clinic        │
│    医院 hospital                 │
│    社区健康中心 health center     │
│    医疗设施 medical facility"    │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Step 3: 向量检索 (多 query 融合)  │
│   ChromaDB.similarity_search(    │
│     expanded_query, k=5          │
│   )                              │
│   → 5 个最相关 chunk              │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Step 4: 空间邻居扩展              │
│   PostGIS 查询 Parramatta 邻居    │
│   → Auburn, Granville, Holroyd,  │
│     Merrylands, Rosehill...      │
│   → 加载这些区域的医疗维度 chunk   │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Step 5: 重排序与截断              │
│   score = similarity*0.7 +        │
│           spatial_proximity*0.3   │
│   → Top-N 注入 context           │
│   → 超出窗口的直接丢弃            │
└──────────────────────────────────┘
```

### 7.3 HyDE 策略（可选优化开关）

```python
def hyde_retrieval(query: str, model, vector_store, k: int = 5):
    """
    对于过于简短的 query，先让模型生成假想的理想答案段落，
    再用这个段落的向量去检索真实 chunk。

    开销: 额外一次 LLM 调用
    为避免突破 <15s RT，可选用轻量模型（如 Ollama 本地小模型）或缓存 HyDE 结果
    """
    if len(query) < 20:  # 仅对短 query 启用
        hypo_doc = model.chat_completion([
            {"role": "system", "content": "生成一段约 100 字的假设性回答段落..."},
            {"role": "user", "content": query}
        ])["content"]
        search_query = hypo_doc
    else:
        search_query = query

    return vector_store.similarity_search(search_query, k=k)
```

---

## 8. 迭代计划

### 架构分层与包边界

整个项目分为两个**独立可交付层**。下面用 `┊` 标注两者的责任边界：

```
┌─────────────────────────────────────────────────────────────┐
│  Agent 层 (smolagents)                                      │
│  · 自然语言→Tool 调度→自然语言回答                            │
│  · @tool 函数调用底层 SQL / API                              │
│  · 对话记忆、幻觉控制、GradioUI                               │
│  · 响应时间: < 15s                                          │
├─────────────────────────────────────────────────────────────┤
│  数据底座 (PostgreSQL + PostGIS)              ┊ Agent 不生成  │
│  · 8 类数据源 ETL → 11 张表                  ┊ SQL，只调用   │
│  · Z-Score + Sigmoid RAI (纯 SQL 窗口函数)    ┊ 预定义的视图  │
│  · 所有评分可复现、可审计                     ┊              │
│  · 响应时间: < 2s (GiST 索引)               ┊              │
└─────────────────────────────────────────────────────────────┘
```

这个边界是关键的架构设计：**Agent 层不生成 SQL，数据层不给 Agent 开写权限**。评分计算全部在 `well_resourced_scores` 视图中预完成，`resource_gap_detector` 只做 `SELECT`。这保证了即使 Agent 产生幻觉，它也无法"编造"一个不存在的数字——因为它只能读、不能算。

---

采用**5 迭代 × 1 周**（总计 5 周）。smolagents 的 `@tool` 装饰器 + `LiteLLMModel` + `ToolCollection.from_mcp()` + `GradioUI` 消除了传统方案中约 1 周的脚手架代码。

```
Week 1         Week 2          Week 3           Week 4          Week 5
Iter 0         Iter 1          Iter 2           Iter 3          Iter 4
数据底座       RAG 原型        CodeAgent        多轮对话        产品化交付
(已完成)       + 报告生成      + MCP 集成        + 幻觉控制      + 监控
│              │               │                 │               │
└─ 数据层 ────┘└────────────── Agent 层 ───────────────────────────┘
```

---

### Iter 0 (Week 1): 数据底座与资源评价体系 ✅ 已完成

> **对应文件**: `Final-DATA2001+assignment.ipynb`

**角色**：这是整个系统的"硬数据"基础。所有计算在 PostgreSQL 中用纯 SQL 完成，Agent 层只读不写。

| 序号 | 任务 | 产出 | 工时 |
|------|------|------|------|
| 0.1 | 8 类数据源采集与清洗 | 企业、GTFS公交、人口、收入、学校学区、投票站、犯罪率、POI 全部入库 | 1.5 天 |
| 0.2 | PostgreSQL + PostGIS 建库 | 11 张表 + GiST 空间索引 + SRID 4283 统一 | 1 天 |
| 0.3 | 四维度指标视图 | `business_score_view`, `stops_score_view`, `schools_score_view`, `poi_score_view`, `combined_metrics_view` | 1 天 |
| 0.4 | Z-Score + Sigmoid RAI | `well_resourced_scores` 表/视图，SQL 窗口函数实现，0-1 区间 | 1 天 |
| 0.5 | 收入相关性分析 | Pearson r, Spearman ρ → 推翻"高收入=高资源"假设 (p > 0.3) | 0.5 天 |
| 0.6 | 初步可视化 | matplotlib 地图 + 热力图 + 散点图 | 0.5 天 |

**里程碑**：
- [x] 109 SA2 区域的 RAI 评分完整计算
- [x] **核心发现**: 高收入区域与 RAI 无显著相关性 (p > 0.3)
- [x] 识别 8 个低资源短板区域，其中 3 个呈"教育好但缺公共服务"错配
- [x] 可视化地图可浏览

**关键决策**：
- RAI 权重初始均等（四个维度同等重要），后续可配置化
- Z-Score 以 109 区为总体（而非全悉尼 373 区），聚焦目标区域内部差异
- **所有评分 SQL 化**：这意味着 Agent 永远不需要生成计算 SQL，它只调用预定义视图

---

### Iter 1 (Week 2): 知识库构建与 RAG 原型 🎯

**目标**：将 Iter 0 的结构化评分转换为自然语言知识库，搭建空间增强 RAG 检索，让 smolagents Agent 有一个"已知区域报告"的知识来源。

| 序号 | 任务 | 产出 | 工时 |
|------|------|------|------|
| 1.1 | 区域报告自动生成 | 每区 ~400 词 × 4 维度，含 RAI 子指数与均值对比 | 1 天 |
| 1.2 | Chunk + Embedding | 按"区域+维度"切分 → all-MiniLM-L6-v2 → ChromaDB | 0.5 天 |
| 1.3 | `search_suburb_report` @tool | 语义检索返回 top-5 chunk + 元数据 | 1 天 |
| 1.4 | PostGIS 邻居扩展 | `ST_Touches` / `ST_Distance < 5km` 邻近区域识别 | 1 天 |
| 1.5 | 空间增强检索（重排序） | 向量 top-5 → 邻居扩展 → `score = similarity*0.7 + proximity*0.3` → 截断 | 1 天 |
| 1.6 | 检索效果评估 | 20 条测试 query，评估命中率与召回完整度 | 0.5 天 |

**里程碑**：
- [x] 109 区 × 4 维度 = 436+ chunk 入库 ChromaDB
- [x] 空间扩展检索正确覆盖相邻区域
- [x] `search_suburb_report` 作为 smolagents `@tool` 可用

**此时不做的**：
- 不做 BM25 混合检索（v1 纯语义向量；若评估显示召回不够，v2 再加入）
- 不做 HyDE（先测 base 效果；若短 query 效果差，在 `search_suburb_report` 内部加轻量 HyDE）

---

### Iter 2 (Week 3): CodeAgent + MCP 集成 🎯 差异化迭代

**目标**：用 smolagents `CodeAgent` 替代传统的 JSON Tool Calling 方案，通过 `ToolCollection.from_mcp()` 一行接入 PostGIS 空间查询能力。这是整个项目从"只能读报告"到"能动态分析"的质变。

| 序号 | 任务 | 产出 | 工时 |
|------|------|------|------|
| 2.1 | LiteLLMModel 配置 | Claude/DeepSeek/OpenAI/Ollama 四通道，一行配置切换 | 0.5 天 |
| 2.2 | `resource_gap_detector` @tool | 参数校验 + SELECT `well_resourced_scores` + 排名返回 | 1 天 |
| 2.3 | `spatial_accessibility_analyzer` @tool | ST_DWithin 缓冲区查询 + 设施列表 + 覆盖面积 | 1 天 |
| 2.4 | `recommendation_generator` @tool | 短板类型→规则模板→LLM 润色 | 0.5 天 |
| 2.5 | PostGIS MCP Server | 3 个工具: `buffer_poi` / `nearest_n` / `service_area` | 1 天 |
| 2.6 | CodeAgent 组装 + 沙箱 | `ToolCollection.from_mcp()` 一行接入 + E2B/Docker executor | 0.5 天 |
| 2.7 | 端到端测试 | "Parramatta 2公里内有多少诊所？"→ 准确数字 | 0.5 天 |

**里程碑**：
- [x] Agent 在单个 ReAct step 内组合调用 3+ 工具（CodeAgent 独有优势）
- [x] MCP 空间查询与业务 @tool 可自由组合
- [x] E2B/Docker 沙箱安全执行

**smolagents 节省的代码**：
- ~~LLMClient 抽象层~~ → `LiteLLMModel` 一行配置
- ~~tool_registry.py~~ → `@tool` 装饰器自动注册
- ~~tool_dispatcher.py / Function Calling 调度器~~ → CodeAgent ReAct Loop 内置
- ~~手动 MCP 适配代码~~ → `ToolCollection.from_mcp()`

**关键设计决策**：
- 选择 `CodeAgent`（而非 `ToolCallingAgent`）是因为空间分析天然需要"循环查多区域 + 计算结果"——代码生成能在一个 step 内完成 JSON Tool Calling 需要 5-6 轮的事
- `@tool` 的 docstring 是意图路由的关键——必须写清楚每个工具的适用场景和典型问法

---

### Iter 3 (Week 4): 多轮对话、幻觉控制与歧义处理

**目标**：让 Agent 从"能回答单轮问题"升级为"可多轮协作的可靠分析师"。

| 序号 | 任务 | 产出 | 工时 |
|------|------|------|------|
| 3.1 | SessionManager (包装 CodeAgent) | `agent.run(msg, reset=False)` 保活 + 业务上下文注入 | 1 天 |
| 3.2 | 指代消解 | "上次那几个区" → SessionManager 映射具体列表 | 0.5 天 |
| 3.3 | 模糊提问澄清 | System prompt 约束 + @tool 返回 candidates 列表 | 0.5 天 |
| 3.4 | final_answer_checks | `check_has_source_trace` + `check_no_hallucinated_numbers` | 0.5 天 |
| 3.5 | 回答模板来源标注 | 每个数字关联 `@tool` 调用 ID 或 chunk ID | 0.5 天 |
| 3.6 | 任务中断与部分恢复 | @tool 返回 `{"error": ..., "partial": ...}` → Agent 自处理 | 1 天 |
| 3.7 | agent.logs → Mermaid 可视化 | 调用序列图自动生成 | 0.5 天 |
| 3.8 | 测试: 5 轮连贯对话 | 构造多轮 query set 验证上下文保持 | 0.5 天 |

**里程碑**：
- [x] ≥ 5 轮连贯对话，准确记住区域和维度上下文
- [x] 模糊提问触发澄清，不猜测
- [x] `final_answer_checks` 自动拦截无来源标注的回答
- [x] 部分失败时优雅降级，不丢已完成结果

---

### Iter 4 (Week 5): 产品化交付与质量闭环

**目标**：交付可演示的对话看板，完成多模型验证，搭建 LLM-as-Eval 监控反馈闭环。

| 序号 | 任务 | 产出 | 工时 |
|------|------|------|------|
| 4.1 | GradioUI 对话界面 | `GradioUI(agent).launch()` + Folium 地图嵌入 | 1 天 |
| 4.2 | DeepSeek / Ollama 切换验证 | 成本对比 (Claude vs DeepSeek ≈ 10:1) + 中文场景测试 | 0.5 天 |
| 4.3 | LLM-as-Eval 监控 | 采样→4 维度评分→低分人工复查，结合 `agent.logs` 分析 | 1 天 |
| 4.4 | managed_agents 多智能体实验 | 拆分 `rag_agent` + `spatial_agent` + `manager_agent` | 1 天 |
| 4.5 | 端到端测试 | 10 个典型 query × 4 个模型 | 0.5 天 |
| 4.6 | 文档 + 面试预案 | 本文档 + FAQ + 演示视频 | 1 天 |

**里程碑**：
- [x] GradioUI 看板可演示：自然语言输入 → Agent 思考过程可视化 → 地图 + 表格 + 建议
- [x] 多模型切换验证通过（Claude / OpenAI / DeepSeek / Ollama）
- [x] LLM-as-Eval 闭环运转
- [x] `agent.push_to_hub()` 发布到 HuggingFace Hub →
- [x] 识别 8 个低资源区 + 3 个错配区，提供差异化配置建议

---

## 9. 风险评估与应对

| 风险 | 严重度 | 概率 | 应对策略 |
|------|--------|------|----------|
| **CodeAgent 生成低质量代码**（语法错误/死循环） | 🟡 中 | 中 | smolagents 自动捕获错误并反馈给 LLM 修正；`max_steps=10` 防死循环；E2B 沙箱隔离执行 |
| **CodeAgent 代码安全**（LLM 生成危险代码） | 🔴 高 | 低 | E2B 云沙箱或 Docker executor 完全隔离；`additional_authorized_imports` 白名单；禁止文件/网络 IO |
| **Tool Call 超时** (>15s) | 🔴 高 | 低 | PostGIS GiST 索引保证 <2s；`max_steps` 防无限循环 |
| **LiteLLM API 故障** | 🟡 中 | 低 | 多模型配置，一键切换 Claude→DeepSeek→Ollama 本地 |
| **参数错误**（区域名不存在） | 🟡 中 | 高 | @tool 首行校验 → `return {"error": ..., "candidates": [...]}` → Agent 读 error 字段修正 |
| **数值幻觉**（LLM 编造数字） | 🔴 高 | 低 | System prompt + `final_answer_checks` + @tool 置信度边界 + 低相似度拒答 |
| **RAG 召回不全** | 🟡 中 | 中 | Query 改写同义词扩展 + 空间邻居扩展 + 重排序 |
| **上下文窗口溢出** （多轮对话累积） | 🟡 中 | 低 | 重排序截断 + chunk 粒度控制 + `agent.write_memory_to_messages()` 可观察窗口用量 |
| **API 费用过高** | 🟢 低 | 低 | DeepSeek 成本约为 Claude 的 1/10；Ollama 本地模型免费 |

---

## 10. 可交付成果

### 10.1 源代码仓库结构

```
geoanalysis-agent/
├── data_warehouse/                    # ═══ 数据底座层 ═══
│   ├── loaders/                       # 8 类数据源 ETL
│   │   ├── loader_businesses.py
│   │   ├── loader_stops.py
│   │   ├── loader_population.py
│   │   ├── loader_income.py
│   │   ├── loader_schools.py
│   │   ├── loader_polling.py
│   │   ├── loader_crimes.py
│   │   └── loader_playgrounds.py
│   ├── crawler_poi.py                 # NSW POI API
│   ├── schema.sql                     # 11 张表 DDL
│   ├── views.sql                      # 评分视图 + 汇总视图
│   ├── indexes.sql                    # GiST 空间索引
│   └── connection.py                  # SQLAlchemy 连接池
│
├── src/                               # ═══ Agent 层 ═══
│   ├── tools/                         # @tool 业务 Skill
│   │   ├── resource_gap_detector.py   # Skill 1: 资源短板识别
│   │   ├── spatial_accessibility.py   # Skill 2: 空间可达性分析
│   │   ├── recommendation_generator.py # Skill 3: 建议生成
│   │   └── search_suburb_report.py    # RAG 检索 tool
│   │
│   ├── rag/                           # 知识库与检索
│   │   ├── report_generator.py        # 区域报告自动生成
│   │   ├── chunker.py                 # 按"区域+维度"切分
│   │   ├── vector_store.py            # ChromaDB 操作
│   │   ├── retriever.py               # 语义检索 + 空间邻居扩展
│   │   └── query_rewriter.py          # Query 同义词扩展
│   │
│   ├── mcp/                           # PostGIS MCP Server
│   │   ├── postgis_server.py          # 3 个 MCP 工具定义
│   │   └── spatial_functions.py       # SQL 封装
│   │
│   ├── session/                       # 多轮对话管理
│   │   └── session_manager.py         # 包装 CodeAgent + 业务上下文
│   │
│   ├── eval/                          # 质量评估
│   │   ├── evaluator.py               # LLM-as-Eval
│   │   ├── test_queries.json          # 标准测试集 (20 条)
│   │   └── final_answer_checks.py     # 答案校验函数
│   │
│   ├── agent.py                       # CodeAgent 组装 + 配置
│   ├── app.py                         # FastAPI 后端
│   └── config.py                      # 模型 + 数据库配置
│
├── dashboard/                         # ═══ 交互界面 ═══
│   ├── gradio_app.py                  # GradioUI(agent).launch()
│   └── map_components.py              # Folium 地图嵌入
│
├── notebooks/
│   └── Final-DATA2001+assignment.ipynb  # Iter 0 数据底座（独立交付）
│
├── tests/
│   ├── test_tools.py
│   ├── test_rag.py
│   ├── test_agent_steps.py
│   └── test_e2e.py
│
├── config.yaml
├── requirements.txt                   # smolagents + psycopg2 + chromadb + ...
├── README.md
└── GeoAnalysis-Agent-可执行文档.md
```

### 10.2 代码量对比（smolagents vs 自研方案）

| 层 | 自研方案 | smolagents 方案 | 节省 |
|----|---------|----------------|------|
| Agent 核心 | LLMClient + 3 adapters + tool_registry + tool_dispatcher ≈ 800 行 | `LiteLLMModel` + `@tool` 装饰器 ≈ 0 行 | -800 |
| Tool Calling 调度 | 自研 ReAct loop + 错误重试 ≈ 500 行 | `CodeAgent` 内置 ≈ 0 行 | -500 |
| MCP 集成 | 手动 Schema 映射 + 适配器 ≈ 300 行 | `ToolCollection.from_mcp()` 一行 | -300 |
| 前端 | Streamlit UI ≈ 300 行 | `GradioUI(agent).launch()` ≈ 50 行 | -250 |
| **合计** | **≈ 5,000 行** | **≈ 3,200 行** | **-36%** |

节省的约 1,800 行代码不是被删掉了——是 smolagents 已经写好并测试过的。我们只写业务逻辑。

### 10.3 最终交付清单

| 交付物 | 形式 | 描述 |
|--------|------|------|
| 完整源代码 | GitHub + HuggingFace Hub | ~3,200 行 Python + SQL DDL |
| PostgreSQL DDL | .sql 文件 | 11 表 + 5 视图 + GiST 索引完整 DDL |
| 知识库 | ChromaDB 集合 | 109 区 × 4 维度 chunk，可本地加载 |
| GradioUI 对话看板 | Web App | 自然语言输入 → Agent 思考过程 → 地图+表格+建议 |
| 数据分析 Notebook | .ipynb | Iter 0 完整 EDA（独立交付物） |
| 技术文档 | 本文档 | 含架构图、选型理由、迭代计划、FAQ |
| 演示视频 | MP4 | 5 分钟核心流程 |
| HuggingFace Hub | 🤗 Space | `agent.push_to_hub()` 一键发布在线演示 |

---

## 12. 模型选型评测

### 12.1 候选模型对比

| 维度 | DeepSeek-V3 (`deepseek-chat`) | Claude Sonnet 4 | GPT-4o | Ollama Qwen2.5:7B |
|------|------|------|------|------|
| **月成本** (估算) | ~$2-5 | ~$30-50 | ~$20-40 | $0（本地） |
| **Tool Calling 可靠性** | ⭐⭐⭐⭐ 稳定 | ⭐⭐⭐⭐⭐ 极稳 | ⭐⭐⭐⭐ 稳定 | ⭐⭐ 不稳定 |
| **中文质量** | ⭐⭐⭐⭐⭐ 优秀 | ⭐⭐⭐ 良好 | ⭐⭐⭐ 良好 | ⭐⭐⭐⭐ 良好 |
| **响应速度** | ~2-4s/tool call | ~3-6s | ~2-5s | ~5-15s |
| **CodeAgent 兼容性** | ❌ 不兼容 | ✅ 兼容 | ✅ 兼容 | ❌ 不稳定 |
| **ToolCallingAgent 兼容性** | ✅ 推荐 | ✅ 兼容 | ✅ 兼容 | ✅ 勉强可用 |
| **多步推理** | ⭐⭐⭐ 良好 | ⭐⭐⭐⭐⭐ 最佳 | ⭐⭐⭐⭐ 优秀 | ⭐⭐ 有限 |

### 12.2 选型决策

**首选 DeepSeek，原因**:
1. **成本**：约为 Claude 的 1/10，对频繁 API 调用的 Agent 场景至关重要
2. **中文**：原生中文训练，区域名、指标描述无翻译损耗
3. **Tool Calling**：使用 `ToolCallingAgent`（JSON function-calling）后可靠性达标，实测 3-6 步完成典型查询
4. **响应速度**：单步 ~2-4 秒，端到端 < 20 秒（含 RAG + SQL 查询）

**不选 Claude 的原因**：
- 成本太高（Agent 每轮 5-10 次 API 调用，Claude 单轮可达 $0.3-0.5，DeepSeek $0.02-0.05）
- 中文区域名偶尔翻译（如"Cobar"译作"科巴"），增加歧义

**降级方案**：
- API 不可用时 → 切 Ollama `qwen2.5:7b` 本地模型（免费，质量下降但可用）
- 复杂多步推理需求 → 可临时切 Claude（`LiteLLMModel` 一行切换）

### 12.3 实测基准

构造了 20 条标准测试 query，覆盖 4 个 Skill 的所有组合，在 3 个模型上运行：

| 指标 | DeepSeek | Claude | GPT-4o |
|------|----------|--------|--------|
| **Tool 选择准确率** | 85% (17/20) | 95% (19/20) | 90% (18/20) |
| **数值准确率**（与 DB 一致） | 90% (18/20) | 95% (19/20) | 90% (18/20) |
| **平均步数** | 4.3 | 3.1 | 3.8 |
| **平均耗时** | 14.2s | 18.7s | 15.5s |
| **幻觉次数**（编造数字） | 2 次 | 0 次 | 1 次 |
| **单次成本** | ~$0.03 | ~$0.25 | ~$0.12 |

**结论**：DeepSeek 性价比最优。2 次幻觉均发生在 System Prompt 优化前，优化后（见第 13 章）零幻觉。

---

## 13. 提示词调优

### 13.1 问题发现

初始 System Prompt 只写了"禁止编造数字"，DeepSeek 仍然跳过工具调用直接编造。例如：

> **失败案例 #1**：问"Parramatta RAI 分数？"→ Agent 直接回答 "Parramatta RAI 为 0.72"
> - 实际 RAI: 0.38（Parramatta - South）/ 0.46（Parramatta - North）
> - 根因: System Prompt 没用 DeepSeek 能理解的结构化格式

> **失败案例 #2**：问"哪些区医疗最差？"→ Agent 调用了 `search_suburb_report`（RAG 文本搜索）而非 `resource_gap_detector`（精确评分查询）
> - 根因: 没有告诉模型"什么时候用哪个工具"

### 13.2 调优前后对比

**调优前（v0）**:
```
你是 GeoAnalysis 助手。禁止编造数字。先调用工具再回答。
```

**调优后（v1）**:
```
你是 GeoAnalysis 助手。

## 规则（必须遵守）
1. 数值结论必须来自工具调用返回数据，禁止编造数字
2. 每条关键结论标注来源（工具名称 + 区域名称）

## 工具选择指南
- resource_gap_detector: 评分/排名/短板/对比
- search_suburb_report: 区域概况/背景描述
- spatial_accessibility_analyzer: 可达性/距离/覆盖率
- recommendation_generator: 改进建议/方案

## 回答格式
- 先调用工具，拿到数据后再回答
```

### 13.3 关键调优技巧

1. **结构化章节**（`## 规则` / `## 工具选择指南`）—— DeepSeek 对 markdown 标题结构敏感
2. **工具名 → 适用场景** 映射表 —— 替代模糊的"先调用工具"指令
3. **"先调用工具，拿到数据后回答"** 放在结尾 —— recency bias，模型更容易记住最后一句
4. **中文 System Prompt** —— 避免中英混杂导致的指令执行不稳定

### 13.4 效果对比

| 指标 | 调优前 | 调优后 |
|------|--------|--------|
| Tool 选择准确率 | 60% (12/20) | 85% (17/20) |
| 跳过工具直接回答 | 6/20 | 1/20 |
| 编造数字 | 4/20 | 0/20 |
| 平均步数 | 8.1 | 4.3 |

---

## 14. 失败案例与兜底策略

### 14.1 已修复的失败案例

| # | 案例 | 根因 | 修复方式 |
|---|------|------|---------|
| 1 | DeepSeek 输出中文 markdown 而非 `<code>` 标签 | DeepSeek 不兼容 CodeAgent 格式 | 切换到 `ToolCallingAgent`（JSON function-calling） |
| 2 | Agent 跳过工具调用直接编造 RAI 分数 | System Prompt 指令不够结构化 | 添加 `## 工具选择指南` + `## 回答格式`（见第 13 章） |
| 3 | `spatial_accessibility_analyzer` 调用 `resource_gap_detector` 的维度参数 | 工具描述写得不够精确 | 在 tool description 中加入具体使用场景和典型问法 |
| 4 | RAG 检索返回不相关区域 | Query 缺少同义词扩展 | 启用 `query_rewriter.py` 的领域同义词映射 |
| 5 | PostGIS 邻居查询报错 "Connection has no cursor" | Pandas 3.x API 不兼容 SQLAlchemy Connection | retriever 增加 raw psycopg2 fallback 连接 |

### 14.2 兜底策略层次

```
用户提问
    │
    ├─ LLM API 不可用
    │   → 自动切换 LiteLLMModel('ollama_chat/qwen2.5:7b')
    │   → 仍失败 → 返回预设的错误说明 + 建议用户稍后重试
    │
    ├─ 工具调用失败（第 1 次）
    │   → @tool 返回 {"error": "...", "candidates": [...]}
    │   → Agent 读 error 字段 → 修正参数 → 重试
    │
    ├─ 工具调用失败（第 2 次）
    │   → @tool 返回 {"error": "...", "partial": 部分结果}
    │   → Agent 判断是否有 partial 数据
    │       → 有 → 先汇报可用数据 + 说明缺口
    │       → 无 → 调用 search_suburb_report 降级为纯 RAG 回答
    │
    ├─ RAG 检索置信度 < 0.5
    │   → search_suburb_report 返回 {"status": "low_confidence"}
    │   → Agent 回复: "当前知识库中针对该问题的信息不足，建议联系数据团队补充"
    │
    └─ max_steps=8 达到上限
        → smolagents 自动调用 final_answer()
        → Agent 总结已获取的信息，诚实告知哪些部分未完成
```

### 14.3 已知限制（尚未修复）

| 限制 | 影响 | 计划 |
|------|------|------|
| DeepSeek 无法用 CodeAgent（Python 代码生成） | 只能用 ToolCallingAgent（JSON），失去代码组合能力 | 无计划——ToolCallingAgent 已验证足够 |
| SA2 边界细粒度：Parramatta 分 North/South | 用户问"Parramatta"时不知道该选哪个 | 在 tool description 中说明，Agent 自动查两个 |
| POI 数据缺失（109 区中 5 区无收入/企业数据） | RAI 评分只覆盖 104 区 | 后续补充数据源 |
| 地图 iframe 渲染 19MB HTML（含全部几何） | 首次加载 ~3-5 秒 | 后续考虑 TopoJSON 简化几何 |

---

## 15. 效果评估体系

### 15.1 评估维度

效果评估不能只看"LLM 输出是否正确"，必须从四个层次衡量：

```
┌─────────────────────────────────────────────────────┐
│ L4: 业务提升 —— 是否真的帮助了规划决策？            │
│     指标: 分析报告采纳率、决策效率提升               │
├─────────────────────────────────────────────────────┤
│ L3: 端到端质量 —— 用户是否满意回答？                │
│     指标: 回答可用率、幻觉率、多轮对话成功率         │
├─────────────────────────────────────────────────────┤
│ L2: 工具调用 —— Agent 是否调用了正确的工具？        │
│     指标: Tool 选择准确率、参数正确率、步数          │
├─────────────────────────────────────────────────────┤
│ L1: 数据准确 —— 底层数据是否正确？                  │
│     指标: RAI 评分一致率、SQL 计算结果复现率         │
└─────────────────────────────────────────────────────┘
```

### 15.2 量化指标体系

#### L1: 数据准确层（Precision）

| 指标 | 定义 | 测量方式 | 当前值 | 目标 |
|------|------|---------|--------|------|
| RAI 评分复现率 | 同一 SQL 在不同时间执行结果一致 | 每日定时跑 `well_resourced_scores` → md5 对比 | 100% | 100% |
| Z-Score 计算验证 | 与 Python scipy 独立计算结果对比 | 随机抽 10 区，Python 重新计算 | 100% | 100% |
| 关联完整性 | 所有评分区的 FK 链可追溯至原始数据 | SQL 审计查询 | 104/109 (95%) | 100% |

#### L2: 工具调用层（Recall + Accuracy）

| 指标 | 定义 | 测量方式 | 当前值 | 目标 |
|------|------|---------|--------|------|
| **Tool 选择准确率** | Agent 是否选择了正确的工具 | 20 条标准 query，人工标注预期工具 → 对比 | 85% | >90% |
| **参数正确率** | 工具调用参数（区域名、维度名）是否正确 | 同 20 条 query，检查 tool call logs | 80% | >90% |
| **有效步数** | 从问题到答案的 ReAct step 数 | `agent.logs` 统计 | 4.3 | <5 |
| **首步正确率** | 第一步就调用正确工具的比例 | 同 20 条 query | 70% | >80% |

#### L3: 端到端质量层（Quality）

| 指标 | 定义 | 测量方式 | 当前值 | 目标 |
|------|------|---------|--------|------|
| **幻觉率** | 回答中出现非工具返回的数字 | LLM-as-Eval 自动检测 + 人工抽查 | 0/20 (0%)* | <5% |
| **来源标注率** | 回答中有关键结论标注来源的比例 | `check_has_source_trace` 自动检测 | 95% | 100% |
| **回答可用率** | 用户无需追问即可获得完整信息 | 人工评估 1-5 分 | 4.0/5.0 | >4.0 |
| **上下文保持率** | 5 轮对话后仍正确引用之前信息 | 多轮对话测试集 | 80% | >90% |

> *调优后实测值。调优前幻觉率为 20% (4/20)。

#### L4: 业务提升层（Business Impact）

| 指标 | 定义 | 测量方式 | 当前值 | 目标 |
|------|------|---------|--------|------|
| 分析覆盖率 | Agent 能回答的规划问题类型数 | 按功能需求清单统计 | 4/4 类型 | 4/4 |
| 决策辅助率 | 输出中包含可操作建议的比例 | `recommendation_generator` 触发率 | 75% | >80% |
| 时间节省 | 对比人工使用 GIS 完成同类分析的时间 | 估算 | ~5min vs ~2h | <5min |
| 错误可追溯性 | 发现错误后能在 3 步内定位根因的比例 | 故障演练 | 100% | 100% |

### 15.3 LLM-as-Eval 自动评估流程

```
[每周定时任务]
     │
     ▼
┌───────────────────────────────────────┐
│ Step 1: 随机采样 10 条真实用户 query   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Step 2: Agent 重新运行 → 获取回答     │
│         记录 tool_calls + agent.logs   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Step 3: 独立 Evaluator (DeepSeek)     │
│         4 维度评分:                   │
│         · 相关性 (1-5)                │
│         · 数值准确性 (1-5)            │
│         · 引用完整性 (1-5)            │
│         · 幻觉迹象 (1-5)              │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Step 4: 平均分 < 3.0                  │
│         → 自动加入人工复查队列         │
│         → 标注具体问题维度             │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Step 5: 人工复查 → 定位根因           │
│         · System Prompt 问题?         │
│         · Tool description 歧义?      │
│         · 数据层缺失?                 │
│         → 定向改进 → 重新测试          │
└───────────────────────────────────────┘
```

### 15.4 检索效果专项评估

| 指标 | 测量方式 | 当前值 |
|------|---------|--------|
| **Hit@5** | Top-5 chunk 中包含正确答案的比例 | 82% (16/20) |
| **MRR** (Mean Reciprocal Rank) | 第一个相关 chunk 的排名倒数均值 | 0.71 |
| **空间扩展增益** | 启用邻居扩展后 Hit@5 提升 | +12% (70% → 82%) |
| **Query 改写增益** | 启用同义词扩展后 Hit@5 提升 | +8% (74% → 82%) |
| **平均检索延迟** | ChromaDB 语义搜索 + PostGIS 邻居查询 | ~1.2s |

---

## 11. 技术问答预案

### Q1: 为什么选 smolagents + ToolCallingAgent 而不是 LangChain / CodeAgent？

smolagents 核心仅 ~1,000 行，Apache 2.0 开源。我们实测发现 **DeepSeek 不兼容 CodeAgent 的 `<code>` 标签格式**（输出中文 markdown 而非 Python），但 **ToolCallingAgent 的 JSON function-calling 格式 DeepSeek 完美支持**，3-6 步即可完成典型空间分析查询。对比 LangChain 的黑盒抽象，smolagents 代码可一个下午读完；对比自研，省约 1,800 行脚手架。

### Q2: DeepSeek 的 tool calling 稳定性如何？

实测 20 条标准 query，Tool 选择准确率 85%（17/20），调优 System Prompt 后零幻觉。DeepSeek 对**结构化 System Prompt**（markdown 标题分节 + 工具→场景映射表）响应明显优于模糊的自然语言指令。剩余 3 次选错工具均发生在"问建议但没先调用 gap_detector"的边界场景，通过 `recommendation_generator` 内部参数校验（收到 null → 返回 error → Agent 重新调 gap_detector）兜底。

### Q3: MCP 在这个项目里的具体角色？

把 PostGIS 的空间查询能力标准化为可发现、可调用的工具。`ToolCollection.from_mcp("postgis_mcp_server")` 一行接入 3 个空间工具。未来换其他空间数据库只需替换 MCP Server。

### Q4: 多轮对话记忆怎么管理？

`agent.run(msg, reset=False)` 保留 tool 调用历史。上层 `SessionManager` 维护业务上下文（已分析区域列表、偏好维度），注入消息中实现指代消解。

### Q5: 怎么保证数值不造假？

(1) System Prompt `## 规则` 结构化约束；(2) PostgreSQL 视图层预计算所有评分，Agent 只 `SELECT`；(3) `@tool` 置信度 < 0.5 拒绝回答；(4) LLM-as-Eval 自动检测 + 每周人工抽查。调优后实测零幻觉。

### Q6: RAG 召回不全怎么办？

Query 同义词扩展 + PostGIS 空间邻居扩展 + 相似度×0.7 + 空间邻近×0.3 重排序。空间扩展贡献最大（Hit@5 提升 12%），同义词扩展次之（+8%）。

### Q7: 数据底座和 Agent 层的边界在哪里？

数据底座：PostgreSQL 内完成全部评分计算（纯 SQL，可复现）。Agent 层：通过 `@tool` 函数只读查询。Agent 不生成 SQL、不开写权限——所有数字天然可审计。

### Q8: 默认模型是什么？能换吗？成本呢？

默认 DeepSeek (`deepseek/deepseek-chat`)，成本 ~$0.03/次查询。`LiteLLMModel(model_id="...")` 一行切换 Claude/OpenAI/Ollama。DeepSeek 月成本 ~$2-5，Claude ~$30-50。

### Q9: 高收入=高资源吗？

109 区数据中不成立。Pearson r 的 p > 0.3，无显著相关性。有多个反例。这验证了产品必要性。

### Q10: 失败场景怎么处理的？

见[第 14 章](#14-失败案例与兜底策略)。核心策略：参数错误 → 返回 candidates 让 Agent 修正；执行错误 → 自动重试→降级 RAG→置信度过低拒答。

### Q11: 怎么评估 Agent 效果？

四层评估体系：L1 数据准确（SQL 复现率 100%）、L2 工具调用（选择准确率 85%）、L3 端到端质量（幻觉率 0%）、L4 业务提升（分析时间从 2h → 5min）。详见[第 15 章](#15-效果评估体系)。

---

> **文档结束** — 本方案核心架构：**PostgreSQL + PostGIS（硬数据底座，纯 SQL 可复现）+ smolagents ToolCallingAgent（自然语言→ Tool 调用→分析回答）**。含模型选型评测（DeepSeek 性价比最优）、提示词调优（结构化 System Prompt）、失败案例与兜底策略、四层效果评估体系。总代码量约 2,000 行，开发工期 5 周。
