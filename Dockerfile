FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py ./
RUN mkdir -p /app/data /app/state && useradd -r -u 10001 market && chown -R market:market /app
USER market
CMD ["python", "bot.py"]
