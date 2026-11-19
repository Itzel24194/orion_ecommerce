"""Pruebas base del pipeline para la app Flask de ORION."""
import pytest

from app import create_app


@pytest.fixture
def client():
    """Crea una instancia de la app Flask y su test client."""
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    with app.test_client() as client:
        yield client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json["status"] == "ok"


def test_health_incluye_version(client):
    """La ruta /health debe incluir 'status' y 'timestamp'."""
    data = client.get("/health").json
    assert "status" in data
    assert "timestamp" in data


def test_ruta_inexistente(client):
    assert client.get("/ruta-inexistente").status_code == 404


def test_docs_disponible(client):
    """La ruta raíz / debe responder (200 o redirección)."""
    r = client.get("/")
    assert r.status_code in (200, 301, 302, 307, 308)


def test_login_sin_datos_rechazado(client):
    """Un login sin datos debe ser rechazado (400/401/422/302)."""
    r = client.post("/login", json={})
    assert r.status_code in (400, 401, 422, 302)


def test_health_metodo_no_permitido(client):
    """La ruta /health solo acepta GET; POST debe devolver 405."""
    r = client.post("/health")
    assert r.status_code == 405


def test_root_responde(client):
    """La ruta raíz / debe responder (200 o redirección)."""
    r = client.get("/")
    assert r.status_code in (200, 301, 302, 307, 308)


def test_login_datos_invalidos_rechazado(client):
    """Un login con credenciales inválidas debe ser rechazado (400/401/403/422/302)."""
    r = client.post("/login", json={
        "email": "noexiste@example.com",
        "password": "wrongpassword"
    })
    assert r.status_code in (400, 401, 403, 422, 302)