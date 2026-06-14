FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY src/ ./src/
COPY scripts/ ./scripts/

# Directorio para la base de datos SQLite
RUN mkdir -p /app/data

EXPOSE 8000

# Variables de entorno con valores por defecto
ENV DATABASE_URL=sqlite:////app/data/world_cup.db \
    SECRET_KEY=change-me-in-production \
    DEBUG=false \
    ADMIN_USERNAME=admin

CMD ["uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
