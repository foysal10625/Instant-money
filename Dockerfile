FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Flask for health check
RUN pip install flask

COPY . .

CMD ["python", "start.py"]