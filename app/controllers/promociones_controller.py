# app/controllers/promociones_controller.py
# Controlador completo para promociones estilo Liverpool

import os
import logging
import traceback
from flask import render_template, request, redirect, url_for, session, current_app, flash, jsonify
from bson import ObjectId
from datetime import datetime, timezone
from app.models.promocion_model import Promocion
from app.models.productos_model import Producto
from app.models.categorias_model import Categoria
from app.models.usuarios_model import Usuario
import sys

# Configurar logging
logger = logging.getLogger(__name__)

# ================================================================
# FUNCIONES AUXILIARES PARA CONVERSIÓN SEGURA
# ================================================================

def safe_float(valor, default=0.0):
    if valor is None or valor == '':
        return default
    try:
        return float(valor)
    except (ValueError, TypeError):
        return default

def safe_int(valor, default=0):
    if valor is None or valor == '':
        return default
    try:
        return int(valor)
    except (ValueError, TypeError):
        return default

# ================================================================
# FUNCIÓN: ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS (normalizada a minúsculas)
# ================================================================

def asignar_segmento_automatico(data):
    """
    Analiza los datos de la promoción y asigna automáticamente los segmentos.
    Los nombres de segmentos se devuelven en minúsculas para consistencia.
    """
    tipo = data.get('tipo')
    descuento_valor = data.get('descuento_valor', 0)
    descuento_tipo = data.get('descuento_tipo', 'porcentaje')
    monto_minimo = data.get('monto_minimo', 0)
    prioridad = data.get('prioridad', 0)
    cantidad_requerida = data.get('cantidad_requerida', 0)

    # Inicializar lista de segmentos
    segmentos = []

    # Reglas de asignación (todas en minúsculas)
    if tipo == 'combo' or tipo == 'cantidad':
        segmentos = ['frecuente', 'todos']
    elif tipo == 'abandono_carrito':
        segmentos = ['inactivo']
    elif tipo == 'cumpleanos':
        segmentos = ['nuevo', 'inactivo']
    elif prioridad == 2:
        segmentos = ['vip']
    elif tipo == 'envio_gratis':
        if monto_minimo > 200:
            segmentos = ['frecuente', 'vip']
        else:
            segmentos = ['todos']
    else:
        descuento_efectivo = descuento_valor
        if descuento_tipo == 'porcentaje':
            if descuento_efectivo >= 20:
                if monto_minimo >= 500:
                    segmentos = ['vip']
                else:
                    segmentos = ['frecuente', 'vip']
            elif descuento_efectivo >= 10:
                if monto_minimo < 200:
                    segmentos = ['inactivo', 'todos']
                else:
                    segmentos = ['frecuente', 'todos']
            else:
                segmentos = ['todos']
        else:  # monto fijo
            if descuento_efectivo >= 200 and monto_minimo >= 500:
                segmentos = ['vip']
            elif descuento_efectivo >= 50:
                segmentos = ['frecuente', 'todos']
            else:
                segmentos = ['todos']

    # Asegurar que todos los segmentos estén en minúsculas
    return [s.lower() for s in segmentos] if segmentos else ['todos']

# ================================================================
# OBTENER PROMOCIONES DESTACADAS
# ================================================================

def obtener_promociones_destacadas(usuario_id=None):
    db = current_app.db
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    filtro = {
        'activo': True,
        'mostrar_en_home': True,
        '$or': [{'fecha_inicio': {'$lte': ahora}}, {'fecha_inicio': None}],
        '$or': [{'fecha_fin': {'$gte': ahora}}, {'fecha_fin': None}]
    }
    promociones = list(db.promociones.find(filtro).sort('prioridad', -1).limit(6))
    if usuario_id:
        segmento_usuario = Usuario.obtener_segmento(usuario_id).lower()  # Normalizar a minúsculas
        promociones = [p for p in promociones if 'todos' in p.get('segmentos', ['todos']) or segmento_usuario in [s.lower() for s in p.get('segmentos', [])]]
    return promociones

# ================================================================
# ADMIN - GESTIÓN DE PROMOCIONES
# ================================================================

def admin_listar_promociones():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    try:
        tipo = request.args.get('tipo', '')
        estado = request.args.get('estado', '')
        busqueda = request.args.get('busqueda', '')
        filtros = {}
        if tipo:
            filtros['tipo'] = tipo
        if estado == 'activo':
            filtros['activo'] = True
        elif estado == 'inactivo':
            filtros['activo'] = False
        if busqueda:
            filtros['nombre'] = busqueda
        
        promociones = Promocion.obtener_todos(filtros)
        todas = Promocion.obtener_todos()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        activas = [p for p in todas if p.get('activo')]
        expiradas = [p for p in todas if p.get('fecha_fin') and p['fecha_fin'] < ahora]
        proximas = [p for p in todas if p.get('fecha_inicio') and p['fecha_inicio'] > ahora]
        
        return render_template('admin/promociones.html',
                               promociones=promociones,
                               total=len(todas),
                               activas=len(activas),
                               expiradas=len(expiradas),
                               proximas=len(proximas),
                               datetime=datetime,
                               ahora=ahora)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_listar_promociones: {str(e)}")
        flash(f'Error al cargar promociones: {str(e)}', 'danger')
        return redirect(url_for('web.dashboard'))

def admin_crear_promocion():
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            if not tipo:
                flash('Debes seleccionar un tipo de promoción', 'danger')
                return redirect(url_for('web.admin_crear_promocion'))

            data_temp = {
                'tipo': tipo,
                'descuento_valor': safe_float(request.form.get('descuento_valor', 0)),
                'descuento_tipo': request.form.get('descuento_tipo'),
                'monto_minimo': safe_float(request.form.get('monto_minimo', 0)),
                'prioridad': safe_int(request.form.get('prioridad', 0)),
                'cantidad_requerida': safe_int(request.form.get('cantidad_requerida', 0))
            }
            segmentos = asignar_segmento_automatico(data_temp)

            productos_aplicables = request.form.getlist('productos_aplicables')
            categorias_aplicables = request.form.getlist('categorias_aplicables')
            empresas_aplicables = request.form.getlist('empresas_aplicables')
            metodos_pago = request.form.getlist('metodos_pago')
            combo_productos = request.form.getlist('combo_productos')

            combo_productos = [p for p in combo_productos if p and p.strip()]
            productos_aplicables = [p for p in productos_aplicables if p and p.strip()]
            categorias_aplicables = [c for c in categorias_aplicables if c and c.strip()]
            empresas_aplicables = [e for e in empresas_aplicables if e and e.strip()]

            fecha_inicio = None
            fecha_fin = None
            if request.form.get('fecha_inicio'):
                fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d')
            if request.form.get('fecha_fin'):
                fecha_fin = datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d')

            codigo = request.form.get('codigo', '').strip()
            if codigo == '':
                codigo = None

            data = {
                'nombre': request.form.get('nombre', '').strip(),
                'descripcion': request.form.get('descripcion', '').strip(),
                'tipo': tipo,
                'activo': request.form.get('activo') == '1',
                'prioridad': safe_int(request.form.get('prioridad', 0)),
                'imagen': request.form.get('imagen', '').strip(),
                'codigo': codigo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'descuento_tipo': request.form.get('descuento_tipo'),
                'descuento_valor': safe_float(request.form.get('descuento_valor', 0)),
                'monto_minimo': safe_float(request.form.get('monto_minimo', 0)),
                'cantidad_requerida': safe_int(request.form.get('cantidad_requerida', 0)),
                'cantidad_gratis': safe_int(request.form.get('cantidad_gratis', 0)),
                'combo_productos': combo_productos,
                'combo_descuento': safe_float(request.form.get('combo_descuento', 0)),
                'productos_aplicables': productos_aplicables,
                'categorias_aplicables': categorias_aplicables,
                'empresas_aplicables': empresas_aplicables,
                'segmentos': segmentos,
                'metodos_pago': metodos_pago,
                'uso_maximo': safe_int(request.form.get('uso_maximo', 0)) or None,
                'usos_por_usuario': safe_int(request.form.get('usos_por_usuario', 0)) or None,
                'mostrar_en_home': request.form.get('mostrar_en_home') == '1',
                'mostrar_en_producto': request.form.get('mostrar_en_producto') == '1'
            }

            if data['tipo'] in ['descuento_directo', 'pago']:
                if not data['descuento_tipo'] or data['descuento_valor'] <= 0:
                    flash('Debes especificar un descuento válido', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))
            if data['tipo'] == 'cantidad':
                if data['cantidad_requerida'] <= 0 or data['cantidad_gratis'] <= 0:
                    flash('Debes especificar cantidad requerida y gratuita', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))
            if data['tipo'] == 'combo':
                if not data['combo_productos'] or len(data['combo_productos']) < 2:
                    flash('Debes seleccionar al menos 2 productos para el combo', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))

            Promocion.crear(data)
            flash('Promoción creada exitosamente', 'success')
            return redirect(url_for('web.admin_listar_promociones'))

        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('web.admin_crear_promocion'))
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error en admin_crear_promocion: {str(e)}")
            flash(f'Error al crear promoción: {str(e)}', 'danger')
            return redirect(url_for('web.admin_crear_promocion'))
    
    try:
        productos = Producto.obtener_todos()
        categorias = Categoria.obtener_todas()
        empresas = db.empresas.find().sort('nombre', 1)
        return render_template('admin/promocion_crear.html',
                               productos=productos,
                               categorias=categorias,
                               empresas=empresas,
                               ahora=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error cargando datos para admin_crear_promocion: {str(e)}")
        flash(f'Error al cargar el formulario: {str(e)}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))

def admin_editar_promocion(promocion_id):
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            flash('Promoción no encontrada', 'danger')
            return redirect(url_for('web.admin_listar_promociones'))
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error obteniendo promoción {promocion_id}: {str(e)}")
        flash('Error al obtener la promoción', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))
    
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            if not tipo:
                flash('Debes seleccionar un tipo de promoción', 'danger')
                return redirect(url_for('web.admin_editar_promocion', promocion_id=promocion_id))

            data_temp = {
                'tipo': tipo,
                'descuento_valor': safe_float(request.form.get('descuento_valor', 0)),
                'descuento_tipo': request.form.get('descuento_tipo'),
                'monto_minimo': safe_float(request.form.get('monto_minimo', 0)),
                'prioridad': safe_int(request.form.get('prioridad', 0)),
                'cantidad_requerida': safe_int(request.form.get('cantidad_requerida', 0))
            }
            segmentos = asignar_segmento_automatico(data_temp)

            productos_aplicables = request.form.getlist('productos_aplicables')
            categorias_aplicables = request.form.getlist('categorias_aplicables')
            empresas_aplicables = request.form.getlist('empresas_aplicables')
            metodos_pago = request.form.getlist('metodos_pago')
            combo_productos = request.form.getlist('combo_productos')

            combo_productos = [p for p in combo_productos if p and p.strip()]
            productos_aplicables = [p for p in productos_aplicables if p and p.strip()]
            categorias_aplicables = [c for c in categorias_aplicables if c and c.strip()]
            empresas_aplicables = [e for e in empresas_aplicables if e and e.strip()]

            fecha_inicio = None
            fecha_fin = None
            if request.form.get('fecha_inicio'):
                fecha_inicio = datetime.strptime(request.form.get('fecha_inicio'), '%Y-%m-%d')
            if request.form.get('fecha_fin'):
                fecha_fin = datetime.strptime(request.form.get('fecha_fin'), '%Y-%m-%d')

            codigo = request.form.get('codigo', '').strip()
            if codigo == '':
                codigo = None

            data = {
                'nombre': request.form.get('nombre', '').strip(),
                'descripcion': request.form.get('descripcion', '').strip(),
                'tipo': tipo,
                'activo': request.form.get('activo') == '1',
                'prioridad': safe_int(request.form.get('prioridad', 0)),
                'imagen': request.form.get('imagen', '').strip(),
                'codigo': codigo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'descuento_tipo': request.form.get('descuento_tipo'),
                'descuento_valor': safe_float(request.form.get('descuento_valor', 0)),
                'monto_minimo': safe_float(request.form.get('monto_minimo', 0)),
                'cantidad_requerida': safe_int(request.form.get('cantidad_requerida', 0)),
                'cantidad_gratis': safe_int(request.form.get('cantidad_gratis', 0)),
                'combo_productos': combo_productos,
                'combo_descuento': safe_float(request.form.get('combo_descuento', 0)),
                'productos_aplicables': productos_aplicables,
                'categorias_aplicables': categorias_aplicables,
                'empresas_aplicables': empresas_aplicables,
                'segmentos': segmentos,
                'metodos_pago': metodos_pago,
                'uso_maximo': safe_int(request.form.get('uso_maximo', 0)) or None,
                'usos_por_usuario': safe_int(request.form.get('usos_por_usuario', 0)) or None,
                'mostrar_en_home': request.form.get('mostrar_en_home') == '1',
                'mostrar_en_producto': request.form.get('mostrar_en_producto') == '1'
            }

            Promocion.actualizar(promocion_id, data)
            flash('Promoción actualizada exitosamente', 'success')
            return redirect(url_for('web.admin_listar_promociones'))
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error en admin_editar_promocion: {str(e)}")
            flash(f'Error al actualizar promoción: {str(e)}', 'danger')
            return redirect(url_for('web.admin_editar_promocion', promocion_id=promocion_id))
    
    try:
        productos = Producto.obtener_todos()
        categorias = Categoria.obtener_todas()
        empresas = db.empresas.find().sort('nombre', 1)
        return render_template('admin/promocion_crear.html',
                               promocion=promocion,
                               productos=productos,
                               categorias=categorias,
                               empresas=empresas,
                               datetime=datetime,
                               ahora=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error cargando datos para admin_editar_promocion: {str(e)}")
        flash(f'Error al cargar el formulario: {str(e)}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))

def admin_eliminar_promocion(promocion_id):
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    if request.method == 'POST':
        try:
            if Promocion.eliminar(promocion_id):
                flash('Promoción eliminada correctamente', 'success')
            else:
                flash('Error al eliminar la promoción', 'danger')
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error en admin_eliminar_promocion: {str(e)}")
            flash(f'Error al eliminar promoción: {str(e)}', 'danger')
    return redirect(url_for('web.admin_listar_promociones'))

def admin_promocion_estadisticas(promocion_id):
    db = current_app.db
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            flash('Promoción no encontrada', 'danger')
            return redirect(url_for('web.admin_listar_promociones'))
        
        estadisticas = Promocion.obtener_estadisticas(promocion_id)
        
        pedidos = list(db.pedidos.find({
            '$or': [
                {'promocion_id': promocion_id},
                {'promocion_id': ObjectId(promocion_id)}
            ]
        }).sort('created_at', -1).limit(20))
        
        for pedido in pedidos:
            pedido['_id'] = str(pedido['_id'])
            if pedido.get('usuario_id'):
                try:
                    usuario_pedido = db.usuarios.find_one({'_id': ObjectId(pedido['usuario_id'])})
                    pedido['usuario_nombre'] = usuario_pedido.get('nombre', 'Desconocido') if usuario_pedido else 'Desconocido'
                except:
                    pedido['usuario_nombre'] = 'Desconocido'
        
        return render_template('admin/promocion_estadisticas.html',
                               promocion=promocion,
                               estadisticas=estadisticas,
                               pedidos=pedidos,
                               datetime=datetime,
                               ahora=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_promocion_estadisticas: {str(e)}")
        flash(f'Error al cargar estadísticas: {str(e)}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))

# ================================================================
# CLIENTE - PROMOCIONES (CON DEPURACIÓN Y NORMALIZACIÓN)
# ================================================================

def listar_promociones_cliente():
    if 'user_id' not in session:
        flash('Inicia sesión para ver promociones', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))
    
    try:
        # Obtener segmento en minúsculas para comparación
        segmento_usuario = Usuario.obtener_segmento(session['user_id']).lower()
        print(f"🔍 Segmento del usuario {session['user_id']}: '{segmento_usuario}'", file=sys.stderr)
        
        carrito_items = session.get('carrito', {})
        monto_carrito = 0
        productos_carrito = []
        
        if isinstance(carrito_items, dict):
            for item in carrito_items.values():
                if isinstance(item, dict):
                    precio = float(item.get('precio', 0))
                    cantidad = int(item.get('cantidad', 1))
                    monto_carrito += precio * cantidad
                    productos_carrito.append({
                        'producto_id': item.get('id'),
                        'cantidad': cantidad,
                        'precio': precio
                    })
        elif isinstance(carrito_items, list):
            for item in carrito_items:
                if isinstance(item, dict):
                    precio = float(item.get('precio', 0))
                    cantidad = int(item.get('cantidad', 1))
                    monto_carrito += precio * cantidad
                    productos_carrito.append({
                        'producto_id': item.get('id'),
                        'cantidad': cantidad,
                        'precio': precio
                    })
        
        destacadas = obtener_promociones_destacadas(session['user_id'])
        disponibles = obtener_promociones_disponibles(session['user_id'], productos=productos_carrito)
        
        # DEPURACIÓN
        print(f"📋 Promociones disponibles: {len(disponibles)}", file=sys.stderr)
        for p in disponibles:
            print(f"  - {p.get('nombre')} | segmentos: {p.get('segmentos')} | monto_min: {p.get('monto_minimo')}", file=sys.stderr)
        
        for promo in disponibles:
            promo['cumple_minimo'] = monto_carrito >= promo.get('monto_minimo', 0)
            promo['monto_carrito'] = monto_carrito
        
        promociones_usadas = list(db.pedidos.find({
            'usuario_id': ObjectId(session['user_id']),
            'promocion_id': {'$exists': True}
        }))
        usadas_ids = [str(p.get('promocion_id')) for p in promociones_usadas if p.get('promocion_id')]
        
        return render_template('tienda/mis_promociones.html',
                               destacadas=destacadas,
                               disponibles=disponibles,
                               usadas_ids=usadas_ids,
                               segmento=segmento_usuario,
                               monto_carrito=monto_carrito,
                               datetime=datetime,
                               ahora=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en listar_promociones_cliente: {str(e)}")
        flash('Error al cargar promociones', 'danger')
        return redirect(url_for('web.raiz_tienda'))

# ================================================================
# FUNCIÓN OBTENER_PROMOCIONES_DISPONIBLES (con normalización)
# ================================================================

def obtener_promociones_disponibles(usuario_id, productos=None):
    """
    Obtiene promociones disponibles para un usuario.
    """
    db = current_app.db
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    filtro = {
        'activo': True,
        '$or': [{'fecha_inicio': {'$lte': ahora}}, {'fecha_inicio': None}],
        '$or': [{'fecha_fin': {'$gte': ahora}}, {'fecha_fin': None}]
    }
    promociones = list(db.promociones.find(filtro).sort('prioridad', -1))
    
    print(f"🔍 Promociones activas y vigentes: {len(promociones)}", file=sys.stderr)
    for p in promociones:
        print(f"  - {p.get('nombre')} | segmentos: {p.get('segmentos')} | descuento: {p.get('descuento_valor')}", file=sys.stderr)
    
    if usuario_id:
        segmento_usuario = Usuario.obtener_segmento(usuario_id).lower()
        print(f"🔍 Segmento para filtrar: '{segmento_usuario}'", file=sys.stderr)
        # Normalizar segmentos de la promoción a minúsculas para comparación
        promociones = [p for p in promociones if 'todos' in p.get('segmentos', ['todos']) or segmento_usuario in [s.lower() for s in p.get('segmentos', [])]]
        
        print(f"🔍 Después de filtrar por segmento: {len(promociones)}", file=sys.stderr)
        
        for p in promociones[:]:
            usos_por_usuario = p.get('usos_por_usuario')
            if usos_por_usuario:
                usos_actuales = db.pedidos.count_documents({
                    'usuario_id': ObjectId(usuario_id),
                    'promocion_id': ObjectId(p['_id'])
                })
                if usos_actuales >= usos_por_usuario:
                    promociones.remove(p)
                    continue
            uso_maximo = p.get('uso_maximo')
            if uso_maximo:
                usos_totales = db.pedidos.count_documents({'promocion_id': ObjectId(p['_id'])})
                if usos_totales >= uso_maximo:
                    promociones.remove(p)
                    continue
    
    if productos and len(productos) > 0:
        print(f"🔍 Filtrado por productos, carrito tiene {len(productos)} productos", file=sys.stderr)
        for p in promociones[:]:
            productos_aplicables = p.get('productos_aplicables', [])
            if productos_aplicables:
                ids_productos = [str(prod['producto_id']) for prod in productos]
                if not any(pid in [str(x) for x in productos_aplicables] for pid in ids_productos):
                    promociones.remove(p)
                    continue
            categorias_aplicables = p.get('categorias_aplicables', [])
            if categorias_aplicables:
                ids_categorias = set()
                for prod in productos:
                    producto = db.productos.find_one({'_id': ObjectId(prod['producto_id'])})
                    if producto and producto.get('categoria_id'):
                        ids_categorias.add(str(producto['categoria_id']))
                if not any(cat in [str(x) for x in categorias_aplicables] for cat in ids_categorias):
                    promociones.remove(p)
                    continue
    
    return promociones

# ================================================================
# FUNCIÓN APLICAR PROMOCIÓN
# ================================================================

def aplicar_promocion():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    data = request.get_json() or {}
    promocion_id = data.get('promocion_id')
    
    carrito = session.get('carrito', {})
    monto_carrito = 0
    productos_carrito = []
    
    if isinstance(carrito, dict):
        for key, item in carrito.items():
            if isinstance(item, dict):
                precio = item.get('precio', 0)
                cantidad = item.get('cantidad', 1)
                monto_carrito += precio * cantidad
                productos_carrito.append({
                    'producto_id': item.get('id'),
                    'cantidad': cantidad,
                    'precio': precio
                })
    elif isinstance(carrito, list):
        for item in carrito:
            if isinstance(item, dict):
                precio = item.get('precio', 0)
                cantidad = item.get('cantidad', 1)
                monto_carrito += precio * cantidad
                productos_carrito.append({
                    'producto_id': item.get('id'),
                    'cantidad': cantidad,
                    'precio': precio
                })
    
    if data.get('monto_carrito'):
        monto_carrito = data.get('monto_carrito', monto_carrito)
    
    metodo_pago = data.get('metodo_pago', '')
    
    if not promocion_id:
        return jsonify({'success': False, 'message': 'Selecciona una promoción'}), 400
    
    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            return jsonify({'success': False, 'message': 'Promoción no encontrada'}), 404
        
        valida, mensaje, detalles = es_valida(
            promocion,
            session['user_id'],
            monto_carrito,
            productos_carrito,
            metodo_pago
        )
        
        if not valida:
            return jsonify({'success': False, 'message': mensaje}), 400
        
        Promocion.registrar_uso(promocion_id, session['user_id'], detalles.get('descuento', 0))
        
        session['promocion_aplicada'] = {
            'id': promocion_id,
            'nombre': promocion.get('nombre'),
            'codigo': promocion.get('codigo'),
            'descuento': detalles.get('descuento', 0),
            'monto_final': detalles.get('monto_final', monto_carrito)
        }
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': 'Promoción aplicada correctamente',
            'descuento': detalles.get('descuento', 0),
            'monto_final': detalles.get('monto_final', monto_carrito)
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en aplicar_promocion: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ================================================================
# QUITAR PROMOCIÓN
# ================================================================

def quitar_promocion():
    if 'promocion_aplicada' in session:
        session.pop('promocion_aplicada', None)
        session.modified = True
        return jsonify({'success': True, 'message': 'Promoción eliminada'})
    return jsonify({'success': False, 'message': 'No hay promoción aplicada'})

# ================================================================
# VALIDAR CÓDIGO DE PROMOCIÓN
# ================================================================

def validar_codigo_promocion():
    data = request.get_json() or {}
    codigo = data.get('codigo', '').strip().upper()
    if not codigo:
        return jsonify({'success': False, 'message': 'Ingresa un código'}), 400
    try:
        promocion = Promocion.obtener_por_codigo(codigo)
        if not promocion:
            return jsonify({'success': False, 'message': 'Código no válido'}), 404
        valida, mensaje, detalles = es_valida(
            promocion,
            session.get('user_id'),
            data.get('monto_carrito', 0),
            data.get('productos_carrito', [])
        )
        if not valida:
            return jsonify({'success': False, 'message': mensaje}), 400
        return jsonify({
            'success': True,
            'message': 'Código válido',
            'promocion': {
                'id': str(promocion['_id']),
                'nombre': promocion.get('nombre'),
                'descuento': detalles.get('descuento', 0)
            }
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en validar_codigo_promocion: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ================================================================
# PROMOCIONES EN CARRITO (API)
# ================================================================

def promociones_carrito():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    try:
        db = current_app.db
        carrito = session.get('carrito', {})
        monto_carrito = 0
        productos_carrito = []
        
        if isinstance(carrito, dict):
            for item in carrito.values():
                if isinstance(item, dict):
                    precio = float(item.get('precio', 0))
                    cantidad = int(item.get('cantidad', 1))
                    monto_carrito += precio * cantidad
                    productos_carrito.append({'producto_id': item.get('id'), 'cantidad': cantidad, 'precio': precio})
        elif isinstance(carrito, list):
            for item in carrito:
                if isinstance(item, dict):
                    precio = float(item.get('precio', 0))
                    cantidad = int(item.get('cantidad', 1))
                    monto_carrito += precio * cantidad
                    productos_carrito.append({'producto_id': item.get('id'), 'cantidad': cantidad, 'precio': precio})
        
        promociones = obtener_promociones_disponibles(session['user_id'], productos=productos_carrito)
        return jsonify({'success': True, 'promociones': promociones, 'monto_carrito': monto_carrito})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en promociones_carrito: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ================================================================
# FUNCIONES DE VALIDACIÓN (es_valida)
# ================================================================

def es_valida(promocion, usuario_id, monto, productos, metodo_pago=''):
    db = current_app.db
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if not promocion.get('activo', False):
        return False, 'Esta promoción no está activa', {}
    
    fecha_inicio = promocion.get('fecha_inicio')
    fecha_fin = promocion.get('fecha_fin')
    if fecha_inicio and fecha_inicio > ahora:
        return False, 'Esta promoción aún no ha comenzado', {}
    if fecha_fin and fecha_fin < ahora:
        return False, 'Esta promoción ha expirado', {}
    
    uso_maximo = promocion.get('uso_maximo')
    if uso_maximo:
        usos_totales = db.pedidos.count_documents({'promocion_id': ObjectId(promocion['_id'])})
        if usos_totales >= uso_maximo:
            return False, 'Esta promoción ya alcanzó su límite de usos', {}
    
    if usuario_id:
        usos_por_usuario = promocion.get('usos_por_usuario')
        if usos_por_usuario:
            usos_actuales = db.pedidos.count_documents({
                'usuario_id': ObjectId(usuario_id),
                'promocion_id': ObjectId(promocion['_id'])
            })
            if usos_actuales >= usos_por_usuario:
                return False, 'Ya has usado esta promoción el número máximo de veces', {}
    
    segmentos = promocion.get('segmentos', ['todos'])
    if 'todos' not in segmentos:
        if usuario_id:
            segmento_usuario = Usuario.obtener_segmento(usuario_id).lower()
            # Normalizar segmentos de la promoción a minúsculas
            segmentos_promocion = [s.lower() for s in segmentos]
            if segmento_usuario not in segmentos_promocion:
                return False, 'Esta promoción no aplica para tu perfil', {}
    
    monto_minimo = promocion.get('monto_minimo', 0)
    if monto < monto_minimo:
        return False, f'El monto mínimo requerido es ${monto_minimo:.2f} y tu carrito tiene ${monto:.2f}', {}
    
    metodos_pago = promocion.get('metodos_pago', [])
    if metodos_pago and metodo_pago:
        if metodo_pago not in metodos_pago:
            return False, 'Esta promoción no aplica para el método de pago seleccionado', {}
    
    descuento = 0
    monto_final = monto
    tipo = promocion.get('tipo')
    
    if tipo == 'descuento_directo':
        if promocion.get('descuento_tipo') == 'porcentaje':
            descuento = monto * (promocion.get('descuento_valor', 0) / 100)
        else:
            descuento = promocion.get('descuento_valor', 0)
    elif tipo == 'envio_gratis':
        descuento = 0
    elif tipo == 'cantidad':
        if productos:
            for prod in productos:
                if prod.get('cantidad', 0) >= promocion.get('cantidad_requerida', 0):
                    descuento = promocion.get('cantidad_gratis', 0) * prod.get('precio', 0)
                    break
    elif tipo == 'combo':
        combo_productos = promocion.get('combo_productos', [])
        if combo_productos:
            ids_combo = [str(p) for p in combo_productos]
            count = sum(1 for prod in productos if str(prod.get('producto_id')) in ids_combo)
            if count >= len(ids_combo):
                descuento = promocion.get('combo_descuento', 0) * sum(prod.get('precio', 0) for prod in productos if str(prod.get('producto_id')) in ids_combo) / 100
    elif tipo == 'pago':
        if promocion.get('descuento_tipo') == 'porcentaje':
            descuento = monto * (promocion.get('descuento_valor', 0) / 100)
        else:
            descuento = promocion.get('descuento_valor', 0)
    
    monto_final = max(0, monto - descuento)
    
    return True, 'Promoción válida', {
        'descuento': descuento,
        'monto_final': monto_final
    }

# ================================================================
# FUNCIONES ADICIONALES (API, TOGGLE, EXPORTACIÓN)
# ================================================================

def admin_toggle_promocion(promocion_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            return jsonify({'success': False, 'message': 'Promoción no encontrada'}), 404
        
        nuevo_estado = not promocion.get('activo', True)
        Promocion.toggle_activo(promocion_id, nuevo_estado)
        return jsonify({'success': True, 'activo': nuevo_estado, 'message': 'Promoción actualizada'})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_toggle_promocion: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

def admin_promocion_accion_masiva():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    data = request.get_json() or {}
    ids = data.get('ids', [])
    accion = data.get('accion', '')
    if not ids:
        return jsonify({'success': False, 'message': 'No hay promociones seleccionadas'}), 400
    
    try:
        count = 0
        for promocion_id in ids:
            if accion == 'activar':
                Promocion.toggle_activo(promocion_id, True)
                count += 1
            elif accion == 'inactivar':
                Promocion.toggle_activo(promocion_id, False)
                count += 1
            elif accion == 'eliminar':
                Promocion.eliminar(promocion_id)
                count += 1
        return jsonify({'success': True, 'message': f'Acción "{accion}" completada para {count} promociones'})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_promocion_accion_masiva: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

def admin_promociones_exportar_csv():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    
    try:
        import csv
        from io import StringIO
        from flask import Response
        
        promociones = Promocion.obtener_todos()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Nombre', 'Tipo', 'Activo', 'Código', 'Fecha Inicio', 'Fecha Fin', 'Usos Actuales', 'Uso Máximo', 'Segmentos'])
        for p in promociones:
            writer.writerow([
                p.get('_id', ''),
                p.get('nombre', ''),
                p.get('tipo', ''),
                p.get('activo', False),
                p.get('codigo', ''),
                p.get('fecha_inicio', ''),
                p.get('fecha_fin', ''),
                p.get('usos_actuales', 0),
                p.get('uso_maximo', ''),
                ', '.join(p.get('segmentos', []))
            ])
        output.seek(0)
        return Response(output.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': 'attachment; filename=promociones.csv'
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_promociones_exportar_csv: {str(e)}")
        flash('Error al exportar promociones', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))

def admin_promociones_exportar_pdf():
    flash('Exportación a PDF aún no implementada', 'warning')
    return redirect(url_for('web.admin_listar_promociones'))

def admin_promociones_api():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    rol_usuario = usuario.get('rol', 'cliente').lower()
    if rol_usuario not in ['admin', 'superadmin', 'administrador']:
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        promociones = Promocion.obtener_todos()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        activas = [p for p in promociones if p.get('activo')]
        expiradas = [p for p in promociones if p.get('fecha_fin') and p['fecha_fin'] < ahora]
        proximas = [p for p in promociones if p.get('fecha_inicio') and p['fecha_inicio'] > ahora]
        return jsonify({
            'total': len(promociones),
            'activas': len(activas),
            'expiradas': len(expiradas),
            'proximas': len(proximas),
            'por_tipo': {
                tipo: len([p for p in promociones if p.get('tipo') == tipo])
                for tipo in set(p.get('tipo') for p in promociones)
            }
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en admin_promociones_api: {str(e)}")
        return jsonify({'error': str(e)}), 500

def promociones_disponibles_api():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    try:
        disponibles = obtener_promociones_disponibles(session['user_id'])
        return jsonify({'success': True, 'promociones': disponibles})
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error en promociones_disponibles_api: {str(e)}")
        return jsonify({'error': str(e)}), 500