FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8080
ENV PYTHONPATH=/app
EXPOSE 8080

CMD ["functions-framework", "--source", "app/handler.py", "--target", "handle_whatsapp", "--port", "8080"]
