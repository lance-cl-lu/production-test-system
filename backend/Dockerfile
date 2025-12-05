# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# 安裝編譯工具
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

COPY . .

# 編譯 PCBA 測試 C 程式
RUN gcc -o /app/pcba_demo /app/pcba_demo.c || true

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# 從 builder 複製依賴
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 複製應用代碼
COPY --from=builder /app .

# 清理不必要的文件
RUN rm -rf requirements.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
