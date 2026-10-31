# ================================================================
# app/controllers/vendedor_controller.py
# Panel de Vendedor - ORION
# ================================================================

from flask import (
    render_template, request, redirect, url_for,
    flash, jsonify, current_app, session, send_file
)
from bson import ObjectId
from datetime import datetime, timedelta, timezone
import sys
import io

from app.decorators import vendedor_required


# ⭐ Temas válidos del hero
TEMAS_HERO_VALIDOS = [
    'azul', 'morado', 'rosa', 'verde', 'naranja', 'rojo', 'turquesa', 'negro',
    'lavanda', 'menta', 'cielo', 'durazno', 'rosa-suave', 'coral', 'oliva', 'jade',
]


# ================================================================
# HELPERS GENERALES
# ================================================================

def _get_usuario_actual():
    """Devuelve el documento del vendedor logueado."""
    if 'user_id' not in session:
        return None
    try:
        db = current_app.db
        return db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception:
        return None


def _get_productos_vendedor(usuario_id):
    """Devuelve todos los productos del vendedor (nativo)."""
    db = current_app.db
    uid = str(usuario_id)
    return list(db.productos.find({
        '$or': [
            {'vendedor_id': uid},
            {'vendedor_id': ObjectId(uid)},
        ]
    }).sort('created_at', -1))


def _get_pedidos_vendedor(usuario_id, limit=None):
    """Devuelve los pedidos que contienen al menos un producto del vendedor."""
    db = current_app.db

    productos = _get_productos_vendedor(usuario_id)
    producto_ids = [str(p['_id']) for p in productos]

    if not producto_ids:
        return []

    cursor = db.pedidos.find({
        'items.id': {'$in': producto_ids}
    }).sort('created_at', -1)

    if limit:
        cursor = cursor.limit(limit)

    return list(cursor)


def _formatear_pedido_para_vendedor(pedido, producto_ids_vendedor):
    """Devuelve solo los items del vendedor dentro de un pedido."""
    items_vendedor = []
    subtotal_vendedor = 0.0

    for item in (pedido.get('items') or []):
        pid = str(item.get('id', ''))
        if pid in producto_ids_vendedor:
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            subtotal_item = precio * cantidad
            subtotal_vendedor += subtotal_item

            items_vendedor.append({
                'id': pid,
                'nombre': item.get('nombre', 'Producto'),
                'cantidad': cantidad,
                'precio': precio,
                'subtotal': subtotal_item,
                'imagen': item.get('imagen', 'default.jpg'),
            })

    return {
        '_id': str(pedido['_id']),
        'numero_pedido': pedido.get('numero_pedido', ''),
        'estado': pedido.get('estado', 'pendiente'),
        'created_at': pedido.get('created_at'),
        'items': items_vendedor,
        'subtotal_vendedor': round(subtotal_vendedor, 2),
        'usuario_nombre': pedido.get('usuario_nombre', ''),
        'usuario_email': pedido.get('usuario_email', ''),
        'usuario_telefono': pedido.get('usuario_telefono', ''),
        'direccion': pedido.get('direccion', {}),
    }


# ================================================================
# HELPERS PARA FORMULARIOS (categorías + marcas)
# ================================================================

def _calcular_nivel_categorias(categorias):
    if not categorias:
        return categorias

    por_id = {str(c['_id']): c for c in categorias}

    def get_nivel(cat, visitados=None):
        if visitados is None:
            visitados = set()
        cid = str(cat['_id'])
        if cid in visitados:
            return 1
        visitados.add(cid)

        padre_id = cat.get('padre_id')
        if not padre_id:
            return 1

        padre = por_id.get(str(padre_id))
        if not padre:
            return 1

        return get_nivel(padre, visitados) + 1

    for cat in categorias:
        cat['nivel'] = get_nivel(cat)

    return categorias


def _get_categorias_para_form():
    db = current_app.db
    try:
        categorias = list(db.categorias.find({}))
    except Exception as e:
        print(f"⚠️ [_get_categorias_para_form] {e}", file=sys.stderr)
        return []

    categorias = _calcular_nivel_categorias(categorias)

    por_id = {str(c['_id']): c for c in categorias}
    for cat in categorias:
        pid = cat.get('padre_id')
        if pid and str(pid) in por_id:
            cat['padre_nombre'] = por_id[str(pid)].get('nombre', '')
        else:
            cat['padre_nombre'] = ''

    return categorias


def _get_marcas_para_form():
    db = current_app.db

    query = {
        '$or': [
            {'estado': 'aprobada'},
            {'estado': 'aprobado'},
            {'estado': 'activa'},
            {'estado': 'activo'},
            {'activa': True},
            {'aprobada': True},
            {'estado': {'$exists': False}},
        ]
    }

    try:
        marcas = list(db.marcas.find(query).sort('nombre_comercial', 1))
    except Exception as e:
        print(f"⚠️ [_get_marcas_para_form] {e}", file=sys.stderr)
        marcas = []

    if not marcas:
        try:
            marcas = list(db.marcas.find({}).sort('nombre_comercial', 1))
        except Exception:
            marcas = []

    return marcas


def _get_temporadas_para_form():
    db = current_app.db
    try:
        temporadas = list(db.temporadas.find({}).sort('fecha_inicio', -1))
    except Exception:
        temporadas = []
    temporadas_dict = {str(t['_id']): t for t in temporadas}
    return temporadas, temporadas_dict


# ================================================================
# DASHBOARD PRINCIPAL
# ================================================================

@vendedor_required
def dashboard():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    total_productos = len(productos)
    productos_activos = sum(1 for p in productos if p.get('activo', True))
    productos_sin_stock = sum(1 for p in productos if int(p.get('stock', 0)) <= 0)
    productos_stock_bajo = sum(1 for p in productos if 0 < int(p.get('stock', 0)) <= 5)

    pedidos_raw = _get_pedidos_vendedor(vendedor['_id'])
    pedidos_formateados = [
        _formatear_pedido_para_vendedor(p, producto_ids)
        for p in pedidos_raw
    ]

    total_pedidos = len(pedidos_formateados)
    pedidos_pendientes = sum(
        1 for p in pedidos_formateados
        if p['estado'] in ('pendiente', 'confirmado', 'preparando')
    )
    pedidos_enviados = sum(
        1 for p in pedidos_formateados if p['estado'] == 'enviado'
    )
    pedidos_entregados = sum(
        1 for p in pedidos_formateados if p['estado'] == 'entregado'
    )

    ventas_totales = sum(p['subtotal_vendedor'] for p in pedidos_formateados)

    hoy = datetime.now(timezone.utc)
    inicio_mes = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    ventas_mes = sum(
        p['subtotal_vendedor'] for p in pedidos_formateados
        if isinstance(p.get('created_at'), datetime) and p['created_at'] >= inicio_mes
    )

    labels_7d = []
    ventas_7d = []
    for i in range(6, -1, -1):
        dia = hoy - timedelta(days=i)
        inicio = datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc)
        fin = inicio + timedelta(days=1)

        total_dia = sum(
            p['subtotal_vendedor'] for p in pedidos_formateados
            if isinstance(p.get('created_at'), datetime)
            and inicio <= p['created_at'] < fin
        )

        labels_7d.append(dia.strftime('%a %d'))
        ventas_7d.append(round(total_dia, 2))

    total_resenas = 0
    promedio_resenas = 0.0
    try:
        resenas = list(db.resenas.find({
            'producto_id': {'$in': producto_ids}
        }))
        total_resenas = len(resenas)
        if total_resenas > 0:
            promedio_resenas = round(
                sum(float(r.get('calificacion', 0)) for r in resenas) / total_resenas,
                1
            )
    except Exception as e:
        print(f"[Vendedor] Error leyendo reseñas: {e}", file=sys.stderr)

    ventas_por_producto = {}
    for p in pedidos_formateados:
        for item in p['items']:
            nombre = item['nombre']
            if nombre not in ventas_por_producto:
                ventas_por_producto[nombre] = {
                    'nombre': nombre,
                    'unidades': 0,
                    'ingresos': 0,
                }
            ventas_por_producto[nombre]['unidades'] += item['cantidad']
            ventas_por_producto[nombre]['ingresos'] += item['subtotal']

    top_productos = sorted(
        ventas_por_producto.values(),
        key=lambda x: x['unidades'],
        reverse=True
    )[:5]

    pedidos_recientes = pedidos_formateados[:5]

    productos_recientes = []
    for p in productos[:5]:
        productos_recientes.append({
            '_id': str(p['_id']),
            'nombre': p.get('nombre', 'Producto'),
            'precio': float(p.get('precio', 0)),
            'stock': int(p.get('stock', 0)),
            'activo': p.get('activo', True),
            'imagen': (p.get('fotos') or ['default.jpg'])[0],
        })

    return render_template(
        'admin/marketplace/dashboard.html',
        vendedor=vendedor,
        total_productos=total_productos,
        productos_activos=productos_activos,
        productos_sin_stock=productos_sin_stock,
        productos_stock_bajo=productos_stock_bajo,
        total_pedidos=total_pedidos,
        pedidos_pendientes=pedidos_pendientes,
        pedidos_enviados=pedidos_enviados,
        pedidos_entregados=pedidos_entregados,
        ventas_totales=round(ventas_totales, 2),
        ventas_mes=round(ventas_mes, 2),
        total_resenas=total_resenas,
        promedio_resenas=promedio_resenas,
        labels_7d=labels_7d,
        ventas_7d=ventas_7d,
        top_productos=top_productos,
        pedidos_recientes=pedidos_recientes,
        productos_recientes=productos_recientes,
    )


# ================================================================
# PRODUCTOS (NATIVO — mantenido por compatibilidad)
# ================================================================

@vendedor_required
def lista_productos():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db
    uid = str(vendedor['_id'])

    filtro = {
        '$or': [
            {'vendedor_id': uid},
            {'vendedor_id': ObjectId(uid)},
        ]
    }

    q = request.args.get('q', '').strip()
    if q:
        import re
        filtro['nombre'] = {'$regex': re.escape(q), '$options': 'i'}

    estado = request.args.get('estado', '')
    if estado == 'activos':
        filtro['activo'] = True
    elif estado == 'inactivos':
        filtro['activo'] = False
    elif estado == 'stock_bajo':
        filtro['stock'] = {'$gt': 0, '$lte': 5}
    elif estado == 'agotados':
        filtro['stock'] = {'$lte': 0}

    productos_raw = list(db.productos.find(filtro).sort('created_at', -1))

    productos = []
    for p in productos_raw:
        productos.append({
            '_id': str(p['_id']),
            'nombre': p.get('nombre', 'Producto'),
            'descripcion': p.get('descripcion', ''),
            'precio': float(p.get('precio', 0)),
            'stock': int(p.get('stock', 0)),
            'activo': p.get('activo', True),
            'imagen': (p.get('fotos') or ['default.jpg'])[0],
            'created_at': p.get('created_at'),
        })

    stats = {
        'total': len(productos_raw),
        'activos': sum(1 for p in productos_raw if p.get('activo', True)),
        'sin_stock': sum(1 for p in productos_raw if int(p.get('stock', 0)) <= 0),
        'stock_bajo': sum(1 for p in productos_raw if 0 < int(p.get('stock', 0)) <= 5),
    }

    return render_template(
        'admin/marketplace/mis_productos.html',
        vendedor=vendedor,
        productos=productos,
        stats=stats,
    )


# ⭐ MODIFICADO: ahora guarda estado, activo, vendedor_nombre y los alias
@vendedor_required
def crear_producto():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    if request.method == 'POST':
        db = current_app.db

        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash("El nombre es obligatorio", "danger")
            return redirect(url_for('web.vendedor_productos'))

        try:
            precio = float(request.form.get('precio', 0))
            stock = int(request.form.get('stock', 0))
        except (ValueError, TypeError):
            flash("Precio y stock deben ser números válidos", "danger")
            return redirect(url_for('web.vendedor_productos'))

        nombre_tienda = vendedor.get('nombre_tienda', '') or vendedor.get('nombre', '')

        producto = {
            'nombre': nombre,
            'descripcion': request.form.get('descripcion', '').strip(),
            'precio': precio,
            'stock': stock,
            'categoria': request.form.get('categoria', '').strip(),
            'marca': request.form.get('marca', '').strip(),

            # ⭐ MARKETPLACE — campos para el badge azul + filtro "Vendido por"
            'vendedor_id': str(vendedor['_id']),
            'vendedor_nombre': nombre_tienda,
            'nombre_tienda': nombre_tienda,
            'tienda_nombre': nombre_tienda,

            # ⭐ Estado consistente con el catálogo
            'estado': 'activo',
            'activo': True,

            'fotos': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }

        file = request.files.get('foto')
        if file and file.filename:
            from werkzeug.utils import secure_filename
            import os
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"prod_{int(datetime.utcnow().timestamp())}_{name[:20]}{ext}"
            folder = os.path.join(current_app.root_path, 'static', 'uploads', 'productos')
            os.makedirs(folder, exist_ok=True)
            file.save(os.path.join(folder, filename))
            producto['fotos'] = [filename]

        db.productos.insert_one(producto)
        flash(f"Producto '{nombre}' creado exitosamente", "success")
        return redirect(url_for('web.vendedor_productos'))

    return redirect(url_for('web.vendedor_productos'))


@vendedor_required
def editar_producto(producto_id):
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(producto_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_productos'))

    producto = db.productos.find_one({
        '_id': oid,
        '$or': [
            {'vendedor_id': str(vendedor['_id'])},
            {'vendedor_id': vendedor['_id']},
        ]
    })

    if not producto:
        flash("Producto no encontrado o no tienes permiso", "danger")
        return redirect(url_for('web.vendedor_productos'))

    if request.method == 'POST':
        try:
            precio = float(request.form.get('precio', producto.get('precio', 0)))
            stock = int(request.form.get('stock', producto.get('stock', 0)))
        except (ValueError, TypeError):
            flash("Precio y stock deben ser números válidos", "danger")
            return redirect(url_for('web.vendedor_productos'))

        update = {
            'nombre': request.form.get('nombre', producto.get('nombre')).strip(),
            'descripcion': request.form.get('descripcion', producto.get('descripcion', '')).strip(),
            'precio': precio,
            'stock': stock,
            'categoria': request.form.get('categoria', producto.get('categoria', '')).strip(),
            'marca': request.form.get('marca', producto.get('marca', '')).strip(),
            'updated_at': datetime.utcnow(),
        }

        # ⭐ Preservar campos marketplace
        if producto.get('vendedor_id'):
            update['vendedor_id'] = producto['vendedor_id']
        if producto.get('vendedor_nombre'):
            update['vendedor_nombre'] = producto['vendedor_nombre']
        if producto.get('nombre_tienda'):
            update['nombre_tienda'] = producto['nombre_tienda']
        if producto.get('tienda_nombre'):
            update['tienda_nombre'] = producto['tienda_nombre']

        file = request.files.get('foto')
        if file and file.filename:
            from werkzeug.utils import secure_filename
            import os
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"prod_{int(datetime.utcnow().timestamp())}_{name[:20]}{ext}"
            folder = os.path.join(current_app.root_path, 'static', 'uploads', 'productos')
            os.makedirs(folder, exist_ok=True)
            file.save(os.path.join(folder, filename))
            update['fotos'] = [filename]

        db.productos.update_one({'_id': oid}, {'$set': update})
        flash("Producto actualizado exitosamente", "success")
        return redirect(url_for('web.vendedor_productos'))

    return redirect(url_for('web.vendedor_productos'))


@vendedor_required
def eliminar_producto(producto_id):
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(producto_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_productos'))

    result = db.productos.delete_one({
        '_id': oid,
        '$or': [
            {'vendedor_id': str(vendedor['_id'])},
            {'vendedor_id': vendedor['_id']},
        ]
    })

    if result.deleted_count > 0:
        flash("Producto eliminado", "success")
    else:
        flash("Producto no encontrado o sin permiso", "danger")

    return redirect(url_for('web.vendedor_productos'))


@vendedor_required
def toggle_producto(producto_id):
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(producto_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_productos'))

    producto = db.productos.find_one({
        '_id': oid,
        '$or': [
            {'vendedor_id': str(vendedor['_id'])},
            {'vendedor_id': vendedor['_id']},
        ]
    })

    if not producto:
        flash("Producto no encontrado", "danger")
        return redirect(url_for('web.vendedor_productos'))

    nuevo = not producto.get('activo', True)
    # ⭐ Sincronizar estado y activo (para que el catálogo lo respete)
    nuevo_estado = 'activo' if nuevo else 'inactivo'
    db.productos.update_one(
        {'_id': oid},
        {'$set': {
            'activo': nuevo,
            'estado': nuevo_estado,
            'updated_at': datetime.utcnow(),
        }}
    )
    flash(f'Producto {"activado" if nuevo else "desactivado"}', 'success')
    return redirect(url_for('web.vendedor_productos'))


# ================================================================
# PEDIDOS
# ================================================================

@vendedor_required
def lista_pedidos():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    filtro = {'items.id': {'$in': producto_ids}} if producto_ids else {'_id': None}

    estado = request.args.get('estado', '')
    if estado:
        filtro['estado'] = estado

    q = request.args.get('q', '').strip()
    if q:
        import re
        filtro['numero_pedido'] = {'$regex': re.escape(q), '$options': 'i'}

    pedidos_raw = []
    if producto_ids:
        pedidos_raw = list(
            db.pedidos.find(filtro).sort('created_at', -1)
        )

    pedidos = [
        _formatear_pedido_para_vendedor(p, producto_ids)
        for p in pedidos_raw
    ]

    stats = {
        'total': len(pedidos),
        'pendientes': sum(1 for p in pedidos if p['estado'] in ('pendiente', 'confirmado', 'preparando')),
        'enviados': sum(1 for p in pedidos if p['estado'] == 'enviado'),
        'entregados': sum(1 for p in pedidos if p['estado'] == 'entregado'),
        'cancelados': sum(1 for p in pedidos if p['estado'] == 'cancelado'),
    }

    return render_template(
        'admin/marketplace/mis_pedidos.html',
        vendedor=vendedor,
        pedidos=pedidos,
        stats=stats,
    )


@vendedor_required
def ver_pedido(pedido_id):
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(pedido_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    pedido = db.pedidos.find_one({'_id': oid})
    if not pedido:
        flash("Pedido no encontrado", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    pedido_fmt = _formatear_pedido_para_vendedor(pedido, producto_ids)

    if not pedido_fmt['items']:
        flash("Este pedido no contiene productos tuyos", "warning")
        return redirect(url_for('web.vendedor_pedidos'))

    return render_template(
        'admin/marketplace/mis_pedidos.html',
        vendedor=vendedor,
        pedido=pedido_fmt,
        pedidos=[pedido_fmt],
        stats={
            'total': 1,
            'pendientes': 1 if pedido_fmt['estado'] in ('pendiente', 'confirmado', 'preparando') else 0,
            'enviados': 1 if pedido_fmt['estado'] == 'enviado' else 0,
            'entregados': 1 if pedido_fmt['estado'] == 'entregado' else 0,
            'cancelados': 1 if pedido_fmt['estado'] == 'cancelado' else 0,
        },
    )


@vendedor_required
def actualizar_estado_pedido(pedido_id):
    if request.method != 'POST':
        return redirect(url_for('web.vendedor_pedidos'))

    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(pedido_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    nuevo_estado = request.form.get('estado', '').strip().lower()
    estados_validos = ['pendiente', 'confirmado', 'preparando', 'enviado', 'entregado', 'cancelado']

    if nuevo_estado not in estados_validos:
        flash("Estado inválido", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    pedido = db.pedidos.find_one({'_id': oid})
    if not pedido:
        flash("Pedido no encontrado", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]
    items_vendedor = [i for i in (pedido.get('items') or []) if str(i.get('id')) in producto_ids]

    if not items_vendedor:
        flash("No tienes permiso sobre este pedido", "danger")
        return redirect(url_for('web.vendedor_pedidos'))

    db.pedidos.update_one(
        {'_id': oid},
        {'$set': {
            'estado': nuevo_estado,
            'updated_at': datetime.utcnow(),
        }}
    )
    flash(f"Estado actualizado a {nuevo_estado}", "success")
    return redirect(url_for('web.vendedor_pedidos'))


# ================================================================
# RESEÑAS
# ================================================================

@vendedor_required
def lista_resenas():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]
    producto_map = {str(p['_id']): p.get('nombre', 'Producto') for p in productos}

    resenas_raw = []
    if producto_ids:
        oids = []
        for pid in producto_ids:
            try:
                oids.append(ObjectId(pid))
            except Exception:
                pass

        resenas_raw = list(
            db.resenas.find({
                '$or': [
                    {'producto_id': {'$in': producto_ids}},
                    {'producto_id': {'$in': oids}},
                ]
            }).sort('fecha', -1)
        )

    resenas = []
    for r in resenas_raw:
        pid_str = str(r.get('producto_id', ''))
        resenas.append({
            '_id': str(r['_id']),
            'producto_id': pid_str,
            'producto_nombre': producto_map.get(pid_str, 'Producto'),
            'usuario_nombre': r.get('usuario_nombre', 'Anónimo'),
            'calificacion': int(r.get('calificacion', 0)),
            'titulo': r.get('titulo', ''),
            'comentario': r.get('comentario', ''),
            'fecha': r.get('fecha', ''),
            'respuesta_vendedor': r.get('respuesta_vendedor', ''),
            'respuesta_fecha': r.get('respuesta_fecha', ''),
        })

    total = len(resenas)
    promedio = round(sum(r['calificacion'] for r in resenas) / total, 1) if total else 0

    distribucion = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in resenas:
        c = r['calificacion']
        if c in distribucion:
            distribucion[c] += 1

    sin_responder = sum(1 for r in resenas if not r['respuesta_vendedor'])

    stats = {
        'total': total,
        'promedio': promedio,
        'sin_responder': sin_responder,
        'distribucion': distribucion,
    }

    return render_template(
        'admin/marketplace/resenas.html',
        vendedor=vendedor,
        resenas=resenas,
        stats=stats,
    )


@vendedor_required
def responder_resena(resena_id):
    if request.method != 'POST':
        return redirect(url_for('web.vendedor_resenas'))

    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    try:
        oid = ObjectId(resena_id)
    except Exception:
        flash("ID inválido", "danger")
        return redirect(url_for('web.vendedor_resenas'))

    resena = db.resenas.find_one({'_id': oid})
    if not resena:
        flash("Reseña no encontrada", "danger")
        return redirect(url_for('web.vendedor_resenas'))

    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    if str(resena.get('producto_id', '')) not in producto_ids:
        flash("No puedes responder esta reseña", "danger")
        return redirect(url_for('web.vendedor_resenas'))

    respuesta = request.form.get('respuesta', '').strip()
    if not respuesta:
        flash("Debes escribir una respuesta", "danger")
        return redirect(url_for('web.vendedor_resenas'))

    db.resenas.update_one(
        {'_id': oid},
        {'$set': {
            'respuesta_vendedor': respuesta,
            'respuesta_fecha': datetime.utcnow().strftime('%d/%m/%Y'),
            'respuesta_vendedor_id': str(vendedor['_id']),
        }}
    )
    flash("Respuesta enviada", "success")
    return redirect(url_for('web.vendedor_resenas'))


# ================================================================
# API
# ================================================================

@vendedor_required
def api_stats():
    vendedor = _get_usuario_actual()
    if not vendedor:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    productos = _get_productos_vendedor(vendedor['_id'])
    pedidos = _get_pedidos_vendedor(vendedor['_id'])

    producto_ids = [str(p['_id']) for p in productos]
    pedidos_fmt = [_formatear_pedido_para_vendedor(p, producto_ids) for p in pedidos]

    return jsonify({
        'success': True,
        'total_productos': len(productos),
        'total_pedidos': len(pedidos_fmt),
        'ventas_totales': round(sum(p['subtotal_vendedor'] for p in pedidos_fmt), 2),
    })


# ================================================================
# HELPERS MARKETPLACE
# ================================================================

def _get_vendedor_marketplace():
    from app.models.marketplace_model import Vendedor
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        v = Vendedor.obtener_por_user(current_app.db, user_id)
        if v and v.get('estado') == 'aprobado' and v.get('activo', True):
            return Vendedor.formatear(v)
    except Exception as e:
        print(f"⚠️ [_get_vendedor_marketplace] {e}", file=sys.stderr)
    return None


def _productos_del_vendedor_marketplace(vendedor_id):
    db = current_app.db
    return list(db.productos.find({
        'vendedor_id': vendedor_id,
    }).sort('created_at', -1))


def _pedidos_del_vendedor_marketplace(vendedor_id):
    db = current_app.db
    return list(db.pedidos.find({
        'items.vendedor_id': vendedor_id,
    }).sort('created_at', -1))


def _procesar_variantes_form():
    skus     = request.form.getlist('sku[]')
    colores  = request.form.getlist('color[]')
    tamanos  = request.form.getlist('tamano[]')
    precios  = request.form.getlist('precio[]')
    stocks   = request.form.getlist('stock[]')

    variantes = []
    total = max(len(skus), len(colores), len(tamanos), len(precios), len(stocks))

    for i in range(total):
        try:
            sku     = (skus[i] if i < len(skus) else '').strip()
            color   = (colores[i] if i < len(colores) else '').strip()
            tamano  = (tamanos[i] if i < len(tamanos) else '').strip()
            precio  = float(precios[i] if i < len(precios) else 0)
            stock   = int(stocks[i] if i < len(stocks) else 0)

            if not sku or not color or not tamano:
                continue
            if precio < 0 or stock < 0:
                continue

            variantes.append({
                'sku': sku,
                'color': color,
                'tamano': tamano,
                'precio': precio,
                'stock': stock,
            })
        except (ValueError, IndexError, TypeError):
            continue

    return variantes


def _procesar_imagenes_form(campo='fotos[]', prefijo='mkt_', max_size_mb=5):
    import os, secrets
    archivos = request.files.getlist(campo)
    guardados = []

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'productos')
    os.makedirs(upload_folder, exist_ok=True)

    for archivo in archivos:
        if not archivo or not archivo.filename:
            continue
        try:
            ext = archivo.filename.rsplit('.', 1)[-1].lower()
        except Exception:
            continue
        if ext not in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
            continue

        filename = f"{prefijo}{secrets.token_hex(8)}.{ext}"
        try:
            archivo.save(os.path.join(upload_folder, filename))
            guardados.append(filename)
        except Exception as e:
            print(f"⚠️ Error guardando imagen {filename}: {e}", file=sys.stderr)

    return guardados


def _procesar_videos_form(campo='videos[]', prefijo='mkt_vid_', max_size_mb=100):
    import os, secrets
    archivos = request.files.getlist(campo)
    guardados = []

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'productos')
    os.makedirs(upload_folder, exist_ok=True)

    for archivo in archivos:
        if not archivo or not archivo.filename:
            continue
        try:
            ext = archivo.filename.rsplit('.', 1)[-1].lower()
        except Exception:
            continue
        if ext not in ('mp4', 'webm', 'mov', 'avi'):
            continue

        filename = f"{prefijo}{secrets.token_hex(8)}.{ext}"
        try:
            archivo.save(os.path.join(upload_folder, filename))
            guardados.append(filename)
        except Exception as e:
            print(f"⚠️ Error guardando video {filename}: {e}", file=sys.stderr)

    return guardados


# ================================================================
# VISTAS DEL PANEL MARKETPLACE
# ================================================================

@vendedor_required
def dashboard_marketplace():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa en el marketplace.', 'warning')
        return redirect(url_for('web.marketplace'))

    vendedor_id = v['_id']

    productos = _productos_del_vendedor_marketplace(vendedor_id)
    pedidos = _pedidos_del_vendedor_marketplace(vendedor_id)[:20]

    metricas = v.get('metricas', {}) or {}
    total_ventas     = metricas.get('ventas', 0)
    total_ingresos   = metricas.get('ingresos', 0)
    total_comisiones = metricas.get('comisiones', 0)
    saldo_neto       = total_ingresos - total_comisiones

    return render_template(
        'admin/marketplace/dashboard.html',
        vendedor=v,
        productos=productos,
        pedidos=pedidos,
        total_ventas=total_ventas,
        total_ingresos=total_ingresos,
        total_comisiones=total_comisiones,
        saldo_neto=saldo_neto,
    )


@vendedor_required
def vendedor_mis_productos():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    productos = _productos_del_vendedor_marketplace(v['_id'])

    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'admin/marketplace/mis_productos.html',
        vendedor=v,
        productos=productos,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
    )


@vendedor_required
def vendedor_nuevo_producto():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    db = current_app.db

    if request.method == 'POST':
        nombre        = (request.form.get('nombre') or '').strip()
        descripcion   = (request.form.get('descripcion') or '').strip()
        categoria_id  = (request.form.get('categoria_id') or '').strip() or None
        marca_id      = (request.form.get('marca_id') or '').strip() or None
        temporada_id  = (request.form.get('temporada_id') or '').strip() or None
        estado        = (request.form.get('estado') or 'activo').strip()

        if not nombre:
            flash('El nombre del producto es obligatorio.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        if not categoria_id:
            flash('Debes seleccionar una categoría.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        if not marca_id:
            flash('Debes seleccionar una marca.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        variantes = _procesar_variantes_form()
        if not variantes:
            flash('Debes agregar al menos una variante (color + talla + SKU + precio + stock).', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        fotos  = _procesar_imagenes_form('fotos[]', 'mkt_')
        videos = _procesar_videos_form('videos[]', 'mkt_vid_')

        precios_v = [x['precio'] for x in variantes if x['precio'] > 0]
        stocks_v  = [x['stock'] for x in variantes]
        precio_min = min(precios_v) if precios_v else 0
        stock_total = sum(stocks_v) if stocks_v else 0

        nombre_tienda = v.get('nombre_tienda', '')

        nuevo_producto = {
            'nombre': nombre,
            'descripcion': descripcion,

            # ⭐ MARKETPLACE — todos los alias para el badge
            'vendedor_id': v['_id'],
            'vendedor_nombre': nombre_tienda,
            'nombre_tienda': nombre_tienda,
            'tienda_nombre': nombre_tienda,

            'categoria_id': ObjectId(categoria_id),
            'marca_id': ObjectId(marca_id),
            'temporada_id': ObjectId(temporada_id) if temporada_id else None,

            'fotos': fotos,
            'videos': videos,
            'variables': variantes,

            'precio': precio_min,
            'stock': stock_total,
            'estado': estado,
            'activo': estado == 'activo',

            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }

        db.productos.insert_one(nuevo_producto)
        flash(f'✅ Producto "{nombre}" publicado correctamente.', 'success')
        return redirect(url_for('web.marketplace_mis_productos'))

    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'admin/marketplace/producto_form.html',
        vendedor=v,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
        producto=None,
    )


@vendedor_required
def vendedor_editar_producto(producto_id):
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    db = current_app.db

    try:
        producto = db.productos.find_one({
            '_id': ObjectId(producto_id),
            'vendedor_id': v['_id'],
        })
    except Exception:
        producto = None

    if not producto:
        flash('Producto no encontrado o no tienes permiso.', 'danger')
        return redirect(url_for('web.marketplace_mis_productos'))

    if request.method == 'POST':
        nombre        = (request.form.get('nombre') or '').strip()
        descripcion   = (request.form.get('descripcion') or '').strip()
        categoria_id  = (request.form.get('categoria_id') or '').strip() or None
        marca_id      = (request.form.get('marca_id') or '').strip() or None
        temporada_id  = (request.form.get('temporada_id') or '').strip() or None
        estado        = (request.form.get('estado') or 'activo').strip()

        if not nombre:
            flash('El nombre del producto es obligatorio.', 'danger')
            return redirect(url_for('web.marketplace_editar_producto', producto_id=producto_id))

        variantes = _procesar_variantes_form()
        if not variantes:
            flash('Debes agregar al menos una variante.', 'danger')
            return redirect(url_for('web.marketplace_editar_producto', producto_id=producto_id))

        fotos_existentes = request.form.getlist('fotos_existentes[]')
        fotos_nuevas = _procesar_imagenes_form('fotos[]', 'mkt_')
        fotos = list(fotos_existentes) + fotos_nuevas

        videos_existentes = request.form.getlist('videos_existentes[]')
        videos_nuevos = _procesar_videos_form('videos[]', 'mkt_vid_')
        videos = list(videos_existentes) + videos_nuevos

        precios_v = [x['precio'] for x in variantes if x['precio'] > 0]
        stocks_v  = [x['stock'] for x in variantes]
        precio_min = min(precios_v) if precios_v else 0
        stock_total = sum(stocks_v) if stocks_v else 0

        nombre_tienda = v.get('nombre_tienda', '')

        update_data = {
            'nombre': nombre,
            'descripcion': descripcion,
            'categoria_id': ObjectId(categoria_id) if categoria_id else None,
            'marca_id': ObjectId(marca_id) if marca_id else None,
            'temporada_id': ObjectId(temporada_id) if temporada_id else None,
            'fotos': fotos,
            'videos': videos,
            'variables': variantes,
            'precio': precio_min,
            'stock': stock_total,
            'estado': estado,
            'activo': estado == 'activo',

            # ⭐ Reafirmar los alias de vendedor por si faltaban
            'vendedor_id': v['_id'],
            'vendedor_nombre': nombre_tienda,
            'nombre_tienda': nombre_tienda,
            'tienda_nombre': nombre_tienda,

            'updated_at': datetime.now(timezone.utc),
        }

        db.productos.update_one({'_id': producto['_id']}, {'$set': update_data})
        flash('✅ Producto actualizado correctamente.', 'success')
        return redirect(url_for('web.marketplace_mis_productos'))

    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'admin/marketplace/producto_form.html',
        vendedor=v,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
        producto=producto,
    )


@vendedor_required
def vendedor_eliminar_producto(producto_id):
    v = _get_vendedor_marketplace()
    if not v:
        flash('No autorizado', 'danger')
        return redirect(url_for('web.marketplace'))

    db = current_app.db
    try:
        result = db.productos.delete_one({
            '_id': ObjectId(producto_id),
            'vendedor_id': v['_id'],
        })
        if result.deleted_count:
            flash('Producto eliminado.', 'success')
        else:
            flash('Producto no encontrado.', 'danger')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')

    return redirect(url_for('web.marketplace_mis_productos'))


@vendedor_required
def vendedor_mis_pedidos():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    pedidos = _pedidos_del_vendedor_marketplace(v['_id'])

    return render_template(
        'admin/marketplace/mis_pedidos.html',
        vendedor=v,
        pedidos=pedidos,
    )


@vendedor_required
def vendedor_ver_pedido(pedido_id):
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(pedido_id)})
    except Exception:
        pedido = None

    if not pedido:
        flash('Pedido no encontrado.', 'danger')
        return redirect(url_for('web.vendedor_mis_pedidos'))

    items_vendedor = []
    subtotal_vendedor = 0.0
    for item in (pedido.get('items') or []):
        if str(item.get('vendedor_id')) == str(v['_id']):
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            sub = precio * cantidad
            subtotal_vendedor += sub
            items_vendedor.append({
                'id': str(item.get('id', '')),
                'vendedor_id': str(item.get('vendedor_id', '')),
                'nombre': item.get('nombre', 'Producto'),
                'cantidad': cantidad,
                'precio': precio,
                'subtotal': sub,
                'imagen': item.get('imagen') or item.get('foto') or 'default.jpg',
            })

    if not items_vendedor:
        flash('Este pedido no contiene productos tuyos.', 'warning')
        return redirect(url_for('web.vendedor_mis_pedidos'))

    pedido_fmt = {
        '_id': str(pedido['_id']),
        'numero_pedido': pedido.get('numero_pedido', ''),
        'estado': pedido.get('estado', 'pendiente'),
        'created_at': pedido.get('created_at'),
        'items': items_vendedor,
        'subtotal_vendedor': round(subtotal_vendedor, 2),
        'usuario_nombre': pedido.get('usuario_nombre', ''),
        'usuario_email': pedido.get('usuario_email', ''),
        'usuario_telefono': pedido.get('usuario_telefono', ''),
        'direccion': pedido.get('direccion', {}),
    }

    return render_template(
        'admin/marketplace/mis_pedidos.html',
        vendedor=v,
        pedidos=[pedido_fmt],
        pedido=pedido_fmt,
    )


# ================================================================
# VENTAS, CLIENTES, RESEÑAS, ENVÍOS, MI TIENDA (MARKETPLACE)
# ================================================================

@vendedor_required
def vendedor_mis_ventas():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    vendedor_id = v['_id']
    db = current_app.db

    pedidos = _pedidos_del_vendedor_marketplace(vendedor_id)

    ventas = []
    total_ventas = 0
    total_ingresos = 0.0
    total_comisiones = 0.0

    for pedido in pedidos:
        items_vendedor = []
        subtotal = 0.0

        for item in (pedido.get('items') or []):
            if str(item.get('vendedor_id')) != str(vendedor_id):
                continue
            precio = float(item.get('precio', 0))
            cantidad = int(item.get('cantidad', 1))
            sub = precio * cantidad
            subtotal += sub
            items_vendedor.append({
                'nombre': item.get('nombre', 'Producto'),
                'cantidad': cantidad,
                'precio': precio,
                'subtotal': sub,
            })

        if not items_vendedor:
            continue

        comision = subtotal * (float(v.get('comision_pct', 15)) / 100)
        neto = subtotal - comision

        total_ventas += 1
        total_ingresos += subtotal
        total_comisiones += comision

        ventas.append({
            '_id': str(pedido['_id']),
            'numero_pedido': pedido.get('numero_pedido') or str(pedido['_id'])[:8].upper(),
            'fecha': pedido.get('created_at'),
            'cliente': pedido.get('usuario_nombre', 'Cliente'),
            'items': items_vendedor,
            'subtotal': round(subtotal, 2),
            'comision': round(comision, 2),
            'neto': round(neto, 2),
            'estado': pedido.get('estado', 'pendiente'),
        })

    saldo_neto = total_ingresos - total_comisiones
    ticket_promedio = (total_ingresos / total_ventas) if total_ventas else 0

    return render_template(
        'admin/marketplace/mis_ventas.html',
        vendedor=v,
        ventas=ventas,
        stats={
            'total_ventas': total_ventas,
            'total_ingresos': round(total_ingresos, 2),
            'total_comisiones': round(total_comisiones, 2),
            'saldo_neto': round(saldo_neto, 2),
            'ticket_promedio': round(ticket_promedio, 2),
        },
        total_ventas=total_ventas,
        total_ingresos=round(total_ingresos, 2),
        total_comisiones=round(total_comisiones, 2),
        saldo_neto=round(saldo_neto, 2),
        ticket_promedio=round(ticket_promedio, 2),
    )


@vendedor_required
def vendedor_mis_clientes():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    vendedor_id = v['_id']
    db = current_app.db

    pedidos = _pedidos_del_vendedor_marketplace(vendedor_id)

    clientes_map = {}
    for pedido in pedidos:
        items_vendedor = [it for it in (pedido.get('items') or [])
                         if str(it.get('vendedor_id')) == str(vendedor_id)]
        if not items_vendedor:
            continue

        uid = str(pedido.get('usuario_id', ''))
        if not uid:
            continue

        if uid not in clientes_map:
            clientes_map[uid] = {
                'user_id': uid,
                'nombre': pedido.get('usuario_nombre', 'Cliente'),
                'email': pedido.get('usuario_email', ''),
                'telefono': pedido.get('usuario_telefono', ''),
                'pedidos': 0,
                'gasto_total': 0.0,
                'primera_compra': None,
                'ultima_compra': None,
            }

        subtotal = sum(
            float(it.get('precio', 0)) * int(it.get('cantidad', 1))
            for it in items_vendedor
        )
        clientes_map[uid]['pedidos'] += 1
        clientes_map[uid]['gasto_total'] += subtotal

        fecha = pedido.get('created_at')
        if fecha:
            if not clientes_map[uid]['ultima_compra'] or fecha > clientes_map[uid]['ultima_compra']:
                clientes_map[uid]['ultima_compra'] = fecha
            if not clientes_map[uid]['primera_compra'] or fecha < clientes_map[uid]['primera_compra']:
                clientes_map[uid]['primera_compra'] = fecha

    clientes = sorted(clientes_map.values(),
                     key=lambda c: c['gasto_total'], reverse=True)

    recurrentes = sum(1 for c in clientes if c['pedidos'] > 1)

    hoy = datetime.now(timezone.utc)
    inicio_mes = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    nuevos_mes = sum(
        1 for c in clientes
        if c['primera_compra'] and c['primera_compra'] >= inicio_mes
    )

    for c in clientes:
        c['gasto_total'] = round(c['gasto_total'], 2)

    return render_template(
        'admin/marketplace/mis_clientes.html',
        vendedor=v,
        clientes=clientes,
        stats={
            'total_clientes': len(clientes),
            'recurrentes': recurrentes,
            'nuevos_mes': nuevos_mes,
        },
        total_clientes=len(clientes),
        recurrentes=recurrentes,
        nuevos_mes=nuevos_mes,
    )


@vendedor_required
def vendedor_resenas():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    vendedor_id = v['_id']
    db = current_app.db

    productos = _productos_del_vendedor_marketplace(vendedor_id)
    producto_ids = [str(p['_id']) for p in productos]
    producto_map = {str(p['_id']): p for p in productos}

    resenas_raw = []
    if producto_ids:
        oids = []
        for pid in producto_ids:
            try:
                oids.append(ObjectId(pid))
            except Exception:
                pass

        resenas_raw = list(
            db.resenas.find({
                '$or': [
                    {'producto_id': {'$in': producto_ids}},
                    {'producto_id': {'$in': oids}},
                ]
            }).sort('created_at', -1)
        )

    resenas = []
    for r in resenas_raw:
        pid_str = str(r.get('producto_id', ''))
        prod = producto_map.get(pid_str, {})
        resenas.append({
            '_id': str(r['_id']),
            'producto_id': pid_str,
            'producto_nombre': prod.get('nombre', 'Producto'),
            'producto_foto': (prod.get('fotos') or [None])[0],
            'usuario_nombre': r.get('usuario_nombre', 'Anónimo'),
            'calificacion': int(r.get('calificacion', 0)),
            'titulo': r.get('titulo', ''),
            'comentario': r.get('comentario', ''),
            'fecha': r.get('fecha') or (r.get('created_at').strftime('%d/%m/%Y') if r.get('created_at') else ''),
            'respuesta_vendedor': r.get('respuesta_vendedor', ''),
        })

    total = len(resenas)
    promedio = round(sum(r['calificacion'] for r in resenas) / total, 1) if total else 0
    distribucion = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in resenas:
        c = r['calificacion']
        if c in distribucion:
            distribucion[c] += 1

    sin_responder = sum(1 for r in resenas if not r['respuesta_vendedor'])

    stats = {
        'total': total,
        'promedio': promedio,
        'distribucion': distribucion,
        'sin_responder': sin_responder,
    }

    return render_template(
        'admin/marketplace/resenas.html',
        vendedor=v,
        resenas=resenas,
        stats=stats,
        total=total,
        promedio=promedio,
        distribucion=distribucion,
        sin_responder=sin_responder,
    )


@vendedor_required
def vendedor_responder_resena(resena_id):
    v = _get_vendedor_marketplace()
    if not v:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    db = current_app.db

    try:
        oid = ObjectId(resena_id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID inválido'}), 400

    resena = db.resenas.find_one({'_id': oid})
    if not resena:
        return jsonify({'success': False, 'message': 'Reseña no encontrada'}), 404

    productos = _productos_del_vendedor_marketplace(v['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    if str(resena.get('producto_id', '')) not in producto_ids:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    data = request.get_json(silent=True) or {}
    respuesta = (data.get('respuesta') or '').strip()
    if not respuesta:
        return jsonify({'success': False, 'message': 'Respuesta vacía'}), 400

    db.resenas.update_one(
        {'_id': oid},
        {'$set': {
            'respuesta_vendedor': respuesta,
            'respuesta_fecha': datetime.utcnow().strftime('%d/%m/%Y'),
            'respuesta_vendedor_id': str(v['_id']),
            'updated_at': datetime.utcnow(),
        }}
    )
    return jsonify({'success': True})


@vendedor_required
def vendedor_envios():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    vendedor_id = v['_id']
    pedidos = _pedidos_del_vendedor_marketplace(vendedor_id)

    pendientes = []
    enviados = []

    for pedido in pedidos:
        items_vendedor = [it for it in (pedido.get('items') or [])
                         if str(it.get('vendedor_id')) == str(vendedor_id)]
        if not items_vendedor:
            continue

        envio = {
            '_id': str(pedido['_id']),
            'numero_pedido': pedido.get('numero_pedido') or str(pedido['_id'])[:8].upper(),
            'cliente': pedido.get('usuario_nombre', 'Cliente'),
            'fecha': pedido.get('created_at'),
            'direccion': pedido.get('direccion', {}) or {},
            'items': items_vendedor,
            'estado': pedido.get('estado', 'pendiente'),
            'numero_seguimiento': pedido.get('numero_seguimiento', ''),
            'paqueteria': pedido.get('paqueteria', ''),
            'fecha_envio': pedido.get('fecha_envio'),
        }

        if pedido.get('estado') in ('enviado', 'entregado'):
            enviados.append(envio)
        elif pedido.get('estado') != 'cancelado':
            pendientes.append(envio)

    stats = {
        'pendientes': len(pendientes),
        'enviados': len(enviados),
    }

    return render_template(
        'admin/marketplace/envios.html',
        vendedor=v,
        pendientes=pendientes,
        enviados=enviados,
        stats=stats,
    )


@vendedor_required
def vendedor_marcar_enviado(pedido_id):
    v = _get_vendedor_marketplace()
    if not v:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    db = current_app.db

    try:
        oid = ObjectId(pedido_id)
    except Exception:
        return jsonify({'success': False, 'message': 'ID inválido'}), 400

    pedido = db.pedidos.find_one({'_id': oid})
    if not pedido:
        return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404

    items_vendedor = [it for it in (pedido.get('items') or [])
                     if str(it.get('vendedor_id')) == str(v['_id'])]
    if not items_vendedor:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    data = request.get_json(silent=True) or {}
    numero = (data.get('numero_seguimiento') or '').strip()
    paqueteria = (data.get('paqueteria') or '').strip()

    db.pedidos.update_one(
        {'_id': oid},
        {'$set': {
            'estado': 'enviado',
            'numero_seguimiento': numero,
            'paqueteria': paqueteria,
            'fecha_envio': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    return jsonify({'success': True})


@vendedor_required
def vendedor_mi_tienda():
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    db = current_app.db

    if request.method == 'POST':
        tema_hero = (request.form.get('tema_hero') or 'azul').strip()
        if tema_hero not in TEMAS_HERO_VALIDOS:
            tema_hero = 'azul'

        update = {
            'nombre_tienda': (request.form.get('nombre_tienda') or v.get('nombre_tienda', '')).strip(),
            'descripcion': (request.form.get('descripcion') or v.get('descripcion', '')).strip(),
            'razon_social': (request.form.get('razon_social') or v.get('razon_social', '')).strip(),
            'rfc': (request.form.get('rfc') or v.get('rfc', '')).strip().upper(),
            'email_contacto': (request.form.get('email_contacto') or v.get('email_contacto', '')).strip(),
            'whatsapp': (request.form.get('whatsapp') or v.get('whatsapp', '')).strip(),
            'ubicacion': (request.form.get('ubicacion') or v.get('ubicacion', '')).strip(),
            'tema_hero': tema_hero,
            'updated_at': datetime.now(timezone.utc),
        }

        if request.form.get('quitar_hero_imagen') == '1':
            update['hero_imagen'] = None

        file = request.files.get('logo')
        if file and file.filename:
            import os, secrets
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
                folder = os.path.join(current_app.root_path, 'static', 'uploads', 'vendedores')
                os.makedirs(folder, exist_ok=True)
                filename = f"vendedor_{secrets.token_hex(6)}.{ext}"
                file.save(os.path.join(folder, filename))
                update['logo'] = filename

        hero_file = request.files.get('hero_imagen')
        if hero_file and hero_file.filename:
            import os, secrets
            ext = hero_file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
                folder = os.path.join(current_app.root_path, 'static', 'uploads', 'vendedores')
                os.makedirs(folder, exist_ok=True)
                filename = f"hero_{secrets.token_hex(6)}.{ext}"
                hero_file.save(os.path.join(folder, filename))
                update['hero_imagen'] = filename

        db.vendedores.update_one({'_id': ObjectId(v['_id'])}, {'$set': update})

        # ⭐ Sincronizar el nombre de tienda en TODOS los productos del vendedor
        # para que el badge del catálogo refleje el nuevo nombre
        if update.get('nombre_tienda'):
            try:
                db.productos.update_many(
                    {'vendedor_id': v['_id']},
                    {'$set': {
                        'vendedor_nombre': update['nombre_tienda'],
                        'nombre_tienda':   update['nombre_tienda'],
                        'tienda_nombre':   update['nombre_tienda'],
                        'updated_at':      datetime.now(timezone.utc),
                    }}
                )
            except Exception as e:
                print(f"⚠️ No se pudo sincronizar nombre_tienda en productos: {e}", file=sys.stderr)

        flash('✅ Información actualizada correctamente.', 'success')
        return redirect(url_for('web.marketplace_mi_tienda'))

    v = _get_vendedor_marketplace()

    return render_template(
        'admin/marketplace/mi_tienda.html',
        vendedor=v,
    )


# ================================================================
# VENTAS, CLIENTES, ENVÍOS, MI TIENDA (VENDEDOR NATIVO)
# ================================================================

@vendedor_required
def lista_ventas():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db
    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    pedidos_raw = _get_pedidos_vendedor(vendedor['_id'])
    pedidos = [_formatear_pedido_para_vendedor(p, producto_ids) for p in pedidos_raw]

    ventas = []
    total_ventas = 0
    total_ingresos = 0.0

    for p in pedidos:
        if not p['items']:
            continue
        subtotal = float(p['subtotal_vendedor'])
        comision = subtotal * 0.15
        neto = subtotal - comision

        total_ventas += 1
        total_ingresos += subtotal

        ventas.append({
            '_id': p['_id'],
            'numero_pedido': p['numero_pedido'] or str(p['_id'])[:8].upper(),
            'fecha': p['created_at'],
            'cliente': p['usuario_nombre'] or 'Cliente',
            'items_count': len(p['items']),
            'subtotal': round(subtotal, 2),
            'comision': round(comision, 2),
            'neto': round(neto, 2),
            'estado': p['estado'],
        })

    total_comisiones = total_ingresos * 0.15
    saldo_neto = total_ingresos - total_comisiones
    ticket_promedio = (total_ingresos / total_ventas) if total_ventas else 0

    stats = {
        'total_ventas': total_ventas,
        'total_ingresos': round(total_ingresos, 2),
        'total_comisiones': round(total_comisiones, 2),
        'saldo_neto': round(saldo_neto, 2),
        'ticket_promedio': round(ticket_promedio, 2),
    }

    return render_template(
        'admin/marketplace/mis_ventas.html',
        vendedor=vendedor,
        ventas=ventas,
        stats=stats,
        total_ventas=total_ventas,
        total_ingresos=round(total_ingresos, 2),
        total_comisiones=round(total_comisiones, 2),
        saldo_neto=round(saldo_neto, 2),
        ticket_promedio=round(ticket_promedio, 2),
    )


@vendedor_required
def lista_clientes():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db
    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    pedidos_raw = _get_pedidos_vendedor(vendedor['_id'])

    clientes_map = {}
    for p in pedidos_raw:
        items = [it for it in (p.get('items') or []) if str(it.get('id')) in producto_ids]
        if not items:
            continue

        uid = str(p.get('usuario_id', ''))
        if not uid:
            continue

        if uid not in clientes_map:
            clientes_map[uid] = {
                'user_id': uid,
                'nombre': p.get('usuario_nombre', 'Cliente'),
                'email': p.get('usuario_email', ''),
                'telefono': p.get('usuario_telefono', ''),
                'pedidos': 0,
                'gasto_total': 0.0,
                'primera_compra': None,
                'ultima_compra': None,
            }

        subtotal = sum(float(it.get('precio', 0)) * int(it.get('cantidad', 1)) for it in items)
        clientes_map[uid]['pedidos'] += 1
        clientes_map[uid]['gasto_total'] += subtotal

        fecha = p.get('created_at')
        if fecha:
            if not clientes_map[uid]['ultima_compra'] or fecha > clientes_map[uid]['ultima_compra']:
                clientes_map[uid]['ultima_compra'] = fecha
            if not clientes_map[uid]['primera_compra'] or fecha < clientes_map[uid]['primera_compra']:
                clientes_map[uid]['primera_compra'] = fecha

    clientes = sorted(clientes_map.values(), key=lambda c: c['gasto_total'], reverse=True)
    for c in clientes:
        c['gasto_total'] = round(c['gasto_total'], 2)

    recurrentes = sum(1 for c in clientes if c['pedidos'] > 1)

    hoy = datetime.now(timezone.utc)
    inicio_mes = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    nuevos_mes = sum(
        1 for c in clientes
        if c['primera_compra'] and c['primera_compra'] >= inicio_mes
    )

    stats = {
        'total_clientes': len(clientes),
        'recurrentes': recurrentes,
        'nuevos_mes': nuevos_mes,
    }

    return render_template(
        'admin/marketplace/mis_clientes.html',
        vendedor=vendedor,
        clientes=clientes,
        stats=stats,
        total_clientes=len(clientes),
        recurrentes=recurrentes,
        nuevos_mes=nuevos_mes,
    )


@vendedor_required
def lista_envios():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db
    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    pedidos_raw = _get_pedidos_vendedor(vendedor['_id'])

    pendientes = []
    enviados = []

    for p in pedidos_raw:
        items = [it for it in (p.get('items') or []) if str(it.get('id')) in producto_ids]
        if not items:
            continue

        envio = {
            '_id': str(p['_id']),
            'numero_pedido': p.get('numero_pedido') or str(p['_id'])[:8].upper(),
            'cliente': p.get('usuario_nombre', 'Cliente'),
            'fecha': p.get('created_at'),
            'direccion': p.get('direccion', {}) or {},
            'items': items,
            'estado': p.get('estado', 'pendiente'),
            'numero_seguimiento': p.get('numero_seguimiento', ''),
            'paqueteria': p.get('paqueteria', ''),
            'fecha_envio': p.get('fecha_envio'),
        }

        if p.get('estado') in ('enviado', 'entregado'):
            enviados.append(envio)
        elif p.get('estado') != 'cancelado':
            pendientes.append(envio)

    stats = {
        'pendientes': len(pendientes),
        'enviados': len(enviados),
    }

    return render_template(
        'admin/marketplace/envios.html',
        vendedor=vendedor,
        pendientes=pendientes,
        enviados=enviados,
        stats=stats,
    )


@vendedor_required
def mi_tienda():
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    if request.method == 'POST':
        tema_hero = (request.form.get('tema_hero') or 'azul').strip()
        if tema_hero not in TEMAS_HERO_VALIDOS:
            tema_hero = 'azul'

        update = {
            'nombre_tienda': (request.form.get('nombre_tienda') or vendedor.get('nombre_tienda', '')).strip(),
            'descripcion': (request.form.get('descripcion') or vendedor.get('descripcion', '')).strip(),
            'razon_social': (request.form.get('razon_social') or vendedor.get('razon_social', '')).strip(),
            'rfc': (request.form.get('rfc') or vendedor.get('rfc', '')).strip().upper(),
            'email_contacto': (request.form.get('email_contacto') or vendedor.get('email', '')).strip(),
            'whatsapp': (request.form.get('whatsapp') or vendedor.get('whatsapp', '')).strip(),
            'ubicacion': (request.form.get('ubicacion') or vendedor.get('ubicacion', '')).strip(),
            'tema_hero': tema_hero,
            'updated_at': datetime.utcnow(),
        }

        if request.form.get('quitar_hero_imagen') == '1':
            update['hero_imagen'] = None

        file = request.files.get('logo')
        if file and file.filename:
            import os, secrets
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
                folder = os.path.join(current_app.root_path, 'static', 'uploads', 'vendedores')
                os.makedirs(folder, exist_ok=True)
                filename = f"vendedor_{secrets.token_hex(6)}.{ext}"
                file.save(os.path.join(folder, filename))
                update['logo'] = filename

        hero_file = request.files.get('hero_imagen')
        if hero_file and hero_file.filename:
            import os, secrets
            ext = hero_file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
                folder = os.path.join(current_app.root_path, 'static', 'uploads', 'vendedores')
                os.makedirs(folder, exist_ok=True)
                filename = f"hero_{secrets.token_hex(6)}.{ext}"
                hero_file.save(os.path.join(folder, filename))
                update['hero_imagen'] = filename

        db.usuarios.update_one({'_id': vendedor['_id']}, {'$set': update})

        # ⭐ Sincronizar nombre_tienda en productos
        if update.get('nombre_tienda'):
            try:
                db.productos.update_many(
                    {'vendedor_id': str(vendedor['_id'])},
                    {'$set': {
                        'vendedor_nombre': update['nombre_tienda'],
                        'nombre_tienda':   update['nombre_tienda'],
                        'tienda_nombre':   update['nombre_tienda'],
                        'updated_at':      datetime.utcnow(),
                    }}
                )
            except Exception as e:
                print(f"⚠️ Sync nombre_tienda: {e}", file=sys.stderr)

        flash('✅ Información actualizada correctamente.', 'success')
        return redirect(url_for('web.vendedor_mi_tienda'))

    vendedor = _get_usuario_actual()

    return render_template(
        'admin/marketplace/mi_tienda.html',
        vendedor=vendedor,
    )


# ================================================================
# PERFIL DEL VENDEDOR (cuenta de usuario)
# ================================================================

@vendedor_required
def perfil():
    """
    Perfil del vendedor con soporte para:
      - Datos personales
      - Cambio de contraseña
      - Complexión
      - Intereses
      - Direcciones
    """
    usuario = _get_usuario_actual()
    if not usuario:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db
    vendedor_mkt = _get_vendedor_marketplace()

    if request.method == 'POST':
        accion = (request.form.get('accion') or 'datos').strip()

        # CAMBIO DE CONTRASEÑA
        if accion == 'password':
            from werkzeug.security import check_password_hash, generate_password_hash

            actual    = (request.form.get('password_actual') or '').strip()
            nueva     = (request.form.get('password_nueva') or '').strip()
            confirmar = (request.form.get('password_confirmar') or '').strip()

            if not actual or not nueva or not confirmar:
                flash('Todos los campos de contraseña son obligatorios.', 'danger')
                return redirect(url_for('web.marketplace_perfil'))
            if nueva != confirmar:
                flash('Las contraseñas nuevas no coinciden.', 'danger')
                return redirect(url_for('web.marketplace_perfil'))
            if len(nueva) < 6:
                flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
                return redirect(url_for('web.marketplace_perfil'))

            hash_guardado = (
                usuario.get('password')
                or usuario.get('password_hash')
                or usuario.get('contrasena')
                or ''
            )
            if not hash_guardado or not check_password_hash(hash_guardado, actual):
                flash('La contraseña actual es incorrecta.', 'danger')
                return redirect(url_for('web.marketplace_perfil'))

            db.usuarios.update_one(
                {'_id': usuario['_id']},
                {'$set': {
                    'password': generate_password_hash(nueva),
                    'updated_at': datetime.utcnow(),
                }}
            )
            flash('✅ Contraseña actualizada correctamente.', 'success')
            return redirect(url_for('web.marketplace_perfil'))

        # DATOS PERSONALES
        if accion == 'datos':
            nombre           = (request.form.get('nombre') or usuario.get('nombre', '')).strip()
            apellido_paterno = (request.form.get('apellido_paterno') or usuario.get('apellido_paterno', '')).strip()
            apellido_materno = (request.form.get('apellido_materno') or usuario.get('apellido_materno', '')).strip()
            email            = (request.form.get('email') or usuario.get('email', '')).strip().lower()
            telefono         = (request.form.get('telefono') or usuario.get('telefono', '')).strip()
            genero           = (request.form.get('genero') or usuario.get('genero', '')).strip()
            fecha_nac        = (request.form.get('fecha_nacimiento') or '').strip()

            update = {
                'nombre': nombre,
                'apellido_paterno': apellido_paterno,
                'apellido_materno': apellido_materno,
                'email': email,
                'telefono': telefono,
                'genero': genero,
                'updated_at': datetime.utcnow(),
            }
            if fecha_nac:
                update['fecha_nacimiento'] = fecha_nac

            file = request.files.get('foto')
            if file and file.filename:
                import os, secrets
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
                    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'perfiles')
                    os.makedirs(folder, exist_ok=True)
                    filename = f"user_{secrets.token_hex(6)}.{ext}"
                    file.save(os.path.join(folder, filename))
                    update['foto'] = f"perfiles/{filename}"
                    session['foto'] = update['foto']

            db.usuarios.update_one({'_id': usuario['_id']}, {'$set': update})

            if nombre: session['nombre'] = nombre
            if email: session['email'] = email
            if telefono: session['telefono'] = telefono

            flash('✅ Datos personales actualizados.', 'success')
            return redirect(url_for('web.marketplace_perfil') + '#personal')

        # COMPLEXIÓN
        if accion == 'complexion':
            try:
                altura = request.form.get('altura_cm')
                peso   = request.form.get('peso_kg')
                medidas = {
                    'pecho_cm':   request.form.get('pecho_cm') or None,
                    'cintura_cm': request.form.get('cintura_cm') or None,
                    'cadera_cm':  request.form.get('cadera_cm') or None,
                }
                complexion = {
                    'altura_cm':      float(altura) if altura else None,
                    'peso_kg':        float(peso) if peso else None,
                    'complexion':     (request.form.get('complexion') or '').strip() or None,
                    'talla_camisa':   (request.form.get('talla_camisa') or '').strip() or None,
                    'talla_pantalon': (request.form.get('talla_pantalon') or '').strip() or None,
                    'talla_calzado':  (request.form.get('talla_calzado') or '').strip() or None,
                    'talla_sujetador':(request.form.get('talla_sujetador') or '').strip() or None,
                    'medidas':        medidas,
                    'estilos_preferidos': request.form.getlist('estilos_preferidos'),
                    'colores_favoritos':  request.form.getlist('colores_favoritos'),
                }
                db.usuarios.update_one(
                    {'_id': usuario['_id']},
                    {'$set': {'complexion': complexion, 'updated_at': datetime.utcnow()}}
                )
                flash('✅ Complexión actualizada.', 'success')
            except Exception as e:
                flash(f'Error al guardar complexión: {e}', 'danger')
            return redirect(url_for('web.marketplace_perfil') + '#complexion')

        # INTERESES
        if accion == 'intereses':
            intereses = {
                'categorias':   request.form.getlist('categorias'),
                'marcas':       request.form.getlist('marcas'),
                'actividades':  request.form.getlist('actividades'),
                'ocasiones':    request.form.getlist('ocasiones'),
                'frecuencia':   (request.form.get('frecuencia') or '').strip() or None,
            }
            db.usuarios.update_one(
                {'_id': usuario['_id']},
                {'$set': {'intereses': intereses, 'updated_at': datetime.utcnow()}}
            )
            flash('✅ Intereses actualizados.', 'success')
            return redirect(url_for('web.marketplace_perfil') + '#intereses')

        # DIRECCIONES — AGREGAR
        if accion == 'dir_agregar':
            dirs = usuario.get('direcciones') or []
            nueva = {
                'nombre':      (request.form.get('dir_nombre') or '').strip(),
                'calle':       (request.form.get('dir_calle') or '').strip(),
                'numero':      (request.form.get('dir_numero') or '').strip(),
                'cp':          (request.form.get('dir_cp') or '').strip(),
                'colonia':     (request.form.get('dir_colonia') or '').strip(),
                'ciudad':      (request.form.get('dir_ciudad') or '').strip(),
                'estado':      (request.form.get('dir_estado') or '').strip(),
                'referencias': (request.form.get('dir_referencias') or '').strip(),
                'predeterminada': bool(request.form.get('dir_predeterminada')),
            }
            if not nueva['calle'] or not nueva['numero'] or not nueva['colonia'] or not nueva['cp']:
                flash('Calle, número, colonia y CP son obligatorios.', 'danger')
                return redirect(url_for('web.marketplace_perfil') + '#direcciones')

            if nueva['predeterminada']:
                for d in dirs:
                    d['predeterminada'] = False
            dirs.append(nueva)

            db.usuarios.update_one({'_id': usuario['_id']}, {'$set': {'direcciones': dirs}})
            flash('✅ Dirección agregada.', 'success')
            return redirect(url_for('web.marketplace_perfil') + '#direcciones')

        # DIRECCIONES — EDITAR
        if accion == 'dir_editar':
            try:
                idx = int(request.form.get('dir_index', -1))
            except (ValueError, TypeError):
                idx = -1
            dirs = usuario.get('direcciones') or []
            if 0 <= idx < len(dirs):
                d = dirs[idx]
                d['nombre']      = (request.form.get('dir_nombre') or '').strip()
                d['calle']       = (request.form.get('dir_calle') or '').strip()
                d['numero']      = (request.form.get('dir_numero') or '').strip()
                d['cp']          = (request.form.get('dir_cp') or '').strip()
                d['colonia']     = (request.form.get('dir_colonia') or '').strip()
                d['ciudad']      = (request.form.get('dir_ciudad') or '').strip()
                d['estado']      = (request.form.get('dir_estado') or '').strip()
                d['referencias'] = (request.form.get('dir_referencias') or '').strip()

                if request.form.get('dir_predeterminada'):
                    for i, x in enumerate(dirs):
                        x['predeterminada'] = (i == idx)

                db.usuarios.update_one({'_id': usuario['_id']}, {'$set': {'direcciones': dirs}})
                flash('✅ Dirección actualizada.', 'success')
            else:
                flash('Dirección no encontrada.', 'danger')
            return redirect(url_for('web.marketplace_perfil') + '#direcciones')

        # DIRECCIONES — ELIMINAR
        if accion == 'dir_eliminar':
            try:
                idx = int(request.form.get('dir_index', -1))
            except (ValueError, TypeError):
                idx = -1
            dirs = usuario.get('direcciones') or []
            if 0 <= idx < len(dirs):
                dirs.pop(idx)
                db.usuarios.update_one({'_id': usuario['_id']}, {'$set': {'direcciones': dirs}})
                flash('Dirección eliminada.', 'success')
            return redirect(url_for('web.marketplace_perfil') + '#direcciones')

        # DIRECCIONES — PREDETERMINAR
        if accion == 'dir_predeterminada':
            try:
                idx = int(request.form.get('dir_index', -1))
            except (ValueError, TypeError):
                idx = -1
            dirs = usuario.get('direcciones') or []
            if 0 <= idx < len(dirs):
                for i, x in enumerate(dirs):
                    x['predeterminada'] = (i == idx)
                db.usuarios.update_one({'_id': usuario['_id']}, {'$set': {'direcciones': dirs}})
                flash('Dirección predeterminada actualizada.', 'success')
            return redirect(url_for('web.marketplace_perfil') + '#direcciones')

    # -------- GET --------
    usuario = _get_usuario_actual()

    return render_template(
        'admin/marketplace/perfil.html',
        usuario=usuario,
        vendedor=vendedor_mkt,
    )