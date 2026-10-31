# Imagen base oficial con soporte de librerías geoespaciales
FROM python:3.12-slim-bookworm

# Evitar generación de bytecode .pyc y habilitar salida de logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5055

# Instalar dependencias del sistema requeridas por GDAL, PROJ, GEOS y curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar requirements primero para optimizar el caché de capas de Docker
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY . /app/

# Exponer el puerto configurado (no por defecto: 5055)
EXPOSE 5055

# Healthcheck para monitorizar la salud del contenedor en el VPS
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Servidor de producción WSGI Gunicorn (3 workers concurrentes)
CMD ["sh", "-c", "gunicorn --workers 3 --bind 0.0.0.0:${PORT} --timeout 120 --access-logfile - app:app"]
