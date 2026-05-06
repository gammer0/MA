# 飞书 Demo App — 设计文档

## 一、概述

飞书 Demo App 是基于安全内核的飞书三 Agent 演示系统，验证课题要求的两个核心场景：
1. **正常委托** — 飞书文档助手成功委托企业数据 Agent 和外部检索 Agent，生成报告
2. **越权拦截** — 外部检索 Agent 尝试访问飞书企业数据，被 deny 令牌阻止

### 技术栈
| **运行环境**: Python 3.12（宿主机部署）
| **飞书 CLI**: `lark-cli` — 封装为 MCP 工具
- **权限对接**: 复用安全内核 3 服务 (identity-service :8001, permission-gateway :8002, audit-service :8003)
- **Agent SDK**: 内嵌版 (`agent_sdk.py` + `signing_utils.py`)

---

## 二、架构

```
                         ┌──────────────────────────┐
                         │   飞书 Demo App (:8005)    │
                         │                          │
  User (Web UI) ────────▶│  ReporterAgent            │
                         │  (飞书文档助手)            │
                         │    │          │           │
                         │    ▼          ▼           │
                         │  DataAgent   SearchAgent  │
                         │  (企业数据)   (外部检索)    │
                         │    │          │           │
                         │    ▼          ▼           │
                         │  lark-cli    web_search   │
                         │  (飞书API)   (Mock)       │
                         └──────────┬───────────────┘
                                    │
              ┌─────────────────────┼──────────────────┐
              │                     ▼                  │
              │           权限网关 (:8002)              │
              │          拦截 + 令牌视图判定            │
              │                     │                  │
              │        ┌────────────┴──────────┐       │
              │        ▼                       ▼       │
              │  身份注册 (:8001)         审计模块 (:8003)│
              │  验签 + 公钥存储         日志 + 调用链   │
              └─────────────────────────────────────────┘
```

### Agent 清单

| Agent | ID | 角色 | 自有工具 | 可委托 |
|-------|----|------|---------|--------|
| reporter | 飞书文档助手 | orchestrator | lark_doc | data_agent, search_agent |
| data_agent | 企业数据 Agent | worker | lark_base, lark_contact, lark_calendar | 无 |
| search_agent | 外部检索 Agent | worker | web_search, page_fetch | 无 |

### MCP 工具清单

| 工具名 | Owner | 说明 |
|--------|-------|------|
| lark_doc | reporter | 飞书云文档创建/读取 |
| lark_base | data_agent | 飞书多维表格查询 |
| lark_contact | data_agent | 飞书通讯录搜索 |
| lark_calendar | data_agent | 飞书日历日程查询 |
| web_search | search_agent | 公开网页搜索（Mock） |
| page_fetch | search_agent | 网页内容抓取（Mock） |

---

## 三、权限预设

```
reporter:
  allow agent: data_agent
  allow agent: search_agent
  allow mcp_tool: lark_doc

data_agent:
  allow mcp_tool: lark_base
  allow mcp_tool: lark_contact
  allow mcp_tool: lark_calendar
  deny  mcp_tool: web_search        ← 不可做外部搜索

search_agent:
  allow mcp_tool: web_search
  allow mcp_tool: page_fetch
  deny  mcp_tool: lark_base         ← 严禁飞书企业数据
  deny  mcp_tool: lark_contact
  deny  mcp_tool: lark_calendar
```

---

## 四、演示场景

### 场景 1: 正常委托流程

```
User: "查询团队日历和项目进度，结合外部动态，生成周报"

reporter 分析:
  ├── A2A → data_agent: "查询企业数据"         ← 交集通过 ✅
  │   ├── MCP → lark_calendar (data_agent)    ← allow ✅
  │   ├── MCP → lark_base (data_agent)        ← allow ✅
  │   └── MCP → lark_contact (data_agent)     ← allow ✅
  │
  ├── A2A → search_agent: "搜索外部动态"        ← 交集通过 ✅
  │   ├── MCP → web_search (search_agent)     ← allow ✅
  │   └── MCP → page_fetch (search_agent)     ← allow ✅
  │
  └── MCP → lark_doc (reporter): "写飞书报告"  ← allow ✅
```

### 场景 2: 越权拦截

```
search_agent 尝试:
  └── MCP → lark_base (search_agent)           ← deny ❌ 硬拒绝
      → 审计日志: search_agent 越权 - explicitly_denied
```

---

## 五、部署

```bash
# 飞书 demo app 随主 docker-compose 一起启动
docker compose up -d feishu-demo-app

# Web UI
http://localhost:8005

# 管理 UI (配置令牌)
http://localhost:8002/admin
```

### 飞书 CLI 配置（可选）
飞书工具运行需要 `lark-cli` 已安装并配置应用凭证：
```bash
lark-cli config init --new
lark-cli auth login --recommend
```
如未配置，飞书 MCP 工具返回 `{"status": "error", "message": "lark-cli 未安装"}`, 不影响权限流程演示。
