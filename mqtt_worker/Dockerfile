FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mqtt_worker.py .
CMD ["python", "mqtt_worker.py"]
