FROM python:3.11-slim

WORKDIR /app

# 安裝編譯工具以編譯 C 程式
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 編譯 PCBA 測試 C 程式
RUN gcc -o /app/pcba_demo /app/pcba_demo.c || true

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
