FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY services/outcome_gateway/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && pip install --no-cache-dir -r /app/requirements.txt
COPY src /app/src
COPY services /app/services
COPY scripts /app/scripts
COPY --from=frontend /frontend/dist /app/frontend
COPY artifacts/security/public-keys.json /app/stage11-security/public-keys.json
ENV PYTHONPATH=/app/src:/app
CMD exec gunicorn --bind :${PORT:-8080} --workers 2 --threads 8 --timeout 120 services.outcome_gateway.main:app
