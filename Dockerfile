FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --default-timeout=200 -i https://pypi.org/simple/ -r requirements.txt
COPY app/ .
COPY prompts/ ./prompts/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]