# 身份注册服务 — 完整设计文档

## 一、概述

身份注册服务是多Agent协作系统安全内核的四大核心模块之一，负责两大职责：

**职责 A — Agent 身份管理：**
- Agent 身份的数字证书**生成、颁发、续期和注销**
- 会话签名的**验证**（供权限网关调用）

**职责 B — MCP 工具注册（与 Agent 管理解耦）：**
- MCP 工具的**注册、查询、吊销**
- 为后期权限网关的可视化权限订阅提供工具清单

---

## 二、注册信息集

| 字段 | 类型 | 生成方式 | 说明 |
|------|------|----------|------|
| `agent_id` | UUID | 服务端生成 | Agent 唯一标识 |
| `agent_name` | string | 管理员提交 | 人类可读名称 |
| `agent_type` | enum: `orchestrator` / `worker` / `tool-proxy` | 管理员提交 | Agent 类型 |
| `public_key` | string(PEM) | 服务端生成 | Ed25519 公钥 |
| `private_key` | string(PEM) | 服务端生成，仅返回一次 | Ed25519 私钥，服务端不存储 |
| `owner` | string | 管理员提交 | 归属组织/团队 |
| `status` | enum: `active` / `revoked` / `expired` | 服务端管理 | 证书状态，软删除 |
| `issued_at` | datetime | 服务端生成 | 颁发时间 |
| `expires_at` | datetime | 服务端生成 | 过期时间（建议 90 天） |
| `revoked_at` | datetime | 服务端管理 | 吊销时间 |
| `metadata` | dict | 管理员提交，可选 | 扩展元数据 |

---

## 三、密钥算法

使用 **Ed25519**（EdDSA）：
- 密钥长度短，签名速度快
- 适合微服务场景的高频验签
- Python 通过 `nacl.signing` 库实现
- PEM 编码使用自定义 base64 格式（因 PyNaCl >= 1.5 移除了内置 PEMEncoder）

---

## 四、存储方案

采用 **方案 E：PostgreSQL（元数据） + Redis（缓存）** 混合方案。

| 存储层 | 职责 | 存储内容 |
|--------|------|----------|
| PostgreSQL | 持久化存储 | Agent 完整注册信息（含公钥），私钥**不存储** |
| Redis | 热缓存 | `agent_id → public_key` 映射，TTL 对齐证书有效期 |

### 缓存策略
- 注册时：写入 PG + 缓存公钥到 Redis
- 吊销时：更新 PG `status='revoked'` + 清除 Redis 缓存
- 续期时：更新 PG 公钥 + 更新 Redis 缓存
- 验签时：优先从 Redis 获取公钥，未命中则回源 PG

---

## 五、注册模式

采用 **模式 A：管理员预注册**。

```
管理员 → POST /agents/register → 身份注册服务
                                    ├── 生成 Ed25519 密钥对
                                    ├── 生成 agent_id (UUID)
                                    ├── 公钥 + 元数据 → PostgreSQL
                                    ├── 公钥 → Redis 缓存
                                    └── 返回 agent_id + private_key_pem

管理员 → 将 agent_id + 私钥 + 签名工具部署到 Agent 运行环境
```

---

## 六、证书生命周期

```
注册(active) → 正常使用(active) → 吊销(revoked) / 过期(expired)
                    │
                    └── 续期(renew) → 生成新密钥对 → active
```

- **有效期**：颁发时设置 `expires_at`（默认 90 天）
- **吊销**：软删除，标记 `status='revoked'`, `revoked_at=now()`
- **续期**：管理员调用 `/agents/{agent_id}/renew`，生成新密钥对并返回新私钥

---

## 七、会话签名机制

### 7.1 签名粒度

采用 **方案 B：每次调用签名**，实现操作级别的不可否认性。

### 7.2 签名 Payload 结构

```python
{
    "agent_id": "uuid-of-agent",
    "session_id": "uuid-of-session",
    "call_id": "uuid-of-call",
    "timestamp": "2026-04-30T10:30:00Z",
    "request_hash": "sha256(request_body)",
    "callee_agent_id": "agent-yyy",    # A2A 场景（可为空）
    "mcp_tool_name": "tool-xxx",       # MCP 场景（可为空）
    "tool_owner": "public"             # MCP 场景：工具属主，"public" 或 "{agent_id}"
}
```

### 7.3 签名流程

```
Agent 侧（SDK）:
  1. 构造规范化 payload
  2. 使用私钥签名
  3. 附带签名发起调用

身份注册服务侧（验签）:
  1. 权限网关调用 POST /verify/signature
  2. 从 Redis/PG 获取 Agent 公钥
  3. 若 Agent 非 active → 返回 verified=False
  4. 使用公钥验签
  5. 返回 { verified: bool }

审计模块侧（记录）:
  签名记录由权限网关构造并发送给审计模块持久化。
  见 SignatureRecord 数据结构。
```

---

## 八、服务接口清单

### 8.1 Agent 管理接口

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/agents/register` | 管理员预注册 Agent，返回 `agent_id` + 私钥 | 管理 API Key |
| `GET` | `/agents/{agent_id}` | 查询 Agent 信息（不含私钥） | 管理 API Key |
| `GET` | `/agents` | 列出所有 Agent | 管理 API Key |
| `POST` | `/agents/{agent_id}/revoke` | 吊销证书（软删除） | 管理 API Key |
| `POST` | `/agents/{agent_id}/renew` | 续期证书，生成新密钥对 | 管理 API Key |
| `POST` | `/verify/signature` | 验证会话签名（供权限网关调用） | 服务间 API Key |
| `GET` | `/agents/{agent_id}/public-key` | 获取 Agent 公钥（供权限网关/审计模块调用） | 服务间 API Key |

### 8.2 MCP 工具注册接口

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| `POST` | `/tools/register` | 注册 MCP 工具 | 管理 API Key |
| `GET` | `/tools/{tool_id}` | 查询工具信息 | 管理 API Key |
| `GET` | `/tools?owner=xxx` | 按属主列出工具 | 管理 API Key |
| `POST` | `/tools/{tool_id}/revoke` | 吊销工具（软删除） | 管理 API Key |
| `GET` | `/tools` | 获取所有已注册工具（供权限网关引用） | 服务间 API Key |

---

## 九、函数清单

### 9.1 `identity_service/crypto.py` — 加密操作

```python
def generate_ed25519_keypair() -> tuple[str, str]:
    """
    生成 Ed25519 密钥对。
    Returns:
        (private_key_pem: str, public_key_pem: str)
    """

def build_session_signature_payload(
    agent_id: str,
    session_id: str,
    call_id: str,
    timestamp: str,              # ISO 8601
    request_body: bytes,
    callee_agent_id: str = "",   # A2A 场景
    mcp_tool_name: str = "",     # MCP 场景
    tool_owner: str = ""         # MCP 场景：工具属主
) -> bytes:
    """
    构造签名的规范化 payload（JSON 序列化后的 UTF-8 字节）。
    此函数同时用于 Agent 侧签名和服务端验签，必须完全一致。
    """

def sign_payload(payload: bytes, private_key_pem: str) -> str:
    """
    使用 Ed25519 私钥对 payload 签名。
    Returns:
        signature_hex: str  # 十六进制字符串
    此函数在 Agent 侧 SDK 中运行。
    内部使用自定义 base64 解码 PEM 格式私钥。
    """

def verify_signature(payload: bytes, signature_hex: str, public_key_pem: str) -> bool:
    """
    使用 Ed25519 公钥验证签名。
    此函数在身份注册服务侧运行。
    内部使用自定义 base64 解码 PEM 格式公钥。
    Returns:
        True if signature is valid, False otherwise.
    """
```

### 9.2 `identity_service/cert_store.py` — PostgreSQL 存储层

```python
async def store_agent_cert(conn, agent: AgentRecord) -> None:
    """将 Agent 证书信息写入 PostgreSQL。"""

async def get_agent_cert(conn, agent_id: str) -> AgentRecord | None:
    """从 PostgreSQL 读取 Agent 证书信息。"""

async def list_agent_certs(conn, status_filter: str | None = None) -> list[AgentRecord]:
    """列出所有 Agent，可按状态过滤。"""

async def update_agent_status(conn, agent_id: str, status: str, **extra) -> None:
    """更新 Agent 状态（revoked/expired）及相关时间戳。"""

async def update_agent_key(conn, agent_id: str, public_key_pem: str,
                            issued_at: datetime, expires_at: datetime) -> None:
    """续期时更新公钥和有效期。"""
```

### 9.3 `identity_service/cache.py` — Redis 缓存层

```python
async def cache_agent_public_key(redis, agent_id: str, public_key_pem: str, ttl: int) -> None:
    """将 Agent 公钥缓存到 Redis，TTL 对齐证书有效期。"""

async def get_cached_public_key(redis, agent_id: str) -> str | None:
    """从 Redis 读取缓存的公钥。"""

async def invalidate_agent_cache(redis, agent_id: str) -> None:
    """吊销/续期时清除 Redis 缓存。"""
```

### 9.4 `identity_service/handlers.py` — API 处理函数

```python
async def handle_register(request: RegisterRequest) -> RegisterResponse:
    """
    POST /agents/register
    1. 验证管理 API Key
    2. 调用 generate_ed25519_keypair() 生成密钥对
    3. 生成 agent_id (UUID)
    4. 构造 AgentRecord，写入 PG
    5. 公钥缓存到 Redis
    6. 返回 agent_id + private_key_pem
    注意：private_key 仅在此次响应中返回，服务端不存储！
    """

async def handle_get_agent(agent_id: str) -> AgentResponse:
    """
    GET /agents/{agent_id}
    返回 Agent 公开信息（不含私钥）。
    """

async def handle_list_agents(status: str | None = None) -> list[AgentResponse]:
    """
    GET /agents
    列出所有 Agent，可按状态过滤。
    """

async def handle_revoke(agent_id: str) -> RevokeResponse:
    """
    POST /agents/{agent_id}/revoke
    1. 验证管理 API Key
    2. 更新 PG: status='revoked', revoked_at=now()
    3. 清除 Redis 缓存
    4. 返回结果
    """

async def handle_renew(agent_id: str) -> RenewResponse:
    """
    POST /agents/{agent_id}/renew
    1. 验证管理 API Key
    2. 生成新密钥对
    3. 更新 PG: new public_key, issued_at, expires_at
    4. 更新 Redis 缓存
    5. 返回 new private_key_pem
    """

async def handle_verify_signature(request: VerifyRequest) -> VerifyResponse:
    """
    POST /verify/signature
    供权限网关调用。
    1. 从 Redis/PG 获取 agent 公钥（优先 Redis）
    2. 若 agent 不存在或已 revoked → 返回 verified=False
    3. 使用 verify_signature() 验签
    4. 返回 { verified: bool, agent_id, ... }
    """

async def handle_get_public_key(agent_id: str) -> PublicKeyResponse:
    """
    GET /agents/{agent_id}/public-key
    供权限网关/审计模块获取公钥用于离线验签。
    """
```

### 9.5 `agent_sdk/signing_utils.py` — Agent 签名工具（分发给 Agent）

```python
def create_signed_request(
    agent_id: str,
    private_key_pem: str,
    session_id: str,
    call_id: str,
    request_body: dict | str,
    callee_agent_id: str = "",
    mcp_tool_name: str = "",
    tool_owner: str = ""
) -> dict:
    """
    Agent 侧调用，生成带签名的请求。
    Returns:
        {
            "agent_id": "...",
            "session_id": "...",
            "call_id": "...",
            "timestamp": "2026-04-30T...",
            "signature_hex": "...",
            "tool_owner": "...",
            "body": { ... }  # 原始请求体
        }
    此函数打包在 Agent SDK 中分发给 Agent 使用。
    """
```

---

## 十、MCP 工具注册

### 10.1 概述

MCP 工具注册功能与 Agent 注册**解耦**，共享同一部署单元（身份注册服务），但使用独立的数据模型和接口。两者的关联在于：

- 工具注册时声明的 `tool_owner` 引用已注册的 Agent ID（或 `"public"` 表示共享池）
- 权限网关在构建令牌条目时，可查询已注册的工具列表辅助权限配置

### 10.2 工具注册信息集

| 字段 | 类型 | 生成方式 | 说明 |
|------|------|----------|------|
| `tool_id` | UUID | 服务端生成 | 工具唯一标识 |
| `tool_name` | string | 管理员提交 | 工具名称（如 `file_read`） |
| `tool_owner` | string | 管理员提交 | 属主：`"public"` 或 `"{agent_id}"` |
| `description` | string | 管理员提交 | 工具功能描述（可视化时展示） |
| `tool_schema` | dict | 管理员提交，可选 | 工具参数 JSON Schema |
| `status` | enum: `active` / `revoked` | 服务端管理 | 工具状态，软删除 |
| `registered_at` | datetime | 服务端生成 | 注册时间 |
| `revoked_at` | datetime | 服务端管理 | 吊销时间 |

### 10.3 函数清单

**新增文件：`identity_service/tool_store.py`**

```python
async def store_tool(conn, tool: ToolRecord) -> None:
    """将 MCP 工具信息写入 PostgreSQL。"""

async def get_tool(conn, tool_id: str) -> ToolRecord | None:
    """按 ID 查询工具。"""

async def list_tools(conn, owner_filter: str | None = None) -> list[ToolRecord]:
    """列出工具，可按 owner 过滤（public / agent_id）。"""

async def update_tool_status(conn, tool_id: str, status: str, revoked_at: datetime) -> None:
    """吊销工具（软删除，标记 revoked）。"""
```

**新增路由：`identity_service/handlers.py`**

```python
async def handle_register_tool(request: RegisterToolRequest) -> RegisterToolResponse:
    """
    POST /tools/register
    1. 验证管理 API Key
    2. 生成 tool_id (UUID)
    3. 验证 tool_owner 为 'public' 或已注册的 agent_id
    4. 校验同一 owner 下 tool_name 唯一
    5. 写入 PG
    6. 返回 tool_id
    """

async def handle_get_tool(tool_id: str) -> ToolResponse:
    """GET /tools/{tool_id}"""

async def handle_list_tools(owner: str | None = None) -> list[ToolResponse]:
    """
    GET /tools?owner=public&owner=agent-a
    按属主过滤，不传则返回全部。
    """

async def handle_revoke_tool(tool_id: str) -> RevokeResponse:
    """
    POST /tools/{tool_id}/revoke
    1. 验证管理 API Key
    2. 更新 PG: status='revoked', revoked_at=now()
    3. 返回结果
    """
```

### 10.4 与权限网关的协作

```
管理员操作流程（未来可视化场景）：

1. 在身份注册服务中注册 Agent
2. 在身份注册服务中注册 MCP Tools（声明 tool_owner）
3. 在权限网关中创建令牌时：
   - 查询 GET /agents → 下拉选择主体 Agent
   - 查询 GET /tools?owner=xxx → 下拉选择客体 Tool
   - 点击 → 快速建立权限条目
```

### 10.5 约束规则

- 同一 `(tool_owner, tool_name)` 组合在 active 状态下必须唯一
- `tool_owner` 为 `"public"` 时表示共享 MCP 池，任意 Agent 可访问（但仍需权限网关授权）
- `tool_owner` 为 `"{agent_id}"` 时表示该 Agent 自有池中的工具
- 工具吊销为软删除，保留审计记录

---

## 十一、数据流图

### 11.1 Agent 注册流程

```
管理员
  │
  │ POST /agents/register { agent_name, agent_type, owner }
  ▼
身份注册服务
  │
  ├── generate_ed25519_keypair()
  ├── store_agent_cert() → PostgreSQL
  ├── cache_agent_public_key() → Redis
  └── 返回 { agent_id, private_key_pem }
        │
        │ 管理员将凭据部署到 Agent 实例
        ▼
  ┌──────────┐
  │ Agent实例 │ ← agent_id + private_key_pem + signing_utils.py
  └──────────┘
```

### 11.2 运行时调用流程

```
┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Agent A  │────▶│ 身份注册服务  │────▶│ 权限网关  │────▶│ 执行层   │────▶│ 审计模块  │
│ (调用方) │     │ (身份验证)   │     │ (权限判定)│     │ (实际执行)│     │ (记录日志)│
└──────────┘     └──────────────┘     └──────────┘     └──────────┘     └──────────┘
     │                                        │                                │
     │  ① 用私钥签名请求                       │                                │
     │  附带 signature_hex                    │                                │
     │───────────────────────────────────────▶│                                │
     │                                        │  ② POST /verify/signature      │
     │                                        │───────────────────────────────▶│
     │                                        │  ③ 返回 { verified: bool }     │
     │                                        │  ④ 令牌视图判定                 │
     │                                        │  ⑤ 构造 SignatureRecord        │
     │                                        │  ⑥ 转发至执行层（并行）         │
     │                                        │───────────────────────────────▶│
     │                                        │────────────────▶              │
```

---

## 十二、数据库表设计

### PostgreSQL — `agents` 表

```sql
CREATE TABLE agents (
    id              UUID PRIMARY KEY,
    agent_name      VARCHAR(255) NOT NULL,
    agent_type      VARCHAR(50) NOT NULL,   -- 'orchestrator', 'worker', 'tool-proxy'
    public_key      TEXT NOT NULL,           -- PEM 格式
    owner           VARCHAR(255) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'revoked', 'expired'
    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_owner ON agents(owner);
```

### PostgreSQL — `mcp_tools` 表

```sql
CREATE TABLE mcp_tools (
    id              UUID PRIMARY KEY,
    tool_name       VARCHAR(255) NOT NULL,
    tool_owner      VARCHAR(255) NOT NULL,   -- 'public' 或 agent_id
    description     TEXT DEFAULT '',
    tool_schema     JSONB DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'revoked'
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX idx_tools_owner ON mcp_tools(tool_owner);
CREATE INDEX idx_tools_status ON mcp_tools(status);
-- 同一属主下工具名唯一（仅 active 状态）
CREATE UNIQUE INDEX idx_tools_owner_name 
    ON mcp_tools(tool_owner, tool_name) WHERE status = 'active';
```

### Redis — 缓存结构

```
Key:   "agent:pubkey:{agent_id}"
Value: "{public_key_pem}"
TTL:   与 expires_at 对齐（秒数）
```

---

## 十三、开发推进计划

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1 | 项目骨架搭建（FastAPI 项目结构 + PG/Redis 连接） | 项目根目录 |
| 2 | `crypto.py` — Ed25519 密钥生成、签名、验签 | `identity_service/crypto.py` |
| 3 | `cert_store.py` — Agent PG 存储层（CRUD） | `identity_service/cert_store.py` |
| 4 | `tool_store.py` — MCP 工具 PG 存储层（CRUD） | `identity_service/tool_store.py` |
| 5 | `cache.py` — Redis 缓存层（Agent 公钥） | `identity_service/cache.py` |
| 6 | `handlers.py` — Agent 管理 API | `identity_service/handlers.py` |
| 7 | `handlers.py` — MCP 工具注册 API | `identity_service/handlers.py` |
| 8 | `handlers.py` — 验证 API（verify/public-key） | `identity_service/handlers.py` |
| 9 | `signing_utils.py` — Agent SDK 签名工具 | `agent_sdk/signing_utils.py` |
| 10 | 集成测试 + 文档 | `tests/` |

---

## 十四、设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 密钥算法 | Ed25519 | 轻量、快速，适合微服务高频验签 |
| 注册模式 | 管理员预注册（模式A） | 流程清晰，避免鸡生蛋问题，适合初期开发 |
| 存储方案 | PG + Redis 混合 | PG 保证一致性和审计能力，Redis 保证验签性能 |
| 吊销方式 | 软删除 | 保留审计轨迹 |
| 签名粒度 | 每次调用签名（方案B） | 操作级不可否认性 |
| capabilities | 不在注册阶段声明 | 留给权限网关管理 |
| 私钥存储 | 服务端不存储 | 仅注册/续期响应时返回一次 |
| MCP 工具注册 | 与 Agent 注册同服务解耦 | 共享部署但独立模型，便于后期可视化权限配置 |
| tool_owner 取值 | `"public"` 或 `"{agent_id}"` | 区分共享池与自有池，不设通配 |
