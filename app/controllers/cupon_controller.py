# app/controllers/cupon_controller.py - COMPLETO CON ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS
# ================================================================

from flask import render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app.models.cupon_model import Cupon, CuponUsuario, calcular_descuento_cupon, aplicar_cupon_pedido
from app.models.usuarios_model import Usuario
from bson import ObjectId
from datetime import datetime, timezone
import random
import string
import sys
import json


# ================================================================
# ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS (similar a promociones)
# ================================================================

def asignar_segmento_automatico(data):
    """
    Analiza los datos del cupón y asigna automáticamente los segmentos.
    Los nombres de segmentos coinciden con los que usa Usuario.obtener_segmento:
    'vip', 'frecuente', 'ocasional', 'inactivo', 'nuevo', 'todos'
    Retorna una lista de segmentos.
    """
    tipo = data.get('tipo', 'porcentaje')
    valor = data.get('valor', 0)
    minimo_compra = data.get('minimo_compra', 0)

    # Si es envío gratis
    if tipo == 'envio_gratis':
        if minimo_compra >= 200:
            return ['frecuente', 'vip']
        elif minimo_compra >= 100:
            return ['frecuente', 'todos']
        else:
            return ['todos']

    # Evaluar descuento
    if tipo == 'porcentaje':
        if valor >= 20:
            if minimo_compra >= 500:
                return ['vip']
            else:
                return ['frecuente', 'vip']
        elif valor >= 10:
            if minimo_compra < 200:
                return ['inactivo', 'todos']
            else:
                return ['frecuente', 'todos']
        else:
            return ['todos']
    else:  # monto_fijo
        if valor >= 200 and minimo_compra >= 500:
            return ['vip']
        elif valor >= 50:
            return ['frecuente', 'todos']
        else:
            return ['todos']

    return ['todos']


# ================================================================
# FUNCIONES PARA EL ADMINISTRADOR
# ================================================================

def admin_listar_cupones():
    """Listar todos los cupones (Admin)"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_usuario = usuario.get('rol', '').lower().strip()
    if rol_usuario not in ['admin', 'administrador']:
        flash('No tienes permisos para acceder a esta sección', 'danger')
        return redirect(url_for('web.dashboard'))

    cupones = Cupon.obtener_todos()
    
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    cupones_activos = 0
    cupones_inactivos = 0
    cupones_expirados = 0
    cupones_proximos = 0
    total_usos = 0
    
    for cupon in cupones:
        total_usos += cupon.get('usos_actuales', 0)
        
        if cupon.get('activo', False):
            fecha_fin = cupon.get('fecha_fin')
            if fecha_fin and fecha_fin < ahora:
                cupones_expirados += 1
            elif cupon.get('fecha_inicio') and cupon.get('fecha_inicio') > ahora:
                cupones_proximos += 1
            else:
                cupones_activos += 1
        else:
            cupones_inactivos += 1

    return render_template('admin/cupones.html', 
                           cupones=cupones, 
                           datetime=datetime,
                           cupones_activos=cupones_activos,
                           cupones_inactivos=cupones_inactivos,
                           cupones_expirados=cupones_expirados,
                           cupones_proximos=cupones_proximos,
                           total_usos=total_usos)


def admin_crear_cupon():
    """Crear un nuevo cupón (Admin) - CON ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_usuario = usuario.get('rol', '').lower().strip()
    if rol_usuario not in ['admin', 'administrador']:
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))

    db = current_app.db
    categorias = list(db.categorias.find({}).sort("nombre", 1))
    productos = list(db.productos.find({}).sort("nombre", 1))

    if request.method == 'POST':
        try:
            codigo = request.form.get('codigo', '').strip().upper()

            if not codigo:
                codigo = Cupon.generar_codigo()

            if Cupon.obtener_por_codigo(codigo):
                flash('El código ya existe. Genera uno diferente.', 'danger')
                return redirect(url_for('web.admin_crear_cupon'))

            # 🔥 OBTENER DATOS PARA ASIGNACIÓN AUTOMÁTICA
            tipo = request.form.get('tipo', 'porcentaje')
            valor = float(request.form.get('valor', 0))
            minimo_compra = float(request.form.get('minimo_compra', 0))

            data_temp = {
                'tipo': tipo,
                'valor': valor,
                'minimo_compra': minimo_compra
            }
            segmentos = asignar_segmento_automatico(data_temp)

            fecha_inicio = request.form.get('fecha_inicio')
            fecha_fin = request.form.get('fecha_fin')

            categorias_seleccionadas = [c for c in request.form.getlist('categorias') if c and c.strip()]
            productos_seleccionados = [p for p in request.form.getlist('productos') if p and p.strip()]

            datos = {
                "codigo": codigo,
                "nombre": request.form.get('nombre', '').strip(),
                "descripcion": request.form.get('descripcion', '').strip(),
                "tipo": tipo,
                "valor": valor,
                "fecha_inicio": datetime.strptime(fecha_inicio, '%Y-%m-%d') if fecha_inicio else None,
                "fecha_fin": datetime.strptime(fecha_fin, '%Y-%m-%d') if fecha_fin else None,
                "uso_maximo": int(request.form.get('uso_maximo', 0)),
                "uso_por_usuario": int(request.form.get('uso_por_usuario', 1)),
                "minimo_compra": minimo_compra,
                "segmentos": segmentos,  # ← ASIGNADOS AUTOMÁTICAMENTE
                "categorias": categorias_seleccionadas,
                "productos": productos_seleccionados,
                "activo": request.form.get('activo') == '1',
                "mostrar_en_tienda": request.form.get('mostrar_en_tienda') == '1'
            }

            if not datos['nombre']:
                flash('El nombre es obligatorio', 'danger')
                return redirect(url_for('web.admin_crear_cupon'))

            if datos['valor'] <= 0 and datos['tipo'] != 'envio_gratis':
                flash('El valor debe ser mayor a 0', 'danger')
                return redirect(url_for('web.admin_crear_cupon'))

            if datos['tipo'] == 'porcentaje' and datos['valor'] > 100:
                flash('El descuento porcentual no puede superar el 100%', 'danger')
                return redirect(url_for('web.admin_crear_cupon'))

            Cupon.crear(datos)
            flash(f'Cupón {codigo} creado correctamente con segmentos: {", ".join(segmentos)}', 'success')
            return redirect(url_for('web.admin_listar_cupones'))

        except Exception as e:
            flash(f'Error al crear cupón: {str(e)}', 'danger')
            return redirect(url_for('web.admin_crear_cupon'))

    # Para GET, pasar las listas de categorías y productos
    return render_template('admin/crear_cupon.html', 
                           categorias=categorias,
                           productos=productos)


def admin_editar_cupon(id):
    """Editar un cupón existente (Admin) - CON ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_usuario = usuario.get('rol', '').lower().strip()
    if rol_usuario not in ['admin', 'administrador']:
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))

    cupon = Cupon.obtener_por_id(id)
    if not cupon:
        flash('Cupón no encontrado', 'danger')
        return redirect(url_for('web.admin_listar_cupones'))

    db = current_app.db
    categorias = list(db.categorias.find({}).sort("nombre", 1))
    productos = list(db.productos.find({}).sort("nombre", 1))

    if request.method == 'POST':
        try:
            # 🔥 OBTENER DATOS PARA ASIGNACIÓN AUTOMÁTICA
            tipo = request.form.get('tipo', 'porcentaje')
            valor = float(request.form.get('valor', 0))
            minimo_compra = float(request.form.get('minimo_compra', 0))

            data_temp = {
                'tipo': tipo,
                'valor': valor,
                'minimo_compra': minimo_compra
            }
            segmentos = asignar_segmento_automatico(data_temp)

            fecha_inicio = request.form.get('fecha_inicio')
            fecha_fin = request.form.get('fecha_fin')

            categorias_seleccionadas = [c for c in request.form.getlist('categorias') if c and c.strip()]
            productos_seleccionados = [p for p in request.form.getlist('productos') if p and p.strip()]

            datos = {
                "nombre": request.form.get('nombre', '').strip(),
                "descripcion": request.form.get('descripcion', '').strip(),
                "tipo": tipo,
                "valor": valor,
                "fecha_inicio": datetime.strptime(fecha_inicio, '%Y-%m-%d') if fecha_inicio else None,
                "fecha_fin": datetime.strptime(fecha_fin, '%Y-%m-%d') if fecha_fin else None,
                "uso_maximo": int(request.form.get('uso_maximo', 0)),
                "uso_por_usuario": int(request.form.get('uso_por_usuario', 1)),
                "minimo_compra": minimo_compra,
                "segmentos": segmentos,  # ← REASIGNADOS AUTOMÁTICAMENTE
                "categorias": categorias_seleccionadas,
                "productos": productos_seleccionados,
                "activo": request.form.get('activo') == '1',
                "mostrar_en_tienda": request.form.get('mostrar_en_tienda') == '1'
            }

            if not datos['nombre']:
                flash('El nombre es obligatorio', 'danger')
                return redirect(url_for('web.admin_editar_cupon', id=id))

            if datos['valor'] <= 0 and datos['tipo'] != 'envio_gratis':
                flash('El valor debe ser mayor a 0', 'danger')
                return redirect(url_for('web.admin_editar_cupon', id=id))

            if datos['tipo'] == 'porcentaje' and datos['valor'] > 100:
                flash('El descuento porcentual no puede superar el 100%', 'danger')
                return redirect(url_for('web.admin_editar_cupon', id=id))

            Cupon.actualizar(id, datos)
            flash(f'Cupón actualizado correctamente con segmentos: {", ".join(segmentos)}', 'success')
            return redirect(url_for('web.admin_listar_cupones'))

        except Exception as e:
            flash(f'Error al actualizar cupón: {str(e)}', 'danger')
            return redirect(url_for('web.admin_editar_cupon', id=id))

    return render_template('admin/editar_cupon.html', 
                           cupon=cupon, 
                           datetime=datetime,
                           categorias=categorias,
                           productos=productos)


def admin_eliminar_cupon(id):
    """Eliminar un cupón (Admin)"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_usuario = usuario.get('rol', '').lower().strip()
    if rol_usuario not in ['admin', 'administrador']:
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))

    try:
        Cupon.eliminar(id)
        flash('Cupón eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar cupón: {str(e)}', 'danger')

    return redirect(url_for('web.admin_listar_cupones'))


def admin_cupon_estadisticas(id):
    """Ver estadísticas de uso de un cupón (Admin)"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_usuario = usuario.get('rol', '').lower().strip()
    if rol_usuario not in ['admin', 'administrador']:
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))

    cupon = Cupon.obtener_por_id(id)
    if not cupon:
        flash('Cupón no encontrado', 'danger')
        return redirect(url_for('web.admin_listar_cupones'))

    usos = CuponUsuario.obtener_usos_por_cupon(cupon.get('codigo'))
    estadisticas = Cupon.obtener_estadisticas(id)

    usuarios_usaron = []
    for uso in usos:
        usuario_id = uso.get('usuario_id')
        if usuario_id:
            user = Usuario.obtener_por_id(usuario_id)
            if user:
                usuarios_usaron.append({
                    'nombre': user.get('nombre', 'Usuario'),
                    'email': user.get('email', ''),
                    'fecha_uso': uso.get('fecha_uso'),
                    'pedido_id': uso.get('pedido_id'),
                    'descuento_aplicado': uso.get('descuento_aplicado', 0)
                })

    return render_template('admin/cupon_estadisticas.html',
                           cupon=cupon,
                           usos=usos,
                           usuarios_usaron=usuarios_usaron,
                           estadisticas=estadisticas,
                           datetime=datetime)


# ================================================================
# FUNCIONES PARA EL CLIENTE (sin cambios)
# ================================================================

def clientes_mis_cupones():
    """Ver los cupones disponibles para el cliente según su segmento"""
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus cupones', 'warning')
        return redirect(url_for('web.login'))

    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))

    segmento = Usuario.obtener_segmento(session['user_id'])
    session['segmento'] = segmento

    carrito_items = session.get('carrito', [])
    total_carrito = 0.0
    
    if not carrito_items:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {'usuario_id': session['user_id']},
            sort=[('created_at', -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get('total', 0))
    else:
        for item in carrito_items:
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            total_carrito += precio * cantidad
    
    session['total_carrito'] = total_carrito
    session.modified = True

    cupones = Cupon.obtener_cupones_cliente(session['user_id'], segmento, total_carrito)
    historial = CuponUsuario.obtener_historial_usuario(session['user_id'])

    db = current_app.db
    categorias = list(db.categorias.find({}))
    productos = list(db.productos.find({}))

    return render_template('tienda/mis_cupones.html',
                           cupones=cupones,
                           historial=historial,
                           segmento=segmento,
                           usuario=usuario,
                           total_carrito=total_carrito,
                           categorias=categorias,
                           productos=productos)


def cliente_aplicar_cupon():
    """Aplicar un cupón al carrito (API) - REDIRIGE AL CARRITO"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    data = request.get_json()
    codigo = data.get('codigo', '').strip().upper()

    if not codigo:
        return jsonify({'success': False, 'message': 'Ingresa un código de cupón'})

    usuario = Usuario.obtener_por_id(session['user_id'])
    segmento = Usuario.obtener_segmento(session['user_id'])
    
    # Calcular total del carrito
    carrito_items = session.get('carrito', [])
    total_carrito = 0.0
    
    if carrito_items:
        for item in carrito_items:
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            total_carrito += precio * cantidad
    else:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {'usuario_id': session['user_id']},
            sort=[('created_at', -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get('total', 0))

    resultado = Cupon.es_valido(codigo, session['user_id'], segmento, total_carrito)

    if not resultado["valido"]:
        return jsonify({'success': False, 'message': resultado["mensaje"]})

    # Calcular descuento
    if resultado["tipo"] == "porcentaje":
        descuento_aplicado = (total_carrito * resultado["valor"]) / 100
    elif resultado["tipo"] == "monto_fijo":
        descuento_aplicado = min(resultado["valor"], total_carrito)
    else:
        descuento_aplicado = 0

    # GUARDAR EN SESIÓN
    session['cupon_aplicado'] = {
        'codigo': codigo,
        'tipo': resultado["tipo"],
        'valor': resultado["valor"],
        'descuento': descuento_aplicado,
        'minimo_compra': resultado["cupon"].get("minimo_compra", 0),
        'nombre': resultado["cupon"].get("nombre")
    }
    
    session['descuento_aplicado'] = descuento_aplicado
    session['total_con_descuento'] = total_carrito - descuento_aplicado
    session.modified = True

    return jsonify({
        'success': True,
        'message': f'Cupón {codigo} aplicado correctamente',
        'descuento': descuento_aplicado,
        'total_con_descuento': total_carrito - descuento_aplicado,
        'redirect': url_for('web.ver_carrito'),
        'cupon': {
            'codigo': codigo,
            'nombre': resultado["cupon"].get("nombre"),
            'tipo': resultado["tipo"],
            'valor': resultado["valor"],
            'descuento': descuento_aplicado,
            'minimo_compra': resultado["cupon"].get("minimo_compra", 0)
        }
    })


def cliente_quitar_cupon():
    """Quitar cupón del carrito (API)"""
    if 'cupon_aplicado' in session:
        session.pop('cupon_aplicado', None)
        session.pop('descuento_aplicado', None)
        session.pop('total_con_descuento', None)
        session.modified = True
        return jsonify({'success': True, 'message': 'Cupón eliminado'})

    return jsonify({'success': False, 'message': 'No hay cupón aplicado'})


def cliente_validar_cupon():
    """Validar cupón sin aplicarlo (API para checkout)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    codigo = request.args.get('codigo', '').strip().upper()
    if not codigo:
        return jsonify({'success': False, 'message': 'Ingresa un código de cupón'})

    usuario = Usuario.obtener_por_id(session['user_id'])
    segmento = Usuario.obtener_segmento(session['user_id'])
    
    carrito_items = session.get('carrito', [])
    total_carrito = 0.0
    
    if carrito_items:
        for item in carrito_items:
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            total_carrito += precio * cantidad
    else:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {'usuario_id': session['user_id']},
            sort=[('created_at', -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get('total', 0))

    resultado = Cupon.es_valido(codigo, session['user_id'], segmento, total_carrito)

    return jsonify({
        'success': resultado["valido"],
        'message': resultado["mensaje"],
        'cupon': {
            'codigo': codigo,
            'nombre': resultado["cupon"].get("nombre") if resultado.get("cupon") else None,
            'tipo': resultado["tipo"] if resultado.get("tipo") else None,
            'valor': resultado["valor"] if resultado.get("valor") else None,
            'descuento': resultado["descuento"] if resultado.get("descuento") else 0,
            'minimo_compra': resultado["cupon"].get("minimo_compra") if resultado.get("cupon") else 0
        } if resultado["valido"] else None
    })


def cliente_cupon_info():
    """Obtener información del cupón aplicado actualmente"""
    if 'cupon_aplicado' in session:
        return jsonify({
            'success': True,
            'cupon': session['cupon_aplicado']
        })
    return jsonify({
        'success': False,
        'message': 'No hay cupón aplicado'
    })