# app/controllers/usuarios_controller.py - COMPLETO CON INTEGRACIÓN DE PROMOCIONES
# ================================================================

import os
import uuid
from flask import render_template, request, redirect, url_for, session, current_app, flash, jsonify
from werkzeug.utils import secure_filename
from app.models.usuarios_model import Usuario as UsuarioModel
from app.models.ventas_model import VentaReporte
from app.models.resenas_model import Resena
from datetime import datetime, timedelta
from app.models.productos_model import Producto
from bson import ObjectId


# ================================================================
# FUNCIÓN AUXILIAR PARA NORMALIZAR ROLES
# ================================================================

def normalizar_rol(rol):
    """Normaliza el rol para comparación consistente"""
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


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
            "sexo": request.form.get('genero', 'Indefinido'),
            "rol": request.form.get('rol', 'cliente'),
            "password": request.form.get('password', ''),
            "foto": None,
            "direcciones": [],
            "confirmado": True,
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

        UsuarioModel.crear_usuario(data)
        flash('Usuario creado correctamente', 'success')
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
        
        data = {
            "nombre": request.form.get('nombre', '').strip(),
            "apellido_paterno": request.form.get('apellido_paterno', '').strip(),
            "apellido_materno": request.form.get('apellido_materno', '').strip(),
            "email": request.form.get('email', '').strip(),
            "telefono": request.form.get('telefono', '').strip(),
            "fecha_nacimiento": request.form.get('fecha_nacimiento', ''),
            "sexo": request.form.get('genero', 'Indefinido'),
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
        flash(f'Error al actualizar usuario: {str(e)}', 'danger')
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
        "genero": request.form.get('genero', 'Indefinido')
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
# CRUD DIRECCIONES
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
# DASHBOARD - CORREGIDO (USA EL MISMO PERÍODO QUE EL REPORTE)
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
    
    # ===== ESTADÍSTICAS BÁSICAS =====
    total_usuarios = db.usuarios.count_documents({})
    total_productos = db.productos.count_documents({})
    total_pedidos = db.pedidos.count_documents({}) if 'pedidos' in db.list_collection_names() else 0
    
    # ===== 🔥 CORRECCIÓN: USAR EL MISMO PERÍODO QUE EL REPORTE (ÚLTIMOS 30 DÍAS) =====
    hoy = datetime.utcnow()
    fecha_fin = hoy
    fecha_inicio = hoy - timedelta(days=30)
    
    # Obtener el resumen de ventas usando VentaReporte (misma lógica que el reporte)
    resumen = VentaReporte.get_resumen_ventas(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    
    total_ventas_correcto = resumen.get('total_monto', 0)
    total_unidades = resumen.get('total_unidades', 0)
    promedio_venta = resumen.get('promedio_venta', 0)
    ventas_mes = resumen.get('total_ventas', 0)  # número de pedidos en el período
    
    # ===== OTRAS ESTADÍSTICAS =====
    mes_actual = datetime.utcnow().month
    año_actual = datetime.utcnow().year
    
    # Usuarios registrados en el mes actual
    usuarios_mes = db.usuarios.count_documents({
        'created_at': {
            '$gte': datetime(año_actual, mes_actual, 1),
            '$lt': datetime(año_actual, mes_actual + 1, 1) if mes_actual < 12 else datetime(año_actual + 1, 1, 1)
        }
    })
    
    productos_stock_bajo = db.productos.count_documents({'stock': {'$lt': 5}}) if 'productos' in db.list_collection_names() else 0
    pedidos_pendientes = db.pedidos.count_documents({'estado': 'pendiente'}) if 'pedidos' in db.list_collection_names() else 0
    
    # ===== VENTAS POR MES PARA GRÁFICOS (últimos 6 meses, usando VentaReporte) =====
    meses_labels = []
    ventas_por_mes = []
    for i in range(5, -1, -1):
        mes = datetime.utcnow().month - i
        año = datetime.utcnow().year
        if mes <= 0:
            mes += 12
            año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses_labels.append(f'{nombre_mes} {año}')
        
        # Obtener ventas de ese mes específico
        fecha_inicio_mes = datetime(año, mes, 1)
        if mes == 12:
            fecha_fin_mes = datetime(año + 1, 1, 1) - timedelta(days=1)
        else:
            fecha_fin_mes = datetime(año, mes + 1, 1) - timedelta(days=1)
        
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
                         meses_labels=meses_labels,
                         ventas_por_mes=ventas_por_mes,
                         datetime=datetime)


# ================================================================
# ANÁLISIS
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


# ================================================================
# SEGMENTACIÓN DE CLIENTES
# ================================================================

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

    vip = 0
    frecuentes = 0
    impulsivos = 0
    inactivos = 0
    clientes_con_segmento = []

    for usuario in usuarios:
        pedidos_usuario = [
            p for p in pedidos
            if str(p.get("usuario_id")) == str(usuario["_id"])
        ]
        cantidad = len(pedidos_usuario)
        total_gastado = sum(float(p.get("total", 0)) for p in pedidos_usuario)

        if total_gastado >= 10000:
            segmento = "VIP"
            vip += 1
        elif cantidad >= 5:
            segmento = "Frecuente"
            frecuentes += 1
        elif cantidad >= 1:
            segmento = "Ocasional"
            impulsivos += 1
        else:
            segmento = "Inactivo"
            inactivos += 1

        clientes_con_segmento.append({
            "nombre": usuario.get("nombre", "Usuario"),
            "email": usuario.get("email", ""),
            "foto": usuario.get("foto"),
            "total_pedidos": cantidad,
            "total_gastado": total_gastado,
            "segmento": segmento
        })

    datos = {
        "vip": vip,
        "frecuentes": frecuentes,
        "impulsivos": impulsivos,
        "inactivos": inactivos,
        "total": len(usuarios),
        "fecha_actualizacion": datetime.now().strftime('%d/%m/%Y %H:%M')
    }

    return render_template('admin/segmentacion.html', datos=datos, clientes=clientes_con_segmento)


# ================================================================
# PREDICCIÓN DE ABANDONO
# ================================================================

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
    activos = 0
    riesgo_medio = 0
    riesgo_alto = 0
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
                dias = (datetime.now() - ultimo_pedido).days
            else:
                try:
                    fecha_pedido = datetime.strptime(ultimo_pedido, "%Y-%m-%d")
                    dias = (datetime.now() - fecha_pedido).days
                except:
                    dias = 999
            
            if dias <= 30:
                activos += 1
            elif dias <= 60:
                riesgo_medio += 1
            else:
                riesgo_alto += 1

    datos = {"activos": activos, "riesgo_medio": riesgo_medio, "riesgo_alto": riesgo_alto, "total": total}
    return render_template("admin/prediccion_abandono.html", datos=datos)


# ================================================================
# PREDICCIÓN DE VENTAS
# ================================================================

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


# ================================================================
# DETECCIÓN DE FRAUDE
# ================================================================

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

    compras_sospechosas = 0
    patrones_anomalos = 0
    intentos_fraudulentos = 0

    for venta in ventas:
        total = float(venta.get("total", 0))
        if total >= 15000:
            compras_sospechosas += 1

    for usuario in usuarios:
        compras_usuario = [v for v in ventas if str(v.get("usuario_id")) == str(usuario["_id"])]
        if len(compras_usuario) >= 10:
            patrones_anomalos += 1
        total_usuario = sum(float(v.get("total", 0)) for v in compras_usuario)
        if total_usuario >= 50000:
            intentos_fraudulentos += 1

    datos = {"compras_sospechosas": compras_sospechosas, "patrones_anomalos": patrones_anomalos,
             "intentos_fraudulentos": intentos_fraudulentos, "total_ventas": len(ventas)}
    return render_template("admin/deteccion_fraude.html", datos=datos)


# ================================================================
# RESEÑAS
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
        "fecha": datetime.now().strftime("%d/%m/%Y"),
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
        
        opiniones = list(db.opiniones.find(
            {'producto_id': ObjectId(producto_id)}
        ).sort('created_at', -1))
        
        for op in opiniones:
            op['_id'] = str(op['_id'])
            op['producto_id'] = str(op['producto_id'])
            op['usuario_id'] = str(op['usuario_id'])
            
            usuario = db.usuarios.find_one({'_id': ObjectId(op['usuario_id'])})
            if usuario:
                op['usuario_nombre'] = usuario.get('nombre', 'Usuario')
            else:
                op['usuario_nombre'] = op.get('usuario_nombre', 'Usuario')
        
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


# ================================================================
# FAVORITOS
# ================================================================

def lista_favoritos():
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus favoritos', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    favoritos = usuario.get('favoritos', []) if usuario else []
    
    productos = []
    for fav_id in favoritos:
        producto = Producto.obtener_por_id(fav_id)
        if producto:
            producto['_id'] = str(producto['_id'])
            productos.append(producto)
    
    return render_template('tienda/favoritos.html', productos=productos)

def agregar_favorito(producto_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    db.usuarios.update_one(
        {'_id': ObjectId(session['user_id'])},
        {'$addToSet': {'favoritos': producto_id}}
    )
    
    return jsonify({'success': True, 'message': 'Agregado a favoritos'})

def eliminar_favorito(producto_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    db.usuarios.update_one(
        {'_id': ObjectId(session['user_id'])},
        {'$pull': {'favoritos': producto_id}}
    )
    
    return jsonify({'success': True, 'message': 'Eliminado de favoritos'})


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
    
    update_data['updated_at'] = datetime.utcnow()
    
    db.usuarios.update_one(
        {'_id': ObjectId(id)},
        {'$set': update_data}
    )
    
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
    db.usuarios.update_one(
        {'_id': ObjectId(id)},
        {'$set': {'activo': nuevo_estado, 'updated_at': datetime.utcnow()}}
    )
    
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
    
    db.usuarios.update_one(
        {'_id': ObjectId(id)},
        {'$set': {'rol': rol, 'updated_at': datetime.utcnow()}}
    )
    
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
            'created_at': datetime.utcnow()
        }
        db.mensajes_contacto.insert_one(mensaje)
        flash('Mensaje enviado correctamente. Te contactaremos pronto.', 'success')
        return redirect(url_for('web.contacto'))
    
    return render_template('tienda/contacto.html')

def terminos():
    return render_template('tienda/terminos.html')

def privacidad():
    return render_template('tienda/privacidad.html')

def faq():
    return render_template('tienda/faq.html')

def devoluciones():
    return render_template('tienda/devoluciones.html')

def nosotros():
    return render_template('tienda/nosotros.html')


# ================================================================
# MANTENIMIENTO
# ================================================================

def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

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
            'updated_at': datetime.utcnow()
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
            'empresas_envio': request.form.getlist('empresas_envio'),
            'updated_at': datetime.utcnow()
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
            'updated_at': datetime.utcnow()
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
            'updated_at': datetime.utcnow()
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
        
        config = {'tiendas': tiendas, 'updated_at': datetime.utcnow()}
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
        mes = datetime.utcnow().month - i
        año = datetime.utcnow().year
        if mes <= 0:
            mes += 12
            año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses.append(f'{nombre_mes} {año}')
        
        count = db.ventas.count_documents({
            'fecha': {'$regex': f'{año}-{str(mes).zfill(2)}'}
        }) if 'ventas' in db.list_collection_names() else 0
        ventas_por_mes.append(count)
    
    productos_vendidos = []
    if 'ventas' in db.list_collection_names():
        pipeline = [
            {'$unwind': '$productos'},
            {'$group': {'_id': '$productos.nombre', 'total': {'$sum': '$productos.cantidad'}}},
            {'$sort': {'total': -1}},
            {'$limit': 10}
        ]
        productos_vendidos = list(db.ventas.aggregate(pipeline))
    
    return render_template('admin/reportes.html',
                         total_ventas=total_ventas,
                         total_usuarios=total_usuarios,
                         total_productos=total_productos,
                         meses=meses,
                         ventas_por_mes=ventas_por_mes,
                         productos_vendidos=productos_vendidos)

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
        try:
            filtro['fecha'] = {'$gte': datetime.strptime(fecha_inicio, '%Y-%m-%d')}
        except:
            pass
    if fecha_fin:
        try:
            if 'fecha' in filtro:
                filtro['fecha']['$lte'] = datetime.strptime(fecha_fin, '%Y-%m-%d')
            else:
                filtro['fecha'] = {'$lte': datetime.strptime(fecha_fin, '%Y-%m-%d')}
        except:
            pass
    if estado:
        filtro['estado'] = estado
    
    ventas = list(db.ventas.find(filtro).sort('fecha', -1)) if 'ventas' in db.list_collection_names() else []
    
    for v in ventas:
        v['_id'] = str(v['_id'])
        if v.get('usuario_id'):
            usuario_venta = db.usuarios.find_one({'_id': ObjectId(v['usuario_id'])})
            v['usuario_nombre'] = usuario_venta.get('nombre', 'Usuario') if usuario_venta else 'Desconocido'
    
    total_ventas = sum(v.get('total', 0) for v in ventas)
    
    return render_template('admin/reportes_ventas.html',
                         ventas=ventas,
                         total_ventas=total_ventas,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         estado=estado)

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
    
    meses = []
    registros_por_mes = []
    for i in range(5, -1, -1):
        mes = datetime.utcnow().month - i
        año = datetime.utcnow().year
        if mes <= 0:
            mes += 12
            año -= 1
        nombre_mes = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][mes - 1]
        meses.append(f'{nombre_mes} {año}')
        
        count = db.usuarios.count_documents({
            'created_at': {'$regex': f'{año}-{str(mes).zfill(2)}'}
        })
        registros_por_mes.append(count)
    
    return render_template('admin/reportes_usuarios.html',
                         total_usuarios=total_usuarios,
                         usuarios_activos=usuarios_activos,
                         usuarios_inactivos=usuarios_inactivos,
                         admins=admins,
                         vendedores=vendedores,
                         clientes=clientes,
                         meses=meses,
                         registros_por_mes=registros_por_mes)

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
    
    pipeline = [{'$group': {'_id': '$categoria', 'total': {'$sum': 1}}}, {'$sort': {'total': -1}}]
    productos_por_categoria = list(db.productos.aggregate(pipeline))
    
    productos_mas_vendidos = []
    if 'ventas' in db.list_collection_names():
        pipeline = [
            {'$unwind': '$productos'},
            {'$group': {'_id': '$productos.nombre', 'total': {'$sum': '$productos.cantidad'}}},
            {'$sort': {'total': -1}},
            {'$limit': 20}
        ]
        productos_mas_vendidos = list(db.ventas.aggregate(pipeline))
    
    return render_template('admin/reportes_productos.html',
                         total_productos=total_productos,
                         productos_activos=productos_activos,
                         productos_inactivos=productos_inactivos,
                         productos_por_categoria=productos_por_categoria,
                         productos_mas_vendidos=productos_mas_vendidos)


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
            'nombre': nombre,
            'email': email,
            'password': hashed,
            'rol': 'admin',
            'confirmado': True,
            'activo': True,
            'created_at': datetime.utcnow()
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
    
    notificacion = {
        'titulo': titulo,
        'mensaje': mensaje,
        'fecha_envio': datetime.utcnow(),
        'leida': False
    }
    
    if usuarios_destino:
        for user_id in usuarios_destino:
            db.usuarios.update_one(
                {'_id': ObjectId(user_id)},
                {'$push': {'notificaciones': notificacion}}
            )
    else:
        for user in db.usuarios.find({}):
            db.usuarios.update_one(
                {'_id': user['_id']},
                {'$push': {'notificaciones': notificacion}}
            )
    
    return jsonify({'success': True, 'message': 'Notificación enviada'})


# ================================================================
# PROMOCIONES - INTEGRACIÓN CON USUARIO
# ================================================================

def obtener_promociones_usuario():
    """Obtiene las promociones disponibles para el usuario actual (API)"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    from app.models.promocion_model import Promocion
    
    # Obtener carrito actual
    carrito = session.get('carrito', [])
    monto_carrito = sum(item.get('precio', 0) * item.get('cantidad', 1) for item in carrito)
    
    promociones = Promocion.obtener_promociones_disponibles(
        session['user_id'],
        monto_carrito,
        carrito
    )
    
    return jsonify({'success': True, 'promociones': promociones})

def promociones_destacadas_usuario():
    """Obtiene promociones destacadas para el usuario (API)"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    from app.models.promocion_model import Promocion
    
    destacadas = Promocion.obtener_promociones_destacadas(session['user_id'])
    return jsonify({'success': True, 'promociones': destacadas})

def segmento_usuario():
    """Obtiene el segmento del usuario actual (API)"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    # Calcular segmento basado en pedidos
    pedidos = list(db.pedidos.find({'usuario_id': ObjectId(session['user_id'])}))
    cantidad = len(pedidos)
    total_gastado = sum(float(p.get('total', 0)) for p in pedidos)
    
    if total_gastado >= 10000:
        segmento = "VIP"
    elif cantidad >= 5:
        segmento = "Frecuente"
    elif cantidad >= 1:
        segmento = "Ocasional"
    else:
        segmento = "Inactivo"
    
    return jsonify({
        'success': True,
        'segmento': segmento,
        'total_pedidos': cantidad,
        'total_gastado': total_gastado
    })