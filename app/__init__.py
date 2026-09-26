import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, session
from flask_mail import Mail
from pymongo import MongoClient
from flask_apscheduler import APScheduler
from flask_babel import Babel, gettext
from datetime import datetime, timedelta

# ================================================================
# CARGAR .env DESDE LA RAÍZ DEL PROYECTO
# ================================================================
BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / '.env'
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ================================================================
# EXTENSIONES (definidas vacías)
# ================================================================
mail = Mail()
scheduler = APScheduler()
babel = Babel()


# ================================================================
# FUNCIÓN AUXILIAR PARA VALIDAR LLAVES DE CONEKTA
# ================================================================
def _conekta_llaves_validas(public_key, private_key):
    """
    Verifica que ambas llaves tengan el formato correcto de Conekta.
    Una llave válida:
      - No está vacía
      - Empieza con 'key_'
      - Tiene al menos 25 caracteres
    """
    def es_valida(k):
        return bool(
            k
            and isinstance(k, str)
            and k.strip().startswith('key_')
            and len(k.strip()) >= 25
        )
    return es_valida(public_key) and es_valida(private_key)


def create_app():
    app = Flask(__name__, template_folder='templates')

    # ========== CONFIGURACIÓN ==========
    app.secret_key = os.getenv('SECRET_KEY', 'orion_super_secret_key_2026')

    # Uploads
    app.config['UPLOAD_FOLDER'] = str(BASE_DIR / 'app' / 'static' / 'uploads')

    # ⭐ MAX_CONTENT_LENGTH ampliado para soportar videos
    app.config['MAX_CONTENT_LENGTH'] = 350 * 1024 * 1024  # 350 MB
    print(f"📦 MAX_CONTENT_LENGTH: {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} MB")

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

    if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
        print(f"📧 Correo configurado: {app.config['MAIL_USERNAME']}")
    else:
        print("⚠️  Correo no configurado (faltan MAIL_USERNAME o MAIL_PASSWORD)")

    # ============================================================
    # ⭐ CONFIGURACIÓN DE CONEKTA (MSI - Meses Sin Intereses)
    # ============================================================
    app.config['CONEKTA_PUBLIC_KEY'] = (os.getenv('CONEKTA_PUBLIC_KEY') or '').strip()
    app.config['CONEKTA_PRIVATE_KEY'] = (os.getenv('CONEKTA_PRIVATE_KEY') or '').strip()

    if _conekta_llaves_validas(
        app.config['CONEKTA_PUBLIC_KEY'],
        app.config['CONEKTA_PRIVATE_KEY']
    ):
        pk = app.config['CONEKTA_PUBLIC_KEY']
        print(f"💳 Conekta configurado (Public Key: {pk[:14]}...{pk[-4:]})")
        print(f"   📏 Longitud total de la public key: {len(pk)} caracteres")
    else:
        print("⚠️  Conekta NO configurado (falta CONEKTA_PUBLIC_KEY o CONEKTA_PRIVATE_KEY en .env)")
        print(f"   CONEKTA_PUBLIC_KEY presente: {bool(app.config['CONEKTA_PUBLIC_KEY'])}")
        print(f"   CONEKTA_PRIVATE_KEY presente: {bool(app.config['CONEKTA_PRIVATE_KEY'])}")

    # ============================================================
    # ⭐⭐⭐ EXPONER CONEKTA COMO VARIABLE GLOBAL DE JINJA
    # ============================================================
    app.jinja_env.globals['CONEKTA_PUBLIC_KEY'] = app.config.get('CONEKTA_PUBLIC_KEY', '')
    app.jinja_env.globals['CONEKTA_PRIVATE_KEY'] = app.config.get('CONEKTA_PRIVATE_KEY', '')
    app.jinja_env.globals['CONEKTA_PUBLIC_KEY_CONFIGURED'] = _conekta_llaves_validas(
        app.config.get('CONEKTA_PUBLIC_KEY', ''),
        app.config.get('CONEKTA_PRIVATE_KEY', '')
    )
    print(f"🌐 CONEKTA_PUBLIC_KEY expuesta como variable global de Jinja")

    # ============================================================
    # ⭐ EXPONER datetime / timedelta A TODOS LOS TEMPLATES
    # ============================================================
    app.jinja_env.globals['timedelta'] = timedelta
    app.jinja_env.globals['datetime'] = datetime
    print("🕐 datetime y timedelta expuestos como globales de Jinja")

    # ============================================================
    # CONFIGURACIÓN DE FLASK-BABEL (idiomas)
    # ============================================================
    app.config['BABEL_DEFAULT_LOCALE'] = 'es'
    app.config['BABEL_DEFAULT_TIMEZONE'] = 'America/Mexico_City'
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = str(BASE_DIR / 'app' / 'translations')
    app.config['LANGUAGES'] = {
        'es': 'Español',
        'en': 'English',
        'pt': 'Português',
        'fr': 'Français',
        'de': 'Deutsch',
        'it': 'Italiano',
        'ja': '日本語',
        'zh': '中文',
    }

    def get_locale():
        if 'idioma' in session:
            return session['idioma'].split('-')[0]
        return request.accept_languages.best_match(
            app.config['LANGUAGES'].keys()
        ) or 'es'

    babel.init_app(app, locale_selector=get_locale)

    # Hacer disponible `_()` en todos los templates
    @app.context_processor
    def inject_babel():
        return dict(
            _=gettext,
            AVAILABLE_LANGUAGES=app.config['LANGUAGES'],
            CURRENT_LANGUAGE=session.get('idioma', 'es').split('-')[0]
        )

    # ============================================================
    # ⭐ INJECTAR CONEKTA EN TODAS LAS PLANTILLAS (context processor)
    # ============================================================
    @app.context_processor
    def inject_conekta():
        pub = app.config.get('CONEKTA_PUBLIC_KEY', '')
        priv = app.config.get('CONEKTA_PRIVATE_KEY', '')
        return dict(
            CONEKTA_PUBLIC_KEY=pub,
            CONEKTA_PRIVATE_KEY=priv,
            CONEKTA_PUBLIC_KEY_CONFIGURED=_conekta_llaves_validas(pub, priv)
        )

    # ============================================================
    # ⭐ INJECTAR CONFIGURACIÓN DE LA TIENDA EN TODAS LAS PLANTILLAS
    # ============================================================
    @app.context_processor
    def inject_configuracion():
        """
        Expone `site_config` a TODAS las plantillas con los datos generales
        de la tienda (nombre, moneda, email, teléfono, dirección).

        Uso en cualquier template:
            {{ site_config.nombre_tienda }}
            {{ site_config.moneda }}
            {{ site_config.email_tienda }}
        """
        defaults = {
            'nombre_tienda': 'ORION System',
            'email_tienda': '',
            'telefono_tienda': '',
            'direccion_tienda': '',
            'moneda': 'MXN',
        }
        try:
            from app.models.configuracion_model import Configuracion
            cfg = Configuracion.obtener_general() or {}
            # Fusionar con defaults para que nunca falte ninguna clave
            return dict(site_config={**defaults, **cfg})
        except Exception:
            # Si el modelo no existe o falla, devolvemos defaults sin romper
            return dict(site_config=defaults)

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

    # ========== SCHEDULER ==========
    def actualizar_productos_por_temporada():
        with app.app_context():
            try:
                from app.models.productos_model import Producto
                Producto.actualizar_estado_segun_temporadas()
                print(f"[{datetime.now()}] ✅ Estados de productos actualizados por temporada")
            except Exception as e:
                print(f"[{datetime.now()}] ❌ Error actualizando productos: {e}")

    if not scheduler.running:
        scheduler.remove_all_jobs()
        scheduler.add_job(
            id='actualizar_temporadas',
            func=actualizar_productos_por_temporada,
            trigger='cron',
            hour=0,
            minute=0
        )
        scheduler.start()
        print("⏰ Scheduler iniciado: actualización automática de productos a las 00:00 horas.")
    else:
        print("⏰ Scheduler ya estaba en ejecución.")

    # ============================================================
    # ⭐ MANEJO DE ERROR 413 (Request Entity Too Large)
    # ============================================================
    @app.errorhandler(413)
    def request_entity_too_large(error):
        from flask import jsonify, request as req
        if req.accept_mimetypes.accept_json and not req.accept_mimetypes.accept_html:
            return jsonify({
                'success': False,
                'message': f'El archivo es demasiado grande. El límite es de '
                           f'{app.config["MAX_CONTENT_LENGTH"] // (1024*1024)} MB en total.'
            }), 413
        return (
            f'<h1>413 - Archivo demasiado grande</h1>'
            f'<p>El tamaño total del formulario supera el límite de '
            f'{app.config["MAX_CONTENT_LENGTH"] // (1024*1024)} MB.</p>'
            f'<p><a href="/admin/productos">Volver al inventario</a></p>',
            413
        )

    # ============================================================
    # ✅ RUTA DE DIAGNÓSTICO i18n
    # ============================================================
    @app.route('/test-i18n')
    def test_i18n():
        from flask_babel import get_locale, gettext
        mo_path = os.path.join(
            app.config['BABEL_TRANSLATION_DIRECTORIES'],
            'en', 'LC_MESSAGES', 'messages.mo'
        )
        return {
            'session_idioma': session.get('idioma', 'NO ESTABLECIDO'),
            'locale_detectado': str(get_locale()),
            'traduccion_MiPerfil': gettext('Mi Perfil'),
            'traduccion_Seguridad': gettext('Seguridad'),
            'carpeta_traducciones': app.config['BABEL_TRANSLATION_DIRECTORIES'],
            'mo_existe': os.path.exists(mo_path),
            'mo_path': mo_path,
        }

    # ============================================================
    # ✅ RUTA DE DIAGNÓSTICO Conekta
    # ============================================================
    @app.route('/test-conekta')
    def test_conekta():
        public_key = (app.config.get('CONEKTA_PUBLIC_KEY') or '').strip()
        private_key = (app.config.get('CONEKTA_PRIVATE_KEY') or '').strip()

        def mask(k):
            if not k:
                return 'NO CONFIGURADA'
            if len(k) < 20:
                return k
            return k[:14] + '...' + k[-4:]

        def es_valida(k):
            return bool(k and k.startswith('key_') and len(k) >= 25)

        valida_public = es_valida(public_key)
        valida_private = es_valida(private_key)
        configurado = valida_public and valida_private

        return {
            'conekta_public_key': mask(public_key),
            'conekta_private_key': mask(private_key),
            'public_valida': valida_public,
            'private_valida': valida_private,
            'longitud_public': len(public_key),
            'longitud_private': len(private_key),
            'configurado': configurado,
            'mensaje': (
                '✅ Conekta está listo para procesar pagos.'
                if configurado else
                '⚠️ Falta una o ambas llaves en el archivo .env.'
            ),
        }

    # ============================================================
    # ⭐⭐⭐ DIAGNÓSTICO — Qué llave recibe el template
    # ============================================================
    @app.route('/test-conekta-template')
    def test_conekta_template():
        from flask import render_template_string
        template_test = """
        <!DOCTYPE html>
        <html>
        <body>
        <h1>🔍 Diagnóstico de Conekta en Templates</h1>
        <table border="1" cellpadding="8" style="border-collapse:collapse;font-family:monospace;">
            <tr><th>Variable</th><th>Valor</th><th>Longitud</th></tr>
            <tr>
                <td><code>CONEKTA_PUBLIC_KEY</code></td>
                <td><code>{{ CONEKTA_PUBLIC_KEY }}</code></td>
                <td>{{ CONEKTA_PUBLIC_KEY|length if CONEKTA_PUBLIC_KEY else 0 }}</td>
            </tr>
            <tr>
                <td><code>config.CONEKTA_PUBLIC_KEY</code></td>
                <td><code>{{ config.CONEKTA_PUBLIC_KEY }}</code></td>
                <td>{{ config.CONEKTA_PUBLIC_KEY|length if config.CONEKTA_PUBLIC_KEY else 0 }}</td>
            </tr>
            <tr>
                <td><code>CONEKTA_PUBLIC_KEY_CONFIGURED</code></td>
                <td><code>{{ CONEKTA_PUBLIC_KEY_CONFIGURED }}</code></td>
                <td>—</td>
            </tr>
        </table>
        <h2>Según el servidor (Python):</h2>
        <ul>
            <li><code>app.config['CONEKTA_PUBLIC_KEY']</code>: {{ pk_python }}</li>
            <li>Longitud en Python: {{ pk_len }}</li>
        </ul>
        <p style="color:#dc2626;"><b>⚠️ Si las 3 primeras filas están vacías pero "Según el servidor" tiene valor → el problema es la caché del navegador o que esta ruta es la del servidor, y el HTML lo tiene el navegador.</b></p>
        <p style="color:#16a34a;"><b>✅ Si las 3 primeras filas tienen la llave → todo OK. El problema es caché del navegador en el carrito.</b></p>
        </body>
        </html>
        """
        pk = app.config.get('CONEKTA_PUBLIC_KEY', '')
        return render_template_string(
            template_test,
            pk_python=pk[:14] + '...' + pk[-4:] if len(pk) > 20 else (pk or 'VACÍO'),
            pk_len=len(pk)
        )

    # ============================================================
    # ⭐⭐⭐ DIAGNÓSTICO — Línea HTML del carrito
    # ============================================================
    @app.route('/test-carrito-html')
    def test_carrito_html():
        from flask import render_template_string
        template_check = """
        <!DOCTYPE html>
        <html>
        <head><title>Check HTML</title></head>
        <body>
        <h1>🔍 Línea exacta que recibiría Conekta.setPublicKey</h1>
        <p>Si abres el carrito y ves el mismo texto, todo OK:</p>
        <pre style="background:#f0f0f0;padding:15px;font-family:monospace;font-size:14px;">Conekta.setPublicKey("{{ CONEKTA_PUBLIC_KEY }}");</pre>
        <p><b>Longitud de la llave inyectada:</b> {{ CONEKTA_PUBLIC_KEY|length }}</p>

        <h2>Comparación:</h2>
        <ul>
            <li>Valor de <code>CONEKTA_PUBLIC_KEY</code> (jinja): <code>{{ CONEKTA_PUBLIC_KEY }}</code></li>
            <li>Valor de <code>config.CONEKTA_PUBLIC_KEY</code>: <code>{{ config.CONEKTA_PUBLIC_KEY }}</code></li>
        </ul>

        {% if CONEKTA_PUBLIC_KEY %}
            <p style="color:green;font-size:20px;">✅ La llave LLEGA al template. Todo OK.</p>
            <p>➡️ Si en el carrito aún ves "vacío", presiona <b>Ctrl+Shift+R</b> para recargar sin caché.</p>
        {% else %}
            <p style="color:red;font-size:20px;">❌ La llave NO llega al template. Problema real.</p>
            <p>➡️ Reinicia el servidor (Ctrl+C, python run.py) e inténtalo de nuevo.</p>
        {% endif %}
        </body>
        </html>
        """
        return render_template_string(template_check)

    # ============================================================
    # ⭐⭐⭐ DIAGNÓSTICO — Configuración de la tienda
    # ============================================================
    @app.route('/test-configuracion')
    def test_configuracion():
        from flask import render_template_string
        template_cfg = """
        <!DOCTYPE html>
        <html>
        <head><title>Config check</title></head>
        <body style="font-family:monospace;padding:20px;">
        <h1>🔍 Diagnóstico del módulo de Configuración</h1>

        <h2>1. ¿Existe el modelo?</h2>
        <p>{{ modelo_ok }}</p>

        <h2>2. Valores en `site_config` (context processor global)</h2>
        <table border="1" cellpadding="8" style="border-collapse:collapse;">
            <tr><th>Clave</th><th>Valor</th></tr>
            <tr><td>nombre_tienda</td><td>{{ site_config.nombre_tienda }}</td></tr>
            <tr><td>email_tienda</td><td>{{ site_config.email_tienda }}</td></tr>
            <tr><td>telefono_tienda</td><td>{{ site_config.telefono_tienda }}</td></tr>
            <tr><td>direccion_tienda</td><td>{{ site_config.direccion_tienda }}</td></tr>
            <tr><td>moneda</td><td>{{ site_config.moneda }}</td></tr>
        </table>

        <h2>3. Documento crudo en la BD (colección `configuracion`, _id='general')</h2>
        <pre>{{ doc_raw }}</pre>

        <p style="color:#16a34a;margin-top:20px;">
            ✅ Si los valores se ven bien aquí, `{{ '{{ site_config.nombre_tienda }}' }}`
            funcionará en cualquier template.
        </p>
        </body>
        </html>
        """
        modelo_ok = "❌ NO se pudo importar Configuracion"
        doc_raw = "—"
        try:
            from app.models.configuracion_model import Configuracion
            modelo_ok = "✅ Modelo importado correctamente"
            doc = Configuracion.obtener_general()
            import json
            doc_raw = json.dumps(doc, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            doc_raw = f"Error: {e}"
        return render_template_string(template_cfg, modelo_ok=modelo_ok, doc_raw=doc_raw)

    # ============================================================
    # ✅ RETURN FINAL (con indentación correcta)
    # ============================================================
    return app