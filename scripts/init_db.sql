-- 数据库初始化 DDL
-- 所有服务的表统一在此定义

-- ============================================================
-- 身份注册服务
-- ============================================================

-- Agent 证书记录
CREATE TABLE IF NOT EXISTS agents (
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

CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner);

-- MCP 工具注册
CREATE TABLE IF NOT EXISTS mcp_tools (
    id              UUID PRIMARY KEY,
    tool_name       VARCHAR(255) NOT NULL,
    tool_owner      VARCHAR(255) NOT NULL,   -- 'public' 或 agent_id
    description     TEXT DEFAULT '',
    tool_schema     JSONB DEFAULT '{}',
    status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'revoked'
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tools_owner ON mcp_tools(tool_owner);
CREATE INDEX IF NOT EXISTS idx_tools_status ON mcp_tools(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tools_owner_name 
    ON mcp_tools(tool_owner, tool_name) WHERE status = 'active';

-- ============================================================
-- 权限网关
-- ============================================================

-- 长期令牌
CREATE TABLE IF NOT EXISTS standard_tokens (
    id              UUID PRIMARY KEY,
    agent_id        UUID NOT NULL,
    label           VARCHAR(255) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_st_agent ON standard_tokens(agent_id, status);

-- 长期令牌条目
CREATE TABLE IF NOT EXISTS standard_token_entries (
    id              UUID PRIMARY KEY,
    token_id        UUID NOT NULL REFERENCES standard_tokens(id) ON DELETE CASCADE,
    effect          VARCHAR(10) NOT NULL,        -- 'allow' | 'deny'
    object_type     VARCHAR(20) NOT NULL,        -- 'agent' | 'mcp_tool'
    object_id       VARCHAR(255) NOT NULL,       -- 目标 ID，支持 '*'
    tool_owner      VARCHAR(255) NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ste_token ON standard_token_entries(token_id);

-- 任务临时权限条目
CREATE TABLE IF NOT EXISTS task_permission_entries (
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

CREATE INDEX IF NOT EXISTS idx_tpe_task_agent ON task_permission_entries(task_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_tpe_expires ON task_permission_entries(expires_at);

-- 权限申请
CREATE TABLE IF NOT EXISTS permission_requests (
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

CREATE INDEX IF NOT EXISTS idx_pr_task_status ON permission_requests(task_id, status);

-- 会话
CREATE TABLE IF NOT EXISTS sessions (
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

CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_sessions_caller ON sessions(caller_agent_id);

-- ============================================================
-- 审计模块
-- ============================================================

-- 签名记录
CREATE TABLE IF NOT EXISTS signature_records (
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

CREATE INDEX IF NOT EXISTS idx_sig_task ON signature_records(task_id);
CREATE INDEX IF NOT EXISTS idx_sig_session ON signature_records(session_id);
CREATE INDEX IF NOT EXISTS idx_sig_caller ON signature_records(caller_agent_id);

-- 会话日志
CREATE TABLE IF NOT EXISTS session_logs (
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

CREATE INDEX IF NOT EXISTS idx_sl_task ON session_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_sl_parent ON session_logs(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sl_caller ON session_logs(caller_agent_id);
CREATE INDEX IF NOT EXISTS idx_sl_task_depth ON session_logs(task_id, depth);

-- 权限判定记录
CREATE TABLE IF NOT EXISTS permission_decisions (
    id                UUID PRIMARY KEY,
    session_id        UUID NOT NULL,
    task_id           UUID NOT NULL,
    caller_agent_id   UUID NOT NULL,
    call_type         VARCHAR(10) NOT NULL,
    target_id         VARCHAR(255) NOT NULL,
    tool_owner        VARCHAR(255) NOT NULL DEFAULT '',
    decision          VARCHAR(10) NOT NULL,
    deny_reason       VARCHAR(50),
    matched_entry_id  UUID,
    matched_effect    VARCHAR(10),
    token_view_id     UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pd_session ON permission_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_pd_task ON permission_decisions(task_id);

-- 任务生命周期事件
CREATE TABLE IF NOT EXISTS task_lifecycle_events (
    id              UUID PRIMARY KEY,
    task_id         UUID NOT NULL,
    event_type      VARCHAR(20) NOT NULL,
    triggered_by    UUID NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tle_task ON task_lifecycle_events(task_id);

-- 权限申请审批日志
CREATE TABLE IF NOT EXISTS permission_request_logs (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL,
    request_id        UUID NOT NULL,
    agent_id          UUID NOT NULL,
    event_type        VARCHAR(20) NOT NULL,
    reason            TEXT DEFAULT '',
    requested_entries JSONB NOT NULL DEFAULT '[]',
    approved_entries  JSONB NOT NULL DEFAULT '[]',
    requested_ttl     INT NOT NULL,
    approved_ttl      INT,
    reviewed_by       VARCHAR(255),
    review_comment    TEXT DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prl_task ON permission_request_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_prl_request ON permission_request_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_prl_agent ON permission_request_logs(agent_id);
