FROM python:3.12-slim

# HF_HUB_OFFLINE: the email model loads from the mounted folder only, never the internet.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# libgomp1: OpenMP runtime LightGBM needs
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY routers routers
COPY services services
COPY vendor vendor

RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
# --proxy-headers: nginx passes the visitor's address, so the rate limit is per visitor, not per proxy.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers", "--forwarded-allow-ips", "*"]
