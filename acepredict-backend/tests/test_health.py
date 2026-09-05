"""Vérifie que l'app FastAPI démarre et que /health répond — pas besoin de DB
(SQLite en mémoire est injecté ici uniquement pour permettre l'import de
app.main sans Postgres ; les routes qui touchent réellement la base ne sont
pas exercées par ce test)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
