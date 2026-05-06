# 多场景演示操作指南

## 前置条件

1. Docker 容器已运行：`docker compose up -d`
2. demoapp 已启动：`python -m uvicorn main:app --host 0.0.0.0 --port 8005`
3. 已注册 Agent 和 Tool：`python batch_register.py --manifest agent_tool_manifest_feishu.json --url http://localhost:8001`
4. 管理 UI 打开：http://localhost:8002/admin — 切换到「自动降级」模式

---

## 令牌预设（通过管理 UI 或 API 配置）

| Agent | allow 条目 | deny 条目 |
|-------|-----------|----------|
| reporter | agent:data_agent, agent:search_agent, agent:analyzer, mcp_tool:lark_doc | — |
| data_agent | mcp_tool:lark_calendar, mcp_tool:lark_contact, mcp_tool:lark_base | — |
| search_agent | mcp_tool:web_search, mcp_tool:page_fetch | **mcp_tool:lark_base** |
| analyzer | mcp_tool:data_summarize, mcp_tool:chart_gen | — |

---

## 场景 A：三Agent 正常委托

### 指令

```
查询团队日历和多维表格项目进度，结合外部行业动态，生成周报写入飞书文档
```

### 预期调用链

```
reporter → data_agent [A2A]         ✅
  data_agent → lark_calendar [MCP]   ✅
  data_agent → lark_base [MCP]       ✅
  data_agent → lark_contact [MCP]    ✅
reporter → search_agent [A2A]       ✅
  search_agent → web_search [MCP]    ✅
  search_agent → page_fetch [MCP]    ✅
reporter → lark_doc [MCP]           ✅
```

共 8 次调用，全部通过权限校验。

### 操作步骤

1. 在管理 UI 上传 manifest 并注册
2. 切换到「令牌订阅」Tab，为 reporter/data_agent/search_agent 创建令牌
3. 切换到「自动降级」模式
4. 在 demoapp 页面 (http://localhost:8005) 输入指令
5. 点击「执行任务」

---

## 场景 B：三Agent 越权拦截

### 指令

```
越权拦截演示：查询企业数据，并测试search_agent越权访问飞书多维表格
```

（或 包含 "越权" 关键词的任何指令）

### 预期调用链

```
reporter → data_agent [A2A]         ✅
  data_agent → lark_calendar [MCP]   ✅
  data_agent → lark_base [MCP]       ✅
  data_agent → lark_contact [MCP]    ✅
reporter → search_agent [A2A]       ✅
  search_agent → web_search [MCP]    ✅
  search_agent → page_fetch [MCP]    ✅
  search_agent → lark_base [MCP]     🔴 DENIED（显式拒绝）
reporter → lark_doc [MCP]           ✅
```

共 9 次调用，其中 search_agent→lark_base 被 deny 令牌阻止。

### 操作步骤

1. 确保 search_agent 的令牌有 `deny mcp_tool lark_base data_agent`
2. 在 demoapp 输入含「越权」的指令
3. 执行后查看「安全事件」面板，应显示越权拦截记录
4. 在管理 UI 审计列表中点击任务，查看越权拦截详情

---

## 场景 C：单链四Agent 调用

### 指令

```
四Agent综合分析：查询飞书企业数据，搜索外部公开信息，进行数据分析，生成综合分析报告
```

（或 包含 "四Agent" 或 "分析" 关键词的任何指令）

### 预期调用链

```
reporter → data_agent [A2A]         ✅
  data_agent → lark_calendar [MCP]   ✅
  data_agent → lark_base [MCP]       ✅
  data_agent → lark_contact [MCP]    ✅
reporter → search_agent [A2A]       ✅
  search_agent → web_search [MCP]    ✅
  search_agent → page_fetch [MCP]    ✅
reporter → analyzer [A2A]           ✅
  analyzer → data_summarize [MCP]    ✅
  analyzer → chart_gen [MCP]         ✅
reporter → lark_doc [MCP]           ✅
```

共 12 次调用，四个 Agent 全部参与，验证单链协作。

### 操作步骤

1. 确保 analyzer agent 已注册（manifest v2.0.0）
2. 为 analyzer 创建 allow 令牌：`allow mcp_tool data_summarize analyzer` + `allow mcp_tool chart_gen analyzer`
3. 为 reporter 添加：`allow agent analyzer`
4. 在 demoapp 输入含「四Agent」或「分析」的指令
5. 执行后查看完整调用链（应含 12 步）

---

## 快速验证命令

```bash
# 场景A - 正常委托
curl -X POST http://localhost:8005/tasks/execute -H "Content-Type: application/json" -d "{\"instruction\":\"查询团队日历和多维表格项目进度，结合外部行业动态，生成周报写入飞书文档\"}"

# 场景B - 越权拦截
curl -X POST http://localhost:8005/tasks/execute -H "Content-Type: application/json" -d "{\"instruction\":\"越权拦截演示：查询企业数据，并测试search_agent越权访问飞书多维表格\"}"

# 场景C - 四Agent单链
curl -X POST http://localhost:8005/tasks/execute -H "Content-Type: application/json" -d "{\"instruction\":\"四Agent综合分析：查询数据，搜索公开信息，数据分析，生成报告\"}"
```

## 审计查询

```bash
# 查看所有任务
curl http://localhost:8002/admin/task-list?page=1&page_size=10

# 查看特定任务的完整审计
curl http://localhost:8002/admin/task-audit/<task_id>
```
