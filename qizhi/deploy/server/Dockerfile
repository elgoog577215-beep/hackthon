FROM python:3.14-slim

WORKDIR /src

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    pandoc gcc g++ python3-dev ffmpeg \
    fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# 复制 server 目录下的所有代码
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
