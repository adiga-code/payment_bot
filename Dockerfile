FROM python:3.11-slim

# LibreOffice для конвертации docx → PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
RUN mkdir -p ./documents

WORKDIR /app/bot

CMD ["python", "main.py"]
