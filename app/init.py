# ================================================================
# app/__init__.py
# ================================================================

from flask import Flask
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    app.config['UPLOAD_FOLDER'] = 'static/uploads/'
    app.config['SECRET_KEY'] = 'tu_clave_secreta_aqui'

    # ------------------------------------------------------------
    # CORS: permite que React Native y SPAs (web nueva) consuman la API
    # ------------------------------------------------------------
    CORS(
        app,
        supports_credentials=True,
        origins=[
            # Desarrollo
            "http://localhost:3000",       # CRA
            "http://localhost:5173",       # Vite
            "http://localhost:8081",       # Expo Metro
            "http://localhost:19006",      # Expo web
            # Cambia esta IP por la tuya si pruebas en dispositivo físico
            # "http://192.168.1.100:19006",
            # Producción (agrega las tuyas)
            # "https://tudominio.com",
        ],
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    # Blueprint principal (web)
    from app.routes.web import web
    app.register_blueprint(web)

    return app