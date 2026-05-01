const API = '/admin';
let agents = [], tools = [];
let selectedAgent = null;
let currentTokenId = null;
let currentEntries = {};
let adminApiKey = '';
let manifestData = null;

function getApiKey() {
  if (!adminApiKey) {
    adminApiKey = document.getElementById('api-key-input').value || '';
  }
  return adminApiKey;
}

// ============================================================
// Tab 切换
// ============================================================
function switchTab(name) {
  document.querySelectorAll('.nav a[data-tab]').forEach(a => a.classList.remove('active'));
  document.querySelector(`.nav a[data-tab="${name}"]`).classList.add('active');
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'tokens') initTokenTab();
}

// ============================================================
// 批量注册
// ============================================================
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      manifestData = JSON.parse(e.target.result);
      const aCount = manifestData.agents ? manifestData.agents.length : 0;
      const tCount = manifestData.tools ? manifestData.tools.length : 0;
      document.getElementById('register-status').textContent = 
        `✅ 文件已加载: ${aCount} 个 Agent, ${tCount} 个 Tool (v${manifestData.version || '?'})`;
      document.getElementById('btn-register').disabled = false;
      addRegLog('ok', `📁 加载 manifest: ${manifestData.description || '无描述'}`);
    } catch(err) {
      document.getElementById('register-status').textContent = '❌ JSON 解析失败: ' + err.message;
      addRegLog('err', '❌ 文件格式错误');
    }
  };
  reader.readAsText(file);
}

async function batchRegister() {
  if (!manifestData) return;
  const btn = document.getElementById('btn-register');
  btn.disabled = true; btn.textContent = '注册中...';
  document.getElementById('progress').style.width = '20%';
  addRegLog('ok', '🚀 开始注册...');

  const apiKey = getApiKey();
  if (!apiKey) { addRegLog('err', '❌ 请先输入 Admin API Key'); return; }

  const baseUrl = window.location.origin.replace(':8002', ':8001');
  let okA = 0, okT = 0;

  // 注册 Agent
  for (const agent of manifestData.agents || []) {
    try {
      const r = await fetch(baseUrl + '/agents/register', {
        method: 'POST', headers: {'Content-Type':'application/json','X-Admin-API-Key':apiKey},
        body: JSON.stringify({agent_name:agent.agent_name,agent_type:agent.agent_type,owner:agent.owner||'default'})
      });
      if (r.ok) {
        const d = await r.json();
        agent._registered_id = d.agent_id;
        agent._private_key = d.private_key_pem;
        okA++;
        addRegLog('ok', `✅ Agent: ${agent.agent_name} → ${d.agent_id.substring(0,8)}...`);
      } else {
        addRegLog('err', `❌ Agent ${agent.agent_name}: HTTP ${r.status}`);
      }
    } catch(e) { addRegLog('err', `❌ Agent ${agent.agent_name}: ${e.message}`); }
  }
  document.getElementById('progress').style.width = '50%';

  // 注册 Tool
  for (const tool of manifestData.tools || []) {
    try {
      const r = await fetch(baseUrl + '/tools/register', {
        method: 'POST', headers: {'Content-Type':'application/json','X-Admin-API-Key':apiKey},
        body: JSON.stringify({tool_name:tool.tool_name,tool_owner:tool.tool_owner,description:tool.description||''})
      });
      if (r.ok || r.status === 409) { okT++; addRegLog('ok', `✅ Tool: ${tool.tool_name} (${tool.tool_owner})`); }
      else { addRegLog('err', `❌ Tool ${tool.tool_name}: HTTP ${r.status}`); }
    } catch(e) { addRegLog('err', `❌ Tool ${tool.tool_name}: ${e.message}`); }
  }
  document.getElementById('progress').style.width = '80%';

  // 注入凭证到执行层
  const execUrl = window.location.origin.replace(':8002', ':8004');
  const payload = {};
  for (const agent of manifestData.agents || []) {
    if (agent._registered_id && agent._private_key) {
      payload[agent.agent_name] = {agent_id: agent._registered_id, private_key: agent._private_key};
    }
  }
  if (Object.keys(payload).length > 0) {
    try {
      const r = await fetch(execUrl + '/admin/keys', {
        method: 'POST', headers: {'Content-Type':'application/json','X-Admin-API-Key':apiKey},
        body: JSON.stringify(payload)
      });
      if (r.ok) addRegLog('ok', '✅ 凭证已注入执行层 (demo-app)');
      else addRegLog('warn', '⚠️ 凭证注入失败: HTTP ' + r.status);
    } catch(e) { addRegLog('warn', '⚠️ 无法连接执行层: ' + e.message); }
  }
  document.getElementById('progress').style.width = '100%';
  btn.textContent = '注册完成'; 
  addRegLog('ok', `🎉 完成! Agent ${okA}/${manifestData.agents?.length||0}, Tool ${okT}/${manifestData.tools?.length||0}`);
  document.getElementById('register-hint').textContent = '注册完成，切换到「令牌订阅」配置权限';
}

function addRegLog(cls, msg) {
  const el = document.getElementById('register-log');
  el.innerHTML += `<div class="${cls}">${msg}</div>`;
  el.scrollTop = el.scrollHeight;
}

function initTokenTab() {
  if (agents.length === 0) loadAgentsAndTools();
}

async function loadAgentsAndTools() {
  await Promise.all([loadAgents(), loadTools()]);
  renderAgentList();
}

async function init() {
  // 默认显示注册面板，不自动加载令牌数据
}

// init() called at end of file

async function loadAgents() {
  try {
    const res = await fetch(API + '/agents');
    agents = await res.json();
  } catch(e) { agents = []; }
}

async function loadTools() {
  try {
    const res = await fetch(API + '/tools');
    tools = await res.json();
  } catch(e) { tools = []; }
}

function renderAgentList() {
  const el = document.getElementById('agent-list');
  if (!agents.length) { el.innerHTML = '<div class="empty">暂无 Agent</div>'; return; }
  el.innerHTML = agents.map(a => `
    <div class="agent-item" data-id="${a.agent_id}" onclick="selectAgent('${a.agent_id}')">
      <span>🤖</span>
      <div>
        <div>${a.agent_name}</div>
        <div class="badge">${a.agent_type}</div>
      </div>
    </div>
  `).join('');
}

async function selectAgent(agentId) {
  selectedAgent = agents.find(a => a.agent_id === agentId);
  if (!selectedAgent) return;

  // 高亮
  document.querySelectorAll('.agent-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`.agent-item[data-id="${agentId}"]`)?.classList.add('active');

  // 加载该 Agent 的现有令牌条目
  currentEntries = {};
  currentTokenId = null;
  await loadExistingTokens(agentId);

  renderConfigPanel();
}

async function loadExistingTokens(agentId) {
  try {
    const res = await fetch(`/tokens?agent_id=${agentId}`);
    const tokens = await res.json();
    // 找第一个 active 的 standard token
    const activeToken = tokens.find(t => t.status === 'active');
    if (activeToken) {
      currentTokenId = activeToken.token_id;
      activeToken.entries.forEach(e => {
        const key = `${e.object_type}|${e.object_id}|${e.tool_owner}`;
        currentEntries[key] = e.effect;
      });
    }
  } catch(e) {}
}

function renderConfigPanel() {
  const a = selectedAgent;
  // 分组工具（tool_owner 是 agent_name 字符串）
  const publicTools = tools.filter(t => t.tool_owner === 'public');
  const ownTools = tools.filter(t => t.tool_owner === a.agent_name);
  const otherTools = tools.filter(t => t.tool_owner !== 'public' && t.tool_owner !== a.agent_name);
  // 其他 Agent
  const otherAgents = agents.filter(ag => ag.agent_id !== a.agent_id);

  document.getElementById('config-panel').innerHTML = `
    <h2>⚙️ ${a.agent_name} (${a.agent_type})</h2>
    <div class="desc">点击项目切换权限状态：⚪ 未设置 → 🟢 allow → 🔴 deny → ⚪ 未设置</div>

    ${otherAgents.length ? `
    <div class="section">
      <h3>👥 可调用的 Agent</h3>
      <div class="agent-grid">
        ${otherAgents.map(ag => renderAgentTarget(ag)).join('')}
      </div>
    </div>` : ''}

    ${publicTools.length ? `
    <div class="section">
      <h3>🌐 公共 MCP 工具 (public)</h3>
      <div class="tool-grid">
        ${publicTools.map(t => renderToolItem(t)).join('')}
      </div>
    </div>` : ''}

    ${ownTools.length ? `
    <div class="section">
      <h3>🔧 自有 MCP 工具 (${a.agent_id})</h3>
      <div class="tool-grid">
        ${ownTools.map(t => renderToolItem(t)).join('')}
      </div>
    </div>` : ''}

    ${otherTools.length ? `
    <div class="section">
      <h3>🔗 其他 Agent 的 MCP 工具</h3>
      <div class="tool-grid">
        ${otherTools.map(t => renderToolItem(t)).join('')}
      </div>
    </div>` : ''}

    <div class="token-summary">
      <h3>📋 当前令牌配置预览</h3>
      <pre>${buildTokenPreview() || '(未配置 — 所有调用将被拒绝)'}</pre>
    </div>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="saveToken()">💾 保存令牌</button>
      ${currentTokenId ? `<button class="btn btn-danger" onclick="revokeToken()">🗑️ 吊销令牌</button>` : ''}
      <button class="btn btn-secondary" onclick="selectAgent('${a.agent_id}')">🔄 刷新</button>
    </div>
  `;
}

function getState(type, id, owner) {
  const key = `${type}|${id}|${owner}`;
  return currentEntries[key] || null;
}

function renderAgentTarget(ag) {
  const state = getState('agent', ag.agent_id, '');
  let cls = '';
  let icon = '⚪';
  if (state === 'allow') { cls = 'allowed'; icon = '🟢'; }
  if (state === 'deny')  { cls = 'denied'; icon = '🔴'; }
  return `<div class="agent-target-item ${cls}" onclick="toggleEntry('agent','${ag.agent_id}','')">
    <div>🤖</div>
    <div>${ag.agent_name}</div>
    <div style="font-size:11px;color:#8b949e">${icon} ${state||'未设置'}</div>
  </div>`;
}

function renderToolItem(t) {
  const state = getState('mcp_tool', t.tool_name, t.tool_owner);
  let cls = '';
  let icon = '⚪';
  if (state === 'allow') { cls = 'allowed'; icon = '🟢'; }
  if (state === 'deny')  { cls = 'denied'; icon = '🔴'; }
  const ownerLabel = t.tool_owner ==='public' ? '公共' : t.tool_owner;
  return `<div class="tool-item ${cls}" onclick="toggleEntry('mcp_tool','${t.tool_name}','${t.tool_owner}')">
    <div class="icon">${icon}</div>
    <div class="info">
      <div class="name">${t.tool_name}</div>
      <div class="owner">归属: ${ownerLabel}</div>
      <div class="status ${state||''}">${state||'未设置'}</div>
    </div>
  </div>`;
}

function toggleEntry(type, id, owner) {
  const key = `${type}|${id}|${owner}`;
  const current = currentEntries[key];
  if (!current) {
    currentEntries[key] = 'allow';
  } else if (current === 'allow') {
    currentEntries[key] = 'deny';
  } else {
    delete currentEntries[key];
  }
  renderConfigPanel();
}

function buildTokenPreview() {
  const entries = Object.entries(currentEntries).map(([key, effect]) => {
    const [type, id, owner] = key.split('|');
    return `  ${effect === 'allow' ? '✅ allow' : '🚫 deny'}  ${type}: ${id}${owner ? ' (' + owner + ')' : ''}`;
  });
  if (!entries.length) return null;
  return `令牌内容 (${entries.length} 条规则):\n${entries.join('\n')}`;
}

async function saveToken() {
  const a = selectedAgent;
  const entries = Object.entries(currentEntries).map(([key, effect]) => {
    const [object_type, object_id, tool_owner] = key.split('|');
    return { effect, object_type, object_id, tool_owner };
  });

  if (!entries.length) {
    showToast('请至少设置一条权限规则', 'error');
    return;
  }

  try {
    let tokenId = currentTokenId;
    if (!tokenId) {
      // 创建新令牌
      const res = await fetch('/tokens', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Admin-API-Key': getApiKey()},
        body: JSON.stringify({ agent_id: a.agent_id, label: `${a.agent_name} 长期令牌`, entries })
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      tokenId = data.token_id;
      currentTokenId = tokenId;
      showToast('令牌创建成功！', 'success');
    } else {
      // 更新令牌：先删全部条目，再添加
      // 获取当前条目
      const getRes = await fetch(`/tokens/${tokenId}/entries`);
      const existingEntries = await getRes.json();
      // 删除全部
      for (const e of existingEntries) {
        await fetch(`/tokens/${tokenId}/entries/${e.entry_id}`, {
          method: 'DELETE',
          headers: {'X-Admin-API-Key': getApiKey()}
        });
      }
      // 添加新条目
      for (const e of entries) {
        await fetch(`/tokens/${tokenId}/entries`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-Admin-API-Key': getApiKey()},
          body: JSON.stringify(e)
        });
      }
      showToast('令牌更新成功！', 'success');
    }
  } catch(e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function revokeToken() {
  if (!currentTokenId || !confirm('确定吊销此令牌？吊销后该 Agent 将失去所有长期权限。')) return;
  try {
    await fetch(`/tokens/${currentTokenId}`, {
      method: 'DELETE',
      headers: {'X-Admin-API-Key': getApiKey()}
    });
    currentTokenId = null;
    // 保留 currentEntries，点击"保存"时将创建新令牌
    renderConfigPanel();
    showToast('令牌已吊销，点击保存可重新创建', 'success');
  } catch(e) {
    showToast('吊销失败: ' + e.message, 'error');
  }
}

function showToast(msg, type) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ============================================================
// 审批窗口（定时刷新待审批列表）
// ============================================================
let approvalMode = 'manual'; // 'manual' | 'auto'

function setApprovalMode(mode) {
  approvalMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('mode-' + mode).classList.add('active');
  document.getElementById('approval-status').textContent = 
    mode === 'auto' ? '当前模式: 自动批准 [降级]' : '当前模式: 人工审批';
  refreshPendingRequests();
}

let pendingRequestsCache = [];

async function refreshPendingRequests() {
  try {
    const r = await fetch('/admin/pending-requests');
    pendingRequestsCache = await r.json();
    const el = document.getElementById('pending-list');
    if (!pendingRequestsCache.length) {
      el.innerHTML = '<div class="empty">暂无待审批请求</div>';
      return;
    }
    el.innerHTML = pendingRequestsCache.map(req => `
      <div class="pending-item" id="req-${req.request_id}">
        <div class="pending-header">
          <span>🔔 ${req.agent_id.substring(0,8)}...</span>
          <span class="pending-time">${new Date(req.created_at).toLocaleTimeString()}</span>
        </div>
        <div class="pending-reason">📝 ${req.reason || '无理由'}</div>
        <div class="pending-entries">请求权限: ${req.requested_entries.map(e => e.object_id + '(' + e.tool_owner + ')').join(', ')}</div>
        <div class="btn-row" style="margin-top:8px">
          <button class="btn btn-primary btn-sm" onclick="approveRequest('${req.request_id}', '${req.task_id}')">✅ 允许</button>
          <button class="btn btn-danger btn-sm" onclick="rejectRequest('${req.request_id}', '${req.task_id}')">❌ 拒绝</button>
        </div>
      </div>
    `).join('');
  } catch(e) {}
}

async function approveRequest(reqId, taskId) {
  const apiKey = getApiKey();
  if (!apiKey) return;
  // 从缓存中找到请求的 entries
  const cached = pendingRequestsCache.find(r => r.request_id === reqId);
  if (!cached) return;
  const action = approvalMode === 'auto' ? 'auto_approve' : 'approve';
  try {
    const r = await fetch(`/tasks/${taskId}/permission-requests/${reqId}/approve`, {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-Admin-API-Key':apiKey},
      body: JSON.stringify({
        action: action,
        approved_entries: cached.requested_entries || [],
        ttl_seconds: cached.requested_ttl || 300,
        comment: action === 'auto_approve' ? '[降级] 自动批准' : '管理员批准'
      })
    });
    if (r.ok) {
      showToast('已批准' + (action === 'auto_approve' ? ' [降级]' : ''), 'success');
      const el = document.getElementById('req-' + reqId);
      if (el) el.remove();
      pendingRequestsCache = pendingRequestsCache.filter(r => r.request_id !== reqId);
    } else {
      const err = await r.text();
      showToast('操作失败: ' + err.substring(0,100), 'error');
    }
  } catch(e) { showToast('操作失败: ' + e.message, 'error'); }
}

async function rejectRequest(reqId, taskId) {
  const apiKey = getApiKey();
  if (!apiKey) return;
  try {
    const r = await fetch(`/tasks/${taskId}/permission-requests/${reqId}/approve`, {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-Admin-API-Key':apiKey},
      body: JSON.stringify({action:'reject', comment:'管理员拒绝'})
    });
    if (r.ok) {
      showToast('已拒绝', 'error');
      document.getElementById('req-' + reqId).remove();
    }
  } catch(e) { showToast('操作失败: ' + e.message, 'error'); }
}

// 每5秒自动刷新
setInterval(refreshPendingRequests, 5000);

init();