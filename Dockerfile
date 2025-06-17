FROM python:3.8-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
