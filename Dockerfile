FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git build-essential curl less sudo vim ca-certificates openssh-client procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sillok_poc ./sillok_poc
COPY tests ./tests
CMD ["python", "-m", "sillok_poc", "--help"]

# Optional GPU inference image; the default final stage stays CPU/data-only.
FROM base AS gpu
COPY requirements-gpu.txt constraints-gpu.txt ./
RUN pip install --no-cache-dir -r requirements-gpu.txt

FROM base AS cpu
