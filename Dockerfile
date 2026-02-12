FROM python:3.12

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8080
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Single worker, single thread – one instance per container.
# Cloud Run scales horizontally by spinning up more container instances.
CMD gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 1 \
    --threads 1 \
    --timeout 120 \
    "functions_framework:create_app(source='api/handler.py', target='handle_request')"
