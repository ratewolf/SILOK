FROM python:3.11-slim

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
