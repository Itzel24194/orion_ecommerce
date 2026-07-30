import os
from flask import Flask
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from flask_mail import Mail
from dotenv import load_dotenv

# 1. Definimos las extensiones vacías (sin inicializar)
class Bcrypt:
    def init_app(self, app):
        app.generate_password_hash = generate_password_hash
        app.check_password_hash = check_password_hash

    @staticmethod
    def generate_password_hash(password, method='pbkdf2:sha256', salt_length=8):
        return generate_password_hash(password, method=method, salt_length=salt_length)

    @staticmethod
    def check_password_hash(pw_hash, password):
        return check_password_hash(pw_hash, password)

bcrypt = Bcrypt()
mail = Mail()

def create_app():
    # Cargar variables de entorno
    load_dotenv()
    
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Flask(__name__, template_folder='templates')
    
    # 2. Configuraciones
    app.secret_key = os.environ.get('SECRET_KEY', 'orion_super_secret_key_2026')
    
    # ✅ CONFIGURACIÓN DE UPLOADS
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
    
    # Asegurar que la carpeta de uploads existe
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f"📁 Carpeta de uploads creada: {upload_folder}")
    
    # Configuración de Correo
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
    
    # 3. Inicialización de MongoDB
    try:
        client = MongoClient("mongodb://localhost:27017/")
        app.db = client["orioon"]
        print("✅ Conexión a MongoDB exitosa.")
    except Exception as e:
        print(f"❌ Error conectando a MongoDB: {e}")
    
    # 4. Inicializamos las extensiones con la app
    bcrypt.init_app(app)
    mail.init_app(app)
    
    # 5. Registramos los Blueprints
    from .routes.web import web
    app.register_blueprint(web)
    
    return app