"""Agent 注册中心 — 密钥热注入 + 实例管理"""


class AgentRegistry:
    """管理多个 Agent 实例的创建、密钥注入和查询。"""

    def __init__(self, gateway_url: str = ""):
        self._agents: dict = {}
        self._gateway_url = gateway_url

    def register(self, name: str, agent_class, **init_kwargs):
        self._agents[name] = {
            "class": agent_class,
            "init_kwargs": init_kwargs,
            "instance": None,
        }

    def get(self, name: str):
        entry = self._agents.get(name)
        return entry["instance"] if entry else None

    def inject_keys(self, keys: dict):
        for name, entry in self._agents.items():
            key = keys.get(name, {})
            agent_id = key.get("agent_id", "") or entry["init_kwargs"].get("agent_id", name)
            pk = key.get("private_key", "") or entry["init_kwargs"].get("private_key_pem", "")
            if entry["instance"] is None:
                kwargs = dict(entry["init_kwargs"])
                kwargs.update(agent_id=agent_id, private_key_pem=pk, gateway_url=self._gateway_url)
                entry["instance"] = entry["class"](**kwargs)
            else:
                entry["instance"].agent_id = agent_id
                entry["instance"]._private_key = pk

    def all(self) -> dict:
        return {n: e["instance"] for n, e in self._agents.items() if e["instance"]}
