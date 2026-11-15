"""Pruebas base del pipeline. Agrega aquí las de auth, productos, carrito y órdenes."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_incluye_version(client):
    assert "version" in client.get("/health").json()


def test_ruta_inexistente(client):
    assert client.get("/ruta-inexistente").status_code == 404


def test_docs_disponible(client):
    assert client.get("/docs").status_code == 200


def test_login_sin_datos_rechazado(client):
    r = client.post("/api/auth/login", json={})
    assert r.status_code in (400, 401, 422)
