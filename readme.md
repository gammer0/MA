# MA — 多Agent协作系统安全内核

给 AI 发通行证：构建 Agent 身份与权限系统。

## 快速启动

### 环境要求
- Docker + Docker Compose
- Python 3.12+ (仅批量注册脚本需要)

### 一键启动

```bash
# 1. 启动所有服务
cd docker
docker compose up -d

# 2. 等待服务就绪（约 10 秒）
# 检查状态：docker compose ps

# 3. 批量注册 Agent 和 Tool（首次）
cd ..
python scripts/batch_register.py \
  --manifest scripts/agent_tool_manifest.json \
  --api-key admin-secret-key-dev \
  --url http://localhost:8001

# 4. 打开权限管理界面配置令牌
# http://localhost:8002/admin
# 点击「🔑 令牌订阅」，为每个 Agent 配置 allow/deny 权限，点击保存

# 5. 打开执行层控制台执行任务
# http://localhost:8004
# 输入自然语言指令，点击「执行任务」
```

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 身份注册服务 | `:8001` | Agent 证书生成/颁发/验签 |
| 权限网关 | `:8002` | 令牌管理 + 调用拦截 + 管理 UI |
| 审计模块 | `:8003` | 签名记录 + 会话日志 + 调用链 |
| 飞书 Demo | `:8005` | 飞书三Agent演示 (Reporter/Data/Search) |
| PostgreSQL | `:5432` | 共享数据库 |
| PostgreSQL | `:5432` | 共享数据库 |
| Redis | `:6379` | 缓存（视图/指令映射） |

### 管理密钥

| 用途 | Key |
|------|-----|
| Admin API | `admin-secret-key-dev` |
| Service API | `service-secret-key-dev` |

---

## 架构

```
User (Web UI)
  │
  ▼
执行层 (Orchestrator → Searcher / Analyzer)
  │
  │  每次调用都经过权限网关
  ▼
权限网关 ──验签──→ 身份注册服务
  │                │
  ├── StandardToken (长期令牌)
  ├── TaskPermissionEntry (临时权限, 审批后注入)
  └── TokenView (会话级视图, Redis缓存)
  │
  ▼
审计模块 ←── 签名记录 + 会话日志 + 调用链
```

**权限模型**：
```
A2A: final_view = (caller令牌视图 ∩ callee长期令牌) ∪ callee临时权限
     ├── deny 优先
     ├── allow 需双方都 allow (精确匹配)
     └── callee 隐式 self-allow (默认允许被调用)

MCP: caller 自身的令牌视图 (长期 + 临时)
```

---

## 目录结构

```
MA/
├── services/                  # 安全内核微服务
│   ├── identity-service/      # 身份注册服务 (:8001)
│   ├── permission-gateway/    # 权限网关 (:8002)
│   ├── audit-service/         # 审计模块 (:8003)
│   └── execution-layer/       # 执行层入口 (配置文件, 业务代码在 demo-app/)
│
├── feishu-demo-app/           # 飞书三Agent演示项目
│   ├── main.py                # FastAPI (:8005)
│   ├── orchestrator.py        # ReporterAgent (飞书文档助手)
│   ├── worker_agents/         # DataAgent / SearchAgent
│   ├── mcp_tools/             # 飞书CLI封装 + Mock搜索工具
│   └── static/                # Web UI
│
├── agent-sdk/                 # Agent SDK（独立包）
├── docker/                    # Docker Compose 编排
├── scripts/                   # 运维脚本
│   ├── batch_register.py      # 批量注册 Agent + Tool
│   └── agent_tool_manifest.json
├── docs/                      # 设计文档 (6 份)
└── tests/                     # 单元测试
```

