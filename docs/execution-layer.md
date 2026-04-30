# 执行层 — 完整设计文档

## 一、概述

执行层是多Agent协作系统安全内核的**演示层**。它是一个模板化的多Agent协作系统，同时采用 **MCP 和 A2A 编排器协作模式**，重点展示**调用拦截**——所有 Agent 的出站调用都经过权限网关实现强行权限管控。

### 核心职责

- 运行一个模板化的多Agent协作示例系统
- 同时展示 MCP 直接调用、A2A 编排调度、A2A + MCP 嵌套三种模式
- 所有调用通过 SDK 封装 → 经过权限网关（递归拦截）
- 提供自然语言交互的 Web UI
- 演示 6 个安全场景（正常/拒绝/申请/deny/self-call/非编排器A2A）

---

## 二、示例场景

### 场景概述

**数据收集与报告生成**（后续替换为飞书三 Agent 场景）：

```
用户输入: "搜索'Python Ed25519'并生成分析报告"

编排器 (Orchestrator)
  │
  ├── ① 调搜索器 Agent 搜索数据
  │     searcher → web_search (自有 MCP)
  │     searcher → page_fetch (自有 MCP)
  │
  ├── ② 调分析器 Agent 分析数据
  │     分析器 → calc (自有 MCP)
  │     分析器 → searcher (A2A, 非编排器调用, 补充搜索)
  │     │   └── searcher → web_search (自有 MCP)
  │     分析器 → chart_gen (自有 MCP)
  │
  └── ③ 调公共 MCP 工具写报告
        编排器 → file_write (公共 MCP)
```

### 三种协作模式覆盖

| 模式 | 在场景中的体现 |
|------|---------------|
| **MCP 直接调用** | searcher → web_search, analyzer → calc 等 |
| **A2A 编排** | orchestrator → searcher, orchestrator → analyzer |
| **A2A + MCP 嵌套** | analyzer → searcher → web_search（递归拦截） |

---

## 三、Agent 与 Tool 清单

### Agent

| Agent ID | 类型 | 自有 MCP 工具 | 说明 |
|----------|------|-------------|------|
| `orchestrator` | orchestrator | 无 | 编排调度，不持有工具 |
| `searcher` | worker | web_search, page_fetch | 搜索相关 |
| `analyzer` | worker | calc, chart_gen | 分析相关 |

### MCP 工具（6 个）

#### 公共 MCP 池

| Tool Name | Owner | 说明 |
|-----------|-------|------|
| `file_read` | public | 读取文件 |
| `file_write` | public | 写入文件 |

#### Searcher 自有池

| Tool Name | Owner | 说明 |
|-----------|-------|------|
| `web_search` | searcher | 网页搜索 |
| `page_fetch` | searcher | 获取网页内容 |

#### Analyzer 自有池

| Tool Name | Owner | 说明 |
|-----------|-------|------|
| `calc` | analyzer | 数据计算 |
| `chart_gen` | analyzer | 图表生成 |

---

## 四、权限配置预设

### 长期令牌 (Standard Token) 预设

```python
# orchestrator 的长期令牌
{
    "agent_id": "orchestrator",
    "label": "编排器基础权限",
    "entries": [
        {"effect": "allow", "object_type": "agent", "object_id": "searcher"},
        {"effect": "allow", "object_type": "agent", "object_id": "analyzer"},
        {"effect": "allow", "object_type": "mcp_tool", "object_id": "*", "tool_owner": "public"},
        {"effect": "deny",  "object_type": "agent", "object_id": "orchestrator"}  # 禁止自调用
    ]
}

# searcher 的长期令牌
{
    "agent_id": "searcher",
    "label": "搜索器基础权限",
    "entries": [
        {"effect": "allow", "object_type": "mcp_tool", "object_id": "*", "tool_owner": "searcher"},
        # 公有工具只开放 file_read
        {"effect": "allow", "object_type": "mcp_tool", "object_id": "file_read", "tool_owner": "public"},
        # 注意：searcher 没有 calc 的权限 → 演示场景 3
        # 注意：searcher 没有 call analyzer 的权限
    ]
}

# analyzer 的长期令牌
{
    "agent_id": "analyzer",
    "label": "分析器基础权限",
    "entries": [
        {"effect": "allow", "object_type": "mcp_tool", "object_id": "*", "tool_owner": "analyzer"},
        {"effect": "allow", "object_type": "mcp_tool", "object_id": "file_read", "tool_owner": "public"},
        {"effect": "allow", "object_type": "agent", "object_id": "searcher"},  # 允许调 searcher (场景6)
        # 注意：deny calc 给 searcher，但 analyzer 自己有 calc → 演示不同属主隔离
        # 注意：deny chart_gen 给所有人（包括 analyzer） → 演示场景 4
        {"effect": "deny",  "object_type": "mcp_tool", "object_id": "chart_gen", "tool_owner": "analyzer"}
    ]
}
```

---

## 五、安全演示场景（6 个）

| # | 场景 | 调用 | 预期结果 | 展示的安全特性 |
|---|------|------|----------|---------------|
| 1 | 正常 A2A 调度 | orchestrator → searcher | ✅ 200 | A2A 权限检查通过 |
| 2 | 正常 MCP 自有工具 | searcher → web_search (searcher) | ✅ 200 | MCP 自有工具 + tool_owner 匹配 |
| 3 | 权限不足 → 申请 | searcher → calc (analyzer) | ❌ 403 → Agent 自动申请 → 审批 → 重试 ✅ | 403 语义区分 + 申请审批流程 |
| 4 | deny 硬拒绝 | analyzer → chart_gen (analyzer) | ❌ 403 + `can_request: false` | deny 优先 + 不可申请覆盖 |
| 5 | A2A 自调用拒绝 | orchestrator → orchestrator | ❌ 403 | 自调用检查 |
| 6 | 非编排器 A2A | analyzer → searcher | ✅ 200 | Worker Agent 之间点对点调用 |

---

## 六、系统架构

### 6.1 目录结构

```
execution-layer/
├── Dockerfile
├── requirements.txt
├── main.py                     # FastAPI 入口 + 静态文件挂载
├── config.py                   # 配置（环境变量读取）
│
├── orchestrator.py             # 编排器 Agent
│
├── worker_agents/              # Worker Agent
│   ├── base_worker.py          # Worker 基类
│   ├── searcher_agent.py       # 搜索器
│   └── analyzer_agent.py       # 分析器
│
├── mcp_tools/                  # MCP 工具集
│   ├── base.py                 # BaseTool 抽象基类
│   ├── public_tools.py         # 公共 MCP 池 (file_read, file_write)
│   ├── searcher_tools.py       # 搜索器自有 (web_search, page_fetch)
│   └── analyzer_tools.py       # 分析器自有 (calc, chart_gen)
│
├── agent_sdk/                  # Agent SDK（内嵌版）
│   ├── __init__.py
│   ├── secure_agent_client.py  # SecureAgentClient 基类
│   └── signing_utils.py        # 签名工具
│
├── gateway_client.py           # 调权限网关的 HTTP 客户端
│
├── web_ui.py                   # Web UI 路由（自然语言交互 + WebSocket 实时推送）
│
├── static/                     # 前端静态文件
│   └── index.html              # 演示控制台（纯 HTML + JS）
│
└── tests/
    └── test_scenarios.py       # 6 个安全演示场景的自动化测试
```

### 6.2 调用拦截流程

```
执行层 Agent (如 searcher)
  │
  │ searcher 需要调 web_search
  │
  ├── 不直接调用 web_search.execute()
  │
  └── 通过 SDK: self.call_mcp_tool("web_search", "searcher", ...)
        │
        ├── ① SDK 生成 session_id, call_id
        ├── ② SDK 使用 Agent 私钥签名请求
        ├── ③ POST {gateway_url}/gateway/call
        │       Headers: X-Agent-Id, X-Session-Id, X-Call-Id, X-Signature-Hex
        │       Body: { call_type: "mcp", tool_name: "web_search", tool_owner: "searcher", ... }
        │
        ├── ④ 网关返回:
        │       200 → 放行 → SDK 返回结果给 Agent
        │       403 + can_request=true → SDK 自动发起权限申请 → 等待审批 → 重试
        │       403 + can_request=false → SDK 抛出 PermissionDeniedError
        │
        └── ⑤ Agent 拿到结果，继续处理
```

---

## 七、核心代码设计

### 7.1 SecureAgentClient（SDK 核心基类）

```python
class SecureAgentClient:
    """
    合规 Agent 的基类。封装与安全内核的全部交互。
    执行层的每个 Agent 都继承此类。
    """
    
    def __init__(self, agent_id: str, private_key_pem: str,
                 gateway_url: str, identity_url: str):
        self.agent_id = agent_id
        self._private_key = private_key_pem
        self._gateway_url = gateway_url
        self._identity_url = identity_url
    
    # ============================================================
    # 核心调用方法（唯一出站通道）
    # ============================================================
    
    async def call_agent(self, callee_agent_id: str, message: dict,
                         task_id: str, parent_session_id: str = None) -> dict:
        """
        调用另一个 Agent（A2A）。
        自动生成 session_id, call_id → 签名 → 过网关 → 处理返回。
        """

    async def call_mcp_tool(self, tool_name: str, tool_owner: str,
                            tool_args: dict, task_id: str,
                            parent_session_id: str = None) -> dict:
        """
        调用 MCP 工具。
        自动生成 session_id, call_id → 签名 → 过网关 → 处理返回。
        """
    
    # ============================================================
    # 权限申请
    # ============================================================
    
    async def request_permission(self, task_id: str, reason: str,
                                  missing_entries: list, ttl: int = 600) -> str:
        """当网关返回 403 + can_request=true 时，自动发起权限申请。"""
    
    async def wait_for_approval(self, task_id: str, request_id: str,
                                 poll_interval: int = 3, timeout: int = 120) -> bool:
        """轮询等待审批结果。"""
    
    # ============================================================
    # 任务生命周期
    # ============================================================
    
    async def finalize_task(self, task_id: str) -> None:
        """通知网关任务结束，触发级联清理。"""
    
    # ============================================================
    # 签名
    # ============================================================
    
    def sign_request(self, session_id: str, call_id: str,
                     request_body: bytes, callee_agent_id: str = "",
                     mcp_tool_name: str = "", tool_owner: str = "") -> str:
        """对请求签名，返回 signature_hex。"""
```

### 7.2 Worker Agent 示例

```python
class SearcherAgent(SecureAgentClient):
    """搜索器 Agent — 负责搜索和获取网页内容"""
    
    async def search(self, query: str, task_id: str,
                     parent_session_id: str = None) -> dict:
        """
        执行搜索任务：
        1. 调自有 web_search 工具
        2. 对搜索结果中的第一个链接调 page_fetch
        """
        # 第一步：搜索
        search_result = await self.call_mcp_tool(
            tool_name="web_search",
            tool_owner="searcher",
            tool_args={"query": query},
            task_id=task_id,
            parent_session_id=parent_session_id
        )
        
        # 第二步：获取第一个结果的详细内容
        if search_result.get("results"):
            first_url = search_result["results"][0]
            page_result = await self.call_mcp_tool(
                tool_name="page_fetch",
                tool_owner="searcher",
                tool_args={"url": first_url},
                task_id=task_id,
                parent_session_id=parent_session_id
            )
            return {"query": query, "search": search_result, "page": page_result}
        
        return {"query": query, "search": search_result}


class AnalyzerAgent(SecureAgentClient):
    """分析器 Agent — 负责数据分析和图表生成"""
    
    async def analyze(self, data: dict, task_id: str,
                      parent_session_id: str = None) -> dict:
        """
        分析数据：
        1. 调自有 calc 工具计算
        2. 如果需要补充信息，调 searcher Agent（非编排器 A2A）
        3. 产生图表
        """
        # 计算
        calc_result = await self.call_mcp_tool(
            tool_name="calc",
            tool_owner="analyzer",
            tool_args={"data": data},
            task_id=task_id,
            parent_session_id=parent_session_id
        )
        
        # 如果需要补充搜索（演示非编排器 A2A）
        if calc_result.get("needs_more_info"):
            search_result = await self.call_agent(
                callee_agent_id="searcher",
                message={"action": "search", "query": calc_result["missing_topic"]},
                task_id=task_id,
                parent_session_id=parent_session_id
            )
            calc_result["supplement"] = search_result
        
        # 生成图表（演示 deny 场景 — 会被网关拒绝）
        try:
            chart = await self.call_mcp_tool(
                tool_name="chart_gen",
                tool_owner="analyzer",
                tool_args={"data": calc_result},
                task_id=task_id,
                parent_session_id=parent_session_id
            )
            calc_result["chart"] = chart
        except PermissionDeniedError:
            calc_result["chart"] = "[denied] chart_gen 被禁止令牌阻止"
        
        return calc_result
```

### 7.3 Orchestrator（编排器）

```python
class OrchestratorAgent(SecureAgentClient):
    """编排器 Agent — 调度 Worker Agent 完成任务"""
    
    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """
        解析自然语言指令，制定执行计划，调度 Agent 执行。
        """
        # 解析指令（简单规则匹配）
        if "搜索" in instruction:
            # Step 1: 调 searcher
            search_result = await self.call_agent(
                callee_agent_id="searcher",
                message={"action": "search", "query": instruction},
                task_id=task_id
            )
        
        if "分析" in instruction or "报告" in instruction:
            # Step 2: 调 analyzer
            analysis = await self.call_agent(
                callee_agent_id="analyzer",
                message={"action": "analyze", "data": search_result},
                task_id=task_id
            )
        
        # Step 3: 写报告（公共 MCP）
        report = await self.call_mcp_tool(
            tool_name="file_write",
            tool_owner="public",
            tool_args={"path": f"/reports/{task_id}.md", "content": str(analysis)},
            task_id=task_id
        )
        
        # 任务结束，级联清理
        await self.finalize_task(task_id)
        
        return {"task_id": task_id, "result": analysis, "report": report}
```

### 7.4 BaseTool 抽象（Mock/MCP 不漂移保障）

```python
from abc import ABC, abstractmethod

class BaseTool(ABC):
    """
    所有 MCP 工具的统一抽象接口。
    Mock 实现和 MCP 实现都必须遵循此接口，保证切换时功能不漂移。
    """
    
    tool_name: str       # 工具名称
    tool_owner: str      # "public" | "{agent_id}"
    tool_schema: dict    # JSON Schema（参数定义）
    
    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """执行工具。返回统一格式: {"status": "ok", ...} 或 {"status": "error", "message": ...}"""
        ...


# Mock 实现示例
class MockWebSearchTool(BaseTool):
    tool_name = "web_search"
    tool_owner = "searcher"
    tool_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"]
    }
    
    async def execute(self, query: str) -> dict:
        return {
            "status": "ok",
            "results": [
                f"[mock] 关于 '{query}' 的搜索结果 1",
                f"[mock] 关于 '{query}' 的搜索结果 2"
            ]
        }
```

---

## 八、Web UI 设计

### 8.1 技术选型

- 后端：FastAPI + WebSocket（实时推送执行状态和审计日志）
- 前端：纯 HTML + 原生 JavaScript（无框架）
- 样式：内联 CSS，简洁现代

### 8.2 页面结构

```
┌─────────────────────────────────────────────────────────┐
│  🔒 Agent 安全系统 — 多Agent协作演示控制台                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  任务指令 (自然语言)                              │   │
│  │  "搜索Python Ed25519用法，分析并生成报告"         │   │
│  │                                        [执行任务] │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────┐ ┌────────────────────────┐   │
│  │  任务状态             │ │  审计日志 (实时)        │   │
│  │                      │ │                        │   │
│  │  Task: task-001      │ │ [10:00:01] s-001 ✅    │   │
│  │  Status: 执行中...    │ │ [10:00:02] s-002 ✅    │   │
│  │                      │ │ [10:00:05] s-004 ❌    │   │
│  │  调用链:              │ │   权限不足 → 申请中...  │   │
│  │  ├── s-001 ✅ A2A    │ │ [10:00:20] 审批通过 ✅  │   │
│  │  │   ├── s-002 ✅ MCP│ │ [10:00:22] s-004 ✅    │   │
│  │  │   └── s-003 ✅ MCP│ │ [10:01:00] s-007 ✅    │   │
│  │  ├── s-004 ❌ (申请)  │ │ ...                    │   │
│  │  └── s-006 ✅ A2A    │ │                        │   │
│  └──────────────────────┘ └────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  安全事件面板                                     │   │
│  │  🔴 s-004: analyzer→chart_gen 被deny令牌阻止     │   │
│  │  🟡 s-005: searcher→calc 权限不足 → 已发起申请   │   │
│  │  🟢 s-007: analyzer→searcher 非编排器A2A 放行   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 8.3 API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/tasks/execute` | 提交自然语言任务指令，触发编排器执行 |
| `GET` | `/tasks/{task_id}/status` | 查询任务执行状态 |
| `GET` | `/tasks/{task_id}/result` | 获取任务执行结果 |
| `WS` | `/ws/tasks/{task_id}` | WebSocket 实时推送执行状态和审计日志 |
| `GET` | `/` | Web UI 页面 |

### 8.4 WebSocket 推送事件

```python
# 事件类型
{
    "event": "session_update",       # 会话状态更新
    "data": {
        "session_id": "s-001",
        "status": "allowed",
        "caller": "orchestrator",
        "target": "searcher",
        "call_type": "a2a"
    }
}

{
    "event": "permission_required",  # 权限不足
    "data": {
        "session_id": "s-005",
        "request_id": "req-001",
        "missing": [{"object_type": "mcp_tool", "object_id": "calc"}]
    }
}

{
    "event": "permission_approved",  # 审批通过
    "data": {"request_id": "req-001"}
}

{
    "event": "task_completed",       # 任务完成
    "data": {"task_id": "task-001", "result": {...}}
}
```

---

## 九、函数清单

### 9.1 `execution_layer/orchestrator.py`

```python
class OrchestratorAgent(SecureAgentClient):
    async def execute_task(self, task_id: str, instruction: str) -> dict:
        """解析指令、制定计划、调度执行、finalize 任务。"""
```

### 9.2 `execution_layer/worker_agents/searcher_agent.py`

```python
class SearcherAgent(SecureAgentClient):
    async def search(self, query: str, task_id: str, parent_session_id: str = None) -> dict:
        """调 web_search + page_fetch。"""
```

### 9.3 `execution_layer/worker_agents/analyzer_agent.py`

```python
class AnalyzerAgent(SecureAgentClient):
    async def analyze(self, data: dict, task_id: str, parent_session_id: str = None) -> dict:
        """调 calc + (可选)调 searcher + (尝试)调 chart_gen(deny)。"""
```

### 9.4 `execution_layer/mcp_tools/base.py`

```python
class BaseTool(ABC):
    tool_name: str
    tool_owner: str
    tool_schema: dict
    
    @abstractmethod
    async def execute(self, **kwargs) -> dict: ...
```

### 9.5 `execution_layer/mcp_tools/public_tools.py`

```python
class FileReadTool(BaseTool): ...
class FileWriteTool(BaseTool): ...
```

### 9.6 `execution_layer/mcp_tools/searcher_tools.py`

```python
class WebSearchTool(BaseTool): ...
class PageFetchTool(BaseTool): ...
```

### 9.7 `execution_layer/mcp_tools/analyzer_tools.py`

```python
class CalcTool(BaseTool): ...
class ChartGenTool(BaseTool): ...
```

### 9.8 `execution_layer/agent_sdk/secure_agent_client.py`

```python
class SecureAgentClient:
    async def call_agent(...) -> dict: ...
    async def call_mcp_tool(...) -> dict: ...
    async def request_permission(...) -> str: ...
    async def wait_for_approval(...) -> bool: ...
    async def finalize_task(...) -> None: ...
    def sign_request(...) -> str: ...
```

### 9.9 `execution_layer/gateway_client.py`

```python
async def gateway_call(gateway_url: str, signed_request: dict) -> dict:
    """调用 POST /gateway/call，处理返回。"""

async def create_permission_request(gateway_url: str, task_id: str, request: dict) -> str:
    """发起权限申请。"""

async def check_approval_status(gateway_url: str, task_id: str, request_id: str) -> str:
    """查询审批状态。"""

async def finalize_task(gateway_url: str, task_id: str) -> None:
    """触发任务结束清理。"""
```

### 9.10 `execution_layer/web_ui.py`

```python
async def handle_execute_task(request: ExecuteTaskRequest) -> TaskResponse:
    """POST /tasks/execute"""

async def handle_get_task_status(task_id: str) -> TaskStatusResponse:
    """GET /tasks/{task_id}/status"""

async def handle_get_task_result(task_id: str) -> TaskResultResponse:
    """GET /tasks/{task_id}/result"""

async def websocket_task_events(websocket: WebSocket, task_id: str):
    """WS /ws/tasks/{task_id} — 实时推送执行状态和审计日志"""
```

---

## 十、设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 调用拦截方式 | SDK 封装所有出站调用 | Agent 不直接调外部，全部经过网关 |
| 拦截粒度 | 递归拦截 | 每个嵌套调用都经过网关 |
| MCP 工具实现 | Mock（BaseTool 抽象） | 模板演示，Mock 与 MCP 通过统一接口保证不漂移 |
| 工具归属 | 公共池 + 自有池 | 完整覆盖 tool_owner 的两种场景 |
| Agent 规模 | 1 orchestrator + 2 worker | 够展示三种模式，不过度复杂 |
| 演示场景 | 6 个安全场景 | 覆盖正常/拒绝/申请/deny/自调用/非编排器A2A |
| Web 交互 | 自然语言 + Web UI (纯 HTML/JS) | 无前端框架依赖，保持简单 |
| 实时推送 | WebSocket | 展示调用链实时状态和审计日志 |
| 场景替换 | 后续替换为飞书三Agent场景 | 当前用数据收集与报告生成场景 |
