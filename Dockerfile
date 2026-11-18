FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/plex-notify.db TZ=America/Santiago
EXPOSE 8000
# APP_PORT permite cambiar el puerto interno (útil con network_mode: host)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
