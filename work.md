你是一个agent安全系统设计工程师

你需要协助我建立一套多agent协作系统安全内核的开发工作

以下是概念层面的架构设计:

    系统由三个服务支撑:身份注册服务，权限网关，审计模块，执行层架构
1. 身份注册服务: 实现agent身份的数字证书生成颁发和注销，用于之后的身份查验，这一部分的核心在于数字证书的储存方式，注册agent所需的最小信息集讨论
2. 权限网关: 以agent为主体，其余agent以及MCP的工具集为客体，进行权限订阅与权限查阅；该网关提供统一的MCP调用与A2A调用处理方法
    令牌机制: 共有三种令牌:禁止令牌【规定agent的非法边界】,长期令牌:agent的固有权限，临时令牌:与任务绑定的权限集，任务结束令牌失效
    令牌视图机制: 令牌视图由禁止令牌，长期令牌，临时令牌的并集，多agent的令牌视图交集组成，与会话绑定，会话结束，视图失效
    会话机制: 一次MCP调用或是A2A调用都算是一次会话，一个任务有多个会话，会话从身份注册开始，由专门的模块发起(并非身份注册模块),到审计模块截止,并将会话计入审计日志;一次会话中会包含各种信息，其中就有令牌视图
3. 执行层架构: 执行层架构内容为实际运行的多agent协作系统，重点是如何在执行层进行调用拦截，实现强行的权限管控；我们需要实现一个模板化的有简单示例的多agent系统，该系统必须同时采用MCP和A2A编排器协作模式
4. 审计模块: 两个功能，一是记录多个任务的多个会话内容，需设计特定日志记录结构，实现同一任务下的调用链建模


数据流:MCP/A2A请求-》身份验证-》权限网关（-》执行层）（-》审计模块） #（）表示可并行



以下是一些注意事项:
1. 项目需严格采用小步推进，功能实现隔离（git分支，提交）的方式推进
2. 项目技术栈: 微服务架构，python工具集
3. 创建工作日志，将项目实际推进工作记录在日志中
4. 严禁随意扩展功能，项目对于过于边界的安全问题，假设不会出现问题，留给外围安全系统，仅作危险预警告知
5. 项目推进多做细节交流，细节到函数功能讨论
6. ...

---

## 修复记录

### 2026-05-01

#### 1. 审批无响应 + 人类可读标签
- **问题**：自动审批模式下新请求不会自动批准；审批面板显示的 agent_id 为 UUID，不易阅读
- **修复**：
  - `admin.js` 中 `refreshPendingRequests()` 在 `auto` 模式下对新请求自动调用 `autoApproveRequest()`
  - 新增 `resolveAgentName()` 和 `resolveEntryLabel()` 将 UUID 映射为 agent 名称
  - 页面加载时预加载 `agents`/`tools` 数组确保标签可解析
  - `missing_entries` 添加 `effect` 字段修复 Pydantic 校验错误

#### 2. 多Agent视图改为前向交集
- **问题**：A2A 调用中 caller 和 callee 的 allow 条目取交集，导致 caller 有权限但 callee 没有对应 agent 条目时被误拒绝
- **修复**：`build_multi_agent_view()` 改为前向交集：
  - caller 的 allow 条目全部保留（不再与 callee 取交集）
  - callee 的 deny 条目合并（callee 仍可拒绝被调用）
  - callee 的 allow 条目不参与判断

#### 3. 人工审批无限循环
- **问题**：审批通过后 SDK 重试使用相同 `session_id`，Redis 缓存命中旧视图（不含新创建的 `TaskPermissionEntry`），导致再次 `permission_required` → 无限循环
- **修复**：SDK `secure_agent_client.py` 重试时生成新的 `session_id` 和 `call_id`，避免命中旧缓存

#### 4. 权限订阅UI重复agent
- **问题**：agent 列表显示了已撤销（revoked）的 agent，导致重复条目
- **修复**：`renderAgentList()` 和 `renderConfigPanel()` 中只显示 `status === 'active'` 的 agent

#### 5. 通配符删除
- **删除**：`_match_entry` 中移除 `"*"` 通配符匹配，仅支持精确匹配

#### 7. Agent 调用意图 (reason)
- **SDK**：`call_agent` / `call_mcp_tool` 新增 `reason=""` 可选参数
- **Gateway**：`GatewayCallRequest` 新增 `reason` 字段，`permission_required` 响应中透传
- **执行层**：orchestrator/searcher/analyzer 所有调用点传入业务 reason
- **审批面板**：`resolveReason` 优先使用 agent 传入的 reason，fallback 到前端生成
- **算法**：`build_multi_agent_view` = caller令牌视图 ∩ callee长期令牌(StandardToken) ∪ callee任务临时权限
- **交集规则**：deny优先，allow需双方都allow，其余隐式拒绝
- **callee 隐式条目**：每个 agent 默认具有 `allow agent: callee_id`（允许任何人调用自己，除非被 deny 覆盖）
- **临时权限 deny 保护**：审批创建临时权限前检查是否被现有deny覆盖
- **自调用禁止**：caller == callee 直接拒绝