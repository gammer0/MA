# 项目架构与目录结构 — 设计文档

## 一、项目全景架构

```
                        ┌─────────────────────────────────────┐
                        │         Docker Network (内部)         │
                        │                                      │
  ┌──────────┐          │  ┌──────────────┐                   │
  │ 管理员    │──HTTPS──▶│  │ API Gateway  │ (可选，统一入口)   │
  └──────────┘          │  │  Nginx/Kong  │                   │
                        │  └──────┬───────┘                   │
                        │         │                           │
                        │    ┌────┴──────────────────────┐    │
                        │    │                           │    │
                        │    ▼                           ▼    │
                        │ ┌──────────────┐     ┌──────────────┐│
                        │ │ 身份注册服务  │     │  权限网关     ││
                        │ │ (管理API)    │     │ (运行时API)  ││
                        │ │ :8001        │     │ :8002        ││
                        │ └──────┬───────┘     └──────┬───────┘│
                        │        │                    │       │
                        │        │     ┌──────────────┘       │
                        │        │     │                      │
                        │        ▼     ▼                      │
                        │ ┌──────────────┐     ┌──────────────┐│
                        │ │  审计模块     │     │  执行层      ││
                        │ │ (记录日志)   │     │ (多Agent协作) ││
                        │ │ :8003        │     │ :8004        ││
                        │ └──────────────┘     └──────────────┘│
                        │                                      │
                        │ ┌──────────┐ ┌──────────┐            │
                        │ │PostgreSQL│ │  Redis   │            │
                        │ │ :5432    │ │ :6379    │            │
                        │ └──────────┘ └──────────┘            │
                        └─────────────────────────────────────┘
```

---

## 二、目录结构

```
MA/
├── docs/                                    # 设计文档
│   ├── identity-registration-service.md     # 身份注册服务设计
│   ├── permission-gateway.md                # 权限网关设计
│   ├── audit-module.md                      # 审计模块设计
│   ├── project-architecture.md              # 本文档
│   ├── execution-layer.md                   # 执行层设计
│
├── services/                                # 微服务根目录
│   ├── identity-service/                    # 身份注册服务
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                          # FastAPI 入口
│   │   ├── config.py                        # 配置（环境变量读取）
│   │   ├── crypto.py                        # Ed25519 密钥生成、签名、验签
│   │   ├── models.py                        # Pydantic 数据模型
│   │   ├── cert_store.py                    # PostgreSQL 存储层
│   │   ├── cache.py                         # Redis 缓存层
│   │   ├── handlers.py                      # API 路由处理
│   │   ├── middleware.py                    # 管理 API Key 认证中间件
│   │   └── tests/
│   │       ├── test_crypto.py
│   │       ├── test_handlers.py
│   │       └── test_integration.py
│   │
│   ├── permission-gateway/                  # 权限网关
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                          # FastAPI 入口
│   │   ├── config.py
│   │   ├── models.py                        # Token, TokenView, Session, PermissionRequest 等模型
│   │   ├── token_manager.py                 # Standard Token 的 CRUD
│   │   ├── task_permissions.py              # 任务临时权限管理
│   │   ├── permission_requests.py           # 权限申请与审批
│   │   ├── view_builder.py                  # 令牌视图构建（并集/交集）
│   │   ├── session_manager.py               # 会话生命周期管理
│   │   ├── identity_client.py               # 调身份注册服务验签的 HTTP 客户端
│   │   ├── audit_client.py                  # 向审计模块发送记录的 HTTP 客户端
│   │   ├── handlers.py                      # API 路由
│   │   ├── middleware.py                    # 拦截中间件
│   │   └── tests/
│   │
│   ├── audit-service/                       # 审计模块
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py                        # SignatureRecord, SessionLog 等
│   │   ├── log_store.py                     # 日志持久化（PG）
│   │   ├── trace_builder.py                 # 调用链建模
│   │   ├── handlers.py                      # 写入/查询 API
│   │   └── tests/
│   │
│   └── execution-layer/                     # 执行层（多Agent协作示例）
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py
│       ├── config.py
│       ├── orchestrator.py                  # 编排器 Agent
│       ├── worker_agents/                   # Worker Agent 示例
│       │   ├── base_worker.py
│       │   ├── code_agent.py
│       │   └── search_agent.py
│       ├── mcp_tools/                       # MCP 工具集示例
│       │   ├── file_tool.py
│       │   └── web_tool.py
│       ├── agent_sdk/                       # Agent 签名 SDK（内嵌版，方便开发调试）
│       │   ├── __init__.py
│       │   └── signing_utils.py
│       ├── interceptor.py                   # 调用拦截器（进入权限网关前）
│       ├── gateway_client.py                # 调权限网关的 HTTP 客户端
│       └── tests/
│
├── agent_sdk/                               # 独立分发的 Agent SDK（正式 pip 包）
│   ├── setup.py
│   ├── README.md
│   └── agent_sdk/
│       ├── __init__.py
│       └── signing_utils.py
│
├── docker/                                  # Docker 编排
│   ├── docker-compose.yml                   # 开发环境
│   ├── docker-compose.prod.yml              # 生产环境（覆盖）
│   └── nginx.conf                           # API Gateway 配置（可选，暂不确定）
│
├── scripts/                                 # 运维脚本
│   ├── init_db.sql                          # 数据库初始化 DDL
│   ├── register_agent.py                    # 管理员注册脚本
│   └── seed_data.py                         # 测试数据填充
│
├── .env.example                             # 环境变量模板
├── .gitignore
├── readme.md
└── work.md
```

---

## 三、服务端口与职责

| 服务 | 端口 | 对外暴露 | 职责 |
|------|------|----------|------|
| 身份注册服务 | 8001 | 管理接口（内网） | Agent 证书生成/颁发/吊销/续期、会话签名验证 |
| 权限网关 | 8002 | 运行时接口 | 令牌管理、令牌视图构建、会话管理、拦截判定 |
| 审计模块 | 8003 | 服务间调用 | 签名记录持久化、会话日志、调用链建模 |
| 执行层 | 8004 | 运行时接口 | 多Agent协作示例、MCP/A2A 编排 |
| PostgreSQL | 5432 | 仅内网 | 持久化存储（共享实例） |
| Redis | 6379 | 仅内网 | 热缓存 |

---

## 四、服务间调用关系

```
┌─────────────────────────────────────────────────────────┐
│                      调用关系图                           │
│                                                         │
│  身份注册服务 ◀──── 权限网关 (验签)                        │
│  身份注册服务 ◀──── 审计模块 (获取公钥用于离线验签)         │
│                                                         │
│  权限网关 ◀──── 执行层 (每次 MCP/A2A 调用都经过网关)       │
│                                                         │
│  审计模块 ◀──── 权限网关 (写入签名记录和会话日志)           │
│  审计模块 ◀──── 执行层 (可选的执行结果日志)                │
│                                                         │
│  PostgreSQL ◀── 身份注册服务 / 权限网关 / 审计模块          │
│  Redis      ◀── 身份注册服务 / 权限网关                    │
└─────────────────────────────────────────────────────────┘
```

---

## 五、数据库共享策略

三个服务共享同一个 PostgreSQL 实例，通过不同的表进行逻辑隔离：

| 服务 | 使用 PG 的表 | 使用 Redis 的 DB |
|------|-------------|------------------|
| 身份注册服务 | `agents`, `mcp_tools` | DB 0（公钥缓存） |
| 权限网关 | `standard_tokens`, `standard_token_entries`, `task_permission_entries`, `permission_requests`, `sessions` | DB 1（令牌视图缓存） |
| 审计模块 | `signature_records`, `session_logs`, `traces` | 不使用 |

> 共享实例避免引入分布式事务复杂度。后续如需严格隔离，可拆分为独立 database。

---

## 六、服务发现

Docker Compose 环境中，服务名即为 DNS：

```
http://identity-service:8001
http://permission-gateway:8002
http://audit-service:8003
http://execution-layer:8004
```

无需引入额外服务发现组件。

---

## 七、Docker Compose 编排

### `docker/docker-compose.yml`

```yaml
version: '3.8'

services:
  # ============ 基础设施 ============
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agent_security
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

  # ============ 微服务 ============
  identity-service:
    build: ./services/identity-service
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql+asyncpg://agent:${PG_PASSWORD}@postgres:5432/agent_security
      REDIS_URL: redis://redis:6379/0
      ADMIN_API_KEY: ${ADMIN_API_KEY}
      SERVICE_API_KEY: ${SERVICE_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  permission-gateway:
    build: ./services/permission-gateway
    ports:
      - "8002:8002"
    environment:
      DATABASE_URL: postgresql+asyncpg://agent:${PG_PASSWORD}@postgres:5432/agent_security
      REDIS_URL: redis://redis:6379/1
      IDENTITY_SERVICE_URL: http://identity-service:8001
      AUDIT_SERVICE_URL: http://audit-service:8003
      SERVICE_API_KEY: ${SERVICE_API_KEY}
    depends_on:
      - identity-service

  audit-service:
    build: ./services/audit-service
    ports:
      - "8003:8003"
    environment:
      DATABASE_URL: postgresql+asyncpg://agent:${PG_PASSWORD}@postgres:5432/agent_security
      SERVICE_API_KEY: ${SERVICE_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy

  execution-layer:
    build: ./services/execution-layer
    ports:
      - "8004:8004"
    environment:
      GATEWAY_URL: http://permission-gateway:8002
    depends_on:
      - permission-gateway

volumes:
  pg_data:
```

---

## 八、环境变量

### `.env.example`

```env
# PostgreSQL
PG_PASSWORD=changeme_in_production

# API Keys (管理接口和服务间调用)
ADMIN_API_KEY=admin-secret-key-dev
SERVICE_API_KEY=service-secret-key-dev
```

---

## 九、技术栈汇总

| 类别 | 技术 | 用途 |
|------|------|------|
| API 框架 | FastAPI (Python) | 所有微服务的 HTTP API |
| 异步驱动 | asyncpg | PostgreSQL 异步访问 |
| 缓存 | redis-py (async) | Redis 缓存操作 |
| 加密 | PyNaCl / cryptography | Ed25519 密钥生成与签名 |
| ORM | SQLAlchemy 2.0 (async) | 数据库操作 |
| 验证 | Pydantic v2 | 数据模型与请求验证 |
| 容器化 | Docker + Docker Compose | 服务编排与部署 |
| 数据库 | PostgreSQL 16 | 持久化存储 |
| 缓存 | Redis 7 | 热缓存 |

---

## 十、Agent SDK 分发策略

| 位置 | 用途 |
|------|------|
| `agent_sdk/` (项目根) | 独立 pip 包，正式分发 |
| `services/execution-layer/agent_sdk/` | 内嵌副本，方便开发调试 |

两者代码保持同步，`signing_utils.py` 为同一份实现。

---

## 十一、待定事项

| 事项 | 状态 | 备注 |
|------|------|------|
| API Gateway (Nginx/Kong) | 暂不确定 | 第一阶段各服务直接暴露端口，后续按需引入 |
| 数据库实例隔离 | 暂用共享 | 当前共享 PG 实例，后续可按需拆分 |
| 生产环境 Compose 覆盖 | 未创建 | 待开发完成后补充 `docker-compose.prod.yml` |
