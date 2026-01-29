FROM python:3.12

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8080
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["functions-framework", "--source", "api/handler.py", "--target", "handle_whatsapp", "--port", "8080"]
