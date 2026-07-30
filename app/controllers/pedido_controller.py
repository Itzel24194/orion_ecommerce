# ================================================================
# app/controllers/pedido_controller.py - COMPLETO CON PROMOCIONES
# ================================================================

from flask import current_app, session, request, jsonify, render_template, flash, redirect, url_for
from datetime import datetime, timedelta
from bson import ObjectId
import random
import string
import sys 
from app.models.pedidos_model import Pedido  
from app.models.productos_model import Producto 


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
# FUNCIONES AUXILIARES
# ================================================================

def _safe_items_list(pedido):
    """
    Convierte el campo 'items' de un pedido en una lista Python segura.
    Maneja todos los casos: lista, dict, None, callable, etc.
    """
    if not pedido:
        return []
    
    raw = pedido.get('items')

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        return list(raw.values())

    if raw is None or callable(raw):
        return []

    try:
        if hasattr(raw, '__iter__') and not isinstance(raw, str):
            return list(raw)
    except Exception:
        pass

    return []


def _enriquecer_items(items):
    """Asegura que cada item tenga los campos imagen y foto."""
    if not items:
        return []
    for item in items:
        if not item.get('imagen'):
            item['imagen'] = 'default.jpg'
        if not item.get('foto'):
            item['foto'] = item['imagen']
    return items


def generar_codigo_recogida():
    """Genera código aleatorio para Click & Collect"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def calcular_descuento_volumen(total_unidades, subtotal):
    """
    Calcula el descuento por volumen según la cantidad de unidades
    Estilo Liverpool - Descuentos progresivos
    """
    porcentaje = 0
    descuento = 0
    
    if total_unidades >= 200:
        porcentaje = 25
    elif total_unidades >= 150:
        porcentaje = 20
    elif total_unidades >= 100:
        porcentaje = 15
    elif total_unidades >= 50:
        porcentaje = 10
    elif total_unidades >= 25:
        porcentaje = 7
    elif total_unidades >= 10:
        porcentaje = 5
    
    if porcentaje > 0:
        descuento = subtotal * (porcentaje / 100)
    
    return descuento, porcentaje


# ================================================================
# CARRITO Y CHECKOUT (CLIENTES) - CON SOPORTE PARA CUPONES Y PROMOCIONES
# ================================================================

def carrito_checkout():
    """Página unificada de Carrito + Checkout (estilo Liverpool) - CON CUPONES Y PROMOCIONES"""
    if 'user_id' not in session:
        flash('Inicia sesión para realizar tu pedido', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))
    
    carrito_items = session.get('carrito', [])
    
    if not carrito_items:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('web.catalogo'))
    
    items_enriquecidos = []
    for item in carrito_items:
        producto = Producto.obtener_por_id(item.get('id'))
        if producto:
            fotos = producto.get('fotos', [])
            imagen = fotos[0] if fotos else 'default.jpg'
            
            atributos = item.get('atributos', {})
            if atributos:
                for key, value in atributos.items():
                    if isinstance(value, str):
                        atributos[key] = ' '.join(value.split())
            
            item_enriquecido = {
                'id': item.get('id'),
                'nombre': item.get('nombre', 'Producto'),
                'precio': float(item.get('precio', 0)),
                'cantidad': int(item.get('cantidad', 1)),
                'atributos': atributos,
                'imagen': imagen,
                'foto': imagen,
                'sku': item.get('sku', '')
            }
            items_enriquecidos.append(item_enriquecido)
        else:
            items_enriquecidos.append(item)
    
    session['carrito_para_guardar'] = items_enriquecidos
    session.modified = True
    
    # Calcular totales del carrito
    subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 1)) for item in items_enriquecidos)
    iva = subtotal * 0.16
    
    total_unidades = sum(int(item.get('cantidad', 0)) for item in items_enriquecidos)
    
    # 🔥 OBTENER CUPÓN APLICADO
    cupon_aplicado = session.get('cupon_aplicado', None)
    descuento_cupon = 0
    
    # 🔥 OBTENER PROMOCIÓN APLICADA (NUEVO)
    promocion_aplicada = session.get('promocion_aplicada', None)
    descuento_promocion = 0
    
    # Calcular descuento por volumen
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
    
    # Calcular descuento total (volumen + cupón + promoción)
    descuento_total = descuento_volumen
    
    if cupon_aplicado:
        descuento_cupon = cupon_aplicado.get('descuento', 0)
        descuento_total += descuento_cupon
        print(f"💰 Cupón aplicado: {cupon_aplicado.get('codigo')} - Descuento: ${descuento_cupon:.2f}", file=sys.stderr)
    
    if promocion_aplicada:
        descuento_promocion = promocion_aplicada.get('descuento', 0)
        descuento_total += descuento_promocion
        print(f"🎁 Promoción aplicada: {promocion_aplicada.get('nombre')} - Descuento: ${descuento_promocion:.2f}", file=sys.stderr)
    
    subtotal_con_descuentos = subtotal - descuento_total
    
    if total_unidades >= 50:
        envio = 199.00
    else:
        envio = 99.00
    
    total_carrito = subtotal_con_descuentos + iva + envio
    
    # Si es POST, procesar checkout
    if request.method == 'POST':
        return procesar_checkout()
    
    tiendas = []
    config = db.configuracion.find_one({'_id': 'tiendas'})
    if config:
        tiendas = config.get('tiendas', [])
    
    categorias = list(db.categorias.find({}))
    
    return render_template('tienda/carrito.html',
                         usuario=usuario,
                         carrito_items=items_enriquecidos,
                         tiendas=tiendas,
                         categorias=categorias,
                         subtotal=subtotal,
                         iva=iva,
                         total_carrito=total_carrito,
                         envio=envio,
                         total_unidades=total_unidades,
                         descuento_volumen=descuento_volumen,
                         porcentaje_descuento=porcentaje_descuento,
                         cupon_aplicado=cupon_aplicado,
                         descuento_cupon=descuento_cupon,
                         promocion_aplicada=promocion_aplicada,      # ← NUEVO
                         descuento_promocion=descuento_promocion,    # ← NUEVO
                         descuento_total=descuento_total,
                         subtotal_con_descuentos=subtotal_con_descuentos)


def procesar_checkout():
    """Procesar el pago y crear pedido - CON SOPORTE PARA CUPONES Y PROMOCIONES"""
    if 'user_id' not in session:
        flash('Inicia sesión para procesar tu pedido', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    try:
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('web.carrito_checkout'))
        
        carrito_items = session.get('carrito', [])
        
        if not carrito_items:
            flash('Tu carrito está vacío', 'warning')
            return redirect(url_for('web.catalogo'))
        
        print("=" * 70, file=sys.stderr)
        print("📦 PROCESANDO CHECKOUT", file=sys.stderr)
        print(f"📦 CARRITO ITEMS: {len(carrito_items)} productos", file=sys.stderr)
        for i, item in enumerate(carrito_items):
            print(f"  Item {i+1}: {item.get('nombre')} - Cant: {item.get('cantidad')} - Precio: {item.get('precio')}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        
        # CREAR LISTA DE ITEMS PARA EL PEDIDO
        items_para_guardar = []
        for item in carrito_items:
            producto = Producto.obtener_por_id(item.get('id'))
            imagen = 'default.jpg'
            if producto:
                fotos = producto.get('fotos', [])
                if fotos:
                    imagen = fotos[0]
            
            atributos = item.get('atributos', {})
            if atributos:
                for key, value in atributos.items():
                    if isinstance(value, str):
                        atributos[key] = ' '.join(value.split())
            
            item_para_guardar = {
                'id': str(item.get('id')),
                'nombre': str(item.get('nombre', 'Producto')),
                'precio': float(item.get('precio', 0)),
                'cantidad': int(item.get('cantidad', 1)),
                'atributos': atributos,
                'imagen': imagen,
                'foto': imagen,
                'sku': str(item.get('sku', ''))
            }
            items_para_guardar.append(item_para_guardar)
        
        # Obtener datos del formulario
        tipo_envio = request.form.get('tipo_envio', 'domicilio')
        metodo_pago = request.form.get('metodo_pago', 'tarjeta')
        notas = request.form.get('notas', '')
        
        # Calcular totales
        subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 1)) for item in items_para_guardar)
        iva = subtotal * 0.16
        
        total_unidades = sum(int(item.get('cantidad', 0)) for item in items_para_guardar)
        
        # 🔥 OBTENER CUPÓN APLICADO
        cupon_aplicado = session.get('cupon_aplicado', None)
        descuento_cupon = 0
        codigo_cupon = None
        
        if cupon_aplicado:
            descuento_cupon = cupon_aplicado.get('descuento', 0)
            codigo_cupon = cupon_aplicado.get('codigo')
            notas = f"{notas}\n🎫 Cupón aplicado: {codigo_cupon} - Descuento: ${descuento_cupon:.2f}"
            print(f"💰 Cupón aplicado en checkout: {codigo_cupon} - ${descuento_cupon:.2f}", file=sys.stderr)
        
        # 🔥 OBTENER PROMOCIÓN APLICADA
        promocion_aplicada = session.get('promocion_aplicada', None)
        descuento_promocion = 0
        promocion_id = None
        
        if promocion_aplicada:
            descuento_promocion = promocion_aplicada.get('descuento', 0)
            promocion_id = promocion_aplicada.get('id')
            notas = f"{notas}\n🎁 Promoción aplicada: {promocion_aplicada.get('nombre')} - Descuento: ${descuento_promocion:.2f}"
            print(f"🎁 Promoción aplicada en checkout: {promocion_aplicada.get('nombre')} - ${descuento_promocion:.2f}", file=sys.stderr)
        
        # Calcular descuento por volumen
        descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
        
        descuento_total = descuento_volumen + descuento_cupon + descuento_promocion
        subtotal_con_descuentos = subtotal - descuento_total
        
        if tipo_envio == 'click_collect':
            envio = 0
        elif total_unidades >= 50:
            envio = 199.00
            notas = f"{notas}\n🚚 ENVÍO PRIORITARIO - Pedido de {total_unidades} unidades"
        else:
            envio = 99.00
        
        total = subtotal_con_descuentos + iva + envio
        
        # Generar número de pedido
        year = datetime.utcnow().year
        count = db.pedidos.count_documents({}) + 1
        numero_pedido = f"ORION-{year}-{str(count).zfill(4)}"
        
        fecha_entrega = datetime.utcnow() + timedelta(days=1 if total_unidades >= 50 else 5)
        
        # ============================================================
        # CREAR PEDIDO CON ITEMS Y CUPÓN / PROMOCIÓN
        # ============================================================
        pedido = {
            'usuario_id': session['user_id'],
            'usuario_nombre': usuario.get('nombre', ''),
            'usuario_email': usuario.get('email', ''),
            'usuario_telefono': usuario.get('telefono', ''),
            'numero_pedido': numero_pedido,
            'items': list(items_para_guardar),
            'subtotal': round(subtotal, 2),
            'iva': round(iva, 2),
            'envio': round(envio, 2),
            'descuento_volumen': round(descuento_volumen, 2),
            'porcentaje_descuento': porcentaje_descuento,
            'descuento_cupon': round(descuento_cupon, 2),
            'codigo_cupon': codigo_cupon,
            'descuento_promocion': round(descuento_promocion, 2),      # ← NUEVO
            'promocion_id': promocion_id,                              # ← NUEVO
            'descuento_total': round(descuento_total, 2),
            'total': round(total, 2),
            'metodo_pago': metodo_pago,
            'tipo_envio': tipo_envio,
            'estado': 'pendiente',
            'pago_estado': 'pendiente',
            'notas': notas,
            'total_unidades': total_unidades,
            'es_mayorista': total_unidades >= 50,
            'fecha_entrega_estimada': fecha_entrega,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Dirección de envío
        if tipo_envio == 'domicilio':
            direccion = {
                'calle': request.form.get('calle'),
                'numero': request.form.get('numero'),
                'colonia': request.form.get('colonia'),
                'ciudad': request.form.get('ciudad'),
                'estado': request.form.get('estado'),
                'cp': request.form.get('cp'),
                'pais': request.form.get('pais', 'México'),
                'referencias': request.form.get('referencias')
            }
            pedido['direccion'] = direccion
        else:
            pedido['tienda_recogida'] = request.form.get('tienda_recogida')
            pedido['codigo_recogida'] = generar_codigo_recogida()
        
        # 🔥 REGISTRAR USO DEL CUPÓN
        if codigo_cupon and session.get('user_id'):
            from app.models.cupon_model import CuponUsuario
            # Insertar pedido primero para obtener el ID
            resultado_insert = db.pedidos.insert_one(pedido)
            pedido_id = str(resultado_insert.inserted_id)
            
            # Registrar el uso del cupón
            CuponUsuario.registrar_uso(
                usuario_id=session['user_id'],
                cupon_codigo=codigo_cupon,
                pedido_id=pedido_id,
                descuento_aplicado=descuento_cupon
            )
            
            # Limpiar cupón de la sesión
            session.pop('cupon_aplicado', None)
            session.pop('descuento_aplicado', None)
            session.pop('total_con_descuento', None)
        else:
            resultado = db.pedidos.insert_one(pedido)
            pedido_id = str(resultado.inserted_id)
        
        # 🔥 REGISTRAR USO DE LA PROMOCIÓN (si existe)
        if promocion_id and session.get('user_id'):
            try:
                from app.models.promocion_model import Promocion
                Promocion.registrar_uso(promocion_id, session['user_id'], descuento_promocion)
            except Exception as e:
                print(f"⚠️ Error al registrar uso de promoción: {e}", file=sys.stderr)
        
        # 🔥 Actualizar pedido con el ID de la venta si es necesario (ya lo tenemos)
        # Si se registró el cupón, ya se actualizó el pedido_id en la colección de cupones_usuarios
        
        print(f"✅ PEDIDO GUARDADO CON ID: {pedido_id}", file=sys.stderr)
        
        # LIMPIAR CARRITO Y PROMOCIÓN DE LA SESIÓN
        session['carrito'] = []
        session['carrito_para_guardar'] = []
        session.pop('promocion_aplicada', None)  # Limpiar promoción
        session.modified = True
        
        flash('¡Pedido realizado con éxito!', 'success')
        return redirect(url_for('web.ver_pedido', id=pedido_id))
        
    except Exception as e:
        print(f"❌ Error en procesar_checkout: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        flash(f'Error al procesar el pedido: {str(e)}', 'danger')
        return redirect(url_for('web.ver_carrito'))


# ================================================================
# PEDIDOS - CLIENTES
# ================================================================

def mis_pedidos_clientes():
    """Lista de pedidos del usuario - VISTA PARA CLIENTES"""
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus pedidos', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    pedidos = list(db.pedidos.find(
        {'usuario_id': session['user_id']}
    ).sort('created_at', -1))
    
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']
        
        if 'total' not in pedido:
            pedido['total'] = 0
        
        pedido['puede_cancelar'] = pedido.get('estado') in ['pendiente', 'confirmado']
    
    categorias = list(db.categorias.find({}))
    
    return render_template('tienda/mis_pedidos_clientes.html', 
                         pedidos=pedidos,
                         categorias=categorias)


def ver_pedido(id):
    """Ver detalle de un pedido específico - CLIENTE - CORREGIDO"""
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus pedidos', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    try:
        pedido = None
        
        try:
            pedido = db.pedidos.find_one({
                '_id': ObjectId(id),
                'usuario_id': session['user_id']
            })
        except Exception:
            pass
        
        if not pedido:
            pedido = db.pedidos.find_one({
                'numero_pedido': id,
                'usuario_id': session['user_id']
            })
        
        if not pedido:
            pedido = db.pedidos.find_one({
                '_id': id,
                'usuario_id': session['user_id']
            })
        
        if not pedido:
            flash('Pedido no encontrado', 'danger')
            return redirect(url_for('web.mis_pedidos_clientes'))
        
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']

        if 'total' not in pedido:
            pedido['total'] = 0
        
        categorias = list(db.categorias.find({}))
        
        return render_template('tienda/detalle_pedido.html', 
                             pedido=pedido,
                             categorias=categorias)
        
    except Exception as e:
        print(f"❌ Error en ver_pedido: {str(e)}", file=sys.stderr)
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('web.mis_pedidos_clientes'))


def cancelar_pedido(id):
    """Cancelar un pedido (API) - CLIENTE"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    
    try:
        pedido = db.pedidos.find_one({
            '_id': ObjectId(id),
            'usuario_id': session['user_id']
        })
        
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        
        if pedido.get('estado') not in ['pendiente', 'confirmado']:
            return jsonify({'success': False, 'message': 'Este pedido no puede ser cancelado'}), 400
        
        db.pedidos.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'estado': 'cancelado',
                'fecha_cancelacion': datetime.utcnow()
            }}
        )
        
        return jsonify({'success': True, 'message': 'Pedido cancelado correctamente'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def generar_codigo_recogida_api(id):
    """Generar código de recogida para Click & Collect (API) - CLIENTE"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    
    try:
        pedido = db.pedidos.find_one({
            '_id': ObjectId(id),
            'usuario_id': session['user_id']
        })
        
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        
        if pedido.get('tipo_envio') != 'click_collect':
            return jsonify({'success': False, 'message': 'Este pedido no es Click & Collect'}), 400
        
        if pedido.get('estado') != 'confirmado':
            return jsonify({'success': False, 'message': 'El pedido aún no está listo'}), 400
        
        codigo = generar_codigo_recogida()
        
        db.pedidos.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'codigo_recogida': codigo,
                'estado': 'preparando',
                'fecha_preparacion': datetime.utcnow()
            }}
        )
        
        return jsonify({
            'success': True,
            'codigo': codigo,
            'tienda': pedido.get('tienda_recogida')
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def confirmar_pedido(id):
    """Confirmar recepción de pedido (API) - CLIENTE"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    
    try:
        pedido = db.pedidos.find_one({
            '_id': ObjectId(id),
            'usuario_id': session['user_id']
        })
        
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        
        if pedido.get('estado') != 'enviado':
            return jsonify({'success': False, 'message': 'El pedido aún no ha sido enviado'}), 400
        
        db.pedidos.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'estado': 'entregado',
                'fecha_entrega_real': datetime.utcnow()
            }}
        )
        
        return jsonify({'success': True, 'message': 'Pedido confirmado como entregado'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def rastrear_pedido():
    """Rastrear pedido sin autenticación - PÚBLICO"""
    db = current_app.db
    
    if request.method == 'POST':
        numero = request.form.get('numero_pedido')
        email = request.form.get('email')
        
        pedido = db.pedidos.find_one({
            'numero_pedido': numero,
            'usuario_email': email
        })
        
        if pedido:
            pedido['_id'] = str(pedido['_id'])
            pedido['items'] = _safe_items_list(pedido)
            _enriquecer_items(pedido['items'])
            
            categorias = list(db.categorias.find({}))
            return render_template('tienda/rastrear_pedido.html', 
                                 pedido=pedido,
                                 categorias=categorias)
        else:
            flash('Pedido no encontrado. Verifica tu número y email.', 'danger')
    
    categorias = list(db.categorias.find({}))
    return render_template('tienda/rastrear_pedido.html', categorias=categorias)


# ================================================================
# API PARA MÓVIL Y FRONTEND
# ================================================================

def api_pedidos():
    """API para listar pedidos del usuario"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    
    pedidos = list(db.pedidos.find(
        {'usuario_id': session['user_id']}
    ).sort('created_at', -1))
    
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['usuario_id'] = str(pedido['usuario_id'])
        pedido['items'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items'])
    
    return jsonify({'pedidos': pedidos})


def api_pedido(id):
    """API para obtener detalle de un pedido"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    
    try:
        pedido = db.pedidos.find_one({
            '_id': ObjectId(id),
            'usuario_id': session['user_id']
        })
        
        if not pedido:
            return jsonify({'error': 'Pedido no encontrado'}), 404
        
        pedido['_id'] = str(pedido['_id'])
        pedido['usuario_id'] = str(pedido['usuario_id'])
        pedido['items'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items'])
        
        return jsonify(pedido)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ================================================================
# ADMIN - FUNCIONES PARA ADMINISTRADORES
# ================================================================

def admin_listar_pedidos():
    """Listar todos los pedidos - ADMIN"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    try:
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception as e:
        print(f"❌ ERROR al buscar usuario: {e}", file=sys.stderr)
        flash('Error al buscar usuario', 'danger')
        return redirect(url_for('web.login'))
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))
    
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    
    if rol_normalizado != 'admin':
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    pedidos = list(db.pedidos.find().sort('created_at', -1))
    
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']
    
    return render_template('admin/pedidos.html', pedidos=pedidos)


def admin_ver_pedido(id):
    """Ver detalle de pedido - ADMIN"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    try:
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception as e:
        print(f"❌ Error al buscar usuario: {e}", file=sys.stderr)
        flash('Error al verificar usuario', 'danger')
        return redirect(url_for('web.admin_listar_pedidos'))
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))
    
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    
    if rol_normalizado != 'admin':
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    pedido = db.pedidos.find_one({'_id': ObjectId(id)})
    
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('web.admin_listar_pedidos'))
    
    pedido['_id'] = str(pedido['_id'])
    pedido['items_list'] = _safe_items_list(pedido)
    _enriquecer_items(pedido['items_list'])
    pedido['items'] = pedido['items_list']
    
    return render_template('admin/detalle_pedido_admin.html', pedido=pedido)


def admin_actualizar_estado_pedido(id):
    """Actualizar estado de pedido (admin) - API"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    
    rol_normalizado = normalizar_rol(usuario.get('rol')) if usuario else None
    
    if not usuario or rol_normalizado != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json() or {}
    nuevo_estado = data.get('estado')
    
    estados_validos = ['pendiente', 'confirmado', 'preparando', 'enviado', 'entregado', 'cancelado']
    if nuevo_estado not in estados_validos:
        return jsonify({'error': 'Estado inválido'}), 400
    
    try:
        db.pedidos.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'estado': nuevo_estado,
                'updated_at': datetime.utcnow()
            }}
        )
        return jsonify({'success': True, 'message': f'Estado actualizado a {nuevo_estado}'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def admin_eliminar_pedido(id):
    """Eliminar pedido (admin) - API"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    
    rol_normalizado = normalizar_rol(usuario.get('rol')) if usuario else None
    
    if not usuario or rol_normalizado != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        db.pedidos.delete_one({'_id': ObjectId(id)})
        return jsonify({'success': True, 'message': 'Pedido eliminado'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def debug_pedido(id):
    """DEBUG - ver estructura raw del pedido en MongoDB"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    db = current_app.db

    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id)})
        if not pedido:
            return jsonify({'error': 'Pedido no encontrado'}), 404

        raw_items = pedido.get('items')

        debug_info = {
            'numero_pedido': pedido.get('numero_pedido'),
            'total': pedido.get('total'),
            'items_type': str(type(raw_items)),
            'items_is_list': isinstance(raw_items, list),
            'items_is_dict': isinstance(raw_items, dict),
            'items_is_callable': callable(raw_items),
            'items_value': None,
            'all_keys': list(pedido.keys()),
        }

        if isinstance(raw_items, list):
            debug_info['items_count'] = len(raw_items)
            debug_info['items_value'] = raw_items
        elif isinstance(raw_items, dict):
            debug_info['items_count'] = len(raw_items)
            debug_info['items_value'] = list(raw_items.values())
        elif raw_items is None:
            debug_info['items_value'] = 'None (campo no existe o es null)'
        elif callable(raw_items):
            debug_info['items_value'] = 'ES UN CALLABLE/BUILTIN - campo items no existe en el documento'
            debug_info['campos_similares'] = [k for k in pedido.keys() if 'item' in k.lower() or 'product' in k.lower() or 'carrito' in k.lower()]
        else:
            debug_info['items_value'] = f'Tipo desconocido: {str(raw_items)[:200]}'

        pedido_raw = {}
        for k, v in pedido.items():
            if k == '_id':
                pedido_raw[k] = str(v)
            elif isinstance(v, list):
                pedido_raw[k] = v
            elif hasattr(v, 'isoformat'):
                pedido_raw[k] = v.isoformat()
            else:
                try:
                    pedido_raw[k] = v
                except Exception:
                    pedido_raw[k] = str(v)

        debug_info['documento_completo'] = pedido_raw

        return jsonify(debug_info), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def test_admin_pedidos():
    """Función de prueba para verificar que la ruta funciona"""
    return "¡La ruta /admin/pedidos está funcionando correctamente!"