# ── knowledge-assistant 容器镜像 ──
# 构建前准备模型缓存（一次性）：
#   mkdir -p .model-cache/hub
#   cp -r ~/.cache/huggingface/hub/* .model-cache/hub/
# 构建：docker build -t knowledge-assistant .
# 运行：docker run -p 8002:8002 -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY knowledge-assistant

FROM python:3.14-slim

WORKDIR /app

# Layer 1: 安装 Python 依赖（走清华镜像）
# 构建参数 TORCH_CPU=1 时先装 CPU 版 torch（省 ~8GB，本机/无GPU服务器用）
# 有 GPU 需要 CUDA 加速时，设 TORCH_CPU=0
ARG TORCH_CPU=1
COPY requirements.txt .
RUN if [ "$TORCH_CPU" = "1" ]; then \
        pip install --no-cache-dir torch \
            --index-url https://download.pytorch.org/whl/cpu \
            --default-timeout=1000; \
    fi && \
    pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt

# Layer 2: 拷项目全部文件
COPY . .

# Layer 3: 模型文件就位 + 清理重复副本
# COPY . . 会把 .model-cache/ 也带进来，搬到 huggingface 标准缓存路径后删掉
RUN mkdir -p /root/.cache/huggingface/hub && \
    cp -r .model-cache/hub/* /root/.cache/huggingface/hub/ 2>/dev/null || true && \
    rm -rf .model-cache

# Layer 4: 环境变量 + 端口 + 启动
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
# DEEPSEEK_API_KEY 不进镜像——运行时通过 -e 或 docker-compose 注入

EXPOSE 8002

CMD ["python", "server.py"]
