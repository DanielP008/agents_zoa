FROM python:3.12

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8080
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV WORKERS=4
EXPOSE 8080

# Use gunicorn with multiple workers for concurrent request handling.
# functions-framework is single-threaded and queues requests.
# --threads 2 gives each worker 2 threads for I/O-bound LLM calls.
CMD gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers ${WORKERS} \
    --threads 2 \
    --timeout 120 \
    "functions_framework:create_app(source='api/handler.py', target='handle_request')"
