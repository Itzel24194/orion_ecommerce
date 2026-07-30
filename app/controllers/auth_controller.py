import os
from flask import render_template, request, redirect, url_for, session, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from app.models.usuarios_model import Usuario as UsuarioModel
from itsdangerous import URLSafeTimedSerializer
from app import mail
from flask_mail import Message  
from datetime import datetime, timedelta
import bcrypt
import jwt
from bson import ObjectId
import re
import sys

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

def normalizar_rol(rol):
    """Normaliza el rol para comparación consistente"""
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

def login():
    """Inicio de sesión con redirección según rol y guardado de segmento"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        print(f"🔍 INTENTO DE LOGIN: {email}", file=sys.stderr)
        
        if not email or not password:
            flash("Por favor, completa todos los campos.", "warning")
            return redirect(url_for('web.login'))
        
        usuario = UsuarioModel.obtener_por_email(email)
        
        if not usuario:
            print(f"❌ Usuario no encontrado: {email}", file=sys.stderr)
            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for('web.login'))
        
        print(f"✅ Usuario encontrado: {usuario.get('email')}", file=sys.stderr)
        print(f"🔍 Rol en BD: {usuario.get('rol')}", file=sys.stderr)
        print(f"🔍 Confirmado: {usuario.get('confirmado')}", file=sys.stderr)
        print(f"🔍 Activo: {usuario.get('activo')}", file=sys.stderr)
        
        if not usuario.get('confirmado', False):
            print(f"❌ Usuario no confirmado: {email}", file=sys.stderr)
            flash("Debes confirmar tu correo electrónico antes de iniciar sesión.", "warning")
            return redirect(url_for('web.login'))
        
        if not usuario.get('activo', True):
            print(f"❌ Usuario inactivo: {email}", file=sys.stderr)
            flash("Tu cuenta está desactivada. Contacta al administrador.", "danger")
            return redirect(url_for('web.login'))
        
        try:
            password_hash = usuario.get('password', '')
            print(f"🔍 Verificando contraseña para: {email}", file=sys.stderr)
            
            if not password_hash:
                print(f"❌ No hay hash de contraseña para: {email}", file=sys.stderr)
                flash("Correo o contraseña incorrectos.", "danger")
                return redirect(url_for('web.login'))
            
            password_correcta = bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            print(f"🔍 Contraseña correcta: {password_correcta}", file=sys.stderr)
            
            if not password_correcta:
                flash("Correo o contraseña incorrectos.", "danger")
                return redirect(url_for('web.login'))
                
        except Exception as e:
            print(f"❌ Error al verificar contraseña: {e}", file=sys.stderr)
            flash("Error al verificar la contraseña.", "danger")
            return redirect(url_for('web.login'))
        
        session.clear()
        
        session['user_id'] = str(usuario['_id'])
        session['email'] = usuario.get('email')
        session['nombre'] = usuario.get('nombre', 'Usuario')
        
        rol = usuario.get('rol', 'cliente')
        rol_normalizado = normalizar_rol(rol)
        session['rol'] = rol_normalizado
        
        # 🔥 CALCULAR Y GUARDAR EL SEGMENTO DEL USUARIO
        segmento = UsuarioModel.obtener_segmento(str(usuario['_id']))
        session['segmento'] = segmento
        
        foto = usuario.get('foto')
        if foto and foto != '': 
            session['foto'] = foto
        else: 
            session.pop('foto', None)
        
        try:
            UsuarioModel.actualizar(str(usuario['_id']), {'ultimo_login': datetime.utcnow()})
        except Exception as e:
            print(f"⚠️ Error al actualizar último login: {e}", file=sys.stderr)
        
        print(f"🔍 ===== LOGIN EXITOSO =====", file=sys.stderr)
        print(f"🔍 Email: {email}", file=sys.stderr)
        print(f"🔍 Rol en BD: {rol}", file=sys.stderr)
        print(f"🔍 Rol normalizado: {rol_normalizado}", file=sys.stderr)
        print(f"🔍 Segmento: {segmento}", file=sys.stderr)
        print(f"🔍 Session: {dict(session)}", file=sys.stderr)
        print(f"🔍 ==========================", file=sys.stderr)
        
        if rol_normalizado == 'admin':
            flash(f"¡Bienvenido Administrador {session['nombre']}!", "success")
            return redirect(url_for('web.dashboard'))
        else:
            flash(f"¡Bienvenido {session['nombre']}!", "success")
            return redirect(url_for('web.raiz_tienda'))
    
    return render_template('auth/login.html')

# ================================================================
# RESTO DEL CÓDIGO (register, confirmar_email, etc.)
# ================================================================

def register():
    """PASO 1: Registro básico. Crea usuario con confirmado=False y envía mail."""
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
            UsuarioModel.crear_usuario({
                "email": email, 
                "password": password, 
                "confirmado": False, 
                "rol": "cliente",
                "activo": True
            })
            
            token = get_serializer().dumps(email, salt='email-confirm')
            confirm_url = url_for('web.confirmar_email', token=token, _external=True)
            
            msg = Message("¡Bienvenido a ORION SYSTEM!", recipients=[email])
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
                <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
                <p>Hola, gracias por registrarte en <strong>ORION SYSTEM</strong>.</p>
                <p>Para activar tu cuenta y completar tu perfil, presiona el siguiente botón:</p>
                <a href="{confirm_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Activar Cuenta</a>
                <p style="font-size: 12px; color: #888; text-align: center;">Este enlace expirará en 1 hora.</p>
                <p style="font-size: 12px; color: #888; text-align: center;">Si no creaste esta cuenta, ignora este mensaje.</p>
            </div>
            """
            try:
                mail.send(msg)
                return render_template('auth/confirmacion_pendiente.html', email=email)
            except Exception as e:
                print(f"❌ Error al enviar correo: {e}", file=sys.stderr)
                flash("Error al enviar el correo de confirmación.", "danger")
                return redirect(url_for('web.register'))
                
        except Exception as e:
            print(f"❌ Error al crear usuario: {e}", file=sys.stderr)
            flash("Error al crear el usuario. Intenta nuevamente.", "danger")
            return redirect(url_for('web.register'))
            
    return render_template('auth/register.html')

def reenviar_confirmacion():
    """Reenviar correo de confirmación"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash("Por favor, ingresa tu correo electrónico.", "warning")
            return render_template('auth/confirmacion_pendiente.html')
        
        usuario = UsuarioModel.obtener_por_email(email)
        if not usuario:
            flash("No existe una cuenta con ese correo.", "danger")
            return render_template('auth/confirmacion_pendiente.html')
        
        if usuario.get('confirmado', False):
            flash("Esta cuenta ya está confirmada. Inicia sesión.", "info")
            return redirect(url_for('web.login'))
        
        token = get_serializer().dumps(email, salt='email-confirm')
        confirm_url = url_for('web.confirmar_email', token=token, _external=True)
        
        msg = Message("Reenvío: Confirma tu cuenta - ORION SYSTEM", recipients=[email])
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
            <p>Haz clic en el siguiente botón para activar tu cuenta:</p>
            <a href="{confirm_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Activar Cuenta</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Este enlace expirará en 1 hora.</p>
        </div>
        """
        try:
            mail.send(msg)
            flash("Se ha enviado un nuevo enlace a tu correo.", "success")
        except Exception as e:
            print(f"❌ Error al reenviar correo: {e}", file=sys.stderr)
            flash("Error al reenviar el correo.", "danger")
            
    return render_template('auth/confirmacion_pendiente.html')

def confirmar_email(token):
    """PASO 2: Valida el token y da acceso temporal al registro de perfil."""
    try:
        email = get_serializer().loads(token, salt='email-confirm', max_age=3600)
    except Exception as e:
        print(f"❌ Token inválido: {e}", file=sys.stderr)
        flash("El enlace es inválido o ha expirado.", "danger")
        return redirect(url_for('web.login'))
    
    try:
        db = current_app.db
        result = db.usuarios.update_one(
            {'email': email},
            {'$set': {'confirmado': True, 'updated_at': datetime.utcnow()}}
        )
        
        if result.modified_count == 0:
            flash("La cuenta ya estaba confirmada. Inicia sesión.", "info")
            return redirect(url_for('web.login'))
        
        session['pending_profile_email'] = email
        flash("¡Cuenta confirmada! Ahora completa tu perfil.", "success")
        return redirect(url_for('web.register_profile'))
        
    except Exception as e:
        print(f"❌ Error al confirmar email: {e}", file=sys.stderr)
        flash("Error al confirmar el correo.", "danger")
        return redirect(url_for('web.login'))

def register_profile():
    """PASO 3: Completar perfil. SOLO se accede con la sesión pendiente."""
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
            print(f"❌ Error al completar perfil: {e}", file=sys.stderr)
            flash("Error al guardar el perfil.", "danger")
            return redirect(url_for('web.register_profile'))
            
    return render_template('auth/register_profile.html')

def logout():
    """Cerrar sesión"""
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('web.login'))

def ver_perfil():
    """Ver perfil del usuario autenticado con sus pedidos"""
    if 'user_id' not in session: 
        flash("Inicia sesión para ver tu perfil.", "warning")
        return redirect(url_for('web.login'))
    
    usuario = UsuarioModel.obtener_por_id(session['user_id'])
    if not usuario:
        flash("Usuario no encontrado.", "danger")
        session.clear()
        return redirect(url_for('web.login'))
    
    db = current_app.db
    pedidos = []
    try:
        pedidos = list(db.pedidos.find({'usuario_id': session['user_id']}).sort('created_at', -1).limit(5))
        for pedido in pedidos:
            pedido['_id'] = str(pedido['_id'])
            if 'created_at' not in pedido:
                pedido['created_at'] = datetime.utcnow()
    except Exception as e:
        print(f"⚠️ Error al obtener pedidos: {e}", file=sys.stderr)
    
    # 🔥 Obtener el segmento del usuario
    segmento = UsuarioModel.obtener_segmento(session['user_id'])
    
    return render_template('tienda/perfil.html', usuario=usuario, pedidos=pedidos, segmento=segmento)

def actualizar_perfil():
    """Actualizar perfil del usuario autenticado"""
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
            flash("Formato de imagen no válido. Usa PNG, JPG, JPEG, GIF o WEBP.", "danger")
            return redirect(url_for('web.perfil'))
    
    try:
        UsuarioModel.actualizar(usuario_id, datos_actualizados)
        session['nombre'] = datos_actualizados.get('nombre', session.get('nombre'))
        flash("Perfil actualizado correctamente.", "success")
    except Exception as e:
        print(f"❌ Error al actualizar perfil: {e}", file=sys.stderr)
        flash("Error al actualizar el perfil.", "danger")
    
    return redirect(url_for('web.perfil'))

def recuperar_password():
    """Recuperar contraseña - Enviar email con enlace de restablecimiento"""
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
        
        msg = Message("Recuperación de contraseña - ORION SYSTEM", recipients=[email])
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🔐 ORION SYSTEM</h1>
            <p>Hemos recibido una solicitud para restablecer tu contraseña.</p>
            <p>Para crear una nueva contraseña, presiona el siguiente botón:</p>
            <a href="{reset_url}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Restablecer Contraseña</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Si no solicitaste esto, ignora este mensaje.</p>
            <p style="font-size: 12px; color: #888; text-align: center;">⏰ El enlace expirará en 1 hora.</p>
        </div>
        """
        try:
            mail.send(msg)
            flash("Se han enviado instrucciones a tu correo electrónico.", "success")
        except Exception as e:
            print(f"❌ Error al enviar correo de recuperación: {e}", file=sys.stderr)
            flash("Error al enviar el correo.", "danger")
            
        return redirect(url_for('web.login'))
    
    return render_template('auth/recuperar_password.html')

def resetear_password(token):
    """Restablecer contraseña con token"""
    try:
        email = get_serializer().loads(token, salt='password-reset', max_age=3600)
    except Exception as e:
        print(f"❌ Token inválido: {e}", file=sys.stderr)
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
        except Exception as e:
            print(f"❌ Error al actualizar contraseña: {e}", file=sys.stderr)
            flash("Error al actualizar la contraseña.", "danger")
            return redirect(url_for('web.resetear_password', token=token))
    
    return render_template('auth/resetear_password.html', token=token)

def cambiar_password():
    """Cambiar contraseña del usuario autenticado"""
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
            
        except Exception as e:
            print(f"❌ Error al cambiar contraseña: {e}", file=sys.stderr)
            flash('Error al cambiar la contraseña', 'danger')
            
        return redirect(url_for('web.perfil'))
    
    flash('Método no permitido', 'danger')
    return redirect(url_for('web.perfil'))

def enviar_email_verificacion(usuario):
    """Enviar email de verificación al usuario"""
    try:
        secret_key = current_app.config.get('SECRET_KEY')
        payload = {
            'usuario_id': str(usuario['_id']),
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        token = jwt.encode(payload, secret_key, algorithm='HS256')
        
        link = url_for('web.confirmar_email', token=token, _external=True)
        
        msg = Message("Confirma tu email - ORION SYSTEM", recipients=[usuario['email']])
        msg.html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 30px; background: #020202; color: #ffffff; border-radius: 20px; border: 2px solid #ff007f;">
            <h1 style="color: #00d4ff; text-align: center;">🌟 ORION SYSTEM</h1>
            <p>Hola {usuario.get('nombre', 'usuario')},</p>
            <p>Para confirmar tu correo electrónico, presiona el siguiente botón:</p>
            <a href="{link}" style="display: block; width: 220px; margin: 30px auto; padding: 15px; background: linear-gradient(90deg, #ff007f, #00d4ff); color: white; text-align: center; text-decoration: none; border-radius: 10px; font-weight: 900; text-transform: uppercase;">Confirmar Email</a>
            <p style="font-size: 12px; color: #888; text-align: center;">Si no solicitaste esto, ignora este mensaje.</p>
        </div>
        """
        mail.send(msg)
        return True
        
    except Exception as e:
        print(f"❌ Error al enviar email de verificación: {e}", file=sys.stderr)
        return False

def obtener_usuario_actual():
    """Obtener usuario actual (API)"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    usuario = UsuarioModel.obtener_por_id(session['user_id'])
    if usuario:
        usuario['_id'] = str(usuario['_id'])
        usuario.pop('password', None)
        return jsonify(usuario)
    return jsonify({'error': 'Usuario no encontrado'}), 404

def verificar_autenticacion():
    """Verificar si el usuario está autenticado (API)"""
    if 'user_id' in session:
        return jsonify({
            'autenticado': True,
            'usuario_id': session['user_id'],
            'email': session.get('email', ''),
            'nombre': session.get('nombre', ''),
            'rol': session.get('rol', 'cliente'),
            'foto': session.get('foto', ''),
            'segmento': session.get('segmento', 'Inactivo')  # 🔥 AGREGAR SEGMENTO
        })
    return jsonify({'autenticado': False})

def registrar_admin():
    """Registrar usuario como administrador (solo para desarrollo)"""
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
                "rol": "admin",
                "nombre": nombre,
                "activo": True
            })
            flash("Administrador registrado exitosamente.", "success")
            return redirect(url_for('web.login'))
        except Exception as e:
            print(f"❌ Error al registrar admin: {e}", file=sys.stderr)
            flash("Error al registrar el administrador.", "danger")
    
    return render_template('auth/registrar_admin.html')

def debug_sesion():
    """Función de depuración para verificar la sesión (solo desarrollo)"""
    db = current_app.db
    user_id = session.get('user_id')
    usuario = None
    if user_id:
        usuario = db.usuarios.find_one({'_id': ObjectId(user_id)})
        if usuario:
            usuario['_id'] = str(usuario['_id'])
            usuario.pop('password', None)
    
    return jsonify({
        'session': dict(session),
        'user_id': session.get('user_id'),
        'rol': session.get('rol'),
        'nombre': session.get('nombre'),
        'email': session.get('email'),
        'foto': session.get('foto'),
        'segmento': session.get('segmento', 'Inactivo'),  # 🔥 AGREGAR SEGMENTO
        'usuario_bd': usuario,
        'es_admin': session.get('rol') == 'admin',
        'redireccion': 'web.dashboard' if session.get('rol') == 'admin' else 'web.raiz_tienda'
    })