import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuración base de la aplicación"""
    
    # Clave secreta
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'orion_super_secret_key_2026'
    
    # MongoDB
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/orioon'
    
    # Configuración de uploads - USAR RUTA ABSOLUTA
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    
    # Límite de tamaño de archivo (16MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Extensiones permitidas
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    
    # Configuración de correo
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'orionecommerce8@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'ifpysudjgsgupzim'
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'orionecommerce8@gmail.com'
    
    # Configuración de la tienda
    TIENDA_NOMBRE = 'Orion E-commerce'
    TIENDA_MONEDA = 'MXN'
    
    # Debug mode
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'