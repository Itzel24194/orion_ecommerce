# ================================================================
# app/controllers/auth_controller.py
# ================================================================

import os
import re
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import bcrypt
import jwt as pyjwt
from flask import render_template, request, redirect, url_for, session, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from bson import ObjectId
from itsdangerous import URLSafeTimedSerializer
from app.models.usuarios_model import Usuario as UsuarioModel


# ================================================================
# FUNCIONES AUXILIARES
# ================================================================

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol_lower = str(rol).strip().lower()
    if rol_lower in ('admin', 'administrador', 'superadmin', 'super_admin', 'root'):
        return 'admin'
    if rol_lower in ('vendedor', 'vendedora', 'vendor', 'seller', 'sellers'):
        return 'vendedor'
    return 'cliente'


def _redirigir_por_rol(rol_normalizado):
    if rol_normalizado == 'admin':
        return redirect(url_for('web.dashboard'))
    if rol_normalizado == 'vendedor':
        return redirect(url_for('web.vendedor_dashboard'))
    return redirect(url_for('web.raiz_tienda'))


# ================================================================
# ⭐ CONFIRMACIÓN — FUENTE COMPATIBLE FLASK ↔ EXPRESS
# ================================================================

def _esta_confirmado(usuario):
    """
    Un usuario está confirmado si CUALQUIERA de estos campos es True:
      - confirmado        (Flask)
      - email_confirmado  (Express)
    """
    if not usuario:
        return False
    return (
        usuario.get('confirmado') is True
        or usuario.get('email_confirmado') is True
    )


# ================================================================
# ⭐ HELPERS 2FA — FUENTE ÚNICA DE VERDAD: two_factor
# ================================================================

def _leer_2fa(usuario):
    if not usuario:
        return {'habilitado': False, 'secreto': None, 'codigos_respaldo': []}

    tf = usuario.get('two_factor') or {}
    legacy = usuario.get('2fa') or {}

    habilitado = tf.get('habilitado')
    secreto = tf.get('secreto') or tf.get('secret')
    codigos = tf.get('codigos_respaldo') or []

    if habilitado is None and legacy:
        habilitado = legacy.get('habilitado')
        secreto = secreto or legacy.get('secreto') or legacy.get('secret')
        codigos = codigos or legacy.get('codigos_respaldo') or []

    return {
        'habilitado': habilitado is True,
        'secreto': secreto,
        'codigos_respaldo': list(codigos) if isinstance(codigos, list) else [],
    }


def _guardar_2fa(db, usuario_id, *, habilitado=None, secreto=None, codigos_respaldo=None):
    set_doc = {}
    if habilitado is not None:
        set_doc['two_factor.habilitado'] = bool(habilitado)
    if secreto is not None:
        set_doc['two_factor.secreto'] = secreto
    if codigos_respaldo is not None:
        set_doc['two_factor.codigos_respaldo'] = list(codigos_respaldo)

    if not set_doc:
        return

    update = {'$set': set_doc}
    usuario = db.usuarios.find_one({'_id': ObjectId(str(usuario_id))}, {'2fa': 1})
    if usuario and '2fa' in usuario:
        update['$unset'] = {'2fa': ''}

    db.usuarios.update_one({'_id': ObjectId(str(usuario_id))}, update)


# ================================================================
# ENVIAR CORREO SMTP
# ================================================================

def enviar_correo_smtp(destinatario, asunto, contenido_html):
    try:
        smtp_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('MAIL_PORT', 587))
        username = os.getenv('MAIL_USERNAME')
        password_mail = os.getenv('MAIL_PASSWORD')
        sender = os.getenv('MAIL_DEFAULT_SENDER', username)

        print("=" * 70, file=sys.stderr)
        print("📧 INTENTANDO ENVÍO DE CORREO", file=sys.stderr)
        print(f"   Servidor: {smtp_server}", file=sys.stderr)
        print(f"   Puerto: {smtp_port}", file=sys.stderr)
        print(f"   Usuario: {username}", file=sys.stderr)
        print(f"   Contraseña: {'*' * len(password_mail) if password_mail else 'NO CARGADA'}", file=sys.stderr)
        print(f"   Destinatario: {destinatario}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)

        if not username or not password_mail:
            print("❌ Faltan credenciales de correo en .env", file=sys.stderr)
            return False

        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = destinatario
        msg['Subject'] = asunto

        text_part = MIMEText(
            contenido_html.replace('<br>', '\n').replace('<p>', '').replace('</p>', ''),
            'plain'
        )
        html_part = MIMEText(contenido_html, 'html')
        msg.attach(text_part)
        msg.attach(html_part)

        print("📤 Conectando al servidor...", file=sys.stderr)
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.set_debuglevel(1)
        server.starttls()
        print("🔑 Iniciando sesión...", file=sys.stderr)
        server.login(username, password_mail)
        print("📧 Enviando mensaje...", file=sys.stderr)
        server.send_message(msg)
        server.quit()
        print("✅ CORREO ENVIADO EXITOSAMENTE", file=sys.stderr)
        return True

    except Exception as e:
        print(f"❌ ERROR en enviar_correo_smtp: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


# ================================================================
# LOGIN (con soporte 2FA) — ⭐ SIN BLOQUEO POR CORREO
# ================================================================

def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash("Por favor, completa todos los campos.", "warning")
            return redirect(url_for('web.login'))

        usuario = UsuarioModel.obtener_por_email(email)

        if not usuario:
            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for('web.login'))

        # ⭐ ELIMINADO: ya no se bloquea por correo sin confirmar.
        # if not _esta_confirmado(usuario):
        #     flash("Debes confirmar tu correo electrónico antes de iniciar sesión.", "warning")
        #     return redirect(url_for('web.login'))

        if not usuario.get('activo', True):
            flash("Tu cuenta está desactivada. Contacta al administrador.", "danger")
            return redirect(url_for('web.login'))

        try:
            password_hash = usuario.get('password', '')
            if not password_hash:
                flash("Correo o contraseña incorrectos.", "danger")
                return redirect(url_for('web.login'))

            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                flash("Correo o contraseña incorrectos.", "danger")
                return redirect(url_for('web.login'))

        except Exception as e:
            print(f"❌ Error bcrypt login: {e}", file=sys.stderr)
            flash("Error al verificar la contraseña.", "danger")
            return redirect(url_for('web.login'))

        tf = _leer_2fa(usuario)
        print(f"🔐 [login web] 2FA: habilitado={tf['habilitado']} tiene_secreto={bool(tf['secreto'])}", file=sys.stderr)

        if tf['habilitado']:
            session.clear()
            session['2fa_pendiente_user_id'] = str(usuario['_id'])
            session['2fa_pendiente_email']   = usuario.get('email')
            session['2fa_pendiente_nombre']  = usuario.get('nombre', 'Usuario')
            session['2fa_pendiente_rol']     = usuario.get('rol', 'cliente')
            session['2fa_pendiente_foto']    = usuario.get('foto')
            flash('Ingresa tu código de verificación de 6 dígitos.', 'info')
            return redirect(url_for('web.verificar_2fa_login'))

        session.clear()

        session['user_id'] = str(usuario['_id'])
        session['email'] = usuario.get('email')
        session['nombre'] = usuario.get('nombre', 'Usuario')

        rol_normalizado = normalizar_rol(usuario.get('rol', 'cliente'))
        session['rol'] = rol_normalizado

        session['es_vendedor'] = bool(usuario.get('es_vendedor', False))

        try:
            segmento = UsuarioModel.obtener_segmento(str(usuario['_id']))
            session['segmento'] = segmento
        except Exception:
            session['segmento'] = 'Inactivo'

        foto = usuario.get('foto')
        if foto:
            session['foto'] = foto
        else:
            session.pop('foto', None)

        try:
            UsuarioModel.actualizar(str(usuario['_id']), {'ultimo_login': datetime.utcnow()})
        except Exception:
            pass

        print(
            f"🔐 LOGIN OK: {email} | rol_raw={usuario.get('rol')!r} "
            f"rol_norm={rol_normalizado!r} es_vendedor={session['es_vendedor']} → redirigiendo",
            file=sys.stderr
        )

        if rol_normalizado == 'admin':
            flash(f"¡Bienvenido Administrador {session['nombre']}!", "success")
            return redirect(url_for('web.dashboard'))

        if rol_normalizado == 'vendedor':
            flash(f"¡Bienvenido, {session['nombre']}! Panel de vendedor.", "success")
            return redirect(url_for('web.vendedor_dashboard'))

        flash(f"¡Bienvenido {session['nombre']}!", "success")
        return redirect(url_for('web.raiz_tienda'))

    return render_template('auth/login.html')


# ================================================================
# VERIFICACIÓN 2FA EN EL LOGIN (WEB)
# ================================================================

def verificar_2fa_login():
    user_id = session.get('2fa_pendiente_user_id')
    if not user_id:
        flash('Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('web.login'))

    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(user_id)})
    if not usuario:
        session.pop('2fa_pendiente_user_id', None)
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('web.login'))

    if request.method == 'POST':
        codigo = (request.form.get('codigo') or '').strip()
        usar_respaldo = request.form.get('usar_respaldo')

        tf = _leer_2fa(usuario)
        secreto = tf['secreto']

        if not secreto:
            session.pop('2fa_pendiente_user_id', None)
            flash('Error de configuración 2FA.', 'danger')
            return redirect(url_for('web.login'))

        if usar_respaldo:
            codigos = list(tf['codigos_respaldo'])
            codigo_up = codigo.upper()
            if codigo_up in codigos:
                codigos.remove(codigo_up)
                _guardar_2fa(db, usuario['_id'], codigos_respaldo=codigos)
                db.usuarios.update_one(
                    {'_id': usuario['_id']},
                    {'$set': {'updated_at': datetime.utcnow()}}
                )
                return _completar_login_2fa(usuario, 'Código de respaldo aceptado.')
            else:
                flash('Código de respaldo inválido.', 'danger')
                return render_template('auth/verificar_2fa.html')

        if not codigo or len(codigo) != 6:
            flash('Ingresa un código de 6 dígitos.', 'danger')
            return render_template('auth/verificar_2fa.html')

        try:
            import pyotp
            totp = pyotp.TOTP(secreto)
            if not totp.verify(codigo, valid_window=1):
                flash('Código incorrecto. Intenta de nuevo.', 'danger')
                return render_template('auth/verificar_2fa.html')
        except Exception as e:
            print(f"❌ Error validando TOTP: {e}", file=sys.stderr)
            flash('Error al validar el código.', 'danger')
            return render_template('auth/verificar_2fa.html')

        return _completar_login_2fa(usuario, '¡Bienvenido!')

    return render_template('auth/verificar_2fa.html')


def _completar_login_2fa(usuario, mensaje):
    session['user_id'] = str(usuario['_id'])
    session['nombre'] = usuario.get('nombre', 'Usuario')
    session['email'] = usuario.get('email', '')

    rol_normalizado = normalizar_rol(usuario.get('rol', 'cliente'))
    session['rol'] = rol_normalizado
    session['es_vendedor'] = bool(usuario.get('es_vendedor', False))

    foto = usuario.get('foto')
    if foto:
        session['foto'] = foto
    else:
        session.pop('foto', None)

    try:
        segmento = UsuarioModel.obtener_segmento(str(usuario['_id']))
        session['segmento'] = segmento
    except Exception:
        session['segmento'] = 'Inactivo'

    try:
        UsuarioModel.actualizar(str(usuario['_id']), {'ultimo_login': datetime.utcnow()})
    except Exception:
        pass

    for k in ('2fa_pendiente_user_id', '2fa_pendiente_email',
              '2fa_pendiente_nombre', '2fa_pendiente_rol',
              '2fa_pendiente_foto'):
        session.pop(k, None)

    flash(mensaje, 'success')

    print(
        f"🔐 LOGIN 2FA OK: {session.get('email')} | "
        f"rol_raw={usuario.get('rol')!r} rol_norm={rol_normalizado!r} "
        f"es_vendedor={session['es_vendedor']}",
        file=sys.stderr
    )

    if rol_normalizado == 'admin':
        return redirect(url_for('web.dashboard'))
    if rol_normalizado == 'vendedor':
        return redirect(url_for('web.vendedor_dashboard'))
    return redirect(url_for('web.raiz_tienda'))


# ================================================================
# REGISTRO (WEB) — ⭐ AUTO-CONFIRMADO
# ================================================================

def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash("Por favor, completa todos los campos.", "warning")
            return redirect(url_for('web.register'))

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash("El correo electrónico no es válido.", "danger")
            return redirect(url_for('web.register'))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for('web.register'))

        if UsuarioModel.obtener_por_email(email):
            flash("Este correo ya está registrado.", "danger")
            return redirect(url_for('web.register'))

        try:
            print(f"📝 Creando usuario web: {email}", file=sys.stderr)
            UsuarioModel.crear_usuario({
                "email": email,
                "password": password,
                # ⭐ AUTO-CONFIRMADO: evita el rebote al login
                "confirmado": True,
                "email_confirmado": True,
                "rol": "cliente",
                "activo": True,
                "two_factor": {"habilitado": False},
            })

            # Correo de bienvenida (opcional, no bloquea)
            try:
                token = get_serializer().dumps(email, salt='email-confirm')
                confirm_url = url_for('web.confirmar_email', token=token, _external=True)

                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
                    <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
                    <p>Hola, gracias por registrarte en <strong>ORION SYSTEM</strong>.</p>
                    <p>Tu cuenta ya está activa. Puedes iniciar sesión ahora mismo.</p>
                    <a href="{confirm_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Ir a ORION</a>
                </div>
                """
                enviar_correo_smtp(email, "¡Bienvenido a ORION SYSTEM!", html_content)
            except Exception as mail_err:
                print(f"⚠️ Correo bienvenida falló: {mail_err}", file=sys.stderr)

            flash("¡Cuenta creada! Ya puedes iniciar sesión.", "success")
            return redirect(url_for('web.login'))

        except Exception as e:
            print(f"❌ Error en register: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            flash("Error al crear el usuario. Intenta nuevamente.", "danger")
            return redirect(url_for('web.register'))

    return render_template('auth/register.html')


# ================================================================
# REENVIAR CONFIRMACIÓN
# ================================================================

def reenviar_confirmacion():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            email = session.get('pending_confirm_email')
        if not email:
            flash("No se pudo identificar tu correo. Regístrate nuevamente.", "danger")
            return redirect(url_for('web.register'))

        usuario = UsuarioModel.obtener_por_email(email)
        if not usuario:
            flash("No existe una cuenta con ese correo.", "danger")
            return redirect(url_for('web.register'))

        if _esta_confirmado(usuario):
            flash("Esta cuenta ya está confirmada. Inicia sesión.", "info")
            return redirect(url_for('web.login'))

        token = get_serializer().dumps(email, salt='email-confirm')
        confirm_url = url_for('web.confirmar_email', token=token, _external=True)

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
            <p>Reenvío: haz clic en el botón para activar tu cuenta:</p>
            <a href="{confirm_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Activar Cuenta</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Este enlace expirará en 1 hora.</p>
        </div>
        """

        if enviar_correo_smtp(email, "Reenvío: Confirma tu cuenta - ORION SYSTEM", html_content):
            flash("Se ha reenviado el enlace a tu correo.", "success")
        else:
            flash("Error al reenviar el correo. Intenta nuevamente.", "danger")

        return render_template('auth/confirmacion_pendiente.html', email=email)

    return redirect(url_for('web.login'))


# ================================================================
# CONFIRMAR EMAIL
# ================================================================

def confirmar_email(token):
    try:
        email = get_serializer().loads(token, salt='email-confirm', max_age=3600)
    except Exception:
        flash("El enlace es inválido o ha expirado.", "danger")
        return redirect(url_for('web.login'))

    try:
        db = current_app.db
        result = db.usuarios.update_one(
            {'email': email},
            {'$set': {
                'confirmado': True,
                'email_confirmado': True,
                'updated_at': datetime.utcnow(),
            }}
        )

        if result.modified_count == 0:
            flash("La cuenta ya estaba confirmada. Inicia sesión.", "info")
            return redirect(url_for('web.login'))

        session['pending_profile_email'] = email
        flash("¡Cuenta confirmada! Ahora completa tu perfil.", "success")
        return redirect(url_for('web.register_profile'))

    except Exception as e:
        print(f"❌ Error confirmar_email: {e}", file=sys.stderr)
        flash("Error al confirmar el correo.", "danger")
        return redirect(url_for('web.login'))


# ================================================================
# REGISTRO DE PERFIL
# ================================================================

def register_profile():
    if 'pending_profile_email' not in session:
        flash("Debes confirmar tu correo para completar el perfil.", "danger")
        return redirect(url_for('web.register'))

    if request.method == 'POST':
        email = session.pop('pending_profile_email')

        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash("El nombre es obligatorio.", "danger")
            session['pending_profile_email'] = email
            return redirect(url_for('web.register_profile'))

        dia = request.form.get('dia', '').zfill(2)
        mes = request.form.get('mes', '').zfill(2)
        anio = request.form.get('anio', '')
        fecha_nacimiento = f"{anio}-{mes}-{dia}" if anio and mes and dia else None

        data = {
            "nombre": nombre,
            "apellido_paterno": request.form.get('apellido_p', '').strip(),
            "apellido_materno": request.form.get('apellido_m', '').strip(),
            "fecha_nacimiento": fecha_nacimiento,
            "genero": request.form.get('genero'),
            "telefono": request.form.get('telefono', '').strip()
        }

        try:
            db = current_app.db
            db.usuarios.update_one(
                {'email': email},
                {'$set': data}
            )
            flash("Perfil completado. ¡Bienvenido a ORION SYSTEM!", "success")
            return redirect(url_for('web.login'))
        except Exception as e:
            print(f"❌ Error register_profile: {e}", file=sys.stderr)
            flash("Error al guardar el perfil.", "danger")
            return redirect(url_for('web.register_profile'))

    return render_template('auth/register_profile.html')


# ================================================================
# LOGOUT
# ================================================================

def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('web.login'))


# ================================================================
# VER PERFIL
# ================================================================

def ver_perfil():
    if 'user_id' not in session:
        flash("Inicia sesión para ver tu perfil.", "warning")
        return redirect(url_for('web.login'))

    usuario = UsuarioModel.obtener_por_id(session['user_id'])
    if not usuario:
        flash("Usuario no encontrado.", "danger")
        session.clear()
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        usuario_oid = ObjectId(session['user_id'])
    except Exception:
        flash("Sesión inválida.", "danger")
        session.clear()
        return redirect(url_for('web.login'))

    pedidos = []
    try:
        pedidos = list(
            db.pedidos.find({'usuario_id': usuario_oid})
                      .sort('created_at', -1)
                      .limit(5)
        )
        for pedido in pedidos:
            pedido['_id'] = str(pedido['_id'])
            if 'items' in pedido and 'items_list' not in pedido:
                pedido['items_list'] = pedido['items']
            elif 'productos' in pedido and 'items_list' not in pedido:
                pedido['items_list'] = pedido['productos']
            if 'created_at' not in pedido:
                pedido['created_at'] = datetime.utcnow()
    except Exception as e:
        current_app.logger.error(f'Error cargando pedidos en perfil: {e}')
        pedidos = []

    favoritos = []
    try:
        favs = list(db.favoritos.find({'usuario_id': usuario_oid}))
        fav_ids = []
        for f in favs:
            pid = f.get('producto_id')
            if not pid:
                continue
            if isinstance(pid, ObjectId):
                fav_ids.append(pid)
            else:
                try:
                    fav_ids.append(ObjectId(pid))
                except Exception:
                    continue

        if fav_ids:
            favoritos = list(db.productos.find({'_id': {'$in': fav_ids}}))
            marcas = list(db.marcas.find({}))
            marcas_dict = {str(m['_id']): m.get('nombre_comercial', '') for m in marcas}
            for prod in favoritos:
                mid = prod.get('marca_id')
                prod['marca_nombre'] = marcas_dict.get(str(mid), '') if mid else ''
    except Exception as e:
        current_app.logger.error(f'Error cargando favoritos en perfil: {e}')
        favoritos = []

    categorias = []
    try:
        categorias = list(db.categorias.find({}))
    except Exception:
        categorias = []

    carrito_items = session.get('carrito', []) or []

    try:
        segmento = UsuarioModel.obtener_segmento(session['user_id'])
    except Exception:
        segmento = 'Inactivo'

    return render_template(
        'tienda/perfil.html',
        usuario=usuario,
        pedidos=pedidos,
        favoritos=favoritos,
        categorias=categorias,
        carrito_items=carrito_items,
        segmento=segmento
    )


# ================================================================
# ACTUALIZAR PERFIL
# ================================================================

def actualizar_perfil():
    if 'user_id' not in session:
        flash("Inicia sesión para actualizar tu perfil.", "warning")
        return redirect(url_for('web.login'))

    usuario_id = session['user_id']

    datos_actualizados = {
        "nombre": request.form.get('nombre', '').strip(),
        "telefono": request.form.get('telefono', '').strip(),
        "apellido_paterno": request.form.get('apellido_paterno', '').strip(),
        "apellido_materno": request.form.get('apellido_materno', '').strip(),
        "fecha_nacimiento": request.form.get('fecha_nacimiento'),
        "genero": request.form.get('genero')
    }

    datos_actualizados = {k: v for k, v in datos_actualizados.items() if v and v != ''}

    if 'foto' in request.files and request.files['foto'].filename != '':
        file = request.files['foto']
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"

            upload_folder = os.path.join(current_app.root_path, 'static/uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            file.save(os.path.join(upload_folder, filename))
            datos_actualizados['foto'] = filename
            session['foto'] = filename
        else:
            flash("Formato de imagen no válido.", "danger")
            return redirect(url_for('web.perfil'))

    try:
        UsuarioModel.actualizar(usuario_id, datos_actualizados)
        session['nombre'] = datos_actualizados.get('nombre', session.get('nombre'))
        flash("Perfil actualizado correctamente.", "success")
    except Exception:
        flash("Error al actualizar el perfil.", "danger")

    return redirect(url_for('web.perfil'))


# ================================================================
# RECUPERAR CONTRASEÑA
# ================================================================

def recuperar_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            flash("Por favor ingresa tu correo electrónico.", "warning")
            return redirect(url_for('web.login'))

        usuario = UsuarioModel.obtener_por_email(email)
        if not usuario:
            flash("No existe una cuenta con ese correo electrónico.", "warning")
            return redirect(url_for('web.login'))

        token = get_serializer().dumps(email, salt='password-reset')
        reset_url = url_for('web.resetear_password', token=token, _external=True)

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🔐 ORION SYSTEM</h1>
            <p>Hemos recibido una solicitud para restablecer tu contraseña.</p>
            <p>Para crear una nueva contraseña, presiona el siguiente botón:</p>
            <a href="{reset_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Restablecer Contraseña</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Si no solicitaste esto, ignora este mensaje.</p>
            <p style="font-size: 12px; color: #888; text-align: center;">⏰ El enlace expirará en 1 hora.</p>
        </div>
        """

        if enviar_correo_smtp(email, "Recuperación de contraseña - ORION SYSTEM", html_content):
            flash("Se han enviado instrucciones a tu correo electrónico.", "success")
        else:
            flash("Error al enviar el correo de recuperación.", "danger")

        return redirect(url_for('web.login'))

    return render_template('auth/recuperar_password.html')


# ================================================================
# RESETEAR CONTRASEÑA
# ================================================================

def resetear_password(token):
    try:
        email = get_serializer().loads(token, salt='password-reset', max_age=3600)
    except Exception:
        flash("El enlace es inválido o ha expirado.", "danger")
        return redirect(url_for('web.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not password or not confirm_password:
            flash("Todos los campos son requeridos.", "danger")
            return redirect(url_for('web.resetear_password', token=token))

        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect(url_for('web.resetear_password', token=token))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for('web.resetear_password', token=token))

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        try:
            db = current_app.db
            db.usuarios.update_one(
                {'email': email},
                {'$set': {'password': hashed, 'updated_at': datetime.utcnow()}}
            )
            flash("Contraseña actualizada correctamente. Ya puedes iniciar sesión.", "success")
            return redirect(url_for('web.login'))
        except Exception:
            flash("Error al actualizar la contraseña.", "danger")
            return redirect(url_for('web.resetear_password', token=token))

    return render_template('auth/resetear_password.html', token=token)


# ================================================================
# CAMBIAR CONTRASEÑA (autenticado)
# ================================================================

def cambiar_password():
    if 'user_id' not in session:
        flash('Inicia sesión para cambiar tu contraseña', 'warning')
        return redirect(url_for('web.login'))

    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '')
        password_nuevo = request.form.get('password_nuevo', '')
        password_confirmar = request.form.get('password_confirmar', '')

        if not password_actual or not password_nuevo or not password_confirmar:
            flash('Todos los campos son requeridos', 'danger')
            return redirect(url_for('web.perfil'))

        if password_nuevo != password_confirmar:
            flash('Las contraseñas nuevas no coinciden', 'danger')
            return redirect(url_for('web.perfil'))

        if len(password_nuevo) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('web.perfil'))

        try:
            db = current_app.db
            usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})

            if not usuario:
                flash('Usuario no encontrado', 'danger')
                return redirect(url_for('web.logout'))

            password_hash = usuario.get('password', '')
            if not bcrypt.checkpw(password_actual.encode('utf-8'), password_hash.encode('utf-8')):
                flash('Contraseña actual incorrecta', 'danger')
                return redirect(url_for('web.perfil'))

            nuevo_hash = bcrypt.hashpw(password_nuevo.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            db.usuarios.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': {'password': nuevo_hash, 'updated_at': datetime.utcnow()}}
            )

            flash('Contraseña actualizada correctamente', 'success')

        except Exception:
            flash('Error al cambiar la contraseña', 'danger')

        return redirect(url_for('web.perfil'))

    flash('Método no permitido', 'danger')
    return redirect(url_for('web.perfil'))


# ================================================================
# ⭐ PERFIL DEL ADMINISTRADOR (GET + POST) — AÑADIDO
# ================================================================

def admin_perfil():
    """
    GET  /admin/perfil → muestra el perfil del admin logueado
    POST /admin/perfil → actualiza datos personales + sube foto
    Solo accesible para rol admin.
    """
    db = current_app.db

    if 'user_id' not in session:
        flash('Inicia sesión para ver tu perfil.', 'warning')
        return redirect(url_for('web.login'))

    try:
        usuario_oid = ObjectId(session['user_id'])
    except Exception:
        flash('Sesión inválida.', 'danger')
        session.clear()
        return redirect(url_for('web.login'))

    usuario = db.usuarios.find_one({'_id': usuario_oid})
    if not usuario:
        flash('Usuario no encontrado.', 'danger')
        session.clear()
        return redirect(url_for('web.login'))

    # Verificar que sea admin
    rol = normalizar_rol(usuario.get('rol') or usuario.get('role') or 'cliente')
    if rol != 'admin':
        flash('Solo administradores pueden acceder a este perfil.', 'danger')
        return redirect(url_for('web.raiz_tienda'))

    if request.method == 'POST':
        datos = {
            'nombre':           (request.form.get('nombre') or '').strip(),
            'apellido_paterno': (request.form.get('apellido_paterno') or '').strip(),
            'apellido_materno': (request.form.get('apellido_materno') or '').strip(),
            'telefono':         (request.form.get('telefono') or '').strip(),
            'email':            (request.form.get('email') or '').strip().lower(),
            'fecha_nacimiento': request.form.get('fecha_nacimiento') or None,
            'genero':           request.form.get('genero') or None,
        }
        datos = {k: v for k, v in datos.items() if v not in (None, '')}

        # Validaciones mínimas
        if not datos.get('nombre'):
            flash('El nombre es obligatorio.', 'danger')
            return redirect(url_for('web.admin_perfil'))

        if not datos.get('email'):
            flash('El email es obligatorio.', 'danger')
            return redirect(url_for('web.admin_perfil'))

        # Si el email cambió, verificar que no esté en uso
        if datos['email'] != (usuario.get('email') or '').lower():
            existente = db.usuarios.find_one({
                'email': datos['email'],
                '_id': {'$ne': usuario_oid},
            })
            if existente:
                flash('Ese correo ya está registrado por otro usuario.', 'danger')
                return redirect(url_for('web.admin_perfil'))

        # Subida de foto
        if 'foto' in request.files and request.files['foto'].filename:
            file = request.files['foto']
            nombre_original = secure_filename(file.filename)
            if '.' in nombre_original:
                ext = nombre_original.rsplit('.', 1)[-1].lower()
            else:
                ext = ''

            if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                nuevo_nombre = f"u{int(datetime.utcnow().timestamp())}_{nombre_original}"

                upload_folder = current_app.config.get('UPLOAD_FOLDER')
                if not upload_folder:
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)

                file.save(os.path.join(upload_folder, nuevo_nombre))

                # Borrar la foto anterior si existía
                foto_vieja = usuario.get('foto')
                if foto_vieja and foto_vieja != nuevo_nombre:
                    try:
                        ruta_vieja = os.path.join(upload_folder, foto_vieja)
                        if os.path.isfile(ruta_vieja):
                            os.remove(ruta_vieja)
                    except Exception:
                        pass

                datos['foto'] = nuevo_nombre
                session['foto'] = nuevo_nombre
            else:
                flash('Formato de imagen no válido (usa png, jpg, jpeg, gif o webp).', 'danger')
                return redirect(url_for('web.admin_perfil'))

        try:
            if datos:
                datos['updated_at'] = datetime.utcnow()
                db.usuarios.update_one({'_id': usuario_oid}, {'$set': datos})

            # Refrescar sesión
            if 'nombre' in datos:
                session['nombre'] = datos['nombre']
            if 'email' in datos:
                session['email'] = datos['email']

            flash('Perfil actualizado correctamente.', 'success')
        except Exception as e:
            current_app.logger.error(f'[admin_perfil] ERROR actualizando: {e}')
            flash('Error al actualizar el perfil.', 'danger')

        return redirect(url_for('web.admin_perfil'))

    # GET → renderizar template
    return render_template('admin/perfil_admin.html', usuario=usuario)


# ================================================================
# API (WEB)
# ================================================================

def obtener_usuario_actual():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    usuario = UsuarioModel.obtener_por_id(session['user_id'])
    if usuario:
        usuario['_id'] = str(usuario['_id'])
        usuario.pop('password', None)
        usuario.pop('two_factor', None)
        usuario.pop('2fa', None)
        return jsonify(usuario)
    return jsonify({'error': 'Usuario no encontrado'}), 404


def verificar_autenticacion():
    if 'user_id' in session:
        return jsonify({
            'autenticado': True,
            'usuario_id': session['user_id'],
            'email': session.get('email', ''),
            'nombre': session.get('nombre', ''),
            'rol': session.get('rol', 'cliente'),
            'rol_normalizado': normalizar_rol(session.get('rol', 'cliente')),
            'foto': session.get('foto', ''),
            'segmento': session.get('segmento', 'Inactivo'),
            'es_vendedor': bool(session.get('es_vendedor', False)),
        })
    return jsonify({'autenticado': False})


def registrar_admin():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        nombre = request.form.get('nombre', 'Administrador').strip()

        if not email or not password:
            flash("Todos los campos son requeridos.", "warning")
            return redirect(url_for('web.registrar_admin'))

        if UsuarioModel.obtener_por_email(email):
            flash("Este correo ya está registrado.", "danger")
            return redirect(url_for('web.registrar_admin'))

        try:
            UsuarioModel.crear_usuario({
                "email": email,
                "password": password,
                "confirmado": True,
                "email_confirmado": True,
                "rol": "admin",
                "nombre": nombre,
                "activo": True,
                "two_factor": {"habilitado": False},
            })
            flash("Administrador registrado exitosamente.", "success")
            return redirect(url_for('web.login'))
        except Exception:
            flash("Error al registrar el administrador.", "danger")

    return render_template('auth/registrar_admin.html')


def debug_sesion():
    db = current_app.db
    user_id = session.get('user_id')
    usuario = None
    if user_id:
        usuario = db.usuarios.find_one({'_id': ObjectId(user_id)})
        if usuario:
            usuario['_id'] = str(usuario['_id'])
            usuario.pop('password', None)

    rol_norm = normalizar_rol(session.get('rol', 'cliente'))

    return jsonify({
        'session': dict(session),
        'user_id': session.get('user_id'),
        'rol': session.get('rol'),
        'rol_normalizado': rol_norm,
        'nombre': session.get('nombre'),
        'email': session.get('email'),
        'foto': session.get('foto'),
        'segmento': session.get('segmento', 'Inactivo'),
        'es_vendedor': bool(session.get('es_vendedor', False)),
        'usuario_bd': usuario,
        'es_admin': rol_norm == 'admin',
        'es_vendedor_rol': rol_norm == 'vendedor',
        'redireccion': (
            'web.dashboard' if rol_norm == 'admin'
            else 'web.vendedor_dashboard' if rol_norm == 'vendedor'
            else 'web.raiz_tienda'
        )
    }), 200


# ================================================================
# API v1 - AUTENTICACIÓN CON JWT (para React Native / SPA)
# ================================================================

from app.jwt_utils import (
    create_access_token,
    get_current_user_from_request,
    create_temp_token_2fa,
    get_temp_token_2fa_payload,
)


def _crear_token_para_usuario(usuario):
    rol_norm = normalizar_rol(usuario.get('rol', 'cliente'))
    return create_access_token(
        user_id=str(usuario['_id']),
        email=usuario.get('email'),
        rol=rol_norm,
        nombre=usuario.get('nombre', 'Usuario'),
    )


def _respuesta_login_ok(usuario):
    rol_norm = normalizar_rol(usuario.get('rol', 'cliente'))
    token = _crear_token_para_usuario(usuario)

    try:
        UsuarioModel.actualizar(str(usuario['_id']), {'ultimo_login': datetime.utcnow()})
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "access_token": token,
        "token": token,
        "token_type": "Bearer",
        "expires_in": int(os.getenv("JWT_EXPIRATION_HOURS", "24")) * 3600,
        "user": {
            "id": str(usuario['_id']),
            "email": usuario.get('email'),
            "nombre": usuario.get('nombre', 'Usuario'),
            "rol": rol_norm,
            "role": rol_norm,
            "foto": usuario.get('foto'),
            "es_vendedor": bool(usuario.get('es_vendedor', False)),
        },
        "usuario": {
            "id": str(usuario['_id']),
            "email": usuario.get('email'),
            "nombre": usuario.get('nombre', 'Usuario'),
            "rol": rol_norm,
            "role": rol_norm,
            "foto": usuario.get('foto'),
        },
        "perfil_completo": bool(usuario.get('perfil_completo', False)),
    }), 200


def api_login_jwt():
    """POST /api/v1/auth/login — Devuelve un JWT (para móvil / SPA)."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Email y contraseña son requeridos"}), 400

    usuario = UsuarioModel.obtener_por_email(email)

    if not usuario:
        return jsonify({"error": "Correo o contraseña incorrectos"}), 401

    # ⭐ ELIMINADO: ya no se bloquea por correo sin confirmar.
    # if not _esta_confirmado(usuario):
    #     return jsonify({
    #         "error": "Debes confirmar tu correo electrónico antes de iniciar sesión.",
    #         "code": "email_no_confirmado",
    #     }), 403

    if not usuario.get('activo', True):
        return jsonify({"error": "Tu cuenta está desactivada. Contacta al administrador."}), 403

    try:
        password_hash = usuario.get('password', '')
        if not password_hash:
            return jsonify({"error": "Correo o contraseña incorrectos"}), 401

        if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
            return jsonify({"error": "Correo o contraseña incorrectos"}), 401
    except Exception as e:
        print(f"❌ [login JWT] bcrypt: {e}", file=sys.stderr)
        return jsonify({"error": "Error al verificar la contraseña"}), 500

    tf = _leer_2fa(usuario)
    print(
        f"🔐 [login JWT] {email} | two_factor.habilitado={tf['habilitado']} "
        f"tiene_secreto={bool(tf['secreto'])}",
        file=sys.stderr
    )

    if tf['habilitado'] is True:
        try:
            temp_token = create_temp_token_2fa(
                user_id=str(usuario['_id']),
                email=usuario.get('email', ''),
            )
        except Exception as e:
            print(f"❌ [login JWT] temp_token: {e}", file=sys.stderr)
            return jsonify({"error": "Error generando token temporal 2FA"}), 500

        return jsonify({
            "ok": True,
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "Ingresa tu código de verificación",
        }), 200

    return _respuesta_login_ok(usuario)


def api_verify_2fa_jwt():
    """
    POST /api/v1/auth/2fa/verificar
    Body: { temp_token, codigo }
    Valida TOTP o código de respaldo y devuelve el token real.
    """
    data = request.get_json(silent=True) or {}
    temp_token = (data.get('temp_token') or '').strip()
    codigo = (data.get('codigo') or '').strip()

    if not temp_token:
        return jsonify({"error": "temp_token requerido"}), 400

    payload = get_temp_token_2fa_payload(temp_token)
    if not payload:
        return jsonify({
            "error": "La verificación expiró. Inicia sesión de nuevo.",
            "code": "temp_token_invalid",
        }), 401

    if not codigo:
        return jsonify({"error": "Ingresa el código de 6 dígitos"}), 400

    usuario = UsuarioModel.obtener_por_id(payload['user_id'])
    if not usuario or usuario.get('activo') is False:
        return jsonify({"error": "Usuario no disponible"}), 401

    tf = _leer_2fa(usuario)
    if not tf['habilitado'] or not tf['secreto']:
        return jsonify({"error": "2FA no configurado"}), 400

    db = current_app.db
    codigo_up = codigo.upper()
    codigos_respaldo = list(tf['codigos_respaldo'])

    if len(codigo) >= 8 and codigo_up in codigos_respaldo:
        codigos_respaldo.remove(codigo_up)
        _guardar_2fa(db, usuario['_id'], codigos_respaldo=codigos_respaldo)

        resp = _respuesta_login_ok(usuario)
        try:
            body = resp[0].get_json()
            body['codigo_respaldo_usado'] = True
            body['codigos_respaldo_restantes'] = len(codigos_respaldo)
            return jsonify(body), 200
        except Exception:
            return resp

    if len(codigo) != 6 or not codigo.isdigit():
        return jsonify({"error": "Código inválido"}), 400

    try:
        import pyotp
        if not pyotp.TOTP(tf['secreto']).verify(codigo, valid_window=1):
            return jsonify({"error": "Código incorrecto"}), 401
    except Exception as e:
        print(f"❌ [verify_2fa] TOTP: {e}", file=sys.stderr)
        return jsonify({"error": "Error al validar el código"}), 500

    resp = _respuesta_login_ok(usuario)
    try:
        body = resp[0].get_json()
        body['codigo_respaldo_usado'] = False
        body['codigos_respaldo_restantes'] = len(codigos_respaldo)
        return jsonify(body), 200
    except Exception:
        return resp


def api_register_jwt():
    """POST /api/v1/auth/register — Crea un usuario y devuelve JWT."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    nombre = (data.get('nombre') or '').strip()

    if not email or not password:
        return jsonify({"error": "Email y contraseña son requeridos"}), 400

    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({"error": "El correo electrónico no es válido"}), 400

    if len(password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400

    if UsuarioModel.obtener_por_email(email):
        return jsonify({"error": "Este correo ya está registrado"}), 409

    try:
        UsuarioModel.crear_usuario({
            "email": email,
            "password": password,
            # ⭐ Auto-confirmado desde móvil (para no bloquear el login)
            "confirmado": True,
            "email_confirmado": True,
            "rol": "cliente",
            "activo": True,
            "nombre": nombre or email.split('@')[0],
            "two_factor": {"habilitado": False},
        })
    except Exception as e:
        print(f"❌ Error creando usuario vía API: {e}", file=sys.stderr)
        return jsonify({"error": "Error al crear el usuario"}), 500

    usuario = UsuarioModel.obtener_por_email(email)
    if not usuario:
        return jsonify({"error": "Error al recuperar el usuario creado"}), 500

    return _respuesta_login_ok(usuario)


def api_me_jwt():
    """GET /api/v1/auth/me — Devuelve el usuario autenticado por JWT."""
    payload = get_current_user_from_request()
    if not payload:
        return jsonify({"error": "No autorizado"}), 401

    usuario = UsuarioModel.obtener_por_id(payload['user_id'])
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404

    usuario['_id'] = str(usuario['_id'])
    usuario.pop('password', None)
    usuario.pop('two_factor', None)
    usuario.pop('2fa', None)

    return jsonify({"ok": True, "user": usuario, "usuario": usuario}), 200


def api_listar_usuarios_jwt():
    """GET /api/v1/usuarios — Lista de usuarios (solo admin)."""
    payload = get_current_user_from_request()
    if not payload:
        return jsonify({"error": "No autorizado"}), 401

    if payload.get('rol') != 'admin':
        return jsonify({"error": "Solo administradores"}), 403

    db = current_app.db
    usuarios = list(db.usuarios.find({}, {
        'email': 1, 'nombre': 1, 'rol': 1,
        'confirmado': 1, 'activo': 1, 'created_at': 1
    }).sort('created_at', -1))

    for u in usuarios:
        u['_id'] = str(u['_id'])
        if 'created_at' in u and u['created_at']:
            u['created_at'] = u['created_at'].isoformat()

    return jsonify({"usuarios": usuarios, "total": len(usuarios)}), 200