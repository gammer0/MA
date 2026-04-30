"""管理员注册 Agent 脚本
用法: python register_agent.py --name "agent-name" --type worker --owner "team-a" --api-key "xxx"
"""
import argparse
import requests
import sys


def main():
    parser = argparse.ArgumentParser(description="注册 Agent")
    parser.add_argument("--name", required=True, help="Agent 名称")
    parser.add_argument("--type", required=True, choices=["orchestrator", "worker", "tool-proxy"], help="Agent 类型")
    parser.add_argument("--owner", required=True, help="归属组织")
    parser.add_argument("--api-key", required=True, help="管理 API Key")
    parser.add_argument("--url", default="http://localhost:8001", help="身份注册服务地址")
    args = parser.parse_args()

    response = requests.post(
        f"{args.url}/agents/register",
        json={
            "agent_name": args.name,
            "agent_type": args.type,
            "owner": args.owner,
        },
        headers={"X-Admin-API-Key": args.api_key},
    )

    if response.status_code == 200:
        data = response.json()
        print(f"Agent 注册成功!")
        print(f"  agent_id: {data['agent_id']}")
        print(f"  agent_name: {data['agent_name']}")
        print(f"  agent_type: {data['agent_type']}")
        print(f"\n私钥（请安全保存，仅返回一次）:")
        print(f"{data['private_key_pem']}")
    else:
        print(f"注册失败: {response.status_code} - {response.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
