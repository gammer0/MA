FROM node:18-slim

# 安装 Python 3 和系统依赖
RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    rm -rf /var/lib/apt/lists/*

# 安装 lark-cli + skills
RUN npm install -g @larksuite/cli && \
    npx skills add larksuite/cli -y -g || true

WORKDIR /app

# Python 依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

EXPOSE 8005

CMD ["python3", "main.py"]
