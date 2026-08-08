import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from flask_mail import Mail
from pymongo import MongoClient

# ================================================================
# CARGAR .env DESDE LA RAÍZ DEL PROYECTO
# ================================================================
BASE_DIR = Path(__file__).parent.parent   # sube dos niveles hasta la raíz
ENV_PATH = BASE_DIR / '.env'
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ================================================================
# EXTENSIONES (definidas vacías)
# ================================================================
mail = Mail()

def create_app():
    app = Flask(__name__, template_folder='templates')

    # ========== CONFIGURACIÓN ==========
    app.secret_key = os.getenv('SECRET_KEY', 'orion_super_secret_key_2026')

    # Uploads
    app.config['UPLOAD_FOLDER'] = str(BASE_DIR / 'app' / 'static' / 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

    # Asegurar carpeta de uploads
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f"📁 Carpeta de uploads creada: {upload_folder}")

    # Configuración de Correo (desde .env)
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

    # Verificar credenciales (opcional)
    if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
        print(f"📧 Correo configurado: {app.config['MAIL_USERNAME']}")
    else:
        print("⚠️  Correo no configurado (faltan MAIL_USERNAME o MAIL_PASSWORD)")

    # ========== MONGODB ==========
    try:
        client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
        app.db = client["orioon"]
        print("✅ Conexión a MongoDB exitosa.")
    except Exception as e:
        print(f"❌ Error conectando a MongoDB: {e}")

    # ========== INICIALIZAR EXTENSIONES ==========
    mail.init_app(app)

    # ========== REGISTRAR BLUEPRINTS ==========
    from .routes.web import web
    app.register_blueprint(web)

    return app