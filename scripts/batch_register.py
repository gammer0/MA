"""批量注册 Agent 和 MCP Tool 脚本

用法: 
    python batch_register.py --manifest agent_tool_manifest.json --api-key "xxx" --url http://localhost:8001

读取开发者提供的 manifest JSON，自动完成所有 Agent 和 Tool 的注册。
注册结果写入 batch_register_output.json（含 agent_id 和 private_key_pem）。
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
    parser.add_argument("--output", default="batch_register_output.json", help="输出文件路径")
    args = parser.parse_args()

    # 读取 manifest
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"📋 读取清单: {manifest['description']} (v{manifest['version']})")
    print(f"   Agent 数量: {len(manifest['agents'])}")
    print(f"   Tool 数量: {len(manifest['tools'])}")
    print()

    results = {"agents": [], "tools": [], "errors": []}

    # ==========================================================
    # 阶段 1：注册 Agent
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
                data = resp.json()
                results["agents"].append({
                    "agent_name": name,
                    "agent_id": data["agent_id"],
                    "agent_type": data["agent_type"],
                    "private_key_pem": data["private_key_pem"],
                })
                print(f"  ✅ {name} → {data['agent_id']}")
            else:
                msg = f"  ❌ {name}: HTTP {resp.status_code} - {resp.text[:200]}"
                print(msg)
                results["errors"].append({"agent": name, "error": resp.text[:200]})
        except requests.RequestException as e:
            msg = f"  ❌ {name}: 连接失败 - {e}"
            print(msg)
            results["errors"].append({"agent": name, "error": str(e)})

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
                data = resp.json()
                results["tools"].append({
                    "tool_name": name,
                    "tool_owner": owner,
                    "tool_id": data["tool_id"],
                })
                print(f"  ✅ {name} ({owner}) → {data['tool_id']}")
            elif resp.status_code == 409:
                print(f"  ⚠️ {name} ({owner}): 已存在，跳过")
            else:
                msg = f"  ❌ {name} ({owner}): HTTP {resp.status_code} - {resp.text[:200]}"
                print(msg)
                results["errors"].append({"tool": name, "owner": owner, "error": resp.text[:200]})
        except requests.RequestException as e:
            msg = f"  ❌ {name} ({owner}): 连接失败 - {e}"
            print(msg)
            results["errors"].append({"tool": name, "owner": owner, "error": str(e)})

    # 写入结果文件
    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    # 汇总
    print()
    print("=" * 60)
    print("注册完成")
    print("=" * 60)
    print(f"  Agent: {len(results['agents'])}/{len(manifest['agents'])} 成功")
    print(f"  Tool:  {len(results['tools'])}/{len(manifest['tools'])} 成功")
    if results["errors"]:
        print(f"  ❌ 错误: {len(results['errors'])}")
        for e in results["errors"]:
            print(f"       {e}")
    print(f"\n📄 详细结果已写入: {output_path}")
    print(f"\n🔐 私钥已在 {output_path} 中，请安全保存后从文件中移除私钥！")

    # ==========================================================
    # 直接注入到执行层(demo-app) — 不经过文件落盘
    # ==========================================================
    if results["agents"] and not results["errors"]:
        exec_url = args.url.replace("8001", "8004")  # demo-app 端口
        payload = {}
        for agent in results["agents"]:
            name = agent["agent_name"]
            payload[name] = {
                "agent_id": agent["agent_id"],
                "private_key": agent["private_key_pem"],
            }
        try:
            resp = requests.post(
                f"{exec_url}/admin/keys",
                json=payload,
                headers={"X-Admin-API-Key": args.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"\n✅ 凭证已直接注入执行层: {exec_url}")
                print(f"   无需中间文件传递私钥")
            else:
                print(f"\n⚠️ 凭证注入执行层失败: HTTP {resp.status_code}")
        except requests.RequestException:
            print(f"\n⚠️ 无法连接执行层 {exec_url}（可能未启动），私钥仍写入文件")

        # 同时注入到飞书 demo app (:8005)
        feishu_url = args.url.replace("8001", "8005")
        try:
            resp = requests.post(
                f"{feishu_url}/admin/keys",
                json=payload,
                headers={"X-Admin-API-Key": args.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"✅ 凭证已直接注入飞书执行层: {feishu_url}")
            else:
                print(f"⚠️ 凭证注入飞书执行层失败: HTTP {resp.status_code}")
        except requests.RequestException:
            print(f"⚠️ 无法连接飞书执行层 {feishu_url}（可能未启动）")

    if results["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
