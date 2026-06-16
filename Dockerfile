# Stage 1 — builder
FROM python:3.11-slim AS builder
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --default-timeout=200 -i https://pypi.org/simple/ -r requirements.txt

# Stage 2 — runtime
FROM python:3.11-slim
WORKDIR /app

# copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# copy app code
COPY app/ .
COPY prompts/ ./prompts/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]