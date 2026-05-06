# Use an official Python runtime as a parent image
FROM docker.m.daocloud.io/library/python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Keep the repository root on PYTHONPATH so imports like
# `from ChatBackend.app import create_app` keep working inside the container.
ENV PYTHONPATH=/app

# Set the working directory to the package root inside the image.
WORKDIR /app/ChatBackend

# Install runtime dependencies including CJK fonts for PDF fallback rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker cache.
COPY ChatBackend/requirements.txt ./requirements.txt

# Upgrade pip first
RUN python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout=600

# Install any needed packages specified in requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout=600

# Copy the backend package plus sibling repo modules it imports at runtime.
COPY ChatBackend /app/ChatBackend
COPY rag_service /app/rag_service
COPY wanxiang_mcp /app/wanxiang_mcp

# Make port 5000 available (Gunicorn will bind to this)
EXPOSE 5000

# Define the command to run Gunicorn
# Adjust the number of workers (-w) based on your server's resources (e.g., 2 * CPU cores + 1)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "-w", "4", "wsgi:app"]
