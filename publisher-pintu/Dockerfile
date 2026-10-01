FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY publisher_pintu.py .

CMD ["python", "-u", "publisher_pintu.py"]
