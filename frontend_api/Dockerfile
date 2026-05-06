FROM docker.m.daocloud.io/library/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY frontend_api/requirements.txt /tmp/frontend_api-requirements.txt
COPY wanxiang_mcp/requirements.txt /tmp/wanxiang_mcp-requirements.txt
COPY ChatBackend/requirements.txt /tmp/chatbackend-requirements.txt

RUN python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout=600 \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout=600 \
    -r /tmp/frontend_api-requirements.txt \
    -r /tmp/wanxiang_mcp-requirements.txt \
    -r /tmp/chatbackend-requirements.txt

COPY frontend_api /app/frontend_api
COPY wanxiang_mcp /app/wanxiang_mcp
COPY ChatBackend /app/ChatBackend
COPY rag_service /app/rag_service

EXPOSE 8001

CMD ["uvicorn", "frontend_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
