FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Applique les migrations au démarrage du conteneur avant de lancer l'API
# (utile en prod sur un hébergeur comme Railway/Render qui lance juste
# `docker run` sans commande custom). docker-compose local override cette
# commande pour aussi lancer scripts.seed_demo — voir docker-compose.yml.
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
