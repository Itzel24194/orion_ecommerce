# ================================================================
# app/__init__.py - INICIALIZADOR DE LA APLICACIÓN ORION
# ================================================================

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.models.categorias_model import Categoria as CategoriaModel


# ================================================================
# CARGAR VARIABLES DE ENTORNO
# ================================================================

# Busca el archivo .env en la raíz del proyecto,
# un nivel arriba de la carpeta app.
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)


# ================================================================
# INSTANCIAS GLOBALES
# ================================================================

bcrypt = Bcrypt()
mongo = None
mongo_client = None


# ================================================================
# CREAR APLICACIÓN FLASK
# ================================================================

def create_app():
    """Crea y configura la aplicación Flask."""

    global mongo, mongo_client

    base_dir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(
        __name__,
        template_folder="templates"
    )

    # ============================================================
    # CONFIGURACIÓN GENERAL
    # ============================================================

    secret_key = os.environ.get("SECRET_KEY")

    if not secret_key:
        raise RuntimeError(
            "Falta SECRET_KEY en el archivo .env. "
            "Configura una clave segura antes de iniciar ORION."
        )

    app.config["SECRET_KEY"] = secret_key
    app.secret_key = secret_key

    # ============================================================
    # CONFIGURACIÓN DE MONGODB
    # ============================================================

    mongo_uri = os.environ.get("MONGO_URI")
    mongo_dbname = os.environ.get("MONGO_DBNAME", "orioon")

    if not mongo_uri:
        raise RuntimeError(
            "Falta MONGO_URI en el archivo .env. "
            "Configura la conexión a MongoDB Atlas."
        )

    app.config["MONGO_URI"] = mongo_uri
    app.config["MONGO_DBNAME"] = mongo_dbname

    # ============================================================
    # CONFIGURACIÓN DE ARCHIVOS
    # ============================================================

    app.config["UPLOAD_FOLDER"] = os.path.join(
        base_dir,
        "static",
        "uploads"
    )

    os.makedirs(
        app.config["UPLOAD_FOLDER"],
        exist_ok=True
    )

    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # ============================================================
    # CONFIGURACIÓN DE SESIONES
    # ============================================================

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # En producción con HTTPS, configura SESSION_COOKIE_SECURE=True.
    # En desarrollo local con HTTP se mantiene en False.
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SESSION_COOKIE_SECURE", "False").lower()
        in ("true", "1", "yes")
    )

    # ============================================================
    # INICIALIZAR EXTENSIONES
    # ============================================================

    bcrypt.init_app(app)

    # ============================================================
    # CONEXIÓN A MONGODB ATLAS
    # ============================================================

    try:
        mongo_client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            appname="ORION"
        )

        # Verifica que el servidor responda y las credenciales
        # permitan establecer la conexión.
        mongo_client.admin.command("ping")

        mongo = mongo_client[mongo_dbname]
        app.db = mongo

        print(
            f"Conexión a MongoDB exitosa. "
            f"Base de datos: {mongo_dbname}"
        )

    except PyMongoError as e:
        if mongo_client is not None:
            mongo_client.close()

        mongo_client = None
        mongo = None

        raise RuntimeError(
            "No fue posible conectar con MongoDB. "
            "Verifica MONGO_URI, la contraseña, el usuario y "
            "Network Access en MongoDB Atlas."
        ) from e

    # ============================================================
    # FILTRO PERSONALIZADO PARA TEMPLATES
    # ============================================================

    @app.template_filter("get_items")
    def get_items(pedido):
        """
        Obtiene los elementos de un pedido y devuelve una lista.
        Maneja documentos de PyMongo y objetos compatibles.
        """

        if not pedido:
            return []

        # Documento de PyMongo.
        if isinstance(pedido, dict):
            items = pedido.get("items")

            if isinstance(items, list):
                return items

            return []

        # Compatibilidad con objetos que exponen items.
        if hasattr(pedido, "items"):
            try:
                items = getattr(pedido, "items", [])

                if callable(items):
                    items = items()

                return items if isinstance(items, list) else []

            except (TypeError, AttributeError, ValueError):
                return []

        return []

    # ============================================================
    # INYECCIÓN GLOBAL DE CATEGORÍAS
    # ============================================================

    @app.context_processor
    def inject_global_data():
        """Hace disponibles las categorías en las plantillas."""

        try:
            todas = list(CategoriaModel.obtener_todas())

            return {
                "categorias": todas
            }

        except Exception as e:
            app.logger.exception(
                "Error cargando categorías: %s",
                e
            )

            return {
                "categorias": []
            }

    # ============================================================
    # INYECCIÓN GLOBAL DEL AÑO ACTUAL
    # ============================================================

    @app.context_processor
    def inject_current_year():
        """Hace disponible el año actual en las plantillas."""

        return {
            "current_year": datetime.utcnow().year
        }

    # ============================================================
    # REGISTRAR BLUEPRINTS
    # ============================================================

    # Se conserva la ruta de importación original del proyecto.
    from routes import web

    app.register_blueprint(web)

    # ============================================================
    # MANEJADORES DE ERRORES
    # ============================================================

    @app.errorhandler(404)
    def page_not_found(e):
        """Muestra la página de recurso no encontrado."""

        from flask import render_template

        return render_template("errores/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        """Muestra la página de error interno."""

        from flask import render_template

        return render_template("errores/500.html"), 500

    @app.errorhandler(403)
    def forbidden(e):
        """Muestra la página de acceso prohibido."""

        from flask import render_template

        return render_template("errores/403.html"), 403

    # ============================================================
    # FINALIZAR Y DEVOLVER LA APLICACIÓN
    # ============================================================

    return app