# app/controllers/user_controller.py - COMPLETO Y CORREGIDO
# ================================================================

import os
import sys
import uuid
import io
import base64
import secrets
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template, request, redirect, url_for, session, current_app, flash, jsonify
from werkzeug.utils import secure_filename
from app.models.usuarios_model import Usuario as UsuarioModel
from app.models.ventas_model import VentaReporte
from app.models.resenas_model import Resena
from datetime import datetime, timedelta, timezone
from app.models.productos_model import Producto
from bson import ObjectId


# ================================================================
# FUNCIÓN AUXILIAR PARA NORMALIZAR ROLES
# ================================================================

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


# ================================================================
# FUNCIÓN AUXILIAR PARA NORMALIZAR GÉNERO
# ================================================================

def normalizar_genero(valor):
    if not valor:
        return 'Indefinido'
    v = valor.strip().lower()
    if v in ['masculino', 'hombre', 'm', 'male', 'man']:
        return 'Masculino'
    if v in ['femenino', 'mujer', 'f', 'female', 'woman']:
        return 'Femenino'
    return 'Indefinido'


# ================================================================
# ✅ EXTRAER COMPLEXIÓN DEL FORMULARIO (ADMIN)
# ================================================================

def _to_int(valor, default=None):
    try:
        if valor is None or valor == '':
            return default
        return int(float(valor))
    except (ValueError, TypeError):
        return default


def _to_float(valor, default=None):
    try:
        if valor is None or valor == '':
            return default
        return float(valor)
    except (ValueError, TypeError):
        return default


def _extraer_complexion_del_form():
    form = request.form

    altura = _to_int(form.get('cx_altura_cm'))
    peso = _to_float(form.get('cx_peso_kg'))
    complexion = (form.get('cx_complexion') or '').strip().lower()

    talla_camisa = (form.get('cx_talla_camisa') or '').strip().upper()
    talla_pantalon = (form.get('cx_talla_pantalon') or '').strip()
    talla_calzado = (form.get('cx_talla_calzado') or '').strip()
    talla_sujetador = (form.get('cx_talla_sujetador') or '').strip().upper()

    pecho = _to_int(form.get('cx_pecho_cm'))
    cintura = _to_int(form.get('cx_cintura_cm'))
    cadera = _to_int(form.get('cx_cadera_cm'))

    estilos = form.getlist('cx_estilos_preferidos') or []
    colores = form.getlist('cx_colores_favoritos') or []

    hay_algo = any([
        altura is not None, peso is not None, complexion, talla_camisa,
        talla_pantalon, talla_calzado, talla_sujetador,
        pecho is not None, cintura is not None, cadera is not None,
        estilos, colores,
    ])

    if not hay_algo:
        return None

    return {
        'altura_cm': altura, 'peso_kg': peso,
        'complexion': complexion or None,
        'talla_camisa': talla_camisa or None,
        'talla_pantalon': talla_pantalon or None,
        'talla_calzado': talla_calzado or None,
        'talla_sujetador': talla_sujetador or None,
        'medidas': {'pecho_cm': pecho, 'cintura_cm': cintura, 'cadera_cm': cadera},
        'estilos_preferidos': estilos,
        'colores_favoritos': colores,
        'actualizado': datetime.now(timezone.utc),
    }


# ================================================================
# HELPER: OBTENER USUARIO ACTUAL DESDE LA SESIÓN
# ================================================================

def _get_usuario_actual():
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        db = current_app.db
        return db.usuarios.find_one({'_id': ObjectId(user_id)})
    except Exception:
        return None


# ================================================================
# ⭐ MONEDERO — HELPERS INTERNOS
# ================================================================
# Pequeños helpers que reutilizan las colecciones del monedero
# sin depender del controlador específico. Útiles para el dashboard
# y para cualquier vista que necesite datos agregados.

def _monedero_saldo_total():
    """Suma todos los saldos del monedero (saldo en circulación)."""
    try:
        db = current_app.db
        pipeline = [
            {'$group': {'_id': None, 'total': {'$sum': '$saldo'}}}
        ]
        resultado = list(db.monedero.aggregate(pipeline))
        return float(resultado[0]['total']) if resultado else 0.0
    except Exception as e:
        print(f"⚠️ [_monedero_saldo_total] Error: {e}", file=sys.stderr)
        return 0.0


def _monedero_contar_activos():
    """Cuenta monederos NO bloqueados."""
    try:
        db = current_app.db
        return db.monedero.count_documents({
            '$or': [
                {'bloqueado': False},
                {'bloqueado': {'$exists': False}},
            ]
        })
    except Exception:
        return 0


def _monedero_contar_bloqueados():
    """Cuenta monederos bloqueados."""
    try:
        db = current_app.db
        return db.monedero.count_documents({'bloqueado': True})
    except Exception:
        return 0


def _monedero_movimientos_hoy():
    """Cuenta movimientos del monedero creados hoy (UTC)."""
    try:
        db = current_app.db
        hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        pipeline = [
            {'$unwind': '$movimientos'},
            {'$match': {'movimientos.fecha': {'$gte': hoy}}},
            {'$count': 'total'},
        ]
        resultado = list(db.monedero.aggregate(pipeline))
        return int(resultado[0]['total']) if resultado else 0
    except Exception:
        return 0


# ================================================================
# FUNCIÓN PARA ENVIAR CORREO CON smtplib
# ================================================================

def enviar_correo_smtp(destinatario, asunto, contenido_html):
    try:
        smtp_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('MAIL_PORT', 587))
        username = os.getenv('MAIL_USERNAME')
        password_mail = os.getenv('MAIL_PASSWORD')
        sender = os.getenv('MAIL_DEFAULT_SENDER', username)

        if not username or not password_mail:
            print("❌ Faltan credenciales de correo en .env", file=sys.stderr)
            return False

        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = destinatario
        msg['Subject'] = asunto

        text_part = MIMEText(contenido_html.replace('<br>', '\n').replace('<p>', '').replace('</p>', ''), 'plain')
        html_part = MIMEText(contenido_html, 'html')
        msg.attach(text_part)
        msg.attach(html_part)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password_mail)
        server.send_message(msg)
        server.quit()
        return True

    except Exception as e:
        print(f"❌ ERROR en enviar_correo_smtp: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


# ================================================================
# CRUD USUARIOS
# ================================================================

def lista_usuarios():
    usuarios = UsuarioModel.obtener_todos()
    edit_id = request.args.get('edit_id')
    return render_template('admin/usuarios.html', usuarios=usuarios, edit_id=edit_id)


def ver_usuario(id):
    usuarios = UsuarioModel.obtener_todos()
    usuario_seleccionado = UsuarioModel.obtener_por_id(id)
    return render_template('admin/usuarios.html',
                           usuarios=usuarios,
                           usuario_seleccionado=usuario_seleccionado)


def agregar_usuario():
    try:
        data = {
            "nombre": request.form.get('nombre', '').strip(),
            "apellido_paterno": request.form.get('apellido_paterno', '').strip(),
            "apellido_materno": request.form.get('apellido_materno', '').strip(),
            "email": request.form.get('email', '').strip(),
            "telefono": request.form.get('telefono', '').strip(),
            "fecha_nacimiento": request.form.get('fecha_nacimiento', ''),
            "sexo": normalizar_genero(request.form.get('genero', 'Indefinido')),
            "rol": request.form.get('rol', 'cliente'),
            "password": request.form.get('password', ''),
            "foto": None,
            "direcciones": [],
            "confirmado": False,
            "activo": True
        }

        if not data['nombre']:
            flash('El nombre es obligatorio', 'danger')
            return redirect(url_for('web.lista_usuarios'))
        if not data['email']:
            flash('El email es obligatorio', 'danger')
            return redirect(url_for('web.lista_usuarios'))
        if not data['password'] or len(data['password']) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('web.lista_usuarios'))
        if UsuarioModel.obtener_por_email(data['email']):
            flash('Este email ya está registrado', 'danger')
            return redirect(url_for('web.lista_usuarios'))

        file = request.files.get('foto')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER')
            if not upload_folder:
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            file.save(os.path.join(upload_folder, filename))
            data['foto'] = filename

        token = secrets.token_urlsafe(32)
        data['token_confirmacion'] = token
        data['token_expira'] = datetime.now(timezone.utc) + timedelta(days=1)

        UsuarioModel.crear_usuario(data)

        confirm_url = url_for('web.confirmar_email', token=token, _external=True)
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
            <p>Hola {data['nombre']}, gracias por registrarte en <strong>ORION SYSTEM</strong>.</p>
            <p>Para activar tu cuenta, presiona el siguiente botón:</p>
            <a href="{confirm_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Activar Cuenta</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Este enlace expirará en 1 hora.</p>
        </div>
        """
        if enviar_correo_smtp(data['email'], "¡Bienvenido a ORION SYSTEM!", html_content):
            flash('Usuario creado correctamente. Se ha enviado un correo de confirmación.', 'success')
        else:
            flash('Usuario creado, pero no se pudo enviar el correo de confirmación.', 'warning')

        return redirect(url_for('web.lista_usuarios'))

    except Exception as e:
        flash(f'Error al crear usuario: {str(e)}', 'danger')
        return redirect(url_for('web.lista_usuarios'))


def editar_usuario(id):
    try:
        usuario_actual = UsuarioModel.obtener_por_id(id)
        if not usuario_actual:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('web.lista_usuarios'))

        seccion = (request.form.get('seccion') or 'personal').strip().lower()

        if seccion == 'complexion':
            complexion_nueva = _extraer_complexion_del_form()
            if complexion_nueva is not None:
                resultado = UsuarioModel.actualizar_usuario(id, {'complexion': complexion_nueva})
                if resultado and resultado.modified_count > 0:
                    flash('Complexión actualizada correctamente', 'success')
                else:
                    flash('No se realizaron cambios en la complexión', 'info')
            else:
                flash('No se recibieron datos de complexión', 'warning')
            return redirect(url_for('web.lista_usuarios'))

        if seccion == 'intereses':
            categorias  = request.form.getlist('in_categorias') or []
            marcas      = request.form.getlist('in_marcas') or []
            actividades = request.form.getlist('in_actividades') or []
            ocasiones   = request.form.getlist('in_ocasiones') or []
            frecuencia  = (request.form.get('in_frecuencia') or '').strip() or None

            intereses = {
                'categorias':  [c for c in categorias if c],
                'marcas':      [m for m in marcas if m],
                'actividades': [a for a in actividades if a],
                'ocasiones':   [o for o in ocasiones if o],
                'frecuencia':  frecuencia,
                'actualizado': datetime.now(timezone.utc),
            }

            resultado = UsuarioModel.actualizar_usuario(id, {'intereses': intereses})
            if resultado and resultado.modified_count > 0:
                flash('Intereses actualizados correctamente', 'success')
            else:
                flash('No se realizaron cambios en los intereses', 'info')
            return redirect(url_for('web.lista_usuarios'))

        data = {
            "nombre": request.form.get('nombre', '').strip(),
            "apellido_paterno": request.form.get('apellido_paterno', '').strip(),
            "apellido_materno": request.form.get('apellido_materno', '').strip(),
            "email": request.form.get('email', '').strip(),
            "telefono": request.form.get('telefono', '').strip(),
            "fecha_nacimiento": request.form.get('fecha_nacimiento', ''),
            "sexo": normalizar_genero(request.form.get('genero', 'Indefinido')),
            "rol": request.form.get('rol', 'cliente'),
        }

        if not data['nombre']:
            flash('El nombre es obligatorio', 'danger')
            return redirect(url_for('web.lista_usuarios'))
        if not data['email']:
            flash('El email es obligatorio', 'danger')
            return redirect(url_for('web.lista_usuarios'))

        if data['email'] != usuario_actual.get('email'):
            if UsuarioModel.obtener_por_email(data['email']):
                flash('Este email ya está registrado por otro usuario', 'danger')
                return redirect(url_for('web.lista_usuarios'))

        password = request.form.get('password', '')
        if password and len(password) >= 6:
            data['password'] = password
        elif password and len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('web.lista_usuarios'))

        file = request.files.get('foto')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER')
            if not upload_folder:
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            file.save(os.path.join(upload_folder, filename))
            data['foto'] = filename
        else:
            if 'foto' not in data:
                data['foto'] = usuario_actual.get('foto')

        if 'activo' in request.form:
            data['activo'] = True
        elif seccion == 'personal':
            if 'activo' not in request.form and request.form.get('_tiene_activo'):
                data['activo'] = False

        resultado = UsuarioModel.actualizar_usuario(id, data)

        if resultado and resultado.modified_count > 0:
            flash('Usuario actualizado correctamente', 'success')
        else:
            usuario_actualizado = UsuarioModel.obtener_por_id(id)
            if usuario_actualizado:
                cambios = False
                for key in ['nombre', 'apellido_paterno', 'apellido_materno', 'email', 'telefono', 'rol']:
                    if usuario_actual.get(key) != usuario_actualizado.get(key):
                        cambios = True
                        break
                if cambios:
                    flash('Usuario actualizado correctamente', 'success')
                else:
                    flash('No se realizaron cambios', 'info')
            else:
                flash('No se realizaron cambios', 'info')

        return redirect(url_for('web.lista_usuarios'))

    except Exception as e:
        current_app.logger.error(f'[editar_usuario] ERROR: {e}')
        flash(f'Error al actualizar usuario: {str(e)}', 'danger')
        return redirect(url_for('web.lista_usuarios'))


def admin_guardar_intereses(usuario_id):
    try:
        if 'user_id' not in session:
            flash('Debes iniciar sesión', 'danger')
            return redirect(url_for('web.login'))

        db = current_app.db
        admin_actual = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
        if not admin_actual or normalizar_rol(admin_actual.get('rol')) != 'admin':
            flash('No tienes permisos para esta acción', 'danger')
            return redirect(url_for('web.raiz_tienda'))

        usuario = UsuarioModel.obtener_por_id(usuario_id)
        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('web.lista_usuarios'))

        categorias  = request.form.getlist('in_categorias') or []
        marcas      = request.form.getlist('in_marcas') or []
        actividades = request.form.getlist('in_actividades') or []
        ocasiones   = request.form.getlist('in_ocasiones') or []
        frecuencia  = (request.form.get('in_frecuencia') or '').strip() or None

        intereses = {
            'categorias':  [c for c in categorias if c],
            'marcas':      [m for m in marcas if m],
            'actividades': [a for a in actividades if a],
            'ocasiones':   [o for o in ocasiones if o],
            'frecuencia':  frecuencia,
            'actualizado': datetime.now(timezone.utc),
        }

        resultado = UsuarioModel.actualizar_usuario(usuario_id, {'intereses': intereses})

        if resultado and resultado.modified_count > 0:
            flash('Intereses del usuario actualizados correctamente', 'success')
        else:
            flash('No se realizaron cambios en los intereses', 'info')

    except Exception as e:
        current_app.logger.error(f'[admin_guardar_intereses] ERROR: {e}')
        flash(f'Error al guardar intereses: {str(e)}', 'danger')

    return redirect(url_for('web.lista_usuarios'))


def borrar_usuario(id):
    try:
        usuario = UsuarioModel.obtener_por_id(id)
        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('web.lista_usuarios'))
        UsuarioModel.eliminar_usuario(id)
        flash('Usuario eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar usuario: {str(e)}', 'danger')
    return redirect(url_for('web.lista_usuarios'))


# ================================================================
# CONFIRMACIÓN DE CUENTA
# ================================================================

def confirmar_cuenta(token):
    db = current_app.db
    usuario = db.usuarios.find_one({'token_confirmacion': token})
    if not usuario:
        flash('Enlace de confirmación inválido o expirado.', 'danger')
        return redirect(url_for('web.login'))

    expira = usuario.get('token_expira')
    if expira and expira < datetime.now(timezone.utc):
        flash('El enlace de confirmación ha expirado. Solicita uno nuevo.', 'danger')
        return redirect(url_for('web.login'))

    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'confirmado': True, 'token_confirmacion': None, 'token_expira': None}}
    )
    flash('¡Cuenta confirmada exitosamente! Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('web.login'))


def reenviar_confirmacion():
    email = request.form.get('email', '').strip()
    if not email:
        flash('Debes proporcionar un email.', 'danger')
        return redirect(url_for('web.login'))

    db = current_app.db
    usuario = db.usuarios.find_one({'email': email})
    if not usuario:
        flash('No existe un usuario con ese email.', 'danger')
        return redirect(url_for('web.login'))

    if usuario.get('confirmado', False):
        flash('Este usuario ya está confirmado. Puedes iniciar sesión.', 'info')
        return redirect(url_for('web.login'))

    token = secrets.token_urlsafe(32)
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'token_confirmacion': token,
            'token_expira': datetime.now(timezone.utc) + timedelta(days=1)
        }}
    )

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
        flash('Se ha reenviado el correo de confirmación a tu email.', 'success')
    else:
        flash('Error al reenviar el correo. Intenta nuevamente.', 'danger')

    return render_template('auth/confirmacion_pendiente.html', email=email)


# ================================================================
# CRUD PERFIL
# ================================================================

def actualizar_perfil():
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "danger")
        return redirect(url_for('web.login'))

    usuario_id = session['user_id']

    datos_actualizados = {
        "nombre": request.form.get('nombre', '').strip(),
        "telefono": request.form.get('telefono', '').strip(),
        "apellido_paterno": request.form.get('apellido_paterno', '').strip(),
        "apellido_materno": request.form.get('apellido_materno', '').strip(),
        "fecha_nacimiento": request.form.get('fecha_nacimiento', ''),
        "sexo": normalizar_genero(request.form.get('genero', 'Indefinido'))
    }

    if 'foto' in request.files and request.files['foto'].filename != '':
        file = request.files['foto']
        filename = secure_filename(file.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if not upload_folder:
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        file.save(os.path.join(upload_folder, filename))
        datos_actualizados['foto'] = filename

    UsuarioModel.actualizar(usuario_id, datos_actualizados)
    session['nombre'] = datos_actualizados.get('nombre', session.get('nombre'))
    flash("Perfil actualizado correctamente.", "success")
    return redirect(url_for('web.perfil'))


# ================================================================
# CRUD DIRECCIONES - ADMIN
# ================================================================

def agregar_direccion(usuario_id):
    try:
        data = {
            "calle": request.form.get('calle', '').strip(),
            "numero": request.form.get('numero', '').strip(),
            "colonia": request.form.get('colonia', '').strip(),
            "cp": request.form.get('cp', '').strip(),
            "ciudad": request.form.get('ciudad', '').strip(),
            "estado": request.form.get('estado', '').strip(),
            "referencias": request.form.get('referencias', '').strip(),
            "nombre": request.form.get('nombre', '').strip(),
            "predeterminada": request.form.get('predeterminada') == '1'
        }

        if not data['calle']:
            flash('La calle es obligatoria', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['numero']:
            flash('El número es obligatorio', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['cp']:
            flash('El CP es obligatorio', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['colonia']:
            flash('La colonia es obligatoria', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        UsuarioModel.agregar_direccion(usuario_id, data)
        flash('Dirección agregada correctamente', 'success')

        usuario = UsuarioModel.obtener_por_id(usuario_id)
        if not usuario:
            return redirect(url_for('web.lista_usuarios'))

        if session.get('rol') == 'admin':
            return redirect(url_for('web.lista_usuarios', edit_id=usuario_id))
        else:
            return redirect(url_for('web.perfil'))

    except Exception as e:
        flash(f'Error al agregar dirección: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('web.lista_usuarios'))


def editar_direccion(usuario_id, direccion_id):
    try:
        data = {
            "calle": request.form.get('calle', '').strip(),
            "numero": request.form.get('numero', '').strip(),
            "colonia": request.form.get('colonia', '').strip(),
            "cp": request.form.get('cp', '').strip(),
            "ciudad": request.form.get('ciudad', '').strip(),
            "estado": request.form.get('estado', '').strip(),
            "referencias": request.form.get('referencias', '').strip(),
            "nombre": request.form.get('nombre', '').strip(),
            "predeterminada": request.form.get('predeterminada') == '1'
        }

        if not data['calle']:
            flash('La calle es obligatoria', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['numero']:
            flash('El número es obligatorio', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['cp']:
            flash('El CP es obligatorio', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))
        if not data['colonia']:
            flash('La colonia es obligatoria', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        try:
            dir_id = int(direccion_id)
        except ValueError:
            flash('ID de dirección inválido', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        resultado = UsuarioModel.editar_direccion(usuario_id, dir_id, data)
        if resultado and resultado.modified_count > 0:
            flash('Dirección actualizada correctamente', 'success')
        else:
            flash('No se realizaron cambios en la dirección', 'info')

    except Exception as e:
        flash(f'Error al editar dirección: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('web.lista_usuarios'))


def establecer_predeterminada(usuario_id, direccion_id):
    try:
        usuario = UsuarioModel.obtener_por_id(usuario_id)
        if not usuario or not usuario.get('direcciones'):
            flash('Usuario o dirección no encontrada', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        direcciones = usuario.get('direcciones', [])
        try:
            dir_id = int(direccion_id)
        except ValueError:
            flash('ID de dirección inválido', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        if dir_id >= len(direcciones):
            flash('Dirección no encontrada', 'danger')
            return redirect(request.referrer or url_for('web.lista_usuarios'))

        for d in direcciones:
            d['predeterminada'] = False
        direcciones[dir_id]['predeterminada'] = True

        resultado = UsuarioModel.actualizar_usuario(usuario_id, {'direcciones': direcciones})
        if resultado.modified_count > 0:
            flash('Dirección predeterminada actualizada', 'success')
        else:
            flash('No se realizaron cambios', 'info')

    except Exception as e:
        flash(f'Error al establecer dirección predeterminada: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('web.lista_usuarios'))


def borrar_direccion(usuario_id, direccion_id):
    try:
        resultado = UsuarioModel.borrar_direccion(usuario_id, direccion_id)
        if resultado and resultado.modified_count > 0:
            flash('Dirección eliminada correctamente', 'success')
        else:
            flash('No se pudo eliminar la dirección', 'danger')
    except Exception as e:
        flash(f'Error al eliminar dirección: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('web.lista_usuarios'))


def obtener_direcciones_usuario(usuario_id):
    usuario = UsuarioModel.obtener_por_id(usuario_id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    direcciones = usuario.get('direcciones', [])
    for d in direcciones:
        if '_id' in d:
            d['_id'] = str(d['_id'])

    return jsonify({'direcciones': direcciones, 'success': True})


def obtener_direccion_predeterminada(usuario_id):
    usuario = UsuarioModel.obtener_por_id(usuario_id)
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    direccion = UsuarioModel.obtener_direccion_predeterminada(usuario_id)
    if direccion and '_id' in direccion:
        direccion['_id'] = str(direccion['_id'])

    return jsonify({'direccion': direccion, 'success': True})


# ================================================================
# CRUD DIRECCIONES - CLIENTE
# ================================================================

def cliente_agregar_direccion():
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Debes iniciar sesión', 'danger')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        nueva_dir = {
            'nombre': (request.form.get('nombre') or '').strip(),
            'calle': (request.form.get('calle') or '').strip(),
            'numero': (request.form.get('numero') or '').strip(),
            'cp': (request.form.get('cp') or '').strip(),
            'colonia': (request.form.get('colonia') or '').strip(),
            'ciudad': (request.form.get('ciudad') or '').strip(),
            'estado': (request.form.get('estado') or '').strip(),
            'referencias': (request.form.get('referencias') or '').strip(),
            'predeterminada': bool(request.form.get('predeterminada')),
            'created_at': datetime.now(timezone.utc),
        }

        if not nueva_dir['calle'] or not nueva_dir['numero'] or not nueva_dir['cp'] or not nueva_dir['colonia']:
            flash('Completa los campos obligatorios (calle, número, CP y colonia)', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        direcciones = usuario.get('direcciones') or []

        if len(direcciones) == 0:
            nueva_dir['predeterminada'] = True

        if nueva_dir['predeterminada']:
            for d in direcciones:
                d['predeterminada'] = False

        direcciones.append(nueva_dir)

        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {'direcciones': direcciones, 'updated_at': datetime.now(timezone.utc)}}
        )
        flash('Dirección agregada correctamente', 'success')
    except Exception as e:
        current_app.logger.error(f'Error cliente_agregar_direccion: {e}')
        flash('Error al guardar la dirección', 'danger')

    return redirect(url_for('web.perfil') + '#tab-direcciones')


def cliente_editar_direccion(direccion_id):
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Debes iniciar sesión', 'danger')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        try:
            dir_id = int(direccion_id)
        except (ValueError, TypeError):
            flash('ID de dirección inválido', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        direcciones = usuario.get('direcciones') or []
        if dir_id < 0 or dir_id >= len(direcciones):
            flash('Dirección no encontrada', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        dir_actual = direcciones[dir_id]
        es_predeterminada = bool(request.form.get('predeterminada'))

        direcciones[dir_id] = {
            'nombre': (request.form.get('nombre') or '').strip(),
            'calle': (request.form.get('calle') or '').strip(),
            'numero': (request.form.get('numero') or '').strip(),
            'cp': (request.form.get('cp') or '').strip(),
            'colonia': (request.form.get('colonia') or '').strip(),
            'ciudad': (request.form.get('ciudad') or '').strip(),
            'estado': (request.form.get('estado') or '').strip(),
            'referencias': (request.form.get('referencias') or '').strip(),
            'predeterminada': es_predeterminada,
            'created_at': dir_actual.get('created_at', datetime.now(timezone.utc)),
            'updated_at': datetime.now(timezone.utc),
        }

        if es_predeterminada:
            for i, d in enumerate(direcciones):
                if i != dir_id:
                    d['predeterminada'] = False

        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {'direcciones': direcciones, 'updated_at': datetime.now(timezone.utc)}}
        )
        flash('Dirección actualizada correctamente', 'success')
    except Exception as e:
        current_app.logger.error(f'Error cliente_editar_direccion: {e}')
        flash('Error al actualizar la dirección', 'danger')

    return redirect(url_for('web.perfil') + '#tab-direcciones')


def cliente_establecer_predeterminada(direccion_id):
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Debes iniciar sesión', 'danger')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        try:
            dir_id = int(direccion_id)
        except (ValueError, TypeError):
            flash('ID de dirección inválido', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        direcciones = usuario.get('direcciones') or []
        if dir_id < 0 or dir_id >= len(direcciones):
            flash('Dirección no encontrada', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        for i, d in enumerate(direcciones):
            d['predeterminada'] = (i == dir_id)

        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {'direcciones': direcciones, 'updated_at': datetime.now(timezone.utc)}}
        )
        flash('Dirección predeterminada actualizada', 'success')
    except Exception as e:
        current_app.logger.error(f'Error cliente_establecer_predeterminada: {e}')
        flash('Error al actualizar la dirección predeterminada', 'danger')

    return redirect(url_for('web.perfil') + '#tab-direcciones')


def cliente_borrar_direccion(direccion_id):
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Debes iniciar sesión', 'danger')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        try:
            dir_id = int(direccion_id)
        except (ValueError, TypeError):
            flash('ID de dirección inválido', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        direcciones = usuario.get('direcciones') or []
        if dir_id < 0 or dir_id >= len(direcciones):
            flash('Dirección no encontrada', 'danger')
            return redirect(url_for('web.perfil') + '#tab-direcciones')

        eliminada = direcciones.pop(dir_id)

        if eliminada.get('predeterminada') and direcciones:
            direcciones[0]['predeterminada'] = True

        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {'direcciones': direcciones, 'updated_at': datetime.now(timezone.utc)}}
        )
        flash('Dirección eliminada', 'success')
    except Exception as e:
        current_app.logger.error(f'Error cliente_borrar_direccion: {e}')
        flash('Error al eliminar la dirección', 'danger')

    return redirect(url_for('web.perfil') + '#tab-direcciones')


# ================================================================
# 2FA
# ================================================================

def estado_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    dos_fa = usuario.get('2fa', {}) or {}
    fecha = dos_fa.get('fecha_activacion')
    return jsonify({
        'success': True,
        'habilitado': bool(dos_fa.get('habilitado', False)),
        'metodo': dos_fa.get('metodo', 'totp'),
        'telefono': dos_fa.get('telefono', usuario.get('telefono', '')),
        'codigos_respaldo_restantes': len(dos_fa.get('codigos_respaldo', []) or []),
        'fecha_activacion': fecha.isoformat() if hasattr(fecha, 'isoformat') else None,
    })


def _generar_codigos_respaldo(cantidad=8):
    return [secrets.token_hex(4).upper() for _ in range(cantidad)]


def iniciar_configuracion_2fa():
    import pyotp
    import qrcode

    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    if (usuario.get('2fa') or {}).get('habilitado'):
        return jsonify({'success': False, 'message': '2FA ya está habilitado. Desactívalo primero.'}), 400

    secreto = pyotp.random_base32()
    session['2fa_secreto_temporal'] = secreto

    issuer = 'ORION System'
    label = usuario.get('email', 'usuario')
    otp_uri = pyotp.totp.TOTP(secreto).provisioning_uri(name=label, issuer_name=issuer)

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(otp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return jsonify({
        'success': True,
        'secreto': secreto,
        'qr_base64': qr_base64,
        'uri': otp_uri,
    })


def confirmar_2fa():
    import pyotp

    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip()

    secreto = session.get('2fa_secreto_temporal')
    if not secreto:
        return jsonify({'success': False, 'message': 'No hay configuración pendiente'}), 400

    if not codigo or len(codigo) != 6:
        return jsonify({'success': False, 'message': 'Código inválido'}), 400

    totp = pyotp.TOTP(secreto)
    if not totp.verify(codigo, valid_window=1):
        return jsonify({'success': False, 'message': 'Código incorrecto. Intenta de nuevo.'}), 400

    codigos_respaldo = _generar_codigos_respaldo(8)

    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            '2fa': {
                'habilitado': True,
                'metodo': 'totp',
                'secreto': secreto,
                'codigos_respaldo': codigos_respaldo,
                'fecha_activacion': datetime.now(timezone.utc),
            },
            'updated_at': datetime.now(timezone.utc),
        }}
    )

    session.pop('2fa_secreto_temporal', None)

    return jsonify({
        'success': True,
        'message': '2FA activado correctamente',
        'codigos_respaldo': codigos_respaldo,
    })


def desactivar_2fa():
    import bcrypt

    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json() or {}
    password = data.get('password') or ''

    if not password:
        return jsonify({'success': False, 'message': 'Contraseña requerida'}), 400

    stored = usuario.get('password', '')
    try:
        if not bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
            return jsonify({'success': False, 'message': 'Contraseña incorrecta'}), 400
    except Exception:
        return jsonify({'success': False, 'message': 'Error al verificar contraseña'}), 500

    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$unset': {'2fa': ''}, '$set': {'updated_at': datetime.now(timezone.utc)}}
    )

    return jsonify({'success': True, 'message': '2FA desactivado correctamente'})


def regenerar_codigos_respaldo():
    import bcrypt

    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    if not (usuario.get('2fa') or {}).get('habilitado'):
        return jsonify({'success': False, 'message': '2FA no está habilitado'}), 400

    data = request.get_json() or {}
    password = data.get('password') or ''

    if not password:
        return jsonify({'success': False, 'message': 'Contraseña requerida'}), 400

    stored = usuario.get('password', '')
    try:
        if not bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')):
            return jsonify({'success': False, 'message': 'Contraseña incorrecta'}), 400
    except Exception:
        return jsonify({'success': False, 'message': 'Error al verificar contraseña'}), 500

    nuevos_codigos = _generar_codigos_respaldo(8)

    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            '2fa.codigos_respaldo': nuevos_codigos,
            'updated_at': datetime.now(timezone.utc),
        }}
    )

    return jsonify({
        'success': True,
        'message': 'Códigos de respaldo regenerados',
        'codigos_respaldo': nuevos_codigos,
    })


def usar_codigo_respaldo():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip().upper()

    dos_fa = usuario.get('2fa', {}) or {}
    codigos = dos_fa.get('codigos_respaldo', []) or []

    if codigo not in codigos:
        return jsonify({'success': False, 'message': 'Código de respaldo inválido'}), 400

    codigos.remove(codigo)
    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'2fa.codigos_respaldo': codigos, 'updated_at': datetime.now(timezone.utc)}}
    )

    return jsonify({
        'success': True,
        'message': 'Código de respaldo aceptado',
        'restantes': len(codigos),
    })


# ================================================================
# DASHBOARD
# ================================================================

def dashboard():
    db = current_app.db

    if 'user_id' not in session:
        flash('Inicia sesión para acceder al dashboard', 'warning')
        return redirect(url_for('web.login'))

    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))

    rol_normalizado = normalizar_rol(usuario.get('rol', 'cliente'))
    session['rol'] = rol_normalizado

    if rol_normalizado != 'admin':
        flash('No tienes permisos para acceder al dashboard', 'danger')
        return redirect(url_for('web.raiz_tienda'))

    total_usuarios = db.usuarios.count_documents({})
    total_productos = db.productos.count_documents({})
    total_pedidos = db.pedidos.count_documents({}) if 'pedidos' in db.list_collection_names() else 0

    hoy = datetime.now(timezone.utc)
    fecha_fin = hoy
    fecha_inicio = hoy - timedelta(days=30)

    resumen = VentaReporte.get_resumen_ventas(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

    total_ventas_correcto = resumen.get('total_monto', 0)
    total_unidades = resumen.get('total_unidades', 0)
    promedio_venta = resumen.get('promedio_venta', 0)
    ventas_mes = resumen.get('total_ventas', 0)

    mes_actual = datetime.now(timezone.utc).month
    año_actual = datetime.now(timezone.utc).year

    usuarios_mes = db.usuarios.count_documents({
        'created_at': {
            '$gte': datetime(año_actual, mes_actual, 1, tzinfo=timezone.utc),
            '$lt': datetime(año_actual, mes_actual + 1, 1, tzinfo=timezone.utc) if mes_actual < 12 else datetime(año_actual + 1, 1, 1, tzinfo=timezone.utc)
        }
    })

    productos_stock_bajo = db.productos.count_documents({'stock': {'$lt': 5}}) if 'productos' in db.list_collection_names() else 0
    pedidos_pendientes = db.pedidos.count_documents({'estado': 'pendiente'}) if 'pedidos' in db.list_collection_names() else 0

    # ⭐ MARKETPLACE: total de vendedores aprobados
    # Usamos $ne: False para incluir documentos sin el campo 'activo'
    try:
        total_vendedores = db['vendedores'].count_documents({
            'estado': 'aprobado',
            'activo': {'$ne': False},
        })
        print(f"🔍 [dashboard] total_vendedores={total_vendedores}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ [dashboard] Error contando vendedores: {e}", file=sys.stderr)
        total_vendedores = 0

    # ⭐ MONEDERO: métricas globales para las stat-cards del dashboard
    monedero_saldo_total     = _monedero_saldo_total()
    monedero_activos         = _monedero_contar_activos()
    monedero_bloqueados      = _monedero_contar_bloqueados()
    monedero_movimientos_hoy = _monedero_movimientos_hoy()
    print(f"🔍 [dashboard] monedero_saldo_total={monedero_saldo_total}", file=sys.stderr)
    print(f"🔍 [dashboard] monedero_activos={monedero_activos}", file=sys.stderr)
    print(f"🔍 [dashboard] monedero_bloqueados={monedero_bloqueados}", file=sys.stderr)
    print(f"🔍 [dashboard] monedero_movimientos_hoy={monedero_movimientos_hoy}", file=sys.stderr)

    meses_labels = []
    ventas_por_mes = []
    for i in range(5, -1, -1):
        mes = datetime.now(timezone.utc).month - i
        año = datetime.now(timezone.utc).year
        if mes <= 0:
            mes += 12
            año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses_labels.append(f'{nombre_mes} {año}')

        fecha_inicio_mes = datetime(año, mes, 1, tzinfo=timezone.utc)
        if mes == 12:
            fecha_fin_mes = datetime(año + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        else:
            fecha_fin_mes = datetime(año, mes + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)

        resumen_mes = VentaReporte.get_resumen_ventas(fecha_inicio=fecha_inicio_mes, fecha_fin=fecha_fin_mes)
        ventas_por_mes.append(resumen_mes.get('total_ventas', 0))

    return render_template('admin/dashboard.html',
                         total_usuarios=total_usuarios,
                         total_productos=total_productos,
                         total_pedidos=total_pedidos,
                         total_ventas_correcto=total_ventas_correcto,
                         total_unidades=total_unidades,
                         promedio_venta=promedio_venta,
                         ventas_mes=ventas_mes,
                         usuarios_mes=usuarios_mes,
                         productos_stock_bajo=productos_stock_bajo,
                         pedidos_pendientes=pedidos_pendientes,
                         total_vendedores=total_vendedores,
                         # ⭐ MONEDERO — stat cards del dashboard
                         monedero_saldo_total=monedero_saldo_total,
                         monedero_activos=monedero_activos,
                         monedero_bloqueados=monedero_bloqueados,
                         monedero_movimientos_hoy=monedero_movimientos_hoy,
                         meses_labels=meses_labels,
                         ventas_por_mes=ventas_por_mes,
                         datetime=datetime)


# ================================================================
# ANÁLISIS / IA
# ================================================================

def analisis():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total_usuarios = db.usuarios.count_documents({})
    total_productos = db.productos.count_documents({})
    total_categorias = db.categorias.count_documents({})
    productos_activos = db.productos.count_documents({"estado": "activo"})
    productos_inactivos = total_productos - productos_activos
    porcentaje_activos = round((productos_activos / total_productos * 100), 2) if total_productos > 0 else 0
    datos = {
        "total_usuarios": total_usuarios,
        "total_productos": total_productos,
        "total_categorias": total_categorias,
        "productos_activos": productos_activos,
        "productos_inactivos": productos_inactivos,
        "porcentaje_activos": porcentaje_activos
    }
    return render_template('admin/analisis.html', datos=datos)


def inteligencia():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    return render_template('admin/inteligencia.html')


def segmentacion_clientes():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    usuarios = list(db.usuarios.find({'rol': 'cliente'}))
    pedidos = list(db.pedidos.find()) if 'pedidos' in db.list_collection_names() else []
    vip = 0; frecuentes = 0; impulsivos = 0; inactivos = 0
    clientes_con_segmento = []
    masculino = 0; femenino = 0; indefinido = 0
    for usuario in usuarios:
        genero_raw = usuario.get('sexo') or usuario.get('genero') or 'Indefinido'
        genero = normalizar_genero(genero_raw)
        if genero == 'Masculino': masculino += 1
        elif genero == 'Femenino': femenino += 1
        else: indefinido += 1
        pedidos_usuario = [p for p in pedidos if str(p.get("usuario_id")) == str(usuario["_id"])]
        cantidad = len(pedidos_usuario)
        total_gastado = sum(float(p.get("total", 0)) for p in pedidos_usuario)
        if total_gastado >= 10000:
            segmento = "VIP"; vip += 1
        elif cantidad >= 5:
            segmento = "Frecuente"; frecuentes += 1
        elif cantidad >= 1:
            segmento = "Ocasional"; impulsivos += 1
        else:
            segmento = "Inactivo"; inactivos += 1
        clientes_con_segmento.append({
            "nombre": usuario.get("nombre", "Usuario"),
            "email": usuario.get("email", ""),
            "foto": usuario.get("foto"),
            "total_pedidos": cantidad,
            "total_gastado": total_gastado,
            "segmento": segmento
        })
    datos = {
        "vip": vip, "frecuentes": frecuentes, "impulsivos": impulsivos,
        "inactivos": inactivos, "total": len(usuarios),
        "fecha_actualizacion": datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')
    }
    generos = {'Masculino': masculino, 'Femenino': femenino, 'Indefinido': indefinido}
    return render_template('admin/segmentacion.html', datos=datos, clientes=clientes_con_segmento, generos=generos)


def prediccion_abandono():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total = db.usuarios.count_documents({})
    activos = 0; riesgo_medio = 0; riesgo_alto = 0
    usuarios = list(db.usuarios.find())
    pedidos = list(db.pedidos.find()) if 'pedidos' in db.list_collection_names() else []
    for usuario in usuarios:
        pedidos_usuario = [p for p in pedidos if str(p.get("usuario_id")) == str(usuario["_id"])]
        if len(pedidos_usuario) == 0:
            riesgo_alto += 1
            continue
        ultimo_pedido = pedidos_usuario[0].get("created_at")
        if ultimo_pedido:
            if isinstance(ultimo_pedido, datetime):
                dias = (datetime.now(timezone.utc) - ultimo_pedido).days
            else:
                try:
                    fecha_pedido = datetime.strptime(ultimo_pedido, "%Y-%m-%d")
                    dias = (datetime.now(timezone.utc) - fecha_pedido).days
                except:
                    dias = 999
            if dias <= 30: activos += 1
            elif dias <= 60: riesgo_medio += 1
            else: riesgo_alto += 1
    datos = {"activos": activos, "riesgo_medio": riesgo_medio, "riesgo_alto": riesgo_alto, "total": total}
    return render_template("admin/prediccion_abandono.html", datos=datos)


def prediccion_ventas():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total_ventas = db.ventas.count_documents({}) if 'ventas' in db.list_collection_names() else 0
    productos_vendidos = {}
    for venta in db.ventas.find() if 'ventas' in db.list_collection_names() else []:
        for producto in venta.get("productos", []):
            nombre = producto.get("nombre")
            if nombre not in productos_vendidos:
                productos_vendidos[nombre] = 0
            productos_vendidos[nombre] += int(producto.get("cantidad", 1))
    top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:5]
    meses = {"Enero": 0, "Febrero": 0, "Marzo": 0, "Abril": 0, "Mayo": 0, "Junio": 0,
             "Julio": 0, "Agosto": 0, "Septiembre": 0, "Octubre": 0, "Noviembre": 0, "Diciembre": 0}
    nombres_meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    for venta in db.ventas.find() if 'ventas' in db.list_collection_names() else []:
        fecha = venta.get("fecha")
        if fecha and isinstance(fecha, datetime):
            meses[nombres_meses[fecha.month - 1]] += 1
    temporada_alta = max(meses, key=meses.get)
    temporada_baja = min(meses, key=meses.get)
    stock_sugerido = []
    for producto in db.productos.find():
        vendidos = 0
        for venta in db.ventas.find() if 'ventas' in db.list_collection_names() else []:
            for item in venta.get("productos", []):
                if item.get("nombre") == producto.get("nombre"):
                    vendidos += int(item.get("cantidad", 1))
        sugerido = int(vendidos * 1.20)
        stock_sugerido.append({"nombre": producto.get("nombre"), "vendidos": vendidos, "sugerido": sugerido})
    datos = {"total_ventas": total_ventas, "top_productos": top_productos,
             "temporada_alta": temporada_alta, "temporada_baja": temporada_baja,
             "stock_sugerido": stock_sugerido[:5]}
    return render_template("admin/prediccion_ventas.html", datos=datos)


def deteccion_fraude():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    ventas = list(db.ventas.find()) if 'ventas' in db.list_collection_names() else []
    usuarios = list(db.usuarios.find())
    compras_sospechosas = 0; patrones_anomalos = 0; intentos_fraudulentos = 0
    for venta in ventas:
        if float(venta.get("total", 0)) >= 15000:
            compras_sospechosas += 1
    for usuario in usuarios:
        compras_usuario = [v for v in ventas if str(v.get("usuario_id")) == str(usuario["_id"])]
        if len(compras_usuario) >= 10:
            patrones_anomalos += 1
        if sum(float(v.get("total", 0)) for v in compras_usuario) >= 50000:
            intentos_fraudulentos += 1
    datos = {"compras_sospechosas": compras_sospechosas, "patrones_anomalos": patrones_anomalos,
             "intentos_fraudulentos": intentos_fraudulentos, "total_ventas": len(ventas)}
    return render_template("admin/deteccion_fraude.html", datos=datos)


# ================================================================
# RESEÑAS / FAVORITOS
# ================================================================

def agregar_opinion():
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "danger")
        return redirect(url_for('web.login'))
    archivos = request.files.getlist('fotos')
    lista_archivos = []
    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'resenas')
    os.makedirs(folder, exist_ok=True)
    for archivo in archivos:
        if archivo and archivo.filename:
            nombre_archivo = f"resena_{os.urandom(4).hex()}_{secure_filename(archivo.filename)}"
            archivo.save(os.path.join(folder, nombre_archivo))
            lista_archivos.append(nombre_archivo)
    data = {
        "_id": str(uuid.uuid4()),
        "producto_id": request.form.get('producto_id'),
        "usuario_id": session.get('user_id'),
        "usuario_nombre": session.get('nombre'),
        "calificacion": int(request.form.get('calificacion', 5)),
        "titulo": request.form.get('titulo', ''),
        "comentario": request.form.get('comentario', ''),
        "foto_path": lista_archivos,
        "fecha": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "compra_verificada": False,
        "votos_utiles": []
    }
    Resena.crear(data)
    return redirect(url_for('web.ver_detalle_producto', id=data['producto_id']))


def editar_opinion():
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "danger")
        return redirect(url_for('web.login'))
    opinion_id = request.form.get('opinion_id')
    producto_id = request.form.get('producto_id')
    cambios = {
        "titulo": request.form.get('titulo', ''),
        "comentario": request.form.get('comentario', ''),
        "calificacion": int(request.form.get('calificacion', 5))
    }
    eliminar_fotos = request.form.getlist('eliminar_foto')
    archivos = request.files.getlist('fotos')
    nuevas_fotos = []
    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'resenas')
    os.makedirs(folder, exist_ok=True)
    for archivo in archivos:
        if archivo and archivo.filename:
            nombre_archivo = f"resena_{os.urandom(4).hex()}_{secure_filename(archivo.filename)}"
            archivo.save(os.path.join(folder, nombre_archivo))
            nuevas_fotos.append(nombre_archivo)
    for foto in eliminar_fotos:
        ruta = os.path.join(folder, foto)
        if os.path.exists(ruta):
            os.remove(ruta)
    Resena.editar(opinion_id, session['user_id'], cambios, nuevas_fotos, eliminar_fotos)
    return redirect(url_for('web.ver_detalle_producto', id=producto_id))


def eliminar_opinion():
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "danger")
        return redirect(url_for('web.login'))
    opinion_id = request.form.get('opinion_id')
    producto_id = request.form.get('producto_id')
    Resena.eliminar(opinion_id, session['user_id'])
    return redirect(url_for('web.ver_detalle_producto', id=producto_id))


def marcar_util():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "No autenticado"}), 401
    body = request.get_json()
    opinion_id = body.get('opinion_id')
    user_id = session['user_id']
    total = Resena.toggle_voto_util(opinion_id, user_id)
    return jsonify({"success": True, "total": total})


def reportar_opinion():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "No autenticado"}), 401
    body = request.get_json()
    opinion_id = body.get('opinion_id')
    Resena.reportar(opinion_id)
    return jsonify({"success": True})


def listar_opiniones(producto_id):
    db = current_app.db
    try:
        producto = db.productos.find_one({'_id': ObjectId(producto_id)})
        if not producto:
            return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
        opiniones = list(db.opiniones.find({'producto_id': ObjectId(producto_id)}).sort('created_at', -1))
        for op in opiniones:
            op['_id'] = str(op['_id'])
            op['producto_id'] = str(op['producto_id'])
            op['usuario_id'] = str(op['usuario_id'])
            usuario = db.usuarios.find_one({'_id': ObjectId(op['usuario_id'])})
            op['usuario_nombre'] = usuario.get('nombre', 'Usuario') if usuario else op.get('usuario_nombre', 'Usuario')
        total_calificaciones = len(opiniones)
        promedio = 0
        if total_calificaciones > 0:
            suma = sum(op.get('calificacion', 0) for op in opiniones)
            promedio = round(suma / total_calificaciones, 1)
        return jsonify({
            'success': True,
            'opiniones': opiniones,
            'total': total_calificaciones,
            'promedio': promedio
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def lista_favoritos():
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus favoritos', 'warning')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        usuario_id = ObjectId(session['user_id'])
    except Exception:
        flash('Sesión inválida', 'danger')
        return redirect(url_for('web.login'))

    favs = list(db.favoritos.find({'usuario_id': usuario_id}).sort('created_at', -1))
    productos = []
    for fav in favs:
        try:
            producto = Producto.obtener_por_id(str(fav['producto_id']))
        except Exception:
            producto = None
        if producto:
            producto['_id'] = str(producto['_id'])
            productos.append(producto)
    return render_template('tienda/favoritos.html', productos=productos)


def agregar_favorito(producto_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    db = current_app.db
    try:
        usuario_id = ObjectId(session['user_id'])
        oid = ObjectId(producto_id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID inválido'}), 400

    existe = db.favoritos.find_one({'usuario_id': usuario_id, 'producto_id': oid})
    if not existe:
        db.favoritos.insert_one({
            'usuario_id': usuario_id,
            'producto_id': oid,
            'created_at': datetime.now(timezone.utc)
        })
    return jsonify({'success': True, 'message': 'Agregado a favoritos'})


def eliminar_favorito(producto_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    db = current_app.db
    try:
        usuario_id = ObjectId(session['user_id'])
        oid = ObjectId(producto_id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID inválido'}), 400

    db.favoritos.delete_one({'usuario_id': usuario_id, 'producto_id': oid})
    return jsonify({'success': True, 'message': 'Eliminado de favoritos'})


def toggle_favorito():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Debes iniciar sesión'}), 401

    db = current_app.db
    data = request.get_json(silent=True) or {}
    producto_id = data.get('producto_id')

    if not producto_id:
        return jsonify({'success': False, 'message': 'Falta producto_id'}), 400

    try:
        usuario_id = ObjectId(session['user_id'])
        oid = ObjectId(producto_id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID inválido'}), 400

    existe = db.favoritos.find_one({
        'usuario_id': usuario_id,
        'producto_id': oid
    })

    if existe:
        db.favoritos.delete_one({'_id': existe['_id']})
        return jsonify({
            'success': True,
            'es_favorito': False,
            'message': 'Eliminado de favoritos'
        })

    db.favoritos.insert_one({
        'usuario_id': usuario_id,
        'producto_id': oid,
        'created_at': datetime.now(timezone.utc)
    })
    return jsonify({
        'success': True,
        'es_favorito': True,
        'message': 'Agregado a favoritos'
    })


# ================================================================
# ADMIN - FUNCIONES ADICIONALES
# ================================================================

def editar_usuario_admin(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    data = request.get_json() or request.form
    update_data = {}
    campos = ['nombre', 'email', 'telefono', 'rol', 'activo']
    for campo in campos:
        if data.get(campo) is not None:
            update_data[campo] = data.get(campo)
    update_data['updated_at'] = datetime.now(timezone.utc)
    db.usuarios.update_one({'_id': ObjectId(id)}, {'$set': update_data})
    return jsonify({'success': True, 'message': 'Usuario actualizado'})


def eliminar_usuario_admin(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    if str(id) == str(session['user_id']):
        return jsonify({'success': False, 'message': 'No puedes eliminar tu propia cuenta'}), 400
    db.usuarios.delete_one({'_id': ObjectId(id)})
    return jsonify({'success': True, 'message': 'Usuario eliminado'})


def toggle_usuario(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    target = db.usuarios.find_one({'_id': ObjectId(id)})
    if not target:
        return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404
    nuevo_estado = not target.get('activo', True)
    db.usuarios.update_one({'_id': ObjectId(id)}, {'$set': {'activo': nuevo_estado, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True, 'message': f'Usuario {"activado" if nuevo_estado else "desactivado"}'})


def asignar_rol(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    data = request.get_json() or request.form
    rol = data.get('rol')
    if rol not in ['usuario', 'admin', 'vendedor', 'cliente']:
        return jsonify({'success': False, 'message': 'Rol inválido'}), 400
    db.usuarios.update_one({'_id': ObjectId(id)}, {'$set': {'rol': rol, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True, 'message': f'Rol actualizado a {rol}'})


# ================================================================
# PÁGINAS ESTÁTICAS
# ================================================================

def contacto():
    if request.method == 'POST':
        db = current_app.db
        mensaje = {
            'nombre': request.form.get('nombre', '').strip(),
            'email': request.form.get('email', '').strip(),
            'asunto': request.form.get('asunto', '').strip(),
            'mensaje': request.form.get('mensaje', '').strip(),
            'created_at': datetime.now(timezone.utc)
        }
        db.mensajes_contacto.insert_one(mensaje)
        flash('Mensaje enviado correctamente. Te contactaremos pronto.', 'success')
        return redirect(url_for('web.contacto'))
    return render_template('tienda/contacto.html')


def terminos(): return render_template('tienda/terminos.html')
def privacidad(): return render_template('tienda/privacidad.html')
def faq(): return render_template('tienda/faq.html')
def devoluciones(): return render_template('tienda/devoluciones.html')
def nosotros(): return render_template('tienda/nosotros.html')


# ================================================================
# MANTENIMIENTO
# ================================================================

def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()})


def limpiar_cache():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    return jsonify({'success': True, 'message': 'Caché limpiado correctamente'})


def migraciones():
    if 'user_id' not in session:
        flash('No autorizado', 'danger')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No autorizado', 'danger')
        return redirect(url_for('web.login'))
    if request.method == 'POST':
        flash('Migraciones ejecutadas correctamente', 'success')
        return redirect(url_for('web.migraciones'))
    return render_template('admin/migraciones.html')


# ================================================================
# API
# ================================================================

def api_usuario():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if usuario:
        usuario['_id'] = str(usuario['_id'])
        usuario.pop('password', None)
        return jsonify(usuario)
    return jsonify({'error': 'Usuario no encontrado'}), 404


# ================================================================
# CONFIGURACIÓN
# ================================================================

def configuracion():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    if request.method == 'POST':
        config = {
            'nombre_tienda': request.form.get('nombre_tienda', '').strip(),
            'email_tienda': request.form.get('email_tienda', '').strip(),
            'telefono_tienda': request.form.get('telefono_tienda', '').strip(),
            'direccion_tienda': request.form.get('direccion_tienda', '').strip(),
            'moneda': request.form.get('moneda', 'MXN'),
            'updated_at': datetime.now(timezone.utc)
        }
        db.configuracion.update_one({'_id': 'general'}, {'$set': config}, upsert=True)
        flash('Configuración guardada correctamente', 'success')
        return redirect(url_for('web.configuracion'))
    config = db.configuracion.find_one({'_id': 'general'})
    return render_template('admin/configuracion.html', config=config)


def configuracion_envios():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    if request.method == 'POST':
        config = {
            'costo_envio': float(request.form.get('costo_envio', 0)),
            'costo_envio_gratis_sobre': float(request.form.get('costo_envio_gratis_sobre', 0)),
            'tiempo_entrega_dias': int(request.form.get('tiempo_entrega_dias', 5)),
            'marcas_envio': request.form.getlist('marcas_envio'),
            'updated_at': datetime.now(timezone.utc)
        }
        db.configuracion.update_one({'_id': 'envios'}, {'$set': config}, upsert=True)
        flash('Configuración de envíos guardada', 'success')
        return redirect(url_for('web.configuracion_envios'))
    config = db.configuracion.find_one({'_id': 'envios'})
    return render_template('admin/configuracion_envios.html', config=config)


def configuracion_pagos():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    if request.method == 'POST':
        config = {
            'metodos_pago': request.form.getlist('metodos_pago'),
            'moneda': request.form.get('moneda', 'MXN'),
            'iva_porcentaje': float(request.form.get('iva_porcentaje', 16)),
            'stripe_key': request.form.get('stripe_key', ''),
            'paypal_client_id': request.form.get('paypal_client_id', ''),
            'paypal_secret': request.form.get('paypal_secret', ''),
            'updated_at': datetime.now(timezone.utc)
        }
        db.configuracion.update_one({'_id': 'pagos'}, {'$set': config}, upsert=True)
        flash('Configuración de pagos guardada', 'success')
        return redirect(url_for('web.configuracion_pagos'))
    config = db.configuracion.find_one({'_id': 'pagos'})
    return render_template('admin/configuracion_pagos.html', config=config)


def configuracion_impuestos():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    if request.method == 'POST':
        config = {
            'iva_porcentaje': float(request.form.get('iva_porcentaje', 16)),
            'ieps_porcentaje': float(request.form.get('ieps_porcentaje', 0)),
            'retencion_isr': float(request.form.get('retencion_isr', 0)),
            'updated_at': datetime.now(timezone.utc)
        }
        db.configuracion.update_one({'_id': 'impuestos'}, {'$set': config}, upsert=True)
        flash('Configuración de impuestos guardada', 'success')
        return redirect(url_for('web.configuracion_impuestos'))
    config = db.configuracion.find_one({'_id': 'impuestos'})
    return render_template('admin/configuracion_impuestos.html', config=config)


def configuracion_tiendas():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    if request.method == 'POST':
        tiendas = []
        nombres = request.form.getlist('tienda_nombre[]')
        direcciones = request.form.getlist('tienda_direccion[]')
        telefonos = request.form.getlist('tienda_telefono[]')
        for i in range(len(nombres)):
            if nombres[i] and nombres[i].strip():
                tiendas.append({
                    'nombre': nombres[i].strip(),
                    'direccion': direcciones[i].strip() if i < len(direcciones) else '',
                    'telefono': telefonos[i].strip() if i < len(telefonos) else '',
                    'activa': True
                })
        config = {'tiendas': tiendas, 'updated_at': datetime.now(timezone.utc)}
        db.configuracion.update_one({'_id': 'tiendas'}, {'$set': config}, upsert=True)
        flash('Configuración de tiendas guardada', 'success')
        return redirect(url_for('web.configuracion_tiendas'))
    config = db.configuracion.find_one({'_id': 'tiendas'})
    tiendas = config.get('tiendas', []) if config else []
    return render_template('admin/configuracion_tiendas.html', tiendas=tiendas)


# ================================================================
# REPORTES
# ================================================================

def reportes():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder a reportes', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos para acceder a reportes', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total_ventas = db.ventas.count_documents({}) if 'ventas' in db.list_collection_names() else 0
    total_usuarios = db.usuarios.count_documents({})
    total_productos = db.productos.count_documents({})
    meses = []
    ventas_por_mes = []
    for i in range(5, -1, -1):
        mes = datetime.now(timezone.utc).month - i
        año = datetime.now(timezone.utc).year
        if mes <= 0:
            mes += 12
            año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses.append(f'{nombre_mes} {año}')
        count = db.ventas.count_documents({'fecha': {'$regex': f'{año}-{str(mes).zfill(2)}'}}) if 'ventas' in db.list_collection_names() else 0
        ventas_por_mes.append(count)
    productos_vendidos = []
    if 'ventas' in db.list_collection_names():
        pipeline = [{'$unwind': '$productos'}, {'$group': {'_id': '$productos.nombre', 'total': {'$sum': '$productos.cantidad'}}}, {'$sort': {'total': -1}}, {'$limit': 10}]
        productos_vendidos = list(db.ventas.aggregate(pipeline))
    return render_template('admin/reportes.html', total_ventas=total_ventas, total_usuarios=total_usuarios, total_productos=total_productos, meses=meses, ventas_por_mes=ventas_por_mes, productos_vendidos=productos_vendidos)


def reporte_ventas():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder a reportes', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    estado = request.args.get('estado', '')
    filtro = {}
    if fecha_inicio:
        try: filtro['fecha'] = {'$gte': datetime.strptime(fecha_inicio, '%Y-%m-%d')}
        except: pass
    if fecha_fin:
        try:
            if 'fecha' in filtro: filtro['fecha']['$lte'] = datetime.strptime(fecha_fin, '%Y-%m-%d')
            else: filtro['fecha'] = {'$lte': datetime.strptime(fecha_fin, '%Y-%m-%d')}
        except: pass
    if estado: filtro['estado'] = estado
    ventas = list(db.ventas.find(filtro).sort('fecha', -1)) if 'ventas' in db.list_collection_names() else []
    for v in ventas:
        v['_id'] = str(v['_id'])
        if v.get('usuario_id'):
            usuario_venta = db.usuarios.find_one({'_id': ObjectId(v['usuario_id'])})
            v['usuario_nombre'] = usuario_venta.get('nombre', 'Usuario') if usuario_venta else 'Desconocido'
    total_ventas = sum(v.get('total', 0) for v in ventas)
    return render_template('admin/reportes_ventas.html', ventas=ventas, total_ventas=total_ventas, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, estado=estado)


def reporte_usuarios():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder a reportes', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total_usuarios = db.usuarios.count_documents({})
    usuarios_activos = db.usuarios.count_documents({'activo': True})
    usuarios_inactivos = total_usuarios - usuarios_activos
    admins = db.usuarios.count_documents({'rol': 'admin'})
    vendedores = db.usuarios.count_documents({'rol': 'vendedor'})
    clientes = db.usuarios.count_documents({'rol': 'cliente'})
    meses = []; registros_por_mes = []
    for i in range(5, -1, -1):
        mes = datetime.now(timezone.utc).month - i
        año = datetime.now(timezone.utc).year
        if mes <= 0: mes += 12; año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses.append(f'{nombre_mes} {año}')
        count = db.usuarios.count_documents({'created_at': {'$regex': f'{año}-{str(mes).zfill(2)}'}})
        registros_por_mes.append(count)
    return render_template('admin/reportes_usuarios.html', total_usuarios=total_usuarios, usuarios_activos=usuarios_activos, usuarios_inactivos=usuarios_inactivos, admins=admins, vendedores=vendedores, clientes=clientes, meses=meses, registros_por_mes=registros_por_mes)


def reporte_productos():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder a reportes', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    total_productos = db.productos.count_documents({})
    productos_activos = db.productos.count_documents({'estado': 'activo'})
    productos_inactivos = total_productos - productos_activos
    productos_por_categoria = list(db.productos.aggregate([{'$group': {'_id': '$categoria', 'total': {'$sum': 1}}}, {'$sort': {'total': -1}}]))
    productos_mas_vendidos = []
    if 'ventas' in db.list_collection_names():
        pipeline = [{'$unwind': '$productos'}, {'$group': {'_id': '$productos.nombre', 'total': {'$sum': '$productos.cantidad'}}}, {'$sort': {'total': -1}}, {'$limit': 20}]
        productos_mas_vendidos = list(db.ventas.aggregate(pipeline))
    return render_template('admin/reportes_productos.html', total_productos=total_productos, productos_activos=productos_activos, productos_inactivos=productos_inactivos, productos_por_categoria=productos_por_categoria, productos_mas_vendidos=productos_mas_vendidos)


# ================================================================
# AUTENTICACIÓN (API)
# ================================================================

def verificar_autenticacion():
    if 'user_id' in session:
        db = current_app.db
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
        return jsonify({
            'autenticado': True,
            'usuario_id': session['user_id'],
            'nombre': session.get('nombre', ''),
            'rol': session.get('rol', 'cliente'),
            'email': usuario.get('email') if usuario else ''
        })
    return jsonify({'autenticado': False})


def registrar_admin():
    if request.method == 'POST':
        db = current_app.db
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        nombre = request.form.get('nombre', 'Admin').strip()
        if not email or not password:
            flash('Email y contraseña son requeridos', 'danger')
            return redirect(url_for('web.registrar_admin'))
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('web.registrar_admin'))
        if db.usuarios.find_one({'email': email}):
            flash('Este correo ya está registrado.', 'danger')
            return redirect(url_for('web.registrar_admin'))
        import bcrypt
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        db.usuarios.insert_one({
            'nombre': nombre, 'email': email, 'password': hashed,
            'rol': 'admin', 'confirmado': True, 'activo': True,
            'created_at': datetime.now(timezone.utc)
        })
        flash('Administrador registrado exitosamente.', 'success')
        return redirect(url_for('web.login'))
    return render_template('auth/registrar_admin.html')


def obtener_usuario_actual():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if usuario:
        usuario['_id'] = str(usuario['_id'])
        usuario.pop('password', None)
        return jsonify(usuario)
    return jsonify({'error': 'Usuario no encontrado'}), 404


# ================================================================
# NOTIFICACIONES
# ================================================================

def enviar_notificacion():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    data = request.get_json() or {}
    titulo = data.get('titulo', '').strip()
    mensaje = data.get('mensaje', '').strip()
    usuarios_destino = data.get('usuarios', [])
    if not titulo or not mensaje:
        return jsonify({'error': 'Título y mensaje requeridos'}), 400
    notificacion = {'titulo': titulo, 'mensaje': mensaje, 'fecha_envio': datetime.now(timezone.utc), 'leida': False}
    if usuarios_destino:
        for user_id in usuarios_destino:
            db.usuarios.update_one({'_id': ObjectId(user_id)}, {'$push': {'notificaciones': notificacion}})
    else:
        for user in db.usuarios.find({}):
            db.usuarios.update_one({'_id': user['_id']}, {'$push': {'notificaciones': notificacion}})
    return jsonify({'success': True, 'message': 'Notificación enviada'})


# ================================================================
# PROMOCIONES / SEGMENTO / PREFERENCIAS
# ================================================================

def obtener_promociones_usuario():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    from app.models.promocion_model import Promocion
    carrito = session.get('carrito', [])
    monto_carrito = sum(item.get('precio', 0) * item.get('cantidad', 1) for item in carrito)
    promociones = Promocion.obtener_promociones_disponibles(session['user_id'], monto_carrito, carrito)
    return jsonify({'success': True, 'promociones': promociones})


def promociones_destacadas_usuario():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    from app.models.promocion_model import Promocion
    destacadas = Promocion.obtener_promociones_destacadas(session['user_id'])
    return jsonify({'success': True, 'promociones': destacadas})


def segmento_usuario():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    pedidos = list(db.pedidos.find({'usuario_id': ObjectId(session['user_id'])}))
    cantidad = len(pedidos)
    total_gastado = sum(float(p.get('total', 0)) for p in pedidos)
    if total_gastado >= 10000: segmento = "VIP"
    elif cantidad >= 5: segmento = "Frecuente"
    elif cantidad >= 1: segmento = "Ocasional"
    else: segmento = "Inactivo"
    return jsonify({'success': True, 'segmento': segmento, 'total_pedidos': cantidad, 'total_gastado': total_gastado})


def obtener_preferencias_comunicacion():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    prefs = usuario.get('preferencias_comunicacion') or {}
    defaults = {
        'email_promo': True, 'email_pedidos': True, 'email_newsletter': True,
        'wa_pedidos': True, 'wa_promo': False, 'push_pedidos': True, 'push_promo': False,
    }
    resultado = {**defaults, **prefs}
    resultado['email_pedidos'] = True

    return jsonify({'success': True, 'preferencias': resultado})


def actualizar_preferencias():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json(silent=True) or request.form

    def _flag(key):
        v = data.get(key)
        if isinstance(v, bool): return v
        if v is None: return False
        return str(v).lower() in ('1', 'true', 'on', 'yes', 'si', 'sí')

    nuevas_prefs = {
        'email_promo':      _flag('email_promo'),
        'email_pedidos':    True,
        'email_newsletter': _flag('email_newsletter'),
        'wa_pedidos':       _flag('wa_pedidos'),
        'wa_promo':         _flag('wa_promo'),
        'push_pedidos':     _flag('push_pedidos'),
        'push_promo':       _flag('push_promo'),
        'updated_at':       datetime.now(timezone.utc),
    }

    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'preferencias_comunicacion': nuevas_prefs,
            'updated_at': datetime.now(timezone.utc),
        }}
    )

    return jsonify({
        'success': True,
        'message': 'Preferencias guardadas correctamente',
        'preferencias': nuevas_prefs,
    })


# ================================================================
# ⭐ INTERESES
# ================================================================

OPCIONES_INTERESES = {
    "categorias": [
        {"valor": "moda", "etiqueta": "Moda", "icono": "bag-heart"},
        {"valor": "electronica", "etiqueta": "Electrónica", "icono": "phone"},
        {"valor": "hogar", "etiqueta": "Hogar", "icono": "house-heart"},
        {"valor": "belleza", "etiqueta": "Belleza", "icono": "flower1"},
        {"valor": "deportes", "etiqueta": "Deportes", "icono": "bicycle"},
        {"valor": "juguetes", "etiqueta": "Juguetes", "icono": "puzzle"},
        {"valor": "libros", "etiqueta": "Libros", "icono": "book"},
        {"valor": "musica", "etiqueta": "Música", "icono": "music-note-beamed"},
        {"valor": "mascotas", "etiqueta": "Mascotas", "icono": "heart"},
        {"valor": "automotriz", "etiqueta": "Automotriz", "icono": "car-front"},
        {"valor": "herramientas", "etiqueta": "Herramientas", "icono": "tools"},
        {"valor": "videojuegos", "etiqueta": "Videojuegos", "icono": "controller"},
    ],
    "marcas": ["Nike", "Adidas", "Apple", "Samsung", "Sony", "Levi's", "Zara", "L'Oréal", "Xiaomi", "Logitech"],
    "actividades": [
        {"valor": "trabajo", "etiqueta": "Trabajo / Oficina", "icono": "briefcase"},
        {"valor": "gym", "etiqueta": "Gym / Fitness", "icono": "activity"},
        {"valor": "viajes", "etiqueta": "Viajes", "icono": "airplane"},
        {"valor": "gaming", "etiqueta": "Gaming", "icono": "controller"},
        {"valor": "lectura", "etiqueta": "Lectura", "icono": "book"},
        {"valor": "cocina", "etiqueta": "Cocina", "icono": "egg-fried"},
        {"valor": "fotografia", "etiqueta": "Fotografía", "icono": "camera"},
        {"valor": "running", "etiqueta": "Running", "icono": "person-walking"},
    ],
    "ocasiones": [
        {"valor": "mi", "etiqueta": "Para mí", "icono": "person-heart"},
        {"valor": "regalo", "etiqueta": "Regalos", "icono": "gift"},
        {"valor": "familia", "etiqueta": "Familia", "icono": "people-fill"},
        {"valor": "pareja", "etiqueta": "Pareja", "icono": "heart-fill"},
        {"valor": "hijos", "etiqueta": "Hijos", "icono": "balloon"},
        {"valor": "amigos", "etiqueta": "Amigos", "icono": "people"},
        {"valor": "trabajo", "etiqueta": "Compañeros de trabajo", "icono": "briefcase-fill"},
        {"valor": "eventos", "etiqueta": "Eventos especiales", "icono": "calendar-heart"},
    ],
}


def api_intereses_get():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401
    try:
        intereses = usuario.get('intereses') or {}
        return jsonify({
            'success': True,
            'intereses': {
                'categorias':  intereses.get('categorias', []) or [],
                'marcas':      intereses.get('marcas', []) or [],
                'actividades': intereses.get('actividades', []) or [],
                'ocasiones':   intereses.get('ocasiones', []) or [],
                'frecuencia':  intereses.get('frecuencia'),
                'actualizado': (
                    intereses.get('actualizado').isoformat()
                    if hasattr(intereses.get('actualizado'), 'isoformat')
                    else intereses.get('actualizado')
                ),
            },
            'opciones': OPCIONES_INTERESES,
        })
    except Exception as e:
        current_app.logger.error(f'[api_intereses_get] ERROR: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


def api_intereses_post():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401
    try:
        data = request.get_json(silent=True) or {}
        categorias  = [c for c in (data.get('categorias')  or []) if isinstance(c, str)]
        marcas      = [m for m in (data.get('marcas')      or []) if isinstance(m, str)]
        actividades = [a for a in (data.get('actividades') or []) if isinstance(a, str)]
        ocasiones   = [o for o in (data.get('ocasiones')   or []) if isinstance(o, str)]
        frecuencia  = data.get('frecuencia') or None
        ahora = datetime.now(timezone.utc)
        db = current_app.db
        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {
                'intereses': {
                    'categorias':  categorias, 'marcas': marcas,
                    'actividades': actividades, 'ocasiones': ocasiones,
                    'frecuencia':  frecuencia, 'actualizado': ahora,
                },
                'updated_at': ahora,
            }}
        )
        return jsonify({
            'success': True, 'message': 'Intereses guardados correctamente',
            'intereses': {
                'categorias': categorias, 'marcas': marcas,
                'actividades': actividades, 'ocasiones': ocasiones,
                'frecuencia': frecuencia, 'actualizado': ahora.isoformat(),
            }
        })
    except Exception as e:
        current_app.logger.error(f'[api_intereses_post] ERROR: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


def api_intereses_delete():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401
    try:
        db = current_app.db
        resultado = db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$unset': {'intereses': ''}, '$set': {'updated_at': datetime.now(timezone.utc)}}
        )
        if resultado.matched_count == 0:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        return jsonify({'success': True, 'message': 'Intereses eliminados correctamente'})
    except Exception as e:
        current_app.logger.error(f'[api_intereses_delete] ERROR: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================================================
# IDIOMA Y REGIÓN
# ================================================================

IDIOMAS_SOPORTADOS = ['es-MX','es-ES','es-AR','es-CO','en-US','en-GB','pt-BR','pt-PT','fr-FR','de-DE','it-IT','ja-JP','zh-CN']
MONEDAS_SOPORTADAS = ['MXN','USD','EUR','GBP','BRL','ARS','COP','CLP','JPY','CNY']
PAISES_SOPORTADOS = ['MX','US','ES','AR','CO','CL','PE','BR','PT','FR','DE','IT','JP','CN']


def obtener_preferencias_idioma():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    prefs = usuario.get('preferencias_idioma') or {}
    defaults = {'idioma': 'es-MX', 'moneda': 'MXN', 'pais': 'MX'}
    resultado = {**defaults, **prefs}
    return jsonify({'success': True, 'preferencias': resultado})


def actualizar_preferencias_idioma():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    data = request.get_json(silent=True) or request.form
    idioma = (data.get('idioma') or 'es-MX').strip()
    moneda = (data.get('moneda') or 'MXN').strip()
    pais = (data.get('pais') or 'MX').strip()
    if idioma not in IDIOMAS_SOPORTADOS: idioma = 'es-MX'
    if moneda not in MONEDAS_SOPORTADAS: moneda = 'MXN'
    if pais not in PAISES_SOPORTADOS: pais = 'MX'
    nuevas_prefs = {
        'idioma': idioma, 'moneda': moneda, 'pais': pais,
        'updated_at': datetime.now(timezone.utc),
    }
    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'preferencias_idioma': nuevas_prefs,
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    session['idioma'] = idioma
    session['moneda'] = moneda
    session['pais'] = pais
    return jsonify({
        'success': True,
        'message': 'Preferencias de idioma guardadas correctamente',
        'preferencias': nuevas_prefs,
    })


# ================================================================
# TIPOS DE CAMBIO - VÍA API (Frankfurter)
# ================================================================

_TIPOS_CAMBIO_CACHE = {'rates': None, 'timestamp': None}
MONEDA_BASE = 'MXN'
FRANKFURTER_URL = 'https://api.frankfurter.app/latest'
SIMBOLOS_MONEDA = {
    'MXN': '$', 'USD': '$', 'EUR': '€', 'GBP': '£',
    'BRL': 'R$', 'ARS': '$', 'COP': '$', 'CLP': '$', 'JPY': '¥', 'CNY': '¥',
}


def _obtener_tipos_cambio_reales():
    ahora = datetime.now()
    cache = _TIPOS_CAMBIO_CACHE
    if cache['rates'] and cache['timestamp']:
        if ahora - cache['timestamp'] < timedelta(hours=1):
            return cache['rates']
    try:
        r = requests.get(FRANKFURTER_URL, params={'from': MONEDA_BASE}, timeout=5)
        r.raise_for_status()
        data = r.json()
        rates = data.get('rates', {})
        rates[MONEDA_BASE] = 1.0
        cache['rates'] = rates
        cache['timestamp'] = ahora
        return rates
    except Exception as e:
        print(f"⚠️ Error obteniendo tipos de cambio: {e}", file=sys.stderr)
        return {
            'MXN': 1.0, 'USD': 0.058, 'EUR': 0.054, 'GBP': 0.046,
            'BRL': 0.29, 'ARS': 8.50, 'COP': 230.0, 'CLP': 55.0,
            'JPY': 8.70, 'CNY': 0.42,
        }


def vista_previa_idioma():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    moneda = (request.args.get('moneda') or '').strip().upper()
    if moneda not in MONEDAS_SOPORTADAS:
        moneda = (usuario.get('preferencias_idioma') or {}).get('moneda', 'MXN')
    if moneda not in MONEDAS_SOPORTADAS:
        moneda = 'MXN'
    db = current_app.db
    productos = []
    try:
        pipeline = [
            {'$match': {'$or': [{'activo': True}, {'activo': {'$exists': False}}, {'estado': 'activo'}]}},
            {'$sample': {'size': 3}},
        ]
        productos = list(db.productos.aggregate(pipeline))
    except Exception:
        productos = []
    if not productos:
        try:
            productos = list(db.productos.find({'$or': [{'activo': True}, {'activo': {'$exists': False}}, {'estado': 'activo'}]}).limit(3))
        except Exception:
            productos = []
    if not productos:
        try:
            productos = list(db.productos.find({}).limit(3))
        except Exception:
            productos = []
    if not productos:
        return jsonify({'success': True, 'moneda': moneda, 'simbolo': SIMBOLOS_MONEDA.get(moneda, '$'),
                        'productos': [], 'mensaje': 'No hay productos disponibles'})
    simbolo = SIMBOLOS_MONEDA.get(moneda, '$')
    rates = _obtener_tipos_cambio_reales()

    def _extraer_precio(p):
        for key in ('variables', 'variantes'):
            if p.get(key):
                for v in p[key]:
                    try:
                        if v.get('precio'):
                            return float(v['precio'])
                    except (ValueError, TypeError):
                        continue
        for key in ('precio', 'precio_base', 'precio_venta'):
            try:
                if p.get(key):
                    return float(p[key])
            except (ValueError, TypeError):
                continue
        return 0.0

    def _extraer_imagen(p):
        for key in ('imagenes', 'fotos', 'imagen', 'foto'):
            val = p.get(key)
            if isinstance(val, list) and val: return val[0]
            if isinstance(val, str) and val: return val
        return ''

    def _formatear(valor, sim, mon):
        if mon in ('JPY', 'CLP', 'COP', 'ARS'):
            return f"{sim}{valor:,.0f}"
        return f"{sim}{valor:,.2f}"

    vista = []
    for p in productos:
        precio_mxn = _extraer_precio(p)
        tasa = rates.get(moneda, 1.0)
        precio_convertido = precio_mxn * tasa
        vista.append({
            'id': str(p.get('_id', '')),
            'nombre': p.get('nombre', 'Producto'),
            'imagen': _extraer_imagen(p),
            'precio_base': precio_mxn,
            'precio_mxn': precio_mxn,
            'precio_mostrado': _formatear(precio_convertido, simbolo, moneda),
            'moneda': moneda,
            'tasa_usada': tasa,
        })
    return jsonify({
        'success': True, 'moneda': moneda, 'simbolo': simbolo,
        'base': MONEDA_BASE, 'productos': vista,
    })


# ================================================================
# ⭐ MÉTODOS DE PAGO (TARJETAS GUARDADAS) — CON NO-CACHE + CONEKTA
# ================================================================

def _safe_oid(val):
    try:
        return ObjectId(str(val))
    except Exception:
        return val


def _json_no_cache(payload, status=200):
    """Devuelve un JSON con headers anti-caché."""
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def obtener_metodos_pago():
    """
    GET /mi-cuenta/metodos-pago
    Devuelve TODOS los métodos de pago del usuario.
    El `id` SIEMPRE va completo — NUNCA truncado.
    Sin caché para evitar IDs fantasma del navegador.
    """
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        uid_oid = usuario['_id']

        metodos = list(db.metodos_pago.find({
            '$or': [
                {'usuario_id': uid_str},
                {'usuario_id': uid_oid},
            ]
        }).sort('created_at', -1))

        lista = []
        for m in metodos:
            id_final = str(m.get('id') or m.get('_id') or '')
            created = m.get('created_at')
            created_iso = created.isoformat() if hasattr(created, 'isoformat') else None

            lista.append({
                'id': id_final,
                '_id': str(m.get('_id') or ''),
                'usuario_id': str(m.get('usuario_id') or ''),
                'tipo': m.get('tipo', 'tarjeta'),
                'marca': m.get('marca', ''),
                'ultimos4': m.get('ultimos4', ''),
                'titular': m.get('titular', ''),
                'expira': m.get('expira', ''),
                'email': m.get('email', ''),
                'predeterminado': bool(m.get('predeterminado', False)),
                'conekta_customer_id': m.get('conekta_customer_id'),
                'conekta_payment_source_id': m.get('conekta_payment_source_id'),
                'created_at': created_iso,
            })

        print(f"💳 [metodos-pago] GET usuario={uid_str} → {len(lista)} métodos", file=sys.stderr)
        for m in lista:
            print(f"   → id='{m['id']}' | tipo='{m['tipo']}' | ultimos4='{m['ultimos4']}'",
                  file=sys.stderr)

        return _json_no_cache({'success': True, 'metodos': lista})

    except Exception as e:
        current_app.logger.error(f'[obtener_metodos_pago] ERROR: {e}')
        import traceback
        traceback.print_exc()
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def agregar_metodo_pago():
    """
    POST /mi-cuenta/metodos-pago

    ⭐ FIX: ahora recibe `token_id` (generado por Conekta.js en el navegador)
    y crea el customer + payment_source en Conekta, guardando los IDs.
    Sin `token_id` no se puede vincular la tarjeta a Conekta.
    """
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        data = request.get_json(silent=True) or request.form
        tipo = (data.get('tipo') or 'tarjeta').strip().lower()
        predeterminado = bool(data.get('predeterminado', False))
        uid_str = str(usuario['_id'])

        nuevo = {
            'id': secrets.token_urlsafe(16),
            'usuario_id': uid_str,
            'tipo': tipo,
            'predeterminado': predeterminado,
            'created_at': datetime.now(timezone.utc),
        }

        if tipo == 'tarjeta':
            token_id = (data.get('token_id') or '').strip()
            marca    = (data.get('marca') or 'Tarjeta').strip()
            ultimos4 = (data.get('ultimos4') or '').strip()
            titular  = (data.get('titular') or '').strip()
            expira   = (data.get('expira') or '').strip()

            if not ultimos4 or len(ultimos4) != 4 or not ultimos4.isdigit():
                return _json_no_cache({'success': False, 'message': 'Últimos 4 dígitos inválidos'}, 400)

            # ⭐ OBLIGATORIO: sin token no se puede vincular a Conekta
            if not token_id:
                return _json_no_cache({
                    'success': False,
                    'message': ('Falta el token de Conekta. '
                                'La tarjeta debe tokenizarse en el navegador antes de guardarla.')
                }, 400)

            from app.services.conekta_service import (
                crear_o_actualizar_customer, crear_payment_source
            )

            # 1) Crear/actualizar el customer en Conekta
            cust_res = crear_o_actualizar_customer(
                usuario_id=uid_str,
                nombre=usuario.get('nombre', 'Cliente'),
                email=usuario.get('email', ''),
                telefono=usuario.get('telefono', ''),
                conekta_customer_id=usuario.get('conekta_customer_id'),
            )
            if not cust_res.get('success'):
                return _json_no_cache({
                    'success': False,
                    'message': f'Error creando customer: {cust_res.get("error")}'
                }, 500)

            customer_id = cust_res['customer_id']

            # 2) Crear el payment_source
            ps_res = crear_payment_source(customer_id, token_id)
            if not ps_res.get('success'):
                return _json_no_cache({
                    'success': False,
                    'message': f'Error creando payment source: {ps_res.get("error")}'
                }, 500)

            payment_source_id = ps_res['payment_source_id']

            # 3) Persistir el customer_id en el usuario
            db = current_app.db
            db.usuarios.update_one(
                {'_id': usuario['_id']},
                {'$set': {'conekta_customer_id': customer_id}}
            )

            nuevo.update({
                'marca': marca,
                'ultimos4': ultimos4,
                'titular': titular,
                'expira': expira,
                'conekta_customer_id': customer_id,           # ⭐
                'conekta_payment_source_id': payment_source_id,  # ⭐
            })

        elif tipo == 'paypal':
            email = (data.get('email') or '').strip()
            if not email:
                return _json_no_cache({'success': False, 'message': 'Email de PayPal requerido'}, 400)
            nuevo['email'] = email

        elif tipo == 'oxxo':
            pass
        else:
            return _json_no_cache({'success': False, 'message': 'Tipo inválido'}, 400)

        db = current_app.db

        if predeterminado:
            db.metodos_pago.update_many(
                {'usuario_id': uid_str},
                {'$set': {'predeterminado': False}}
            )

        if db.metodos_pago.count_documents({'usuario_id': uid_str}) == 0:
            nuevo['predeterminado'] = True

        db.metodos_pago.insert_one(nuevo)

        print(f"💾 [metodos-pago] POST nuevo método id='{nuevo['id']}' tipo='{nuevo['tipo']}' "
              f"conekta_customer_id={nuevo.get('conekta_customer_id')} "
              f"conekta_payment_source_id={nuevo.get('conekta_payment_source_id')}",
              file=sys.stderr)

        return _json_no_cache({
            'success': True,
            'message': 'Método guardado correctamente',
            'metodo': {
                'id': nuevo['id'], 'tipo': nuevo['tipo'],
                'marca': nuevo.get('marca'), 'ultimos4': nuevo.get('ultimos4'),
                'titular': nuevo.get('titular'),
                'predeterminado': nuevo['predeterminado'],
            }
        })

    except Exception as e:
        current_app.logger.error(f'[agregar_metodo_pago] ERROR: {e}')
        import traceback
        traceback.print_exc()
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def eliminar_metodo_pago(metodo_id):
    """DELETE /mi-cuenta/metodos-pago/<metodo_id>"""
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        oid = _safe_oid(metodo_id)

        filtro = {
            '$or': [{'id': metodo_id}, {'_id': oid}],
            'usuario_id': uid_str,
        }
        resultado = db.metodos_pago.delete_one(filtro)

        if resultado.deleted_count == 0:
            return _json_no_cache({'success': False, 'message': 'Método no encontrado'}, 404)

        print(f"🗑️ [metodos-pago] DELETE id='{metodo_id}'", file=sys.stderr)
        return _json_no_cache({'success': True, 'message': 'Método eliminado'})

    except Exception as e:
        current_app.logger.error(f'[eliminar_metodo_pago] ERROR: {e}')
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def marcar_metodo_predeterminado(metodo_id):
    """POST /mi-cuenta/metodos-pago/<metodo_id>/predeterminado"""
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        oid = _safe_oid(metodo_id)

        metodo = db.metodos_pago.find_one({
            '$or': [{'id': metodo_id}, {'_id': oid}],
            'usuario_id': uid_str,
        })
        if not metodo:
            return _json_no_cache({'success': False, 'message': 'Método no encontrado'}, 404)

        db.metodos_pago.update_many(
            {'usuario_id': uid_str},
            {'$set': {'predeterminado': False}}
        )
        db.metodos_pago.update_one(
            {'_id': metodo['_id']},
            {'$set': {'predeterminado': True}}
        )

        print(f"⭐ [metodos-pago] predeterminado id='{metodo_id}'", file=sys.stderr)
        return _json_no_cache({'success': True, 'message': 'Método predeterminado actualizado'})

    except Exception as e:
        current_app.logger.error(f'[marcar_metodo_predeterminado] ERROR: {e}')
        return _json_no_cache({'success': False, 'message': str(e)}, 500)