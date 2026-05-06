"""Agent 注册中心 — 密钥加密本地持久化 + 实例管理。

密钥流：
  注册时 identity-service 推送私钥 → demoapp POST /admin/keys
  → inject_keys() 创建 Agent 实例
  → 同时加密写入本地文件 ~/.agent-secrets/keys.enc
  下次 demoapp 重启
  → AgentRegistry 启动时自动从本地加密文件恢复密钥
  → 创建 Agent 实例，无需重新注册
"""

from pathlib import Path

from .key_store import save_keys, load_keys


class AgentRegistry:
    """管理多个 Agent 实例的密钥持久化、创建和查询。

    密钥加密存储在 ~/.agent-secrets/keys.enc，绑定额外的机器标识。
    """

    def __init__(self, gateway_url: str = "", key_file: str = "", salt_file: str = ""):
        self._agents: dict = {}
        self._gateway_url = gateway_url
        self._key_file = key_file
        self._salt_file = salt_file
        # 启动时尝试从本地加密文件恢复密钥
        self._restore_from_disk()

    def _restore_from_disk(self):
        """启动时从本地加密文件恢复已注册的 Agent 密钥。"""
        if not self._key_file:
            return
        stored = load_keys(self._key_file, self._salt_file)
        if not stored:
            return
        # 对已注册但尚未实例化的 Agent 执行注入
        for name in list(self._agents.keys()):
            self._restore_one_from_disk(name)

    def register(self, name: str, agent_class, **init_kwargs):
        self._agents[name] = {
            "class": agent_class,
            "init_kwargs": init_kwargs,
            "instance": None,
        }
        # 注册后立即尝试从本地加密文件恢复该 Agent 的密钥
        self._restore_one_from_disk(name)

    def _restore_one_from_disk(self, name: str):
        """尝试从本地加密文件恢复单个 Agent 的密钥。"""
        if not self._key_file:
            return
        stored = load_keys(self._key_file, self._salt_file)
        if not stored:
            return
        entry = self._agents.get(name)
        if not entry or entry["instance"] is not None:
            return
        key_data = stored.get(name)
        if key_data:
            agent_id = key_data.get("agent_id", "")
            pk = key_data.get("private_key", "")
            if agent_id and pk:
                kwargs = dict(entry["init_kwargs"])
                kwargs.update(agent_id=agent_id, private_key_pem=pk, gateway_url=self._gateway_url)
                entry["instance"] = entry["class"](**kwargs)

    def get(self, name: str):
        entry = self._agents.get(name)
        return entry["instance"] if entry else None

    def inject_keys(self, keys: dict):
        """注入密钥：创建/更新 Agent 实例 + 加密持久化到本地文件。"""
        changed = False
        for name, entry in self._agents.items():
            key = keys.get(name, {})
            agent_id = key.get("agent_id", "") or entry["init_kwargs"].get("agent_id", name)
            pk = key.get("private_key", "") or entry["init_kwargs"].get("private_key_pem", "")
            if not agent_id or not pk:
                continue
            if entry["instance"] is None:
                kwargs = dict(entry["init_kwargs"])
                kwargs.update(agent_id=agent_id, private_key_pem=pk, gateway_url=self._gateway_url)
                entry["instance"] = entry["class"](**kwargs)
            else:
                entry["instance"].agent_id = agent_id
                entry["instance"]._private_key = pk
            changed = True

        # 密钥有变动则加密持久化到本地文件
        if changed and self._key_file:
            self._persist_to_disk()

    def _persist_to_disk(self):
        """将当前所有已注入的密钥加密写入本地文件。"""
        keys = {}
        for name, entry in self._agents.items():
            inst = entry["instance"]
            if inst:
                keys[name] = {
                    "agent_id": inst.agent_id,
                    "private_key": inst._private_key,
                }
        if keys:
            save_keys(keys, self._key_file, self._salt_file)

    def all(self) -> dict:
        return {n: e["instance"] for n, e in self._agents.items() if e["instance"]}
