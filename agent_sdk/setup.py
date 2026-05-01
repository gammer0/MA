from setuptools import setup, find_packages

setup(
    name="agent-security-sdk",
    version="0.1.0",
    description="Agent Security SDK — Ed25519 签名 + 权限网关交互 + Agent 注册中心",
    packages=find_packages(),
    install_requires=["httpx>=0.27", "pynacl>=1.5"],
    python_requires=">=3.10",
)
