# 权限网关 — 完整设计文档

## 一、概述

权限网关是多Agent协作系统安全内核的核心拦截模块。所有 Agent 的出站调用（A2A 或 MCP）都必须经过权限网关进行拦截判定。

### 核心职责

- **令牌管理**：Standard Token（长期，绑定 Agent）的 CRUD 及条目级管理
- **任务临时权限**：TaskPermissionEntry（绑定 Task+Agent，临时）的管理
- **权限申请审批**：Agent 按需申请 → 人工审批 / 自动降级 → 写入临时权限。支持两种模式：
  - **人工审批模式**：管理员在 Web UI 审批窗口手动点击允许/拒绝
  - **自动降级模式**：管理员点击允许时自动标记 `[降级]`，审计日志记录告警
- **令牌视图构建**：单Agent视图（并集）+ 多Agent视图（交集+隐式self条目），deny 优先
- **会话管理**：会话与令牌视图绑定，视图缓存于 Redis
- **调用拦截**：验签（`json.dumps(sort_keys=True)` 统一序列化）→ 自调用检查 → 视图判定 → 审计记录 → 放行/拒绝
- **权限订阅管理 UI**：`/admin` 三合一界面（批量注册 | 令牌订阅 | 审批窗口）

---

## 二、权限体系总览

```
┌─────────────────────────────────────────────────┐
│                  权限体系                         │
│                                                 │
│  StandardToken (绑定 Agent, 长期)                │
│  ├── token_id                                   │
│  ├── agent_id                                   │
│  ├── entries: [TokenEntry, ...]                 │
│  │     ├── effect: allow | deny                 │
│  │     ├── object_type: agent | mcp_tool        │
│  │     ├── object_id: 目标ID，精确匹配             │
│  │     └── tool_owner: "public" | "{agent_id}"  │
│  └── status: active | revoked                   │
│                                                 │
│  TaskPermissionEntry (绑定 Task+Agent, 临时)     │
│  ├── entry_id                                   │
│  ├── task_id                                    │
│  ├── agent_id                                   │
│  ├── effect/object_type/object_id/tool_owner    │
│  ├── expires_at                                 │
│  └── source: manual | request_approved          │
│                                                 │
│  令牌视图 = StandardToken.entries                │
│           ∪ TaskPermissionEntry(task, agent)     │
│           → deny 优先                            │
│           → 会话级缓存于 Redis                    │
└─────────────────────────────────────────────────┘
```

### 关键设计原则

- **长期令牌绑定 Agent**：定义 Agent 的固有权限和禁止边界
- **临时权限绑定任务**：不绑定单个 Agent，属于任务的一次性权限声明
- **deny 优先**：禁止令牌不可被 allow 覆盖
- **白名单模式**：无匹配条目 → 隐式拒绝
- **签名一致性**：网关与 SDK 统一使用 `json.dumps(sort_keys=True, ensure_ascii=False)` 序列化请求体，确保签名 payload 一致

---

## 三、核心数据模型

### 3.1 TokenEntry（权限条目，最小管理单元）

```python
class TokenEntry:
    entry_id: str          # UUID
    token_id: str          # 所属令牌 ID
    effect: str            # "allow" | "deny"
    object_type: str       # "agent" | "mcp_tool"
    object_id: str         # 目标 agent_id 或 tool_name，精确匹配
    tool_owner: str        # MCP 场景："public" | "{agent_id}"；A2A 场景：""
    created_at: datetime
```

**匹配逻辑**：

```python
def match_entry(entry: TokenEntry, call_type: str, 
                object_id: str, tool_owner: str) -> bool:
    """判断一条权限条目是否匹配当前调用"""
    if entry.object_type != ("agent" if call_type == "a2a" else "mcp_tool"):
        return False
    if entry.object_id != object_id:
        return False
    if call_type == "mcp":
        if entry.tool_owner != tool_owner:
            return False
    return True
```

### 3.2 StandardToken（长期令牌）

```python
class StandardToken:
    token_id: str          # UUID
    agent_id: str          # 绑定的 Agent
    label: str             # 人类可读标签
    entries: list[TokenEntry]
    status: str            # "active" | "revoked"
    created_at: datetime
    revoked_at: datetime | None
```

### 3.3 TaskPermissionEntry（任务临时权限条目）

```python
class TaskPermissionEntry:
    entry_id: str          # UUID
    task_id: str           # 绑定到任务
    agent_id: str          # 该条目适用于哪个 Agent
    effect: str            # "allow" | "deny"
    object_type: str       # "agent" | "mcp_tool"
    object_id: str
    tool_owner: str
    source: str            # "manual" | "request_approved"
    source_request_id: str | None  # 关联权限申请 ID
    expires_at: datetime   # 过期时间
    created_at: datetime
```

### 3.4 TokenView（令牌视图，会话级）

```python
class TokenView:
    view_id: str           # UUID
    session_id: str        # 绑定的会话
    agent_id: str          # 视图所属 Agent
    task_id: str | None
    entries: list[TokenEntry]  # 最终有效的权限条目集合
    built_at: datetime
```

### 3.5 PermissionRequest（权限申请）

```python
class PermissionRequest:
    request_id: str        # UUID
    task_id: str
    agent_id: str          # 申请人
    reason: str            # 申请理由
    status: str            # "pending_approval" | "approved" | "rejected"
    requested_entries: list[TokenEntry]    # Agent 申请的条目
    approved_entries: list[TokenEntry]     # 审批后的条目
    requested_ttl: int                     # Agent 申请的 TTL（秒）
    approved_ttl: int | None               # 审批后的 TTL（秒）
    reviewed_by: str | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None
```

### 3.6 Session（会话）

```python
class Session:
    session_id: str        # UUID
    task_id: str | None    # 所属任务
    caller_agent_id: str
    call_type: str         # "a2a" | "mcp"
    target_id: str         # callee_agent_id 或 tool_name
    tool_owner: str        # MCP 场景
    token_view_id: str     # 关联的令牌视图
    status: str            # "active" | "completed" | "rejected"
    created_at: datetime
    completed_at: datetime | None
```

---

## 四、令牌视图构建算法

### 4.1 单 Agent 视图

```python
async def build_agent_view(conn, agent_id: str, task_id: str | None) -> TokenView:
    """
    单 Agent 视图 = 
        StandardToken(agent_id).entries          # Agent 的长期令牌条目
      ∪ TaskPermissionEntry(task_id, agent_id)   # 任务中该 Agent 的临时权限条目（有效期内）
    
    deny 条目排在前面（优先匹配）。
    """
    entries = []
    
    # 1. Agent 的长期令牌条目（active 状态的）
    standard_tokens = await get_agent_standard_tokens(conn, agent_id)
    for token in standard_tokens:
        if token.status == "active":
            entries.extend(token.entries)
    
    # 2. 任务中该 Agent 的临时权限条目（有效期内）
    if task_id:
        task_entries = await get_task_permission_entries(conn, task_id, agent_id)
        for e in task_entries:
            if e.expires_at > utcnow():
                entries.append(e)
    
    # deny 优先排序
    entries.sort(key=lambda e: 0 if e.effect == "deny" else 1)
    return TokenView(agent_id=agent_id, task_id=task_id, entries=entries)
```

### 4.2 多 Agent 视图（A2A 场景）

```python
async def build_multi_agent_view(conn, caller_id: str, callee_id: str,
                                  task_id: str | None) -> TokenView:
    """
    多 Agent 视图 = caller令牌视图 ∩ callee长期令牌(StandardToken) ∪ callee任务临时权限

    交集规则（按 (type, object_id, tool_owner) 逐对）:
      caller条目 | callee条目 | 结果
      deny       | *          | deny   (任一方 deny 即 deny)
      allow      | deny       | deny
      allow      | unset      | 不构建 (隐式拒绝, 需申请临时权限)
      allow      | allow      | allow
      unset      | *          | 不构建 (隐式拒绝)

    特殊规则:
    - callee 默认具有隐式条目 allow agent: callee_id (允许任何人调用自己, 除非被 deny 覆盖)
    - callee 任务临时权限直接追加到最终视图（审批时已校验 deny 不会被绕过）
    """
    caller_view = await build_agent_view(conn, caller_id, task_id)
    callee_standard = await _build_standard_only_view(conn, callee_id)

    # callee 隐式: 默认允许被调用
    callee_idx[("agent", callee_id, "")] = "allow"  # 仅当未显式设置时

    # 交集: deny 优先, allow 需双方都 allow
    final_deny = [...]  # 任一方 deny
    final_allow = [...] # 双方都是 allow (含 callee 隐式条目)

    # callee 任务临时权限直接并集
    callee_task = await get_task_permissions(conn, task_id, callee_id)

    return TokenView(entries=final_deny + final_allow + callee_task)
```

#### 临时权限 deny 保护

审批通过创建临时权限前，检查申请的条目是否被 callee 的现有令牌 deny 覆盖：

```python
denied = await check_temp_permission_denied(conn, agent_id, task_id, entries)
if denied:
    raise HTTPException(409, "Cannot approve: entry is explicitly denied.")
```

### 4.3 视图缓存策略

```
Key:   "session:{session_id}:view"
Value: JSON(TokenView)
TTL:   会话时长（默认 300s）

- 会话首次调用时构建视图，写入 Redis
- 同一会话后续调用直接复用缓存
- 权限变更（审批通过/吊销）时主动清除相关会话的视图缓存
- 任务结束时级联清除所有关联会话的视图缓存
```

---

## 五、判定流程（POST /gateway/call）

### 5.1 规则优先级（从高到低）

1. **自调用检查**：`caller == callee` 且 `call_type == "a2a"` → 直接拒绝 403
2. **deny 优先**：任一匹配 deny 条目 → 拒绝 403（含 `can_request: false`）
3. **allow 匹配**：存在匹配 allow 条目 → 放行 200
4. **隐式拒绝**：无任何匹配条目 → 拒绝 403（含 `can_request: true`，提示可申请）

### 5.2 完整调用流程

```
POST /gateway/call
  │
  ├── ① 解析请求
  │     请求头: X-Agent-Id, X-Session-Id, X-Call-Id, 
  │              X-Signature-Hex, X-Timestamp
  │     请求体: call_type, target 信息
  │
  ├── ② 身份验证
  │     POST identity-service:8001/verify/signature
  │     ├── verified=False → 401 Unauthorized
  │     └── verified=True → 继续
  │
  ├── ③ 自调用检查
  │     if call_type=="a2a" and caller_id==callee_id:
  │         → 403 Self-call denied
  │
  ├── ④ 获取/构建令牌视图
  │     ├── Redis: "session:{session_id}:view" → 命中则直接使用
  │     └── 未命中:
  │         ├── MCP 场景: build_agent_view(caller, task_id)
  │         ├── A2A 场景: build_multi_agent_view(caller, callee, task_id)
  │         └── 写入 Redis 缓存
  │
  ├── ⑤ 权限判定
  │     ├── 遍历视图 entries，先检查 deny
  │     │   └── 命中 deny → 403 { can_request: false, reason: "explicitly_denied" }
  │     ├── 遍历视图 entries，检查 allow
  │     │   └── 命中 allow → 放行 200
  │     └── 无匹配 → 403 { can_request: true, reason: "permission_required",
  │                         missing_entries: [...], 
  │                         message: "{agent传入的reason}",
  │                         request_url: "/tasks/{task_id}/permission-requests" }
  │
  ├── ⑥ 审计记录（异步，不阻塞）
  │     POST audit-service:8003/signature-records
  │     fire-and-forget
  │
  └── ⑦ 返回结果
```

### 5.3 403 响应的语义区分

**显式禁止（deny 命中）**：
```json
{
    "status": "denied",
    "reason": "explicitly_denied",
    "can_request": false,
    "denied_by_entry": "entry-uuid",
    "message": "该操作被禁止令牌明确禁止，不可申请"
}
```

**权限不足（可申请）**：
```json
{
    "status": "denied",
    "reason": "permission_required",
    "can_request": true,
    "request_permission_url": "/tasks/task-001/permission-requests",
    "missing_entries": [
        {
            "object_type": "mcp_tool",
            "object_id": "tool_x",
            "tool_owner": "public"
        }
    ]
}
```

---

## 六、权限申请与审批流程

### 6.1 流程概览

```
Agent B 尝试调 tool_x
  │
  ├── POST /gateway/call → 403 (can_request: true)
  │
  ├── Agent B 发起权限申请
  │    POST /tasks/{task_id}/permission-requests
  │    {
  │        "agent_id": "agent-b",
  │        "task_id": "task-001",
  │        "reason": "生成数据可视化图表",          // ← 来自 Agent SDK call_mcp_tool(reason=...)
  │        "requested_entries": [
  │            { "effect": "allow", "object_type": "mcp_tool",
  │              "object_id": "tool_x", "tool_owner": "public" }
  │        ],
  │        "ttl_seconds": 600
  │    }
  │    → status: "pending_approval"
  │
  ├── 管理员审批
  │    POST /tasks/{task_id}/permission-requests/{req_id}/approve
  │    {
  │        "action": "approve",
  │        "approved_entries": [ ... ],   // 可裁剪
  │        "ttl_seconds": 300,            // 可缩短
  │        "comment": "仅此任务有效"
  │    }
  │
  │    权限网关：
  │    ├── 创建 TaskPermissionEntry（直接写入任务临时权限表）
  │    ├── PermissionRequest.status = "approved"
  │    ├── 清除该任务该 Agent 相关的 Redis 视图缓存
  │    └── 返回成功
  │
  └── Agent B 重试调用 → 视图重建，包含新条目 → 放行
```

### 6.2 审批操作

管理员审批时可以：
- ✅ **通过**：创建 TaskPermissionEntry，条目可裁剪（缩小范围）
- ✅ **拒绝**：`PermissionRequest.status = "rejected"`，不创建任何权限
- ✅ **调整 TTL**：可以缩短（不超过申请值），不能延长

---

## 七、任务结束时级联清理

### 7.1 清理流程

```
POST /tasks/{task_id}/finalize
  │
  ├── ① 删除任务临时权限
  │     DELETE FROM task_permission_entries WHERE task_id = xxx
  │     （物理删除，任务级临时数据无需软删除保留）
  │
  ├── ② 清除 Redis 视图缓存
  │     查询该任务所有 sessions
  │     → 逐个 DELETE "session:{session_id}:view"
  │
  └── ③ 标记会话完成
        UPDATE sessions SET status='completed', completed_at=now()
        WHERE task_id = xxx AND status='active'
```

### 7.2 TTL 兜底机制

`TaskPermissionEntry.expires_at` 确保即使忘记调 `finalize`：
- 过期的条目在视图构建时自动过滤
- Redis 视图缓存 TTL 对齐，到期自动失效
- 下次调用时视图重建，不再包含过期条目

---

## 八、服务接口清单

### 8.1 Standard Token 管理

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/tokens` | 创建长期令牌（含初始条目列表） | 管理 API Key |
| `GET` | `/tokens/{token_id}` | 查询令牌及所有条目 | 管理 API Key |
| `GET` | `/tokens?agent_id=xxx` | 按 Agent 列出令牌 | 管理 API Key |
| `DELETE` | `/tokens/{token_id}` | 吊销令牌（软删除） | 管理 API Key |
| `POST` | `/tokens/{token_id}/entries` | 向令牌添加条目 | 管理 API Key |
| `GET` | `/tokens/{token_id}/entries` | 列出令牌下所有条目 | 管理 API Key |
| `DELETE` | `/tokens/{token_id}/entries/{entry_id}` | 删除单条条目 | 管理 API Key |

### 8.2 任务临时权限管理

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/tasks/{task_id}/permissions` | 管理员手动添加任务临时权限 | 管理 API Key |
| `GET` | `/tasks/{task_id}/permissions` | 查看任务的所有临时权限 | 管理 API Key |
| `DELETE` | `/tasks/{task_id}/permissions/{entry_id}` | 删除单条临时权限 | 管理 API Key |
| `POST` | `/tasks/{task_id}/finalize` | 任务结束，级联清理 | 编排器 API Key |

### 8.3 权限申请与审批

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/tasks/{task_id}/permission-requests` | Agent 提交权限申请 | Agent 签名 |
| `GET` | `/tasks/{task_id}/permission-requests` | 查看任务的所有权限申请 | 管理 API Key |
| `GET` | `/tasks/{task_id}/permission-requests/{req_id}` | 查看单个申请详情 | 管理 API Key |
| `POST` | `/tasks/{task_id}/permission-requests/{req_id}/approve` | 审批申请（支持 action: approve / reject / auto_approve） | 管理 API Key |
| `GET` | `/admin/pending-requests` | 列出所有待审批权限申请 | 无（全局查询） |

### 8.4 运行时接口

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/gateway/call` | 统一 MCP/A2A 调用入口（核心拦截点） | Agent 签名 |
| `GET` | `/sessions/{session_id}/view` | 查询会话的令牌视图 | 服务间 API Key |

### 8.5 权限订阅管理 UI（三合一界面）

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `GET` | `/admin` | 权限订阅管理 Web UI 页面（双Tab+审批窗口） | 无 |
| `GET` | `/admin/agents` | 代理查询已注册 Agent 列表 | 无 |
| `GET` | `/admin/tools` | 代理查询已注册 Tool 列表 | 无 |
| `GET` | `/admin/pending-requests` | 列出所有待审批权限申请 | 无 |

> 管理 UI 三个功能区域：
> - 📋 **批量注册**：上传 manifest.json → 一键注册 Agent+Tool → 注入执行层凭证
> - 🔑 **令牌订阅**：点击式可视化长期令牌配置
> - ⏳ **审批窗口**：人工审批/自动降级双模式，5秒轮询刷新
> 
> JS 提取到 `admin.js` 独立文件。

---

## 九、统一调用入口

```
POST /gateway/call

Headers:
  X-Agent-Id: agent-a
  X-Session-Id: uuid
  X-Call-Id: uuid
  X-Signature-Hex: ...
  X-Timestamp: 2026-04-30T10:00:00Z

Body:
{
    "call_type": "mcp",           // "mcp" | "a2a"
    "task_id": "task-001",
    "reason": "读取配置文件",      // (可选) Agent 传入的调用意图
    
    // === MCP 场景 ===
    "tool_name": "file_read",
    "tool_owner": "public",       // "public" | "{agent_id}"
    "tool_args": { ... },
    
    // === A2A 场景 ===
    "callee_agent_id": "agent-b",
    "message": { ... }
}
```

---

## 十、函数清单

### 10.1 `permission_gateway/token_manager.py` — Standard Token 管理

```python
async def create_token(conn, token: StandardToken) -> StandardToken:
    """创建长期令牌，写入 PG。"""

async def get_token(conn, token_id: str) -> StandardToken | None:
    """按 ID 查询令牌及所有条目。"""

async def list_tokens(conn, agent_id: str = None) -> list[StandardToken]:
    """按 Agent 列出令牌。"""

async def revoke_token(conn, token_id: str) -> None:
    """吊销令牌（软删除）。"""

async def add_entry(conn, token_id: str, entry: TokenEntry) -> TokenEntry:
    """向令牌添加条目。"""

async def list_entries(conn, token_id: str) -> list[TokenEntry]:
    """列出令牌所有条目。"""

async def remove_entry(conn, entry_id: str) -> None:
    """删除单条条目。"""
```

### 10.2 `permission_gateway/task_permissions.py` — 任务临时权限管理

```python
async def add_task_permission(conn, entry: TaskPermissionEntry) -> TaskPermissionEntry:
    """添加任务临时权限条目。"""

async def get_task_permissions(conn, task_id: str, agent_id: str = None) -> list[TaskPermissionEntry]:
    """查询任务的临时权限，可按 Agent 过滤。"""

async def delete_task_permission(conn, entry_id: str) -> None:
    """删除单条临时权限。"""

async def delete_all_task_permissions(conn, task_id: str) -> None:
    """删除任务的所有临时权限（finalize 时调用）。"""
```

### 10.3 `permission_gateway/permission_requests.py` — 权限申请与审批

```python
async def create_permission_request(conn, req: PermissionRequest) -> PermissionRequest:
    """Agent 提交权限申请。"""

async def get_permission_request(conn, req_id: str) -> PermissionRequest | None:
    """查询单个申请。"""

async def list_permission_requests(conn, task_id: str, status: str = None) -> list[PermissionRequest]:
    """列出任务的权限申请。"""

async def approve_permission_request(conn, req_id: str, reviewer: str,
                                      approved_entries: list, ttl: int, 
                                      comment: str) -> list[TaskPermissionEntry]:
    """
    审批通过权限申请：
    1. 更新 PermissionRequest.status = "approved"
    2. 为每个 approved_entry 创建 TaskPermissionEntry
    3. 返回创建的 TaskPermissionEntry 列表
    """

async def reject_permission_request(conn, req_id: str, reviewer: str, 
                                     comment: str) -> None:
    """拒绝权限申请。"""
```

### 10.4 `permission_gateway/view_builder.py` — 令牌视图构建

```python
async def build_agent_view(conn, agent_id: str, task_id: str | None) -> TokenView:
    """
    构建单 Agent 的权限视图（并集）。
    = StandardToken(agent_id).entries ∪ TaskPermissionEntry(task_id, agent_id, valid)
    """

async def build_multi_agent_view(conn, caller_id: str, callee_id: str,
                                  task_id: str | None) -> TokenView:
    """
    构建多 Agent 调用视图（交集 + deny 优先）。
    """

def evaluate_view(view: TokenView, call_type: str,
                  object_id: str, tool_owner: str) -> tuple[str, str | None]:
    """
    判定：遍历视图条目，先 deny 后 allow。
    Returns:
        ("allowed", None)
        ("explicitly_denied", entry_id)
        ("permission_required", None)
    """
```

### 10.5 `permission_gateway/session_manager.py` — 会话管理

```python
async def create_session(conn, session: Session) -> Session:
    """创建会话记录。"""

async def cache_token_view(redis, session_id: str, view: TokenView, ttl: int) -> None:
    """将会话的令牌视图缓存到 Redis。"""

async def get_cached_view(redis, session_id: str) -> TokenView | None:
    """从 Redis 获取缓存的令牌视图。"""

async def invalidate_session_views(redis, task_id: str, agent_id: str = None) -> None:
    """权限变更时使相关会话的视图缓存失效。"""

async def complete_session(conn, session_id: str) -> None:
    """标记会话完成。"""

async def complete_task_sessions(conn, task_id: str) -> None:
    """标记任务的所有活跃会话为完成。"""
```

### 10.6 `permission_gateway/identity_client.py` — 身份验证客户端

```python
async def verify_signature(identity_url: str, api_key: str,
                            agent_id: str, session_id: str, call_id: str,
                            signature_hex: str, payload: bytes) -> bool:
    """调身份注册服务验签。"""
```

### 10.7 `permission_gateway/audit_client.py` — 审计客户端

```python
async def send_signature_record(audit_url: str, api_key: str,
                                 record: SignatureRecord) -> None:
    """异步发送签名记录到审计模块（fire-and-forget）。"""
```

### 10.8 `permission_gateway/handlers.py` — API 路由处理

```python
# --- Standard Token 管理 ---
async def handle_create_token(request: CreateTokenRequest) -> CreateTokenResponse:
    """POST /tokens"""

async def handle_get_token(token_id: str) -> TokenResponse:
    """GET /tokens/{token_id}"""

async def handle_list_tokens(agent_id: str = None) -> list[TokenResponse]:
    """GET /tokens"""

async def handle_revoke_token(token_id: str) -> RevokeResponse:
    """DELETE /tokens/{token_id}"""

async def handle_add_entry(token_id: str, request: AddEntryRequest) -> EntryResponse:
    """POST /tokens/{token_id}/entries"""

async def handle_list_entries(token_id: str) -> list[EntryResponse]:
    """GET /tokens/{token_id}/entries"""

async def handle_remove_entry(token_id: str, entry_id: str) -> None:
    """DELETE /tokens/{token_id}/entries/{entry_id}"""

# --- 任务临时权限 ---
async def handle_add_task_permission(task_id: str, request: AddTaskPermissionRequest):
    """POST /tasks/{task_id}/permissions"""

async def handle_get_task_permissions(task_id: str) -> list[TaskPermissionResponse]:
    """GET /tasks/{task_id}/permissions"""

async def handle_delete_task_permission(task_id: str, entry_id: str) -> None:
    """DELETE /tasks/{task_id}/permissions/{entry_id}"""

async def handle_finalize_task(task_id: str) -> FinalizeResponse:
    """POST /tasks/{task_id}/finalize"""

# --- 权限申请审批 ---
async def handle_create_permission_request(task_id: str, 
                                            request: CreatePermissionRequestRequest):
    """POST /tasks/{task_id}/permission-requests"""

async def handle_list_permission_requests(task_id: str, 
                                           status: str = None):
    """GET /tasks/{task_id}/permission-requests"""

async def handle_get_permission_request(task_id: str, req_id: str):
    """GET /tasks/{task_id}/permission-requests/{req_id}"""

async def handle_approve_permission_request(task_id: str, req_id: str,
                                              request: ApproveRequest):
    """POST /tasks/{task_id}/permission-requests/{req_id}/approve"""

# --- 运行时 ---
async def handle_gateway_call(request: GatewayCallRequest) -> GatewayCallResponse:
    """POST /gateway/call — 完整拦截流程"""

async def handle_get_session_view(session_id: str) -> TokenViewResponse:
    """GET /sessions/{session_id}/view"""
```

### 10.9 `permission_gateway/middleware.py` — 中间件

```python
async def extract_agent_signature(request: Request) -> SignatureInfo:
    """从请求头提取签名信息。"""

async def admin_api_key_middleware(request: Request, call_next):
    """管理接口的 API Key 认证中间件。"""

async def service_api_key_middleware(request: Request, call_next):
    """服务间调用的 API Key 认证中间件。"""
```

---

## 十一、数据库表设计

```sql
-- ============================================================
-- 长期令牌
-- ============================================================
CREATE TABLE standard_tokens (
    id              UUID PRIMARY KEY,
    agent_id        UUID NOT NULL,
    label           VARCHAR(255) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX idx_st_agent ON standard_tokens(agent_id, status);

-- ============================================================
-- 长期令牌条目
-- ============================================================
CREATE TABLE standard_token_entries (
    id              UUID PRIMARY KEY,
    token_id        UUID NOT NULL REFERENCES standard_tokens(id) ON DELETE CASCADE,
    effect          VARCHAR(10) NOT NULL,        -- 'allow' | 'deny'
    object_type     VARCHAR(20) NOT NULL,        -- 'agent' | 'mcp_tool'
    object_id       VARCHAR(255) NOT NULL,       -- 目标 ID，支持 '*'
    tool_owner      VARCHAR(255) NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ste_token ON standard_token_entries(token_id);

-- ============================================================
-- 任务临时权限条目
-- ============================================================
CREATE TABLE task_permission_entries (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL,
    agent_id          UUID NOT NULL,
    effect            VARCHAR(10) NOT NULL,
    object_type       VARCHAR(20) NOT NULL,
    object_id         VARCHAR(255) NOT NULL,
    tool_owner        VARCHAR(255) NOT NULL DEFAULT '',
    source            VARCHAR(20) NOT NULL DEFAULT 'manual',
    source_request_id UUID,
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tpe_task_agent ON task_permission_entries(task_id, agent_id);
CREATE INDEX idx_tpe_expires ON task_permission_entries(expires_at);

-- ============================================================
-- 权限申请
-- ============================================================
CREATE TABLE permission_requests (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL,
    agent_id          UUID NOT NULL,
    reason            TEXT DEFAULT '',
    status            VARCHAR(20) NOT NULL DEFAULT 'pending_approval',
    requested_entries JSONB NOT NULL DEFAULT '[]',
    approved_entries  JSONB NOT NULL DEFAULT '[]',
    requested_ttl     INT NOT NULL,
    approved_ttl      INT,
    reviewed_by       VARCHAR(255),
    review_comment    TEXT DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at       TIMESTAMPTZ
);

CREATE INDEX idx_pr_task_status ON permission_requests(task_id, status);

-- ============================================================
-- 会话
-- ============================================================
CREATE TABLE sessions (
    id              UUID PRIMARY KEY,
    task_id         UUID,
    caller_agent_id UUID NOT NULL,
    call_type       VARCHAR(10) NOT NULL,        -- 'a2a' | 'mcp'
    target_id       VARCHAR(255) NOT NULL,
    tool_owner      VARCHAR(255) NOT NULL DEFAULT '',
    token_view_id   UUID,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_sessions_task ON sessions(task_id);
CREATE INDEX idx_sessions_caller ON sessions(caller_agent_id);
```

### Redis 缓存结构

```
Key:   "session:{session_id}:view"
Value: JSON(TokenView)
TTL:   会话时长（默认 300s）
```

---

## 十二、安全护栏总结

| 护栏 | 说明 |
|------|------|
| **自调用检查** | A2A 场景 caller == callee → 直接拒绝 |
| **deny 优先** | 禁止令牌不可被 allow 覆盖，命中 deny → 不可申请 |
| **白名单模式** | 无匹配条目 → 隐式拒绝 |
| **权限不扩散** | 临时权限只能通过人工审批获得 |
| **审批可裁剪** | 管理员可缩小 Agent 申请的权限范围、缩短 TTL |
| **TTL 硬限制** | 系统级 `MAX_TEMP_PERMISSION_TTL`（默认 3600s） |
| **任务结束清理** | finalize 物理删除所有临时权限 + 清除视图缓存 |
| **TTL 兜底** | 即使忘记 finalize，过期条目自动过滤 |
| **审计追踪** | 权限申请 → 审批 → 临时权限创建 → 全链路可追溯 |
| **Agent 意图** | SDK 调用时可选传入 reason，审批面板展示人类可读意图 |
| **精确匹配** | 仅支持精确 object_id 匹配，无通配符 |

---

## 十三、设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 令牌类型 | StandardToken（长期） + TaskPermissionEntry（临时） | 临时权限绑定任务而非 Agent，职责清晰 |
| 权限条目管理 | 增删查改 | 适应动态权限调整 |
| 临时权限生成 | Agent 按需申请 + 人工审批 | 应对不确定性，编排器不应有权限知识 |
| 视图构建 | 并集 + 交集，deny 优先 | 符合白名单 + 黑名单语义 |
| 视图缓存 | Redis，会话级，首次构建后续复用 | 减少 PG 查询 |
| 审计写入 | 异步 fire-and-forget | 不阻塞主调用链 |
| 自调用 | A2A 拒绝，MCP self-call 允许 | Agent 应有权调自己的工具 |
| 隐式拒绝 | 无匹配 → 拒绝（可申请） | 白名单模式，安全默认 |
| 调用入口 | 统一 `/gateway/call` | MCP 和 A2A 共用处理逻辑 |
| tool_owner | 精确匹配，无通配 | 避免权限传递歧义 |
| 递归拦截 | 每个 Agent 出站调都过网关 | 支持自有 MCP 池场景 |
| explicit deny | 不可申请覆盖 | deny 是硬边界 |
| 任务结束清理 | 物理删除 + Redis 清除 + TTL 兜底 | 及时 + 安全 |
