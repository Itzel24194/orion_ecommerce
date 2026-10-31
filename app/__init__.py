# app/__init__.py
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, session, jsonify, send_from_directory
from flask_mail import Mail
from pymongo import MongoClient
from flask_apscheduler import APScheduler
from flask_babel import Babel, gettext
from datetime import datetime, timedelta
from bson import ObjectId # ⭐ Añadido para buscar por ID

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
# ⭐ CONFIG SANDBOX (sin pasarela externa)
# ================================================================
SANDBOX_MODE = True
CONEKTA_MSI_PLAZOS = [3, 6, 9, 12, 18, 24]  # plazos MSI permitidos en sandbox
PAYMENT_GATEWAY = 'sandbox'                  # 'sandbox' | 'stripe' | 'mercadopago' | ...


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

    # ============================================================
    # ⭐⭐⭐ RUTA EXPLÍCITA PARA SERVIR /static/uploads/
    # (Necesario cuando Express y Flask comparten la misma carpeta)
    # ============================================================
    @app.route('/static/uploads/<path:filename>')
    def serve_upload(filename):
        return send_from_directory(
            os.path.join(app.root_path, 'static', 'uploads'),
            filename
        )

    print("✅ Ruta explícita /static/uploads/<filename> registrada")

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
    # ⭐ CONFIG SANDBOX (reemplaza la config de Conekta)
    # ============================================================
    app.config['SANDBOX_MODE'] = SANDBOX_MODE
    app.config['CONEKTA_MSI_PLAZOS'] = CONEKTA_MSI_PLAZOS
    app.config['PAYMENT_GATEWAY'] = PAYMENT_GATEWAY

    print(f"🧪 Modo SANDBOX activo: {app.config['SANDBOX_MODE']}")
    print(f"💳 Plazos MSI disponibles: {app.config['CONEKTA_MSI_PLAZOS']}")
    print(f"🔌 Pasarela: {app.config['PAYMENT_GATEWAY']} (no se llama a ninguna API externa)")

    # ============================================================
    # ⭐ EXPONER SANDBOX Y MSI COMO VARIABLES GLOBALES DE JINJA
    # ============================================================
    app.jinja_env.globals['SANDBOX_MODE'] = app.config['SANDBOX_MODE']
    app.jinja_env.globals['MSI_PLAZOS'] = app.config['CONEKTA_MSI_PLAZOS']
    app.jinja_env.globals['PAYMENT_GATEWAY'] = app.config['PAYMENT_GATEWAY']
    print(f"🌐 SANDBOX_MODE y MSI_PLAZOS expuestos como variables globales de Jinja")

    # ============================================================
    # ⭐ EXPONER datetime / timedelta A TODOS LOS TEMPLATES
    # ============================================================
    app.jinja_env.globals['timedelta'] = timedelta
    app.jinja_env.globals['datetime'] = datetime
    print("🕐 datetime y timedelta expuestos como globales de Jinja")

    # ============================================================
    # ⭐⭐⭐ FILTROS JINJA PARA FOTOS / VIDEOS (base64 y URLs)
    # ============================================================
    from flask import url_for as _url_for
    import os as _os

    def _foto_src(foto):
        if not foto:
            return ''
        s = str(foto).strip()
        if not s:
            return ''

        # 1. Si ya es una URL completa o base64, devolverla tal cual
        if s.startswith(('data:', 'http://', 'https://', 'blob:')):
            return s

        # 2. Si ya incluye /static/ o static/, devolverla corregida
        if s.startswith('/static/'):
            return s
        if s.startswith('static/'):
            return '/' + s

        # 3. ⭐ Detectar la carpeta REAL del archivo en disco
        #    - Fotos de perfil → app/static/uploads/<archivo>
        #    - Fotos de producto → app/static/uploads/productos/<archivo>
        #    Se comprueba si existe en cada carpeta para no adivinar por prefijo.
        try:
            uploads_dir = _os.path.join(app.static_folder, 'uploads')
            productos_dir = _os.path.join(uploads_dir, 'productos')

            # 3a. ¿Existe en uploads/ (foto de perfil)?
            if _os.path.isfile(_os.path.join(uploads_dir, s)):
                return _url_for('static', filename='uploads/' + s)

            # 3b. ¿Existe en uploads/productos/ (foto de producto)?
            if _os.path.isfile(_os.path.join(productos_dir, s)):
                return _url_for('static', filename='uploads/productos/' + s)
        except Exception:
            pass

        # 4. Fallback: si no se pudo comprobar en disco, mantener
        #    la heurística por prefijo (fotos de perfil nuevas).
        if s.startswith('u') or s.startswith('user_'):
            return _url_for('static', filename='uploads/' + s)
        return _url_for('static', filename='uploads/productos/' + s)

    # Registrar como FILTRO (permite: {{ foto | foto_src }})
    app.add_template_filter(_foto_src, name='foto_src')
    app.add_template_filter(_foto_src, name='video_src')

    # ⭐ Registrar como FUNCIÓN GLOBAL (permite: {{ foto_src(foto) }})
    app.jinja_env.globals['foto_src'] = _foto_src
    app.jinja_env.globals['video_src'] = _foto_src

    print("🖼️  Filtros y globales Jinja registrados: foto_src, video_src")

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
    # ⭐ INJECTAR SANDBOX EN TODAS LAS PLANTILLAS
    # ============================================================
    @app.context_processor
    def inject_sandbox():
        return dict(
            SANDBOX_MODE=app.config.get('SANDBOX_MODE', True),
            MSI_PLAZOS=app.config.get('CONEKTA_MSI_PLAZOS', []),
            PAYMENT_GATEWAY=app.config.get('PAYMENT_GATEWAY', 'sandbox'),
        )

    # ============================================================
    # ⭐ INJECTAR CONFIGURACIÓN DE LA TIENDA
    # ============================================================
    @app.context_processor
    def inject_configuracion():
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
            return dict(site_config={**defaults, **cfg})
        except Exception:
            return dict(site_config=defaults)

    # ========== MONGODB ==========
    try:
        client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
        app.db = client["orioon"]
        print("✅ Conexión a MongoDB exitosa.")
    except Exception as e:
        print(f"❌ Error conectando a MongoDB: {e}")

    # ============================================================
    # ⭐⭐⭐ INYECTAR FOTO FRESCA DE LA BD PARA EL NAVBAR
    # ============================================================
    @app.context_processor
    def inject_user_foto():
        """Asegura que el navbar siempre use la foto más reciente de la BD, no la sesión."""
        if 'user_id' in session:
            try:
                # Buscar el ID del usuario en la sesión
                raw_uid = session.get('user_id')

                # Manejar si el ID guardado es string o ObjectId
                query_id = ObjectId(raw_uid) if ObjectId.is_valid(raw_uid) else raw_uid

                user = app.db.usuarios.find_one({'_id': query_id}, {'foto': 1})
                if user:
                    return dict(current_user_foto=user.get('foto'))
            except Exception as e:
                print(f"⚠️ Error obteniendo foto fresca de BD en navbar: {e}")
        return dict(current_user_foto=None)

    # ========== INICIALIZAR EXTENSIONES ==========
    mail.init_app(app)

    # ========== REGISTRAR BLUEPRINTS ==========
    from .routes.web import web

    try:
        from .controllers import resenas_controller  # noqa: F401
        print("✅ Controlador de reseñas importado (rutas registradas en blueprint 'web')")
    except Exception as e:
        print(f"⚠️ No se pudo importar resenas_controller: {e}")

    app.register_blueprint(web)

    # ============================================================
    # ⭐⭐⭐ REGISTRAR RUTAS DE LA API PARA LA APP MÓVIL
    # ============================================================
    from .controllers import cuenta_controller

    # API: Subir foto de perfil (base64)
    @app.route('/api/v1/cuenta/foto', methods=['POST'])
    def subir_foto_api():
        return cuenta_controller.api_subir_foto()

    print("✅ Rutas de API de la cuenta registradas (incluyendo subida de foto)")

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
    # ⭐ MANEJO DE ERROR 413
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
    # ⭐ NUEVO: MANEJO DE ERROR 500 EN JSON (útil para la app móvil)
    # ============================================================
    @app.errorhandler(500)
    def internal_error(error):
        from flask import jsonify, request as req
        if req.accept_mimetypes.accept_json and not req.accept_mimetypes.accept_html:
            return jsonify({
                'success': False,
                'message': 'Error interno del servidor',
                'error': str(error),
            }), 500
        return render_template_500()

    def render_template_500():
        try:
            return app.jinja_env.get_template('errores/500.html').render(), 500
        except Exception:
            return '<h1>500 - Error interno</h1>', 500

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
    # ✅ RUTA DE DIAGNÓSTICO SANDBOX
    # ============================================================
    @app.route('/test-sandbox')
    def test_sandbox():
        return {
            'sandbox_mode': app.config.get('SANDBOX_MODE', True),
            'payment_gateway': app.config.get('PAYMENT_GATEWAY', 'sandbox'),
            'msi_plazos': app.config.get('CONEKTA_MSI_PLAZOS', []),
            'mensaje': (
                '✅ Modo SANDBOX activo. Los pagos se simulan localmente, '
                'sin llamar a ninguna pasarela externa.'
            ),
        }

    # ============================================================
    # ⭐⭐⭐ DIAGNÓSTICO — Qué recibe el template (SANDBOX)
    # ============================================================
    @app.route('/test-sandbox-template')
    def test_sandbox_template():
        from flask import render_template_string
        template_test = """
        <!DOCTYPE html>
        <html>
        <body style="font-family:monospace;padding:20px;">
        <h1>🔍 Diagnóstico de SANDBOX en Templates</h1>
        <table border="1" cellpadding="8" style="border-collapse:collapse;">
            <tr><th>Variable</th><th>Valor</th></tr>
            <tr>
                <td><code>SANDBOX_MODE</code></td>
                <td><code>{{ SANDBOX_MODE }}</code></td>
            </tr>
            <tr>
                <td><code>PAYMENT_GATEWAY</code></td>
                <td><code>{{ PAYMENT_GATEWAY }}</code></td>
            </tr>
            <tr>
                <td><code>MSI_PLAZOS</code></td>
                <td><code>{{ MSI_PLAZOS }}</code></td>
            </tr>
        </table>
        <h2>Según el servidor (Python):</h2>
        <ul>
            <li><code>app.config['SANDBOX_MODE']</code>: {{ sandbox_python }}</li>
            <li><code>app.config['PAYMENT_GATEWAY']</code>: {{ gateway_python }}</li>
        </ul>
        {% if SANDBOX_MODE %}
            <p style="color:green;font-size:20px;">✅ El modo SANDBOX llega al template.</p>
        {% else %}
            <p style="color:red;font-size:20px;">❌ SANDBOX_MODE NO llega al template.</p>
        {% endif %}
        </body>
        </html>
        """
        return render_template_string(
            template_test,
            sandbox_python=app.config.get('SANDBOX_MODE', True),
            gateway_python=app.config.get('PAYMENT_GATEWAY', 'sandbox'),
        )

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
        <h2>2. Valores en `site_config`</h2>
        <table border="1" cellpadding="8" style="border-collapse:collapse;">
            <tr><th>Clave</th><th>Valor</th></tr>
            <tr><td>nombre_tienda</td><td>{{ site_config.nombre_tienda }}</td></tr>
            <tr><td>email_tienda</td><td>{{ site_config.email_tienda }}</td></tr>
            <tr><td>telefono_tienda</td><td>{{ site_config.telefono_tienda }}</td></tr>
            <tr><td>direccion_tienda</td><td>{{ site_config.direccion_tienda }}</td></tr>
            <tr><td>moneda</td><td>{{ site_config.moneda }}</td></tr>
        </table>
        <h2>3. Documento crudo en la BD</h2>
        <pre>{{ doc_raw }}</pre>
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
    # ⭐ FILTROS DE FECHAS Y TEMPORADAS
    # ============================================================
    from datetime import datetime as _dt

    def _to_datetime(value):
        if value is None:
            return None
        if isinstance(value, _dt):
            return value
        try:
            s = str(value).strip().replace('Z', '+00:00')
            if len(s) == 10:
                return _dt.strptime(s, '%Y-%m-%d')
            return _dt.fromisoformat(s)
        except Exception:
            return None

    @app.template_filter('fmt_fecha')
    def fmt_fecha(value, fmt='%d/%m/%Y'):
        d = _to_datetime(value)
        return d.strftime(fmt) if d else '—'

    @app.template_filter('fmt_fecha_input')
    def fmt_fecha_input(value):
        d = _to_datetime(value)
        return d.strftime('%Y-%m-%d') if d else ''

    @app.template_filter('estado_temporada')
    def estado_temporada(temp):
        from datetime import datetime as _d
        activa = temp.get('activa', True) is not False
        fi = _to_datetime(temp.get('fecha_inicio'))
        ff = _to_datetime(temp.get('fecha_fin'))
        ahora = _d.now()

        if not activa:
            return 'inactiva', 'Inactiva'
        if fi and ahora < fi:
            return 'proxima', 'Próxima'
        if ff and ahora > ff:
            return 'finalizada', 'Finalizada'
        if fi and ff and fi <= ahora <= ff:
            return 'en_curso', 'En curso'
        return 'activa', 'Activa'

    # ============================================================
    # ⭐ RUTA TEMPORAL: actualizar .avif → .jpg en MongoDB
    # ============================================================
    @app.route('/admin/fix-fotos-avif')
    def fix_fotos_avif():
        from flask import jsonify
        total = 0
        detalles = []
        for p in app.db.productos.find({}):
            cambios = False
            fotos = p.get('fotos') or []
            videos = p.get('videos') or []

            nuevas_fotos = [f.replace('.avif', '.jpg') if isinstance(f, str) else f for f in fotos]
            nuevos_videos = [v.replace('.avif', '.jpg') if isinstance(v, str) else v for v in videos]

            if nuevas_fotos != fotos or nuevos_videos != videos:
                app.db.productos.update_one(
                    {'_id': p['_id']},
                    {'$set': {'fotos': nuevas_fotos, 'videos': nuevos_videos}}
                )
                total += 1
                detalles.append(p.get('nombre', 'sin nombre'))

        return jsonify({
            'ok': True,
            'actualizados': total,
            'productos': detalles,
        })

    # ============================================================
    # ✅ RETURN FINAL
    # ============================================================
    return app