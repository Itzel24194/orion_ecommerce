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


def _filtro_productos_vendedor(vendedor_id):
    """
    Construye el filtro Mongo para productos de un vendedor.
    Soporta vendedor_id como string u ObjectId.
    NO filtra por 'activo' (igual que el dashboard).
    """
    vid_str = str(vendedor_id)
    filtro = {'$or': [{'vendedor_id': vid_str}]}
    if ObjectId.is_valid(vid_str):
        filtro['$or'].append({'vendedor_id': ObjectId(vid_str)})
    return filtro


# ============================================================
# ⭐ HELPER: CALCULAR MÉTRICAS REALES DE UN VENDEDOR
# ============================================================
def _calcular_metricas_reales(vendedor_id, db=None):
    """
    Calcula las métricas REALES de un vendedor leyendo directamente
    las colecciones `productos` y `pedidos`.
    """
    if db is None:
        db = _db()

    if not vendedor_id:
        return {'productos': 0, 'ventas': 0, 'ingresos': 0.0, 'comisiones': 0.0}

    vid_str = str(vendedor_id)

    # 1. Contar productos del vendedor (mismo criterio que el dashboard)
    total_productos = 0
    try:
        filtros_productos = _filtro_productos_vendedor(vendedor_id)
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
            items = pedido.get('items') or pedido.get('items_list') or []
            for item in items:
                item_vid = str(item.get('vendedor_id') or '')
                if item_vid == vid_str:
                    total_ventas += int(item.get('cantidad') or 1)
                    precio = float(item.get('precio') or 0)
                    cantidad = int(item.get('cantidad') or 1)
                    total_ingresos += precio * cantidad
    except Exception as e:
        current_app.logger.warning(f'[_calcular_metricas_reales] Error contando ventas: {e}')

    # 3. Comisiones
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
    """Toma un doc de vendedor, lo formatea y le inyecta métricas reales."""
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


def _precio_de_producto(p):
    """
    Devuelve el precio "mostrado" de un producto.
    Si tiene variantes, toma el precio de la primera con stock > 0.
    Si no, usa el campo 'precio'.
    """
    variables = p.get('variables') or []
    if variables:
        con_stock = [var for var in variables if (var.get('stock') or 0) > 0]
        if con_stock:
            return float(con_stock[0].get('precio') or 0)
        return float(variables[0].get('precio') or 0)
    return float(p.get('precio') or 0)


def _normalizar_producto(p, cat_map=None, marca_map=None):
    """
    Normaliza un documento de producto para su uso en templates:
    - str _id
    - precio_mostrado
    - foto_principal
    - nombre_categoria / nombre_marca (si se pasan los mapas)
    """
    p['_id'] = str(p['_id'])

    p['precio_mostrado'] = _precio_de_producto(p)

    fotos = p.get('fotos') or []
    p['foto_principal'] = fotos[0] if fotos else None

    # Categoría / marca (nombres legibles)
    if cat_map is not None:
        cat_id = p.get('categoria_id')
        p['nombre_categoria'] = cat_map.get(str(cat_id), '') if cat_id else ''
    if marca_map is not None:
        marca_id = p.get('marca_id')
        p['nombre_marca'] = marca_map.get(str(marca_id), '') if marca_id else ''

    return p


# ============================================================
# ⭐ PÁGINA PRINCIPAL DEL MARKETPLACE
# ============================================================
def index():
    """
    Página pública principal del marketplace.
    Muestra:
      - Vendedores aprobados (destacados)
      - Productos activos (con filtro de búsqueda)
      - Categorías y marcas para filtros
      - Stats reales: vendedores activos + productos disponibles
    """
    db = _db()

    # ---------- Parámetros ----------
    q = (request.args.get('q') or '').strip()
    categoria_id = (request.args.get('categoria') or '').strip()
    marca_id = (request.args.get('marca') or '').strip()
    orden = (request.args.get('orden') or 'recientes').strip()

    # ---------- Vendedores aprobados ----------
    try:
        vendedores_raw = list(
            db[Vendedor.COLLECTION].find({
                'estado': 'aprobado',
                'activo': True,
            }).sort('created_at', -1).limit(8)
        )
        vendedores = []
        for v in vendedores_raw:
            v_fmt = _formatear_vendedor_con_metricas(v)
            if v_fmt:
                vendedores.append(v_fmt)
    except Exception as e:
        current_app.logger.warning(f'[marketplace.index] vendedores: {e}')
        vendedores = []

    # ---------- Categorías y marcas (para selects) ----------
    try:
        categorias = list(db.categorias.find({}).sort('nombre', 1))
    except Exception:
        categorias = []

    try:
        marcas = list(db.marcas.find({
            '$or': [
                {'estado': 'aprobada'},
                {'estado': 'aprobado'},
                {'estado': 'activa'},
                {'estado': 'activo'},
                {'activa': True},
                {'estado': {'$exists': False}},
            ]
        }).sort('nombre_comercial', 1).limit(50))
    except Exception:
        marcas = []

    cat_map = {str(c['_id']): c.get('nombre', '') for c in categorias}
    marca_map = {str(m['_id']): m.get('nombre_comercial', m.get('nombre', '')) for m in marcas}

    # ---------- Productos ----------
    filtro_prod = {'activo': True, 'estado': 'activo'}

    if q:
        import re
        filtro_prod['nombre'] = {'$regex': re.escape(q), '$options': 'i'}

    if categoria_id and ObjectId.is_valid(categoria_id):
        filtro_prod['categoria_id'] = ObjectId(categoria_id)

    if marca_id and ObjectId.is_valid(marca_id):
        filtro_prod['marca_id'] = ObjectId(marca_id)

    orden_map = {
        'recientes':   ('created_at', -1),
        'precio_asc':  ('precio', 1),
        'precio_desc': ('precio', -1),
        'nombre':      ('nombre', 1),
    }
    sort_field, sort_dir = orden_map.get(orden, ('created_at', -1))

    try:
        productos_raw = list(
            db.productos.find(filtro_prod)
                       .sort(sort_field, sort_dir)
                       .limit(48)
        )
    except Exception as e:
        current_app.logger.warning(f'[marketplace.index] productos: {e}')
        productos_raw = []

    productos = [_normalizar_producto(p, cat_map, marca_map) for p in productos_raw]

    # ============================================================
    # ⭐ STATS REALES para la landing (vendedores + productos)
    # ============================================================
    total_vendedores = 0
    try:
        total_vendedores = db[Vendedor.COLLECTION].count_documents({
            'estado': 'aprobado',
            'activo': True,
        })
    except Exception as e:
        current_app.logger.warning(f'[marketplace.index] contando vendedores: {e}')

    total_productos = 0
    try:
        total_productos = db.productos.count_documents({
            'activo': True,
            'estado': 'activo',
        })
    except Exception as e:
        current_app.logger.warning(f'[marketplace.index] contando productos: {e}')

    # Fallback por si tu esquema no tiene 'estado' en productos
    if total_productos == 0:
        try:
            total_productos = db.productos.count_documents({'activo': True})
        except Exception:
            total_productos = 0

    stats = {
        'vendedores': total_vendedores,
        'productos':  total_productos,
    }

    # ---------- Usuario actual (opcional) ----------
    usuario = None
    if _uid():
        try:
            usuario = db.usuarios.find_one({'_id': ObjectId(_uid())})
            if usuario:
                usuario.pop('password', None)
                usuario.pop('password_hash', None)
                usuario.pop('contrasena', None)
        except Exception:
            usuario = None

    # ---------- Vendedor actual (opcional, para el sidebar) ----------
    vendedor_mkt = None
    if _uid():
        v_raw = _vendedor_actual()
        if _vendedor_es_valido(v_raw):
            vendedor_mkt = _formatear_vendedor_con_metricas(v_raw)

    return render_template(
        'tienda/marketplace/index.html',
        vendedores=vendedores,
        productos=productos,
        categorias=categorias,
        marcas=marcas,
        usuario=usuario,
        vendedor=vendedor_mkt,
        stats=stats,                    # ⭐ NUEVO — conteos reales
        q=q,
        categoria_id=categoria_id,
        marca_id=marca_id,
        orden=orden,
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

            db.usuarios.update_one(
                {'_id': ObjectId(_uid())},
                {'$set': {'es_vendedor': True, 'updated_at': datetime.now(timezone.utc)}}
            )

            flash('¡Solicitud enviada! Un administrador revisará tu tienda pronto.', 'success')
            return redirect(url_for('web.marketplace_estado'))

        except Exception as e:
            current_app.logger.error(f'[marketplace_registro] ERROR: {e}')
            flash(f'Error al crear la tienda: {e}', 'danger')

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

    v = _formatear_vendedor_con_metricas(v_raw)
    db = _db()

    # Productos del vendedor
    try:
        productos = list(
            db.productos.find(_filtro_productos_vendedor(v['_id'])).sort('created_at', -1)
        )
    except Exception:
        productos = []

    # Ventas recientes
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

    metricas = v.get('metricas', {}) or {}
    total_ventas     = metricas.get('ventas', 0)
    total_ingresos   = metricas.get('ingresos', 0)
    total_comisiones = metricas.get('comisiones', 0)
    saldo_neto       = round(total_ingresos - total_comisiones, 2)

    return render_template(
        'admin/marketplace/dashboard.html',
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

    vendedores = []
    for v in vendedores_raw:
        v_fmt = _formatear_vendedor_con_metricas(v)
        if v_fmt:
            vendedores.append(v_fmt)

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

    v = _formatear_vendedor_con_metricas(v_raw)
    db = _db()

    try:
        productos = list(db.productos.find(_filtro_productos_vendedor(v['_id'])))
    except Exception:
        productos = []

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
    URL: /marketplace/tienda_vendedor/<slug>
    """
    db = _db()

    v_raw = Vendedor.obtener_por_slug(db, slug)
    if not v_raw:
        abort(404)

    if v_raw.get('estado') != 'aprobado' or not v_raw.get('activo', True):
        abort(404)

    v = _formatear_vendedor_con_metricas(v_raw)

    try:
        productos = list(
            db.productos.find(_filtro_productos_vendedor(v['_id']))
              .sort('created_at', -1)
              .limit(48)
        )
    except Exception as e:
        current_app.logger.warning(f'[ver_tienda_publica] Error buscando productos: {e}')
        productos = []

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

    try:
        categorias_ids = db.productos.distinct(
            'categoria_id',
            dict(_filtro_productos_vendedor(v['_id']), categoria_id={'$ne': None})
        )
        categorias = list(db.categorias.find({
            '_id': {'$in': [ObjectId(cid) for cid in categorias_ids if cid]}
        }))
    except Exception:
        categorias = []

    return render_template(
        'tienda/marketplace/vendedor_tienda.html',
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
    """
    try:
        db = _db()

        v_raw = Vendedor.obtener_por_id(db, vid)
        if not v_raw:
            return jsonify({'success': False, 'error': 'Vendedor no encontrado'}), 404

        if v_raw.get('estado') != 'aprobado' or not v_raw.get('activo', True):
            return jsonify({'success': False, 'error': 'Vendedor no disponible'}), 404

        v = _formatear_vendedor_con_metricas(v_raw)

        try:
            productos = list(
                db.productos.find(_filtro_productos_vendedor(v['_id']))
                  .limit(20).sort('created_at', -1)
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