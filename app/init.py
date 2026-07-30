from flask import Flask

def create_app():
    app = Flask(__name__)
    
    app.config['UPLOAD_FOLDER'] = 'static/uploads/'
    app.config['SECRET_KEY'] = 'tu_clave_secreta_aqui'

    # IMPORTANTE: Aquí es donde Pylance busca. 
    # Asegúrate de que esta carpeta "app" sea la que está en la raíz.
    from app.routes.web import web
    app.register_blueprint(web)

    return app