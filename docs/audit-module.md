# 审计模块 — 完整设计文档

## 一、概述

审计模块是多Agent协作系统安全内核的日志记录与追溯模块。与权限网关**并行运行**，不阻塞主调用链。

### 核心职责

- 记录多个任务的多个会话内容（签名记录、会话日志、权限判定、任务事件、权限申请审批）
- 实现同一任务下的**调用链建模**（树形结构，通过 `parent_session_id` 串联）
- 提供审计查询接口（按任务查调用链、按任务查会话、按 Agent 查历史行为）

### 关键设计原则

- **被动接收**：仅提供写入 API，不做任何判定
- **异步写入**：权限网关 fire-and-forget，不影响主调用链性能
- **调用链建模**：通过 `parent_session_id` + `task_id` + `depth` 构建树形追溯

---

## 二、审计记录类型

| 记录类型 | 来源 | 触发时机 | 说明 |
|----------|------|----------|------|
| **SignatureRecord** | 权限网关 | 每次 `/gateway/call` | 签名验证结果、签名者、被签 payload |
| **SessionLog** | 权限网关 | 每次 `/gateway/call` | 会话基本信息 + 调用链信息 |
| **PermissionDecision** | 权限网关 | 每次 `/gateway/call` | 权限判定详情（匹配规则、allow/deny） |
| **TaskLifecycleEvent** | 权限网关 | 任务创建/结束 | 任务生命周期事件 |
| **PermissionRequestLog** | 权限网关 | 申请提交 + 审批完成 | 权限申请→审批全链路 |

---

## 三、核心数据模型

### 3.1 SignatureRecord（签名记录）

```python
class SignatureRecord:
    record_id: str           # UUID
    task_id: str
    session_id: str
    call_id: str
    caller_agent_id: str     # 签名者
    callee_agent_id: str     # A2A 场景
    mcp_tool_name: str       # MCP 场景
    request_hash: str        # SHA256(请求体)
    payload_raw: str         # 被签名的原始 payload（JSON）
    signature_hex: str       # Ed25519 签名（128字符）
    algorithm: str           # 固定 "Ed25519"
    signed_at: datetime      # Agent 声称的签名时间
    recorded_at: datetime    # 审计模块收到的时间（服务端时间）
    verified: bool           # 是否已由身份注册服务验证通过
```

### 3.2 SessionLog（会话日志）

```python
class SessionLog:
    session_id: str
    parent_session_id: str | None   # 调用链父子关系（顶层为 None）
    task_id: str
    caller_agent_id: str
    call_type: str                  # "a2a" | "mcp"
    target_id: str                  # callee_agent_id 或 tool_name
    tool_owner: str                 # MCP 场景
    depth: int                      # 调用深度（顶层=0）
    decision: str                   # "allowed" | "denied"
    deny_reason: str | None         # "explicitly_denied" | "permission_required" | None
    matched_entry_id: str | None    # 匹配的权限条目 ID
    signature_verified: bool
    created_at: datetime
```

### 3.3 PermissionDecision（权限判定记录）

```python
class PermissionDecision:
    decision_id: str         # UUID
    session_id: str
    task_id: str
    caller_agent_id: str
    call_type: str           # "a2a" | "mcp"
    target_id: str
    tool_owner: str
    decision: str            # "allowed" | "denied"
    deny_reason: str | None  # "self_call" | "explicitly_denied" | "permission_required" | "unauthorized"
    matched_entry_id: str | None
    matched_effect: str | None  # "allow" | "deny"
    token_view_id: str | None   # 当时使用的令牌视图 ID
    created_at: datetime
```

### 3.4 TaskLifecycleEvent（任务生命周期事件）

```python
class TaskLifecycleEvent:
    event_id: str            # UUID
    task_id: str
    event_type: str          # "task_started" | "task_finalized"
    triggered_by: str        # agent_id（编排器）
    metadata: dict           # 扩展信息
    created_at: datetime
```

### 3.5 PermissionRequestLog（权限申请审批日志）

```python
class PermissionRequestLog:
    log_id: str              # UUID
    task_id: str
    request_id: str          # 关联 PermissionRequest
    agent_id: str            # 申请人
    event_type: str          # "requested" | "approved" | "rejected"
    reason: str              # 申请理由
    requested_entries: list  # 原始申请条目
    approved_entries: list   # 审批后条目（审批时填充）
    requested_ttl: int       # 申请 TTL
    approved_ttl: int | None # 审批后 TTL
    reviewed_by: str | None  # 审批人
    review_comment: str | None
    created_at: datetime
```

---

## 四、调用链建模

### 4.1 建模方式

通过 `parent_session_id` + `task_id` + `depth` 三个字段构建树形调用链：

- `parent_session_id = null` → 顶层调用（编排器直接发起）
- `parent_session_id = "s-xxx"` → 嵌套调用（某个 Agent 在处理过程中发起的子调用）
- `depth` → 快速判断调用深度，方便限深查询

### 4.2 parent_session_id 的传递

由 Agent SDK 在嵌套调用时显式传递：

```
Agent B 内部调 tool_read:
  POST /gateway/call
  {
    session_id: "s-002",
    parent_session_id: "s-001"  ← SDK 自动携带上游 session_id
  }
```

网关不负责推断父子关系，仅透传到审计模块。

### 4.3 调用链示例（3 Agent, 10 次调用）

```
任务 T1: 数据分析任务
  编排器 (orchestrator)
  搜索器 (searcher) — 自有 MCP: [web_search, page_fetch]
  分析器 (analyzer) — 自有 MCP: [calc, chart_gen]
  公共 MCP: [file_read, file_write]

调用链树：

  Task T1
  │
  ├── s-001: orchestrator → searcher (A2A) [depth=0]
  │   ├── s-002: searcher → web_search (MCP, searcher) [depth=1]
  │   └── s-003: searcher → page_fetch (MCP, searcher) [depth=1]
  │
  ├── s-004: orchestrator → analyzer (A2A) [depth=0]
  │   ├── s-005: analyzer → file_read (MCP, public) [depth=1]
  │   ├── s-006: analyzer → calc (MCP, analyzer) [depth=1]
  │   ├── s-007: analyzer → searcher (A2A) [depth=1]
  │   │   └── s-008: searcher → web_search (MCP, searcher) [depth=2]
  │   └── s-009: analyzer → chart_gen (MCP, analyzer) [depth=1]
  │
  └── s-010: orchestrator → file_write (MCP, public) [depth=0]
```

### 4.4 数据库存储视图

| session_id | parent | task_id | caller | target | call_type | tool_owner | depth |
|------------|--------|---------|--------|--------|-----------|------------|-------|
| s-001 | null | T1 | orchestrator | searcher | a2a | | 0 |
| s-002 | s-001 | T1 | searcher | web_search | mcp | searcher | 1 |
| s-003 | s-001 | T1 | searcher | page_fetch | mcp | searcher | 1 |
| s-004 | null | T1 | orchestrator | analyzer | a2a | | 0 |
| s-005 | s-004 | T1 | analyzer | file_read | mcp | public | 1 |
| s-006 | s-004 | T1 | analyzer | calc | mcp | analyzer | 1 |
| s-007 | s-004 | T1 | analyzer | searcher | a2a | | 1 |
| s-008 | s-007 | T1 | searcher | web_search | mcp | searcher | 2 |
| s-009 | s-004 | T1 | analyzer | chart_gen | mcp | analyzer | 1 |
| s-010 | null | T1 | orchestrator | file_write | mcp | public | 0 |

查询 `GET /audit/tasks/T1/trace` 时按 `parent_session_id` 组装树返回。

---

## 五、服务接口清单

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/audit/signature-records` | 写入签名记录 | 服务间 API Key |
| `POST` | `/audit/session-logs` | 写入会话日志 | 服务间 API Key |
| `POST` | `/audit/permission-decisions` | 写入权限判定记录 | 服务间 API Key |
| `POST` | `/audit/task-events` | 写入任务生命周期事件 | 服务间 API Key |
| `POST` | `/audit/permission-request-logs` | 写入权限申请审批日志 | 服务间 API Key |
| `GET` | `/audit/tasks/{task_id}/trace` | 查询任务的完整调用链（树形） | 管理 API Key |
| `GET` | `/audit/tasks/{task_id}/sessions` | 查询任务的所有会话日志（平铺） | 管理 API Key |
| `GET` | `/audit/agents/{agent_id}/history` | 查询 Agent 的历史行为 | 管理 API Key |
| `GET` | `/audit/tasks/{task_id}/permission-requests` | 查询任务的权限申请审批历史 | 管理 API Key |

---

## 六、函数清单

### 6.1 `audit_service/log_store.py` — 日志持久化

```python
async def store_signature_record(conn, record: SignatureRecord) -> None:
    """写入签名记录。"""

async def store_session_log(conn, log: SessionLog) -> None:
    """写入会话日志。"""

async def store_permission_decision(conn, decision: PermissionDecision) -> None:
    """写入权限判定记录。"""

async def store_task_event(conn, event: TaskLifecycleEvent) -> None:
    """写入任务生命周期事件。"""

async def store_permission_request_log(conn, log: PermissionRequestLog) -> None:
    """写入权限申请审批日志。"""
```

### 6.2 `audit_service/trace_builder.py` — 调用链建模

```python
async def build_task_trace(conn, task_id: str) -> dict:
    """
    构建任务的完整调用链树。
    1. 查询 task_id 下所有 session_logs
    2. 按 parent_session_id 组装树形结构
    3. 返回嵌套 JSON
    Returns:
        {
            "task_id": "...",
            "root_sessions": [
                {
                    "session_id": "s-001",
                    "depth": 0,
                    "children": [
                        { "session_id": "s-002", "depth": 1, "children": [] }
                    ]
                }
            ]
        }
    """

async def get_task_sessions(conn, task_id: str, flat: bool = True) -> list[SessionLog]:
    """
    查询任务的所有会话。
    flat=True: 平铺返回
    flat=False: 按 depth 排序
    """

async def get_agent_history(conn, agent_id: str, 
                             limit: int = 100, 
                             offset: int = 0) -> list[SessionLog]:
    """查询 Agent 的历史行为（按时间倒序）。"""

async def get_task_permission_request_history(conn, task_id: str) -> list[PermissionRequestLog]:
    """查询任务的权限申请审批历史。"""
```

### 6.3 `audit_service/handlers.py` — API 路由处理

```python
# --- 写入接口 ---
async def handle_write_signature_record(request: SignatureRecordRequest) -> None:
    """POST /audit/signature-records"""

async def handle_write_session_log(request: SessionLogRequest) -> None:
    """POST /audit/session-logs"""

async def handle_write_permission_decision(request: PermissionDecisionRequest) -> None:
    """POST /audit/permission-decisions"""

async def handle_write_task_event(request: TaskEventRequest) -> None:
    """POST /audit/task-events"""

async def handle_write_permission_request_log(request: PermissionRequestLogRequest) -> None:
    """POST /audit/permission-request-logs"""

# --- 查询接口 ---
async def handle_get_task_trace(task_id: str) -> TaskTraceResponse:
    """
    GET /audit/tasks/{task_id}/trace
    返回完整的树形调用链。
    """

async def handle_get_task_sessions(task_id: str) -> list[SessionLogResponse]:
    """GET /audit/tasks/{task_id}/sessions"""

async def handle_get_agent_history(agent_id: str, limit: int = 100, 
                                    offset: int = 0) -> list[SessionLogResponse]:
    """GET /audit/agents/{agent_id}/history"""

async def handle_get_task_permission_requests(task_id: str) -> list[PermissionRequestLogResponse]:
    """GET /audit/tasks/{task_id}/permission-requests"""
```

### 6.4 `audit_service/middleware.py` — 中间件

```python
async def service_api_key_middleware(request: Request, call_next):
    """服务间调用的 API Key 认证中间件（写入接口需要）。"""
```

---

## 七、数据库表设计

```sql
-- ============================================================
-- 签名记录
-- ============================================================
CREATE TABLE signature_records (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL,
    session_id        UUID NOT NULL,
    call_id           UUID NOT NULL,
    caller_agent_id   UUID NOT NULL,
    callee_agent_id   UUID,
    mcp_tool_name     VARCHAR(255),
    request_hash      VARCHAR(64) NOT NULL,
    payload_raw       TEXT NOT NULL,
    signature_hex     VARCHAR(128) NOT NULL,
    algorithm         VARCHAR(20) NOT NULL DEFAULT 'Ed25519',
    signed_at         TIMESTAMPTZ NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified          BOOLEAN NOT NULL
);

CREATE INDEX idx_sig_task ON signature_records(task_id);
CREATE INDEX idx_sig_session ON signature_records(session_id);
CREATE INDEX idx_sig_caller ON signature_records(caller_agent_id);
CREATE INDEX idx_sig_recorded ON signature_records(recorded_at);

-- ============================================================
-- 会话日志
-- ============================================================
CREATE TABLE session_logs (
    session_id          UUID PRIMARY KEY,
    parent_session_id   UUID,
    task_id             UUID NOT NULL,
    caller_agent_id     UUID NOT NULL,
    call_type           VARCHAR(10) NOT NULL,      -- 'a2a' | 'mcp'
    target_id           VARCHAR(255) NOT NULL,
    tool_owner          VARCHAR(255) NOT NULL DEFAULT '',
    depth               INT NOT NULL DEFAULT 0,
    decision            VARCHAR(10) NOT NULL,       -- 'allowed' | 'denied'
    deny_reason         VARCHAR(50),
    matched_entry_id    UUID,
    signature_verified  BOOLEAN NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sl_task ON session_logs(task_id);
CREATE INDEX idx_sl_parent ON session_logs(parent_session_id);
CREATE INDEX idx_sl_caller ON session_logs(caller_agent_id);
CREATE INDEX idx_sl_task_depth ON session_logs(task_id, depth);

-- ============================================================
-- 权限判定记录
-- ============================================================
CREATE TABLE permission_decisions (
    id                UUID PRIMARY KEY,
    session_id        UUID NOT NULL,
    task_id           UUID NOT NULL,
    caller_agent_id   UUID NOT NULL,
    call_type         VARCHAR(10) NOT NULL,
    target_id         VARCHAR(255) NOT NULL,
    tool_owner        VARCHAR(255) NOT NULL DEFAULT '',
    decision          VARCHAR(10) NOT NULL,         -- 'allowed' | 'denied'
    deny_reason       VARCHAR(50),                  -- 'self_call' | 'explicitly_denied' | 'permission_required' | 'unauthorized'
    matched_entry_id  UUID,
    matched_effect    VARCHAR(10),                  -- 'allow' | 'deny'
    token_view_id     UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pd_session ON permission_decisions(session_id);
CREATE INDEX idx_pd_task ON permission_decisions(task_id);
CREATE INDEX idx_pd_decision ON permission_decisions(task_id, decision);

-- ============================================================
-- 任务生命周期事件
-- ============================================================
CREATE TABLE task_lifecycle_events (
    id              UUID PRIMARY KEY,
    task_id         UUID NOT NULL,
    event_type      VARCHAR(20) NOT NULL,           -- 'task_started' | 'task_finalized'
    triggered_by    UUID NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tle_task ON task_lifecycle_events(task_id);

-- ============================================================
-- 权限申请审批日志
-- ============================================================
CREATE TABLE permission_request_logs (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL,
    request_id        UUID NOT NULL,
    agent_id          UUID NOT NULL,
    event_type        VARCHAR(20) NOT NULL,         -- 'requested' | 'approved' | 'rejected'
    reason            TEXT DEFAULT '',
    requested_entries JSONB NOT NULL DEFAULT '[]',
    approved_entries  JSONB NOT NULL DEFAULT '[]',
    requested_ttl     INT NOT NULL,
    approved_ttl      INT,
    reviewed_by       VARCHAR(255),
    review_comment    TEXT DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_prl_task ON permission_request_logs(task_id);
CREATE INDEX idx_prl_request ON permission_request_logs(request_id);
CREATE INDEX idx_prl_agent ON permission_request_logs(agent_id);
```

---

## 八、数据流

```
┌──────────┐          ┌──────────┐
│ 权限网关  │          │  执行层   │
└────┬─────┘          └────┬─────┘
     │                     │
     │  每次 /gateway/call  │  任务生命周期（编排器）
     │                     │
     ├── POST /audit/signature-records ──────▶│
     ├── POST /audit/session-logs ───────────▶│
     ├── POST /audit/permission-decisions ───▶│
     ├── POST /audit/task-events ────────────▶│
     ├── POST /audit/permission-request-logs ─▶│
     │                                         │
     │  异步 fire-and-forget（不阻塞调用链）     │
     │                                         ▼
     │                                   ┌──────────┐
     │                                   │ 审计模块  │
     │                                   │ (写入PG) │
     │                                   └────┬─────┘
     │                                        │
     │  查询接口（按需）                        │
     │  GET /audit/tasks/{id}/trace ◀─────────│
     │  GET /audit/agents/{id}/history ◀──────│
     └────────────────────────────────────────┘
```

> **写入策略**：权限网关异步发送，推荐本地内存缓冲 + 后台重试作为兜底（实现细节，设计阶段标记）。

---

## 九、设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 模块角色 | 被动接收，不做判定 | 职责单一，不参与业务逻辑 |
| 写入方式 | 异步 fire-and-forget | 不阻塞主调用链 |
| 调用链建模 | parent_session_id + depth | 简洁直观，查询组装方便 |
| parent_session_id 来源 | Agent SDK 显式传递 | 网关不推断父子关系 |
| 执行结果 | 不记录 | 安全内核不关心业务执行结果 |
| 日志保留 | 无 TTL | 不做自动归档，由运维决定 |
| 审计查询 | 提供查询接口 | 支持事后追溯和可视化 |

---

## 十、与权限网关的协作接口

权限网关在以下时机向审计模块发送记录：

| 时机 | 发送内容 |
|------|----------|
| `/gateway/call` 验签后 | `SignatureRecord` |
| `/gateway/call` 判定后 | `SessionLog` + `PermissionDecision` |
| `/tasks/{task_id}/finalize` | `TaskLifecycleEvent(event_type="task_finalized")` |
| Agent 提交权限申请 | `PermissionRequestLog(event_type="requested")` |
| 管理员审批权限申请 | `PermissionRequestLog(event_type="approved"/"rejected")` |

所有发送均为异步，不等待审计模块响应。
