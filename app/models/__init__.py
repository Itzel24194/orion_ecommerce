# ================================================================
# app/__init__.py - INICIALIZADOR DE LA APLICACIÓN
# ================================================================

import os
from flask import Flask
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from datetime import datetime
from app.models.categorias_model import Categoria as CategoriaModel

# ====== INSTANCIAS GLOBALES ======
bcrypt = Bcrypt()
mongo = None

def create_app():
    """Crea y configura la aplicación Flask"""
    
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Flask(__name__, template_folder='templates')
    
    # ====== CONFIGURACIÓN ======
    app.secret_key = os.environ.get('SECRET_KEY', 'una_clave_muy_secreta_y_larga_2026')
    
    app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    app.config['MONGO_DBNAME'] = os.environ.get('MONGO_DBNAME', 'orioon')
    
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static', 'uploads')
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    # ====== INICIALIZAR EXTENSIONES ======
    bcrypt.init_app(app)
    
    # ====== CONEXIÓN A MONGODB ======
    global mongo
    client = MongoClient(app.config['MONGO_URI'])
    db = client[app.config['MONGO_DBNAME']]
    mongo = db
    app.db = db
    
    print("✅ Conexión a MongoDB exitosa.")
    
    # ====== FILTRO PERSONALIZADO PARA TEMPLATES ======
    @app.template_filter('get_items')
    def get_items(pedido):
        """Obtiene los items de un pedido, manejando si es función o lista"""
        if not pedido:
            return []
        # Si es un diccionario (pymongo)
        if isinstance(pedido, dict):
            items = pedido.get('items')
            if items is None:
                return []
            if isinstance(items, list):
                return items
            return []
        # Si es un objeto (mongoengine) - pero no debería pasar
        if hasattr(pedido, 'items'):
            items = getattr(pedido, 'items', [])
            if callable(items):
                try:
                    return list(items()) if items() else []
                except:
                    return []
            return items if isinstance(items, list) else []
        return []
    
    # ====== INYECCIÓN GLOBAL DE CATEGORÍAS ======
    @app.context_processor
    def inject_global_data():
        try:
            todas = list(CategoriaModel.obtener_todas())
            return dict(categorias=todas)
        except Exception as e:
            print(f"Error cargando categorías: {e}")
            return dict(categorias=[])
    
    # ====== INYECCIÓN GLOBAL DE FECHA ======
    @app.context_processor
    def inject_current_year():
        return dict(current_year=datetime.utcnow().year)
    
    # ====== REGISTRAR BLUEPRINTS ======
    from routes import web
    app.register_blueprint(web)
    
    # ====== MANEJADORES DE ERRORES ======
    @app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('errores/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        from flask import render_template
        return render_template('errores/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('errores/403.html'), 403
    
    return app