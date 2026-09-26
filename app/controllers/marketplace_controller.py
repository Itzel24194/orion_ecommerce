# ================================================================
# CONTROLLER: MARKETPLACE
# ================================================================
from datetime import datetime, timezone
from flask import (
    render_template, request, redirect, url_for, session,
    jsonify, flash, abort, current_app
)
from app.models.marketplace_model import Vendedor
from app.models.productos_model import Producto
from bson import ObjectId


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def _db():
    return current_app.db


def _uid():
    return session.get('user_id')


def _es_admin():
    return session.get('rol') == 'admin'


def _vendedor_actual():
    """Devuelve el documento del vendedor del usuario logueado (si existe)."""
    if not _uid():
        return None
    return Vendedor.obtener_por_user(_db(), _uid())


def _vendedor_es_valido(v):
    return v and v.get('estado') == 'aprobado' and v.get('activo')


# ============================================================
# ⭐ HELPER: CALCULAR MÉTRICAS REALES DE UN VENDEDOR
# ============================================================
def _calcular_metricas_reales(vendedor_id, db=None):
    """
    Calcula las métricas REALES de un vendedor leyendo directamente
    las colecciones `productos` y `pedidos`.

    Sirve como fallback cuando el doc del vendedor tiene `metricas`
    en 0 (porque se crearon productos vía vendedor_controller sin
    incrementar el contador).

    Args:
        vendedor_id: str o ObjectId del documento en 'vendedores'
        db: instancia de Mongo (opcional)

    Returns:
        dict con {productos, ventas, ingresos, comisiones}
    """
    if db is None:
        db = _db()

    if not vendedor_id:
        return {'productos': 0, 'ventas': 0, 'ingresos': 0.0, 'comisiones': 0.0}

    vid_str = str(vendedor_id)

    # 1. Contar productos activos del vendedor
    # El vendedor_id puede estar guardado como string o como ObjectId
    total_productos = 0
    try:
        filtros_productos = {
            '$or': [
                {'vendedor_id': vid_str},
            ],
            'activo': True,
        }
        # Intentar también como ObjectId si es válido
        if ObjectId.is_valid(vid_str):
            filtros_productos['$or'].append({'vendedor_id': ObjectId(vid_str)})

        total_productos = db.productos.count_documents(filtros_productos)
    except Exception as e:
        current_app.logger.warning(f'[_calcular_metricas_reales] Error contando productos: {e}')
        total_productos = 0

    # 2. Contar ventas: pedidos que contengan items del vendedor
    total_ventas = 0
    total_ingresos = 0.0
    try:
        filtro_pedidos = {
            '$or': [
                {'items.vendedor_id': vid_str},
                {'items_list.vendedor_id': vid_str},
            ],
            'estado': {'$ne': 'cancelado'},
        }
        if ObjectId.is_valid(vid_str):
            filtro_pedidos['$or'].append({'items.vendedor_id': ObjectId(vid_str)})
            filtro_pedidos['$or'].append({'items_list.vendedor_id': ObjectId(vid_str)})

        pedidos = list(db.pedidos.find(filtro_pedidos))

        for pedido in pedidos:
            # Recorrer items (soporta 'items' e 'items_list')
            items = pedido.get('items') or pedido.get('items_list') or []
            for item in items:
                item_vid = str(item.get('vendedor_id') or '')
                if item_vid == vid_str:
                    # 1 venta = 1 item vendido del vendedor
                    total_ventas += int(item.get('cantidad') or 1)
                    precio = float(item.get('precio') or 0)
                    cantidad = int(item.get('cantidad') or 1)
                    total_ingresos += precio * cantidad
    except Exception as e:
        current_app.logger.warning(f'[_calcular_metricas_reales] Error contando ventas: {e}')

    # 3. Comisiones (usando comision_pct del vendedor)
    comision_pct = 15.0
    try:
        v = Vendedor.obtener_por_id(db, vendedor_id)
        if v:
            comision_pct = float(v.get('comision_pct', 15.0))
    except Exception:
        pass

    total_comisiones = round(total_ingresos * (comision_pct / 100.0), 2)

    return {
        'productos':  total_productos,
        'ventas':     total_ventas,
        'ingresos':   round(total_ingresos, 2),
        'comisiones': total_comisiones,
    }


def _formatear_vendedor_con_metricas(v):
    """
    Toma un doc de vendedor, lo formatea y le inyecta métricas reales.
    Devuelve un dict listo para el template.
    """
    if not v:
        return {}
    try:
        v_fmt = Vendedor.formatear(v)
    except Exception as e:
        current_app.logger.warning(f'[_formatear_vendedor_con_metricas] Error formateando: {e}')
        return {}

    vid = v_fmt.get('_id') or str(v.get('_id', ''))
    metricas_reales = _calcular_metricas_reales(vid)
    v_fmt['metricas'] = metricas_reales
    return v_fmt


# ============================================================
# VISTA PÚBLICA — LANDING MARKETPLACE
# ============================================================
def index():
    """Landing pública del marketplace con vendedores destacados."""
    db = _db()

    # Vendedores aprobados y activos
    try:
        vendedores_raw = Vendedor.listar(db, estado='aprobado', limite=24)
    except Exception as e:
        current_app.logger.error(f'[marketplace.index] Error listando vendedores: {e}')
        vendedores_raw = []

    # ⭐ Inyectar métricas reales a cada vendedor
    vendedores = []
    for v in vendedores_raw:
        v_fmt = _formatear_vendedor_con_metricas(v)
        if v_fmt:
            vendedores.append(v_fmt)

    # Productos del marketplace (los que tengan vendedor_id)
    try:
        productos_mkt = list(
            db.productos.find({
                'vendedor_id': {'$exists': True, '$ne': None},
                'activo': True,
            }).limit(12).sort('created_at', -1)
        )
        # Serializar _id
        for p in productos_mkt:
            p['_id'] = str(p['_id'])
    except Exception as e:
        current_app.logger.warning(f'[marketplace.index] Error cargando productos: {e}')
        productos_mkt = []

    stats = {
        'vendedores':  len(vendedores),
        'productos':   len(productos_mkt),
    }

    return render_template(
        'tienda/marketplace/index.html',
        vendedores=vendedores,
        productos=productos_mkt,
        stats=stats,
    )


# ============================================================
# REGISTRO DE VENDEDOR
# ============================================================
def registro():
    """Formulario público para postularse como vendedor."""
    if not _uid():
        flash('Debes iniciar sesión para registrarte como vendedor', 'warning')
        return redirect(url_for('web.login') + '?next=' + url_for('web.marketplace_registro'))

    db = _db()

    # Si ya tiene una tienda, redirige al dashboard
    existing = Vendedor.obtener_por_user(db, _uid())
    if existing:
        estado = existing.get('estado', 'pendiente')
        if estado == 'aprobado':
            return redirect(url_for('web.marketplace_dashboard'))
        else:
            return redirect(url_for('web.marketplace_estado'))

    if request.method == 'POST':
        data = {
            'nombre_tienda':   request.form.get('nombre_tienda', '').strip(),
            'descripcion':     request.form.get('descripcion', '').strip(),
            'rfc':             request.form.get('rfc', '').strip(),
            'razon_social':    request.form.get('razon_social', '').strip(),
            'telefono':        request.form.get('telefono', '').strip(),
            'email_contacto':  request.form.get('email_contacto', '').strip(),
            'categorias':      request.form.getlist('categorias') or [],
            'comision_pct':    float(request.form.get('comision_pct', 15) or 15),
            'banco_nombre':    request.form.get('banco_nombre', '').strip(),
            'banco_clabe':     request.form.get('banco_clabe', '').strip(),
            'banco_titular':   request.form.get('banco_titular', '').strip(),
            'direccion': {
                'calle':       request.form.get('dir_calle', '').strip(),
                'numero':      request.form.get('dir_numero', '').strip(),
                'colonia':     request.form.get('dir_colonia', '').strip(),
                'cp':          request.form.get('dir_cp', '').strip(),
                'ciudad':      request.form.get('dir_ciudad', '').strip(),
                'estado':      request.form.get('dir_estado', '').strip(),
            },
        }

        # Validaciones básicas
        if not data['nombre_tienda']:
            flash('El nombre de la tienda es obligatorio', 'danger')
            return render_template('tienda/marketplace/registro.html', form=data)

        if not data['rfc'] or len(data['rfc']) < 12:
            flash('El RFC es obligatorio (12-13 caracteres)', 'danger')
            return render_template('tienda/marketplace/registro.html', form=data)

        if not data['banco_clabe'] or len(data['banco_clabe']) != 18:
            flash('La CLABE debe tener 18 dígitos', 'danger')
            return render_template('tienda/marketplace/registro.html', form=data)

        try:
            vid = Vendedor.crear(db, data, _uid())

            # Actualizar el rol del usuario a "vendedor" (sin quitarle el de cliente)
            db.usuarios.update_one(
                {'_id': ObjectId(_uid())},
                {'$set': {'es_vendedor': True, 'updated_at': datetime.now(timezone.utc)}}
            )

            flash('¡Solicitud enviada! Un administrador revisará tu tienda pronto.', 'success')
            return redirect(url_for('web.marketplace_estado'))

        except Exception as e:
            current_app.logger.error(f'[marketplace_registro] ERROR: {e}')
            flash(f'Error al crear la tienda: {e}', 'danger')

    # GET
    return render_template('tienda/marketplace/registro.html', form={})


def estado_solicitud():
    """Muestra el estado de la solicitud pendiente."""
    if not _uid():
        return redirect(url_for('web.login'))

    v = _vendedor_actual()
    if not v:
        return redirect(url_for('web.marketplace_registro'))

    v = _formatear_vendedor_con_metricas(v)
    return render_template('tienda/marketplace/estado.html', vendedor=v)


# ============================================================
# DASHBOARD DEL VENDEDOR
# ============================================================
def dashboard():
    if not _uid():
        flash('Inicia sesión', 'warning')
        return redirect(url_for('web.login'))

    v_raw = _vendedor_actual()
    if not v_raw:
        return redirect(url_for('web.marketplace_registro'))

    if v_raw.get('estado') != 'aprobado':
        return redirect(url_for('web.marketplace_estado'))

    # ⭐ Formatear con métricas reales
    v = _formatear_vendedor_con_metricas(v_raw)
    db = _db()

    # Productos del vendedor
    try:
        productos = list(
            db.productos.find({'vendedor_id': v['_id']}).sort('created_at', -1)
        )
    except Exception:
        productos = []

    # Ventas recientes (pedidos que incluyan productos de este vendedor)
    try:
        pedidos_recientes = list(
            db.pedidos.find({
                '$or': [
                    {'items.vendedor_id': v['_id']},
                    {'items_list.vendedor_id': v['_id']},
                ]
            }).sort('created_at', -1).limit(10)
        )
    except Exception:
        pedidos_recientes = []

    # ⭐ Métricas reales
    metricas = v.get('metricas', {}) or {}
    total_ventas     = metricas.get('ventas', 0)
    total_ingresos   = metricas.get('ingresos', 0)
    total_comisiones = metricas.get('comisiones', 0)
    saldo_neto       = round(total_ingresos - total_comisiones, 2)

    return render_template(
        'tienda/marketplace/dashboard.html',
        vendedor=v,
        productos=productos,
        pedidos=pedidos_recientes,
        total_ventas=total_ventas,
        total_ingresos=total_ingresos,
        total_comisiones=total_comisiones,
        saldo_neto=saldo_neto,
    )


# ============================================================
# ADMIN — LISTA Y GESTIÓN DE VENDEDORES
# ============================================================
def admin_lista():
    if not _es_admin():
        abort(403)

    db = _db()
    estado_filtro = request.args.get('estado', 'todos')
    vendedores_raw = Vendedor.listar(db, estado=estado_filtro, solo_activos=False, limite=200)

    # ⭐ Formatear con métricas reales
    vendedores = []
    for v in vendedores_raw:
        v_fmt = _formatear_vendedor_con_metricas(v)
        if v_fmt:
            vendedores.append(v_fmt)

    # Contadores por estado
    counts = {
        'todos':      db[Vendedor.COLLECTION].count_documents({}),
        'pendiente':  db[Vendedor.COLLECTION].count_documents({'estado': 'pendiente'}),
        'aprobado':   db[Vendedor.COLLECTION].count_documents({'estado': 'aprobado'}),
        'rechazado':  db[Vendedor.COLLECTION].count_documents({'estado': 'rechazado'}),
        'suspendido': db[Vendedor.COLLECTION].count_documents({'estado': 'suspendido'}),
    }

    return render_template(
        'admin/marketplace/vendedores.html',
        vendedores=vendedores,
        counts=counts,
        estado_filtro=estado_filtro,
    )


def admin_detalle(vid):
    if not _es_admin():
        abort(403)

    v_raw = Vendedor.obtener_por_id(_db(), vid)
    if not v_raw:
        abort(404)

    # ⭐ Formatear con métricas reales
    v = _formatear_vendedor_con_metricas(v_raw)
    db = _db()

    # Productos del vendedor
    try:
        productos = list(db.productos.find({'vendedor_id': v['_id']}))
    except Exception:
        productos = []

    # Info del usuario dueño
    usuario = None
    if v.get('user_id'):
        try:
            usuario = db.usuarios.find_one({'_id': ObjectId(v['user_id'])})
            if usuario:
                usuario['_id'] = str(usuario['_id'])
                usuario.pop('password', None)
        except Exception:
            pass

    return render_template(
        'admin/marketplace/vendedor_detalle.html',
        vendedor=v,
        productos=productos,
        usuario=usuario,
    )


def admin_cambiar_estado(vid):
    if not _es_admin():
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    data = request.get_json() or {}
    nuevo_estado = data.get('estado', '').strip()
    motivo = (data.get('motivo') or '').strip()

    if nuevo_estado not in Vendedor.ESTADOS:
        return jsonify({'success': False, 'error': 'Estado inválido'}), 400

    ok = Vendedor.cambiar_estado(_db(), vid, nuevo_estado, motivo)
    if ok:
        return jsonify({
            'success': True,
            'message': f'Vendedor marcado como {nuevo_estado}',
        })
    return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 500


def admin_actualizar_comision(vid):
    if not _es_admin():
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    data = request.get_json() or {}
    try:
        pct = float(data.get('comision_pct', 15))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Comisión inválida'}), 400

    if pct < 0 or pct > 50:
        return jsonify({'success': False, 'error': 'La comisión debe estar entre 0 y 50'}), 400

    ok = Vendedor.actualizar(_db(), vid, {'comision_pct': pct})
    if ok:
        return jsonify({'success': True, 'message': f'Comisión actualizada a {pct}%'})
    return jsonify({'success': False, 'error': 'No se pudo actualizar'}), 500


def admin_eliminar(vid):
    if not _es_admin():
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    ok = Vendedor.eliminar(_db(), vid)
    if ok:
        return jsonify({'success': True, 'message': 'Vendedor eliminado'})
    return jsonify({'success': False, 'error': 'No se pudo eliminar'}), 500


# ============================================================
# ⭐ VISTA PÚBLICA — TIENDA DE UN VENDEDOR
# ============================================================
def ver_tienda_publica(slug):
    """
    Vista pública de la tienda de un vendedor.
    URL: /marketplace/tienda/<slug>
    Ej: /marketplace/tienda/mi-tienda-fitness-abc123
    """
    db = _db()

    # Buscar al vendedor por slug
    v_raw = Vendedor.obtener_por_slug(db, slug)
    if not v_raw:
        abort(404)

    # Solo mostrar tiendas aprobadas y activas
    if v_raw.get('estado') != 'aprobado' or not v_raw.get('activo', True):
        abort(404)

    # ⭐ Formatear con métricas reales
    v = _formatear_vendedor_con_metricas(v_raw)

    # Productos del vendedor (activos)
    try:
        productos = list(
            db.productos.find({
                'vendedor_id': v['_id'],
                'activo': True,
            }).sort('created_at', -1).limit(48)
        )
    except Exception as e:
        current_app.logger.warning(f'[ver_tienda_publica] Error buscando productos: {e}')
        productos = []

    # Normalizar precios de los productos (variantes)
    for p in productos:
        p['_id'] = str(p['_id'])
        variables = p.get('variables') or []
        if variables:
            con_stock = [var for var in variables if (var.get('stock') or 0) > 0]
            if con_stock:
                p['precio_mostrado'] = float(con_stock[0].get('precio') or 0)
            else:
                p['precio_mostrado'] = float(variables[0].get('precio') or 0)
        else:
            p['precio_mostrado'] = float(p.get('precio') or 0)

        # Foto principal
        fotos = p.get('fotos') or []
        p['foto_principal'] = fotos[0] if fotos else None

    # Categorías únicas que vende
    try:
        categorias_ids = db.productos.distinct(
            'categoria_id',
            {'vendedor_id': v['_id'], 'activo': True, 'categoria_id': {'$ne': None}}
        )
        categorias = list(db.categorias.find({
            '_id': {'$in': [ObjectId(cid) for cid in categorias_ids if cid]}
        }))
    except Exception:
        categorias = []

    return render_template(
        'tienda/marketplace/tienda_vendedor.html',
        vendedor=v,
        productos=productos,
        categorias=categorias,
    )


# ============================================================
# ⭐ API — LISTAR VENDEDORES (JSON)
# ============================================================
def api_vendedores():
    """
    GET /api/marketplace/vendedores
    Params opcionales:
      - limite:      int (default 24, máx 100)
      - categoria:   str (filtra por categoría)
      - destacados:  1  (solo vendedores marcados como destacados)
      - q:           str (búsqueda por nombre de tienda)
    """
    try:
        db = _db()

        limite = min(int(request.args.get('limite', 24)), 100)
        categoria = (request.args.get('categoria') or '').strip()
        solo_destacados = request.args.get('destacados') == '1'
        q = (request.args.get('q') or '').strip()

        query = {'estado': 'aprobado', 'activo': True}

        if categoria:
            query['categorias'] = categoria

        if solo_destacados:
            query['destacado'] = True

        if q:
            query['nombre_tienda'] = {'$regex': q, '$options': 'i'}

        vendedores_raw = list(
            db[Vendedor.COLLECTION]
              .find(query)
              .sort('created_at', -1)
              .limit(limite)
        )

        # ⭐ Inyectar métricas reales
        vendedores = []
        for v in vendedores_raw:
            v_fmt = _formatear_vendedor_con_metricas(v)
            if v_fmt:
                vendedores.append(v_fmt)

        return jsonify({
            'success': True,
            'total': len(vendedores),
            'vendedores': vendedores,
        })

    except Exception as e:
        current_app.logger.error(f'[api_vendedores] ERROR: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ⭐ API — DETALLE DE UN VENDEDOR (JSON)
# ============================================================
def api_vendedor(vid):
    """
    GET /api/marketplace/vendedor/<vid>
    Devuelve el detalle público de un vendedor aprobado,
    más la lista de sus productos activos (máx 20).
    """
    try:
        db = _db()

        v_raw = Vendedor.obtener_por_id(db, vid)
        if not v_raw:
            return jsonify({'success': False, 'error': 'Vendedor no encontrado'}), 404

        if v_raw.get('estado') != 'aprobado' or not v_raw.get('activo', True):
            return jsonify({'success': False, 'error': 'Vendedor no disponible'}), 404

        # ⭐ Formatear con métricas reales
        v = _formatear_vendedor_con_metricas(v_raw)

        # Productos del vendedor (máx 20 para el detalle)
        try:
            productos = list(
                db.productos.find({
                    'vendedor_id': v['_id'],
                    'activo': True,
                }).limit(20).sort('created_at', -1)
            )
            for p in productos:
                p['_id'] = str(p['_id'])
                variables = p.get('variables') or []
                if variables:
                    con_stock = [var for var in variables if (var.get('stock') or 0) > 0]
                    if con_stock:
                        p['precio_mostrado'] = float(con_stock[0].get('precio') or 0)
                    else:
                        p['precio_mostrado'] = float(variables[0].get('precio') or 0)
                else:
                    p['precio_mostrado'] = float(p.get('precio') or 0)
                fotos = p.get('fotos') or []
                p['foto_principal'] = fotos[0] if fotos else None
        except Exception:
            productos = []

        return jsonify({
            'success': True,
            'vendedor': v,
            'productos': productos,
        })

    except Exception as e:
        current_app.logger.error(f'[api_vendedor] ERROR: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500