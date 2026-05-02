# 智旅Agent工作流平台

基于 LangGraph 的多智能体工作流系统，为携程瑞士航空提供航班查询、酒店预订、租车服务、游览推荐等一站式旅行助理能力。

## 项目概览

本项目实现了一个主-子 Agent 协作架构：

- **主助理（CtripAssistant）** 接收用户请求，判断意图后路由到对应的子助理
- **4 个子助理** 分别处理：航班、酒店、租车、游览
- **敏感操作**（预订/取消/修改）执行前需用户确认
- **流式输出** 支持，实时展示 Agent 思考过程
- **自动评测系统** 可量化评估 Agent 表现

## 技术栈

| 技术 | 用途 |
|------|------|
| LangGraph | 多 Agent 工作流编排 |
| LangChain | LLM 调用、工具定义 |
| SQLite | 航班/酒店/租车/游览数据存储 |
| Tavily | 网络搜索（主助理工具） |
| DashScope (通义千问) | LLM 推理 + 文本嵌入 |
| Streamlit | 交互式 Web 页面 |
| Pydantic | 数据模型验证 |

## 目录结构

```
多Agent工作流旅行助手项目/
├── README.md                          # 本文件
├── requirements.txt                   # 项目依赖
├── trip_assistant/                    # 主项目目录
│   ├── app.py                         # 命令行入口（第三个流程图）
│   ├── travel_new.sqlite              # 业务数据库（航班/酒店/租车/游览）
│   ├── travel2.sqlite                 # 数据库备份
│   ├── order_faq.md                   # FAQ 政策文档（向量检索用）
│   ├──
│   ├── graph_chat/                    # 核心工作流逻辑
│   │   ├── assistant.py               # CtripAssistant 节点类 + 主助理提示词
│   │   ├── agent_assistant.py         # 4个子助理的提示词和工具绑定
│   │   ├── build_child_graph.py       # 子工作流构建（航班/酒店/租车/游览）
│   │   ├── base_data_model.py         # Pydantic 路由模型（CompleteOrEscalate 等）
│   │   ├── entry_node.py              # 入口节点工厂（dialog_state 栈管理）
│   │   ├── state.py                   # LangGraph 状态定义
│   │   ├── llm_tavily.py             # LLM 初始化 + Tavily 搜索
│   │   └── draw_png.py                # 流程图可视化
│   │
│   ├── tools/                         # 工具函数
│   │   ├── flights_tools.py           # 航班搜索/改签/取消
│   │   ├── hotels_tools.py            # 酒店搜索/预订/更新/取消
│   │   ├── car_tools.py               # 租车搜索/预订/更新/取消
│   │   ├── trip_tools.py              # 游览推荐/预订/更新/取消
│   │   ├── location_trans.py          # 中英文城市名转换
│   │   ├── retriever_vector.py        # FAQ 向量检索
│   │   ├── tools_handler.py           # 工具节点回退 + 事件打印
│   │   └── init_db.py                 # 数据库时间重置
│   │
│   ├── evaluation/                    # 自动化评测系统
│   │   ├── test_cases.json            # 28 条评测用例数据集
│   │   ├── runner.py                  # 评测执行器（路由/工具/评分）
│   │   ├── judge.py                   # LLM 评委（回复质量打分）
│   │   ├── reporter.py                # 报告生成（控制台 + HTML）
│   │   └── run_eval.py                # 一键评测入口
│   │
│   └── evaluation_ui/                 # Streamlit 交互页面
│       └── app.py                     # 聊天界面 + 流式输出 + 历史记录
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 LLM

编辑 `trip_assistant/graph_chat/llm_tavily.py`，配置你的 API Key：

```python
llm = ChatOpenAI(
    temperature=0,
    model='qwen3.6-plus',  # 或其他模型
    api_key="your-api-key",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
```

### 3. 启动方式

#### 方式一：命令行交互

```bash
cd trip_assistant
python app.py
```

#### 方式二：Streamlit Web 页面

```bash
cd trip_assistant/evaluation_ui
streamlit run app.py
```

#### 方式三：一键评测

```bash
cd trip_assistant/evaluation
python run_eval.py
```

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

### 路由机制

| 用户意图 | 路由到 | 可用工具 |
|----------|--------|----------|
| 查航班/改签/取消 | update_flight | search_flights, update_ticket_to_new_flight, cancel_ticket |
| 订酒店 | book_hotel | search_hotels, book_hotel, update_hotel, cancel_hotel |
| 租车 | book_car_rental | search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental |
| 游览推荐 | book_excursion | search_trip_recommendations, book_excursion, update_excursion, cancel_excursion |
| 查政策/通用 | primary_assistant | tavily_tool, search_flights, lookup_policy |

### 安全机制

- **敏感工具分离**: 每个子助理区分 safe_tools（只读）和 sensitive_tools（写操作）
- **中断确认**: sensitive_tools 执行前自动中断，等待用户输入 `y` 确认
- **dialog_state 栈**: 子任务完成后弹出栈，自动回到主助理

## 评测系统

评测维度（三维度加权）：

| 维度 | 权重 | 说明 |
|------|------|------|
| 路由准确性 | 40% | 是否路由到正确的子助理 |
| 工具调用准确性 | 35% | 是否调用了正确的工具 |
| 回复质量 | 25% | LLM 评委 1-5 分打分 |

28 条测试用例覆盖：航班查询/改签/取消、酒店搜索/预订、租车搜索/预订、游览推荐、政策查询。

## 数据库表

SQLite 数据库 `travel_new.sqlite` 包含：

| 表 | 说明 |
|---|------|
| `flights` | 航班信息 |
| `tickets` / `ticket_flights` / `boarding_passes` | 用户机票及座位 |
| `hotels` | 酒店信息及预订状态 |
| `car_rentals` | 租车信息及预订状态 |
| `trip_recommendations` | 游览推荐及预订状态 |
| `bookings` | 总预订记录 |

## 交互示例

**用户**: "帮我查苏黎世到上海的航班"  
**Agent**: 路由到航班助理 → 调用 `search_flights` → 返回航班列表

**用户**: "我要取消机票 0005432000984"  
**Agent**: 路由到航班助理 → 调用 `cancel_ticket` → ⚠️ 中断等待确认 → 用户确认 → 执行取消

**用户**: "瑞士航空的行李规定是什么"  
**Agent**: 主助理 → 调用 `lookup_policy`（FAQ 向量检索）→ 返回政策说明

## 注意事项

- 数据库路径已改为基于 `Path(__file__)` 的相对路径，移动项目无需修改
- LLM API Key 和 Tavily Key 目前硬编码在 `llm_tavily.py` 中，生产环境建议使用环境变量
- 每次运行 `app.py` 前调用 `update_dates()` 重置数据库时间到最近
- 项目无测试框架，验证依赖手动评测
