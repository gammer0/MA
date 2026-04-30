# 三角色操作集

## 一、角色定义

| 角色 | 身份标识 | 说明 |
|------|----------|------|
| **系统开发者** | 持有 Docker/服务器权限 | 负责部署、配置、维护系统基础设施和服务运行 |
| **权限管理员** | 持有 `ADMIN_API_KEY` | 负责管理 Agent 身份、工具注册、权限令牌、审批权限申请、审计查询 |
| **用户** | 浏览器访问 Web UI | 通过自然语言下达任务指令，触发多 Agent 协作 |

---

## 二、系统开发者操作集

| 操作 | 涉及模块 | 命令/说明 |
|------|----------|-----------|
| 启动所有服务 | 全部 | `docker compose up -d` |
| 停止所有服务 | 全部 | `docker compose down` |
| 初始化数据库 | PostgreSQL | 容器自动执行 `scripts/init_db.sql` |
| 配置环境变量 | 全部 | 编辑 `.env`（PG 密码、API Keys） |
| 部署 Agent SDK | 执行层 | 将 `agent_sdk/` 分发给各 Agent |
| 查看服务健康 | 全部 | `GET :8001/health`, `:8002/health`, `:8003/health`, `:8004/health` |
| 查看服务日志 | 全部 | `docker compose logs -f [service]` |
| 更新服务 | 全部 | `docker compose pull && docker compose up -d` |
| 备份数据库 | PostgreSQL | `pg_dump > backup.sql` |
| 恢复数据库 | PostgreSQL | `pg_restore < backup.sql` |
| 编写/更新执行层 Agent | 执行层 | 新增或修改 Agent 代码和 Tool 实现 |
| 向管理员移交 Agent-Tool 清单 | 执行层 | 提供当前版本的 Agent 列表和 Tool 列表，供管理员注册 |

### 2.1 Agent-Tool 清单移交

系统开发者部署或更新执行层后，需向权限管理员提供以下格式的清单：

#### Agent 清单

| Agent ID | 类型 | 说明 |
|----------|------|------|
| `orchestrator` | orchestrator | 编排器，调度 Worker Agent |
| `searcher` | worker | 搜索器，负责搜索和获取网页内容 |
| `analyzer` | worker | 分析器，负责数据计算和图表生成 |

#### MCP Tool 清单

| Tool Name | Owner | 说明 |
|-----------|-------|------|
| `file_read` | public | 读取文件（公共池） |
| `file_write` | public | 写入文件（公共池） |
| `web_search` | searcher | 网页搜索（searcher 自有） |
| `page_fetch` | searcher | 获取网页内容（searcher 自有） |
| `calc` | analyzer | 数据计算（analyzer 自有） |
| `chart_gen` | analyzer | 图表生成（analyzer 自有） |

> **自动化注册**：管理员拿到清单后，使用 `scripts/batch_register.py` 一键完成所有 Agent 和 Tool 的注册。
> ```
> python batch_register.py --manifest agent_tool_manifest.json --api-key "xxx" --url http://localhost:8001
> ```
> 注册结果写入 `batch_register_output.json`（含 agent_id 和 private_key_pem）。
> 
> **人工配置**：长期令牌包含 `allow`/`deny` 安全决策，需管理员参考 manifest 中的 `permission_hints` 手动创建。

---

## 三、权限管理员操作集

权限管理员通过 `X-Admin-API-Key` 请求头调用管理接口。

### 3.1 身份管理（身份注册服务 :8001）

| 操作 | 方法 | 接口 | 说明 |
|------|------|------|------|
| 注册 Agent | `POST` | `/agents/register` | 提交 `agent_name`, `agent_type`, `owner` → 返回 `agent_id` + `private_key_pem` |
| 查看 Agent | `GET` | `/agents/{agent_id}` | 查看证书状态、公钥、有效期 |
| 列出所有 Agent | `GET` | `/agents?status=active` | 可按 status 过滤 |
| 吊销 Agent | `POST` | `/agents/{agent_id}/revoke` | 软删除，证书立即失效 |
| 续期 Agent | `POST` | `/agents/{agent_id}/renew` | 生成新密钥对，返回新私钥 |
| 注册 MCP 工具 | `POST` | `/tools/register` | 声明 `tool_name`, `tool_owner`, `description` |
| 查看 MCP 工具 | `GET` | `/tools/{tool_id}` | 查看工具详情 |
| 列出 MCP 工具 | `GET` | `/tools?owner=public` | 按属主过滤 |
| 吊销 MCP 工具 | `POST` | `/tools/{tool_id}/revoke` | 软删除 |
| 批量注册 Agent+Tool | 脚本 | `python batch_register.py --manifest agent_tool_manifest.json` | 一键自动化注册 |

### 3.2 令牌管理（权限网关 :8002）

| 操作 | 方法 | 接口 | 说明 |
|------|------|------|------|
| 创建长期令牌 | `POST` | `/tokens` | 为 Agent 创建 allow/deny 规则集 |
| 查看令牌 | `GET` | `/tokens/{token_id}` | 查看令牌及所有条目 |
| 列出令牌 | `GET` | `/tokens?agent_id=xxx` | 按 Agent 过滤 |
| 吊销令牌 | `DELETE` | `/tokens/{token_id}` | 软删除 |
| 添加条目 | `POST` | `/tokens/{token_id}/entries` | 增加一条权限规则 |
| 查看条目 | `GET` | `/tokens/{token_id}/entries` | 列出所有条目 |
| 删除条目 | `DELETE` | `/tokens/{token_id}/entries/{entry_id}` | 删除单条规则 |
| 手动添加临时权限 | `POST` | `/tasks/{task_id}/permissions` | 直接写入任务临时权限 |

### 3.3 审批管理（权限网关 :8002）

| 操作 | 方法 | 接口 | 说明 |
|------|------|------|------|
| 查看待审批 | `GET` | `/tasks/{task_id}/permission-requests?status=pending_approval` | 列出待处理申请 |
| 查看申请详情 | `GET` | `/tasks/{task_id}/permission-requests/{req_id}` | 审查申请内容 |
| 审批通过 | `POST` | `/tasks/{task_id}/permission-requests/{req_id}/approve` `{"action":"approve",...}` | 可裁剪条目、缩短 TTL |
| 审批拒绝 | `POST` | `/tasks/{task_id}/permission-requests/{req_id}/approve` `{"action":"reject",...}` | 拒绝并记录原因 |

### 3.4 审计查询（审计模块 :8003）

| 操作 | 方法 | 接口 | 说明 |
|------|------|------|------|
| 查看任务调用链 | `GET` | `/audit/tasks/{task_id}/trace` | 树形调用链结构 |
| 查看任务会话 | `GET` | `/audit/tasks/{task_id}/sessions` | 所有会话平铺列表 |
| 查看 Agent 历史 | `GET` | `/audit/agents/{agent_id}/history` | 某 Agent 所有历史行为 |
| 查看权限申请历史 | `GET` | `/audit/tasks/{task_id}/permission-requests` | 审批全链路追溯 |

---

## 四、用户操作集

用户通过浏览器访问执行层 Web UI（`http://localhost:8004`），使用自然语言交互。

| 操作 | 入口 | 说明 |
|------|------|------|
| 打开控制台 | `GET /` | 访问 Web UI 页面 |
| 下达任务指令 | 输入框 → `[执行任务]` → `POST /tasks/execute` | 自然语言描述任务 |
| 查看调用链 | 控制台实时展示 | 树形展示每次调用 |
| 查看审计日志 | 控制台实时展示 | 实时日志流 |
| 查看安全事件 | 控制台实时展示 | deny/申请/放行 告警 |

---

## 五、角色权限矩阵

| 操作域 | 操作 | 开发者 | 管理员 | 用户 |
|--------|------|:---:|:---:|:---:|
| 基础设施 | 启动/停止服务 | ✅ | ❌ | ❌ |
| 基础设施 | 数据库管理 | ✅ | ❌ | ❌ |
| 基础设施 | 环境变量配置 | ✅ | ❌ | ❌ |
| 基础设施 | 查看服务健康 | ✅ | ❌ | ❌ |
| 基础设施 | 查看日志 | ✅ | ❌ | ❌ |
| 执行层 | 编写/更新 Agent 和 Tool | ✅ | ❌ | ❌ |
| 执行层 | 移交 Agent-Tool 清单 | ✅ | ❌ | ❌ |
| 身份管理 | Agent 注册/吊销/续期 | ❌ | ✅ | ❌ |
| 身份管理 | Agent 查看 | ❌ | ✅ | ❌ |
| 身份管理 | MCP 工具注册/吊销 | ❌ | ✅ | ❌ |
| 身份管理 | MCP 工具查看 | ❌ | ✅ | ❌ |
| 权限管理 | 长期令牌 CRUD | ❌ | ✅ | ❌ |
| 权限管理 | 令牌条目增删查 | ❌ | ✅ | ❌ |
| 权限管理 | 临时权限管理 | ❌ | ✅ | ❌ |
| 审批管理 | 查看/审批权限申请 | ❌ | ✅ | ❌ |
| 审计 | 查询调用链/会话/历史 | ❌ | ✅ | ❌ |
| 任务 | 下达任务指令 | ❌ | ❌ | ✅ |
| 任务 | 查看任务状态/结果 | ❌ | ❌ | ✅ |
| 任务 | 查看调用链(实时) | ❌ | ❌ | ✅ |
| 任务 | 查看安全事件 | ❌ | ❌ | ✅ |
