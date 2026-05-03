# 智旅Agent工作流平台

> 基于 LangGraph + MCP 协议的多智能体旅行服务协作平台，实现 17 个业务工具的标准化远程调用与 4 个子 Agent 的配置化动态编排。

---

## 项目描述

作为 **Agent 应用开发工程师**，独立设计并实现了基于 LangGraph 的多智能体工作流系统，为携程瑞士航空提供航班查询、酒店预订、租车服务、游览推荐等一站式旅行助理能力。

### 核心成果（量化）

| 指标 | 数据 |
|------|------|
| **MCP 工具数** | 17 个业务工具全部通过 FastMCP 封装为标准化 MCP Server，支持 stdio/SSE/HTTP 三种传输协议 |
| **Agent 数量** | 1 个主 Agent + 4 个子 Agent（航班/酒店/租车/游览），覆盖 5 大业务域 |
| **代码精简** | Skill 可配置系统将子助理定义从 ~180 行硬编码缩减至 21 行配置文件，新增技能零代码改动 |
| **测试覆盖** | 28 条评测用例 + 22 个单元测试全部通过，三维度加权评分（路由 40% + 工具 35% + 回复质量 25%） |
| **安全机制** | 敏感操作（预订/取消/修改）执行前自动中断等待用户确认，safe/sensitive 工具分层管控 |
| **容错降级** | MCP Server 不可用时自动降级为本地工具调用，系统可用性不受影响 |
| **RAG 检索** | 基于 ChromaDB + 文本嵌入的 FAQ 政策向量检索，支持自然语言查询 |

### 架构亮点

- **MCP 标准化**：所有工具通过 Anthropic MCP 标准协议暴露，Agent 通过 stdio 子进程动态加载，实现工具热插拔
- **Skill 配置化**：子助理提示词、工具绑定、触发路由全部 JSON 配置驱动，SkillRegistry 单例自动构建子图
- **dialog_state 栈管理**：LIFO 栈实现子任务生命周期管理，完成后自动弹出回到主助理
- **流式输出**：支持 Streamlit Web 页面实时展示 Agent 思考与工具调用过程

---

## 目录结构

```
智旅Agent工作流平台/
├── README.md
├── requirements.txt
├── trip_assistant/
│   ├── app.py                         # 命令行入口
│   ├── config.py                      # 统一配置管理
│   ├── skills.json                    # Skill 配置文件（4 个子助理定义）
│   ├── mcp_server.py                  # MCP Server 入口（17 个工具）
│   ├── travel_new.sqlite              # 业务数据库
│   ├── travel2.sqlite                 # 航班数据库
│   ├── order_faq.md                   # FAQ 政策文档（RAG 向量检索源）
│   │
│   ├── graph_chat/                    # 核心工作流逻辑
│   │   ├── assistant.py               # 主助理节点 + 提示词
│   │   ├── agent_assistant.py         # Skill 注册入口
│   │   ├── skill_loader.py            # Skill 加载器（JSON → Runnable）
│   │   ├── skill_registry.py          # Skill 注册中心（单例，动态构建子图）
│   │   ├── build_child_graph.py       # 子图构建入口
│   │   ├── base_data_model.py         # Pydantic 路由模型
│   │   ├── entry_node.py              # 入口节点工厂
│   │   ├── state.py                   # LangGraph 状态定义
│   │   ├── llm_tavily.py              # LLM 初始化 + Tavily 搜索
│   │   └── log_utils.py               # 日志系统（loguru）
│   │
│   ├── tools/                         # 业务工具函数
│   │   ├── flights_tools.py           # 航班搜索/改签/取消
│   │   ├── hotels_tools.py            # 酒店搜索/预订/更新/取消
│   │   ├── car_tools.py               # 租车搜索/预订/更新/取消
│   │   ├── trip_tools.py              # 游览推荐/预订/更新/取消
│   │   ├── location_trans.py          # 中英文城市名转换
│   │   ├── retriever_vector.py        # FAQ 向量检索（ChromaDB）
│   │   ├── tools_handler.py           # 工具节点 + 中断处理
│   │   └── init_db.py                 # 数据库时间重置
│   │
│   ├── mcp_client/                    # MCP 客户端
│   │   ├── __init__.py
│   │   └── client.py                  # MCPClientManager（stdio/sse/http）
│   │
│   ├── evaluation/                    # 自动化评测系统
│   │   ├── test_cases.json            # 28 条评测用例
│   │   ├── runner.py                  # 评测执行器
│   │   ├── judge.py                   # LLM 评委
│   │   ├── reporter.py                # 报告生成
│   │   └── run_eval.py                # 一键评测入口
│   │
│   ├── evaluation_ui/                 # Streamlit 交互页面
│   │   └── app.py                     # 聊天界面 + 流式输出
│   │
│   └── tests/                         # 单元测试
│       ├── test_skill_registry.py      # Skill 注册机制测试（7 个）
│       └── test_tools.py              # 工具函数测试（15 个）
```

---

## 核心架构

### 主-子 Agent 工作流

```
START → fetch_user_info → primary_assistant
                               ↓
                    route_primary_assistant
         ┌────┬────┬────┬────┬────┐
         ↓    ↓    ↓    ↓    ↓    ↓
    primary  航班   租车   酒店   游览   END
    tools   子图   子图   子图   子图
```

### MCP 工具远程调用架构

```
┌──────────────────────────────────────────────┐
│  主 Agent（LangGraph）                         │
│  ┌────────────────────────────────────────┐  │
│  │  MCPClientManager                      │  │
│  │  通过 stdio 启动 MCP Server 子进程       │  │
│  │  自动加载 17 个工具为 LangChain 工具      │  │
│  └────────────────┬───────────────────────┘  │
│                   │ stdio                      │
│  ┌────────────────▼───────────────────────┐  │
│  │  MCP Server (mcp_server.py) - 独立进程   │  │
│  │  航班: search / update / cancel / fetch │  │
│  │  酒店: search / book / update / cancel  │  │
│  │  租车: search / book / update / cancel  │  │
│  │  游览: search / book / update / cancel  │  │
│  │  FAQ:  lookup_policy (RAG 向量检索)    │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**MCP 特性**：
- **独立进程**：MCP Server 是独立 Python 子进程，通过 stdio 通信
- **标准化协议**：使用 Anthropic MCP 标准，非自造协议
- **自动发现**：Agent 启动时自动获取所有工具的描述和参数 schema
- **热插拔**：修改 `.env` 配置即可增减 MCP Server，无需改代码
- **降级容错**：MCP Server 不可用时自动降级为空工具列表

### Skill 配置系统

子助理通过 `skills.json` 配置，支持热扩展：

```json
{
  "name": "update_flight",
  "dialog_state": "update_flight",
  "entry_name": "enter_update_flight",
  "assistant_label": "Flight Updates & Booking Assistant",
  "system_prompt": "您是专门处理航班查询...",
  "safe_tools": ["search_flights"],
  "sensitive_tools": ["update_ticket_to_new_flight", "cancel_ticket"],
  "trigger_model": "ToFlightBookingAssistant"
}
```

新增技能只需在 `skills.json` 中添加定义 + 在 `base_data_model.py` 添加触发模型，图结构、路由、中断控制全部自动生成。

### 路由机制

| 用户意图 | 路由到 | 可用工具 |
|----------|--------|----------|
| 查航班/改签/取消 | update_flight | search_flights, update_ticket_to_new_flight, cancel_ticket |
| 订酒店 | book_hotel | search_hotels, book_hotel, update_hotel, cancel_hotel |
| 租车 | book_car_rental | search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental |
| 游览推荐 | book_excursion | search_trip_recommendations, book_excursion, update_excursion, cancel_excursion |
| 查政策/通用 | primary_assistant | tavily_tool, search_flights, lookup_policy + 全部 MCP 工具 |

### 安全机制

- **敏感工具分离**：每个子助理区分 safe_tools（只读，直接执行）和 sensitive_tools（写操作，需用户确认）
- **中断确认**：sensitive_tools 执行前自动中断，等待用户输入确认
- **dialog_state 栈**：子任务完成后弹出栈，自动回到主助理
- **MCP 工具安全**：MCP 工具统一归入 safe_tools，外部工具默认只读

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入 API Key：

```bash
cp .env.example .env
```

### 3. 启动方式

```bash
# 命令行交互
cd trip_assistant && python app.py

# Streamlit Web 页面
cd trip_assistant/evaluation_ui && streamlit run app.py

# 一键评测
cd trip_assistant/evaluation && python run_eval.py

# 运行测试
pytest trip_assistant/tests/ -v
```

---

## 评测系统

三维度加权评分，28 条测试用例：

| 维度 | 权重 | 说明 |
|------|------|------|
| 路由准确性 | 40% | 是否路由到正确的子助理 |
| 工具调用准确性 | 35% | 是否调用了正确的工具 |
| 回复质量 | 25% | LLM 评委 1-5 分打分 |

---

## 技术栈

| 技术 | 用途 |
|------|------|
| **LangGraph** | 多 Agent 有状态工作流编排，StateGraph + 条件边 + 中断 + checkpointer |
| **LangChain** | LLM 调用抽象、@tool 装饰器、ChatPromptTemplate、bind_tools |
| **MCP (Model Context Protocol)** | Anthropic 标准化工具远程调用协议，Server/Client 分离 |
| **FastMCP** | MCP Server 构建框架，装饰器式工具注册 |
| **langchain-mcp-adapters** | MCP 工具 → LangChain 工具适配层 |
| **DeepSeek / DashScope** | LLM 推理 + 文本嵌入（OpenAI 兼容接口） |
| **Streamlit** | 交互式 Web 页面，流式输出 |
| **SQLite** | 航班/酒店/租车/游览数据存储 |
| **ChromaDB** | 向量检索（FAQ 政策 RAG 查询） |
| **Tavily** | 外部网络搜索 API |
| **Pydantic** | 数据模型验证，路由模型定义 |
| **pytest** | 单元测试框架（22 个测试用例） |
| **loguru** | 结构化日志系统 |
