FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt .
RUN pip install -r requirements.txt

COPY bot/ .

CMD ["python", "bot.py"]
