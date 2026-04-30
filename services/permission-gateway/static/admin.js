const API = '/admin';
let agents = [], tools = [];
let selectedAgent = null;
let currentTokenId = null;
let currentEntries = {}; // key: "type|id|owner" → "allow"|"deny"|null

async function init() {
  await Promise.all([loadAgents(), loadTools()]);
  renderAgentList();
}

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
      <pre>${buildTokenPreview() || '(空 — 所有调用将被拒绝)}</pre>
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
        headers: {'Content-Type': 'application/json', 'X-Admin-API-Key': prompt('请输入 Admin API Key:')},
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
          headers: {'X-Admin-API-Key': prompt('请输入 Admin API Key:')}
        });
      }
      // 添加新条目
      for (const e of entries) {
        await fetch(`/tokens/${tokenId}/entries`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-Admin-API-Key': prompt('请输入 Admin API Key:')},
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
      headers: {'X-Admin-API-Key': prompt('请输入 Admin API Key:')}
    });
    currentTokenId = null;
    currentEntries = {};
    renderConfigPanel();
    showToast('令牌已吊销', 'success');
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

init();