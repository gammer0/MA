"""批量注册 Agent 和 MCP Tool 脚本

用法: 
    python batch_register.py --manifest agent_tool_manifest.json --api-key "xxx" --url http://localhost:8001

读取开发者提供的 manifest JSON，自动完成所有 Agent 和 Tool 的注册。
私钥由 identity-service 直接推送到 demoapp，不在脚本中落盘。
"""
import argparse
import json
import sys
import requests
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="批量注册 Agent 和 MCP Tool")
    parser.add_argument("--manifest", required=True, help="agent_tool_manifest.json 路径")
    parser.add_argument("--api-key", required=True, help="管理 API Key")
    parser.add_argument("--url", default="http://localhost:8001", help="身份注册服务地址")
    args = parser.parse_args()

    # 读取 manifest
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"📋 读取清单: {manifest['description']} (v{manifest['version']})")
    print(f"   Agent 数量: {len(manifest['agents'])}")
    print(f"   Tool 数量: {len(manifest['tools'])}")
    print()

    agents_ok = 0
    tools_ok = 0
    errors = []

    # ==========================================================
    # 阶段 1：注册 Agent（私钥自动推送 demoapp，不返回给管理员）
    # ==========================================================
    print("=" * 60)
    print("阶段 1/2: 注册 Agent")
    print("=" * 60)

    for agent in manifest["agents"]:
        name = agent["agent_name"]
        try:
            resp = requests.post(
                f"{args.url}/agents/register",
                json={
                    "agent_name": agent["agent_name"],
                    "agent_type": agent["agent_type"],
                    "owner": agent.get("owner", "default"),
                },
                headers={"X-Admin-API-Key": args.api_key},
                timeout=30,
            )
            if resp.status_code == 200:
                agents_ok += 1
                data = resp.json()
                print(f"  ✅ {name} → {data['agent_id']}")
            else:
                msg = f"  ❌ {name}: HTTP {resp.status_code} - {resp.text[:200]}"
                print(msg)
                errors.append({"agent": name, "error": resp.text[:200]})
        except requests.RequestException as e:
            msg = f"  ❌ {name}: 连接失败 - {e}"
            print(msg)
            errors.append({"agent": name, "error": str(e)})

    # ==========================================================
    # 阶段 2：注册 MCP Tool
    # ==========================================================
    print()
    print("=" * 60)
    print("阶段 2/2: 注册 MCP Tool")
    print("=" * 60)

    for tool in manifest["tools"]:
        name = tool["tool_name"]
        owner = tool["tool_owner"]
        try:
            resp = requests.post(
                f"{args.url}/tools/register",
                json={
                    "tool_name": name,
                    "tool_owner": owner,
                    "description": tool.get("description", ""),
                    "tool_schema": tool.get("tool_schema", {}),
                },
                headers={"X-Admin-API-Key": args.api_key},
                timeout=30,
            )
            if resp.status_code == 200:
                tools_ok += 1
                data = resp.json()
                print(f"  ✅ {name} ({owner}) → {data['tool_id']}")
            elif resp.status_code == 409:
                tools_ok += 1
                print(f"  ⚠️ {name} ({owner}): 已存在，跳过")
            else:
                msg = f"  ❌ {name} ({owner}): HTTP {resp.status_code} - {resp.text[:200]}"
                print(msg)
                errors.append({"tool": name, "owner": owner, "error": resp.text[:200]})
        except requests.RequestException as e:
            msg = f"  ❌ {name} ({owner}): 连接失败 - {e}"
            print(msg)
            errors.append({"tool": name, "owner": owner, "error": str(e)})

    # 汇总
    print()
    print("=" * 60)
    print("注册完成")
    print("=" * 60)
    print(f"  Agent: {agents_ok}/{len(manifest['agents'])} 成功")
    print(f"  Tool:  {tools_ok}/{len(manifest['tools'])} 成功")
    if errors:
        print(f"  ❌ 错误: {len(errors)}")
        for e in errors:
            print(f"       {e}")
        sys.exit(1)

    print()
    print("🔐 私钥已由身份注册服务自动推送到 demoapp 并加密持久化到本地文件。")
    print("   管理员全程不接触私钥。")


if __name__ == "__main__":
    main()
