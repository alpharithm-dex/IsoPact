FROM python:3.12-slim
WORKDIR /app
COPY services/outcome_gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY src /app/src
COPY services /app/services
ENV PYTHONPATH=/app/src:/app
CMD exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 8 --timeout 120 services.outcome_gateway.main:app
