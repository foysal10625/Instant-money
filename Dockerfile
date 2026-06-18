FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt .
RUN pip install -r requirements.txt

# Add Flask for dummy health check
RUN pip install flask

COPY bot/ .

# Run both bot and health server
CMD ["python", "start.py"]