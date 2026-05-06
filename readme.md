# MA — 多 Agent 协作系统安全内核

> **给 AI 发通行证：构建 Agent 身份与权限系统**

为 AI Agent 建立专属的身份与权限基础设施 —— 身份注册、细粒度权限管控、委托授权、越权拦截、审计追溯。

---

## 目录

- [快速演示（10 分钟）](#快速演示10-分钟)
- [功能边界](#功能边界)
- [系统架构](#系统架构)
- [权限模型详解](#权限模型详解)
- [三种角色使用指南](#三种角色使用指南)
  - [开发者：Agent SDK](#开发者agent-sdk)
  - [权限管理员](#权限管理员)
  - [最终用户](#最终用户)
- [目录结构](#目录结构)
- [服务端口](#服务端口)
- [API 参考](#api-参考)
- [设计文档](#设计文档)

---

## 快速演示（10 分钟）

演示场景：飞书中有四个 AI Agent —— 文档助手（reporter）、企业数据 Agent（data_agent）、外部检索 Agent（search_agent）、数据分析 Agent（analyzer）。系统提供三个硬编码安全场景：
- **场景A**：三Agent正常委托（查询数据 → 写报告）
- **场景B**：三Agent越权拦截（search_agent 越权调飞书数据被 deny 阻止）
- **场景C**：四Agent单链调用（reporter → data → search → analyzer → 文档）

### 前置准备

- Docker Desktop（含 Docker Compose）
- Python 3.12+
- `lark-cli`（飞书 CLI 工具，可选；如需真实飞书数据则必须）

> **⚠️ 飞书 CLI 配置提醒**：如果希望飞书工具（日历/通讯录/多维表格/文档）返回真实数据而非 mock 结果，需提前安装并登录 `lark-cli`：
> ```bash
> npm install -g lark-cli                        # 安装
> lark-cli config init                           # 初始化配置
> lark-cli auth login                            # 登录飞书账号
> ```
> 如未配置 `lark-cli`，飞书工具调用将返回 `lark-cli 未安装` 错误，但不影响权限拦截演示。

### 第 1 步：配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY、FEISHU_APP_ID、FEISHU_APP_SECRET
```

### 第 2 步：启动安全内核

```bash
cd docker
docker compose --env-file ../.env up -d
```
### 第3步：启动 Demo App：
```sh
   cd feishu-demo-app && pip install -r requirements.txt && python main.py
```
   
等待所有服务 healthy（约 15 秒）：

```bash
docker compose ps
# 应看到 postgres、redis、identity-service、permission-gateway、audit-service 均为 healthy/running
```

### 第 3 步：注册 Agent + 启动 Demo App + 创建令牌

在管理 UI 中完成全部操作，无需命令行：

1. 打开 **权限管理 UI**：`http://localhost:8002/admin`

2. **批量注册**：点击「📁 上传」选择 `scripts/agent_tool_manifest_feishu.json`，再点击「🚀 开始注册」
   - 自动注册 4 个 Agent + 8 个 Tool
   - 私钥自动推送至 demoapp 并加密持久化


3. **创建令牌**：切换到「🔑 令牌订阅」标签，为每个 Agent 创建令牌：
   - **reporter**：`allow agent:data_agent` / `allow agent:search_agent` / `allow agent:analyzer` / `allow mcp_tool:lark_doc`
   - **data_agent**：`allow mcp_tool:lark_calendar` / `allow mcp_tool:lark_base` / `allow mcp_tool:lark_contact`
   - **search_agent**：`allow mcp_tool:web_search` / `allow mcp_tool:page_fetch` / **`deny mcp_tool:lark_base`**
   - **analyzer**：`allow mcp_tool:data_summarize` / `allow mcp_tool:chart_gen`

4. 在「⏳ 权限申请审批」面板点击「自动降级」

### 第 4 步：执行三种安全场景

打开 **演示控制台**：`http://localhost:8005`，在文本框中依次输入以下指令并点击「执行任务」：

| 场景 | 输入指令 | 预期调用 |
|------|---------|---------|
| **A. 正常委托** | `查询团队日历和多维表格项目进度，结合外部行业动态，生成周报写入飞书文档` | reporter → data(3工具) + search(2工具) → lark_doc |
| **B. 越权拦截** | `越权拦截演示：查询企业数据，测试search_agent越权访问飞书多维表格` | 同上 + search→lark_base 🔴 被 deny 阻止 |
| **C. 四Agent单链** | `四Agent综合分析：查询数据，搜索公开信息，数据分析，生成报告` | 同上 + analyzer(2工具) 共 4 Agent |

6. 在管理 UI（`:8002/admin`）查看「📋 任务审计列表」验证调用链

### 停止服务

```bash
# 停止飞书 Demo：Ctrl+C
# 停止 Docker 服务：
docker compose -f docker/docker-compose.yml --env-file .env down -v
```

---

## 功能边界

### ✅ 本系统提供

| 功能 | 说明 |
|------|------|
| Agent 身份注册 | Ed25519 密钥对生成、私钥自动推送到执行层 |
| 加密密钥持久化 | 私钥加密存储于本地文件，重启自动恢复 |
| 长期令牌 (StandardToken) | Agent 注册时由管理员预定义的权限集合 |
| 临时权限 (TaskPermission) | 与任务绑定的动态权限，自动审批降级 |
| A2A 权限控制 | Agent 调用 Agent 时的交集权限模型 |
| MCP 权限控制 | Agent 调用 MCP 工具时的自主权限检查 |
| deny 优先 | 任一方 deny 即拒绝，精确匹配 |
| 审计日志 | 签名记录、权限决策、安全事件全量记录 |
| 多场景演示 | 正常委托 / 越权拦截 / 四Agent单链 |

### ❌ 本系统不覆盖（留给外围安全系统）

- 网络层 DDoS 防护
- 操作系统级别安全加固
- 密钥泄露后的证书吊销自动化（预留了 `revoke` 接口）
- 多租户隔离
- 用户 (User) → Agent 的委托授权链
- Token 的 JWT 格式标准化（当前为自定义格式）
- 生产级密钥管理（KMS/HashiCorp Vault）

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    最终用户                           │
│              http://localhost:8005                    │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│  执行层 (feishu-demo-app)                            │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │ Reporter │──▶│DataAgent │   │SearchAgent│        │
│  │ (编排器)  │   │(企业数据) │   │(外部检索) │        │
│  └──────────┘   └────┬─────┘   └────┬─────┘        │
│                      │              │               │
│         每次 A2A/MCP 调用都经过权限网关              │
└──────────────────────┼──────────────┼───────────────┘
                       │              │
                       ▼              ▼
┌─────────────────────────────────────────────────────┐
│              权限网关 (:8002)                         │
│  ┌─────────────────────────────────────────────┐    │
│  │  TokenView = caller_view ∩ callee_standard  │    │
│  │              ∪ callee_task_permissions       │    │
│  │                                              │    │
│  │  deny 优先 → 精确匹配 → 隐式拒绝             │    │
│  └─────────────────────────────────────────────┘    │
│         │                                           │
│         ├──▶ 身份注册服务 (:8001) — 验签             │
│         └──▶ 审计模块 (:8003) — 记录日志             │
└─────────────────────────────────────────────────────┘

基础设施: PostgreSQL 16 + Redis 7
```

---

## 权限模型详解

### 令牌类型

| 令牌 | 生命周期 | 说明 |
|------|---------|------|
| StandardToken | 长期（手动吊销） | Agent 注册时管理员配置的固有权限 |
| TaskPermissionEntry | 任务期间 | 与 task_id 绑定，任务结束后失效 |
| TokenView | 会话期间 | 以上二者的并集/交集，Redis 缓存 |

### A2A 调用权限计算

```
final_view = (caller_view ∩ callee_standard) ∪ callee_task_permission
```

交集规则（按 `(object_type, object_id, tool_owner)` 精确匹配）：

| caller 条目 | callee 条目 | 结果 |
|------------|------------|------|
| deny | * | **deny** |
| * | deny | **deny** |
| allow | allow | **allow** |
| allow | unset | 无条目（需申请） |
| unset | * | 无条目（需申请） |

特殊规则：
- callee 默认具有 `allow agent: callee_id`（可被调用）
- deny 条目排在视图最前面，优先匹配

### MCP 调用权限计算

```
view = agent_standard ∪ agent_task_permission
```

仅检查 caller 自身的令牌视图，不涉及 callee。

---

## 三种角色使用指南

### 开发者：Agent SDK

Agent SDK (`agent_sdk/`) 是开发者的唯一接入点。所有 Agent 都应继承 `SecureAgentClient`。

#### 安装

```bash
pip install -e agent_sdk/
```

#### 核心类

```python
from agent_sdk import SecureAgentClient, AgentRegistry, PermissionDeniedError
```

#### SecureAgentClient —— Agent 基类

每个 Agent 继承此类，获得安全调用能力：

```python
class MyAgent(SecureAgentClient):
    def __init__(self, agent_id, private_key_pem, gateway_url):
        super().__init__(agent_id, private_key_pem, gateway_url)

    async def do_work(self, task_id: str):
        # 调用另一个 Agent（A2A）
        result = await self.call_agent(
            callee_agent_id="data_agent",
            message={"action": "query", "query": "本周进度"},
            task_id=task_id,
            reason="查询项目进度数据",
        )

        # 调用 MCP 工具
        result = await self.call_mcp_tool(
            tool_name="lark_doc",
            tool_owner="reporter",
            tool_args={"action": "create", "title": "周报"},
            task_id=task_id,
            reason="生成周报文档",
        )
```

关键方法：

| 方法 | 说明 |
|------|------|
| `call_agent(callee_agent_id, message, task_id, reason)` | A2A 调用，reason 显示在审批面板 |
| `call_mcp_tool(tool_name, tool_owner, tool_args, task_id, reason)` | MCP 调用，reason 显示在审批面板 |

SDK 自动处理：
- Ed25519 签名（每个请求自动生成签名 payload）
- 会话 ID 生成
- 权限拒绝时的 `PermissionDeniedError` 异常
- 临时权限申请后的自动重试（新 session_id）

#### PermissionDeniedError —— 权限异常

```python
try:
    await self.call_mcp_tool(...)
except PermissionDeniedError as e:
    print(f"权限拒绝: {e.reason}")       # 拒绝原因
    print(f"可申请: {e.can_request}")    # 是否可申请临时权限
```

#### AgentRegistry —— 注册中心

管理多个 Agent 实例，支持密钥热注入：

```python
registry = AgentRegistry(gateway_url="http://localhost:8002")

# 注册 Agent 类型（不创建实例）
registry.register("reporter", ReporterAgent, data_agent=None, search_agent=None)
registry.register("data_agent", DataAgent)
registry.register("search_agent", SearchAgent)

# 热注入密钥（运行时，无需重启）
registry.inject_keys({
    "reporter": {"agent_id": "uuid-xxx", "private_key": "-----BEGIN PRIVATE KEY-----\n..."},
    "data_agent": {"agent_id": "uuid-yyy", "private_key": "-----BEGIN PRIVATE KEY-----\n..."},
})

# 获取实例
reporter = registry.get("reporter")
```

#### 编写新 Agent 的完整示例

```python
# my_agent.py
from agent_sdk import SecureAgentClient, PermissionDeniedError

class MyWorkerAgent(SecureAgentClient):
    def __init__(self, agent_id, private_key_pem, gateway_url):
        super().__init__(agent_id, private_key_pem, gateway_url)

    async def process(self, task_id: str, query: str) -> dict:
        # 通过网关调用 MCP 工具
        await self.call_mcp_tool(
            tool_name="my_tool",
            tool_owner="my_agent",
            tool_args={"query": query},
            task_id=task_id,
            reason=f"处理查询: {query[:40]}",
        )
        # ... 执行实际逻辑
        return {"status": "ok", "result": "..."}
```

```json
// agent_tool_manifest.json 中注册
{
    "agents": [
        {"agent_name": "my_agent", "agent_type": "worker", "owner": "my-team"}
    ],
    "tools": [
        {"tool_name": "my_tool", "tool_owner": "my_agent", "description": "我的工具"}
    ]
}
```

---

### 权限管理员

权限管理员通过 **权限网关管理 UI** 进行日常运维。

#### 管理 UI 入口

`http://localhost:8002/admin`

#### 主要操作

##### 1. 令牌订阅（长期权限）

在「🔑 令牌订阅」面板：

1. 选择目标 Agent
2. 填写标签（如 "数据 Agent 标准权限"）
3. 添加条目（effect + object_type + object_id + tool_owner）：
   - `allow agent data_agent` — 允许被其他 Agent 调用
   - `allow mcp_tool lark_base data_agent` — 允许调用某工具
   - `deny mcp_tool lark_base data_agent` — 明确拒绝某工具
4. 点击「创建令牌」

> **原则**：先配置 deny 边界，再配置 allow 权限。

##### 2. 审批面板

在「📋 审批队列」面板：

- **自动模式**：新请求自动批准（开发环境）
- **手动模式**：逐条审核临时权限申请
- 每条申请显示：申请人、目标资源、申请原因

##### 3. 审计列表

在「📊 审计日志」面板：

- 分页浏览所有任务
- 展开查看调用链（每个任务的会话列表）
- 查看签名验证记录
- 查看权限决策日志（allowed / denied）

##### 4. 批量注册

首次部署时，管理员运行：

```bash
python scripts/batch_register.py \
  --manifest scripts/agent_tool_manifest_feishu.json
```

此脚本自动完成 Agent 和 Tool 的注册，并将私钥注入执行层。

---

### 最终用户

最终用户通过 **飞书演示应用 Web UI** 与系统交互。

#### 访问地址

`http://localhost:8005`

#### 使用方法

1. 在输入框中输入自然语言任务指令，如：
   - `帮我生成本周项目进度周报`
   - `查询团队日程并汇总`

2. 点击「执行」

3. 观察结果：
   - **调用链**：显示 reporter → data_agent → search_agent 的调用关系
     - ⏳ = 等待中
     - ✅ = 允许
     - 🔴 = 拒绝
   - **安全事件**：越权拦截详情
   - **任务总结**：LLM 生成的自然语言摘要

#### 演示的两个核心场景

**场景 1 — 正常委托**：
```
用户 → reporter → data_agent → lark_calendar ✅
                             → lark_base     ✅
                             → lark_contact  ✅
                → search_agent → web_search  ✅
                             → page_fetch    ✅
                → lark_doc (写入飞书)        ✅
```

**场景 3 — 四Agent单链**：
```
用户 → reporter → data_agent (3工具)
                → search_agent (2工具)
                → analyzer (data_summarize + chart_gen)
                → lark_doc (综合分析报告) ✅
```

---

## 目录结构

```
MA/
├── agent_sdk/                          # Agent SDK（独立 Python 包）
│   ├── __init__.py                     # 导出: SecureAgentClient, AgentRegistry, PermissionDeniedError
│   ├── secure_agent_client.py          # 安全 Agent 基类（call_agent / call_mcp_tool）
│   ├── signing_utils.py                # Ed25519 签名/验签
│   ├── agent_registry.py               # Agent 注册中心（密钥热注入）
│   ├── setup.py                        # pip install -e .
│   └── requirements.txt
│
├── services/                           # 安全内核微服务（Docker 化）
│   ├── identity-service/               # 身份注册服务 (:8001)
│   │   ├── main.py                     # FastAPI 入口
│   │   ├── crypto.py                   # Ed25519 密钥生成
│   │   ├── models.py                   # Agent/Tool 数据模型
│   │   ├── cert_store.py              # PG 证书存储
│   │   ├── tool_store.py              # PG 工具存储
│   │   ├── cache.py                    # Redis 公钥缓存
│   │   └── Dockerfile
│   │
│   ├── permission-gateway/             # 权限网关 (:8002)
│   │   ├── main.py                     # FastAPI 入口 + 管理 UI
│   │   ├── models.py                   # Token/View/Session 数据模型
│   │   ├── handlers.py                 # API 路由（令牌/视图/审批/调用）
│   │   ├── view_builder.py             # 权限视图构建器（交集模型）
│   │   ├── token_manager.py           # 长期令牌管理
│   │   ├── task_permissions.py        # 临时权限管理
│   │   ├── permission_requests.py     # 审批请求管理
│   │   ├── session_manager.py         # 会话 + Redis 视图缓存
│   │   ├── identity_client.py         # 身份验签客户端
│   │   ├── audit_client.py            # 审计记录客户端
│   │   ├── static/
│   │   │   ├── admin.html             # 管理 UI
│   │   │   └── admin.js               # 管理 UI 逻辑
│   │   └── Dockerfile
│   │
│   ├── audit-service/                  # 审计模块 (:8003)
│   │   ├── main.py                     # FastAPI 入口
│   │   ├── models.py                   # 审计日志模型
│   │   ├── handlers.py                 # 审计 API
│   │   └── Dockerfile
│   │
│   └── execution-layer/               # 执行层配置（业务代码在 feishu-demo-app/）
│
├── feishu-demo-app/                    # 飞书三 Agent 演示项目
│   ├── main.py                         # FastAPI 入口 (:8005)
│   ├── orchestrator.py                 # ReporterAgent（编排器）
│   ├── config.py                       # 配置
│   ├── llm_client.py                   # DeepSeek LLM 客户端
│   ├── worker_agents/
│   │   ├── data_agent.py               # 企业数据 Agent
│   │   └── search_agent.py             # 外部检索 Agent
│   ├── mcp_tools/
│   │   ├── lark_tools.py               # 飞书工具封装（lark-cli）
│   │   └── search_tools.py             # Mock 搜索工具
│   ├── static/
│   │   └── index.html                  # Web UI
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker/
│   └── docker-compose.yml              # Docker Compose 编排
│
├── scripts/
│   ├── batch_register.py               # 批量注册 Agent + Tool
│   ├── agent_tool_manifest_feishu.json  # 飞书演示 Agent/Tool 清单
│   ├── register_agent.py               # 单 Agent 注册脚本
│   └── init_db.sql                     # 数据库初始化
│
├── docs/                               # 设计文档（6 份）
│   ├── project-architecture.md
│   ├── identity-registration-service.md
│   ├── permission-gateway.md
│   ├── audit-module.md
│   ├── feishu-demo-app.md
│   └── role-operations.md
│
├── tests/                              # 单元测试
│   ├── identity_service/
│   ├── permission_gateway/
│   └── audit_service/
│
├── .env                                # 环境变量（不提交）
├── .env.example                        # 环境变量模板
├── .gitignore
├── pyproject.toml
├── 课题.md                              # 赛题描述
├── 开发日志.md                          # 开发日志
└── readme.md                           # 本文件
```

---

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 身份注册服务 (Identity) | `:8001` | Agent 证书生成/颁发/验签 |
| 权限网关 (Gateway) | `:8002` | 令牌管理 + 调用拦截 + 管理 UI |
| 审计模块 (Audit) | `:8003` | 签名记录 + 会话日志 + 调用链 |
| 飞书 Demo App | `:8005` | 飞书四 Agent 演示 (宿主机部署) |
| PostgreSQL | `:5432` | 共享数据库 |
| Redis | `:6379` | 视图缓存 + 指令映射 |

### 安全密钥存储

Agent 私钥由 identity-service 注册时自动推送至 demoapp，
加密持久化到 `agent_sdk/keys.enc`。
管理员全程不接触私钥，进程重启后自动从加密文件恢复。

---

## API 参考

### 身份注册服务 (:8001)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agents/register` | 注册 Agent，返回 agent_id（私钥自动推送 demoapp） |
| POST | `/tools/register` | 注册 MCP Tool |
| GET | `/agents/{agent_id}` | 查询 Agent 信息 |
| GET | `/agents/{agent_id}/public-key` | 获取 Agent 公钥 |
| POST | `/verify` | 验签（服务间调用） |

### 权限网关 (:8002)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tokens` | 创建长期令牌 |
| GET | `/tokens` | 列出令牌 |
| POST | `/tokens/{id}/entries` | 添加令牌条目 |
| DELETE | `/tokens/{id}/entries/{entry_id}` | 删除令牌条目 |
| POST | `/tasks/{task_id}/permissions` | 添加临时权限 |
| POST | `/gateway/call` | **核心**：A2A/MCP 调用入口 |
| POST | `/gateway/finalize` | 结束任务会话 |
| GET | `/views/{agent_id}` | 查看 Agent 权限视图 |
| POST | `/permission-requests` | 申请临时权限 |
| GET | `/permission-requests/pending` | 查看待审批 |
| POST | `/permission-requests/{id}/approve` | 批准 |
| GET | `/admin` | 管理 UI |

### 审计模块 (:8003)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/signature-records` | 写入签名记录 |
| POST | `/session-logs` | 写入会话日志 |
| POST | `/permission-decisions` | 写入权限决策 |
| GET | `/tasks/{task_id}/sessions` | 查询任务会话 |
| GET | `/tasks` | 列出所有任务 |

---

## 设计文档

详细设计见 `docs/` 目录：

- `project-architecture.md` — 项目整体架构
- `identity-registration-service.md` — 身份注册服务设计
- `permission-gateway.md` — 权限网关设计
- `audit-module.md` — 审计模块设计
- `feishu-demo-app.md` — 飞书演示应用设计
- `role-operations.md` — 角色运维操作

