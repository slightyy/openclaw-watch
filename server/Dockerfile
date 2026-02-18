FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY server/main.py .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8080 9000

# 启动命令
CMD ["python", "main.py"]
