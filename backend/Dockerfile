FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "run.py"]
