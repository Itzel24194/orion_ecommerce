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
# ⭐ HELPERS PARA FORMULARIOS (categorías + marcas)
# ================================================================

def _calcular_nivel_categorias(categorias):
    """
    Calcula el nivel (1, 2, 3...) de cada categoría basado en padre_id.
    Modifica los diccionarios in-place y devuelve la lista.
    """
    if not categorias:
        return categorias

    por_id = {str(c['_id']): c for c in categorias}

    def get_nivel(cat, visitados=None):
        if visitados is None:
            visitados = set()
        cid = str(cat['_id'])
        if cid in visitados:
            return 1  # ref circular
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
    """
    Devuelve categorías con 'nivel' calculado y 'padre_nombre' resuelto
    para que el template pueda renderizar la jerarquía.
    """
    db = current_app.db
    try:
        categorias = list(db.categorias.find({}))
    except Exception as e:
        print(f"⚠️ [_get_categorias_para_form] {e}", file=sys.stderr)
        return []

    # Calcular nivel
    categorias = _calcular_nivel_categorias(categorias)

    # Resolver padre_nombre
    por_id = {str(c['_id']): c for c in categorias}
    for cat in categorias:
        pid = cat.get('padre_id')
        if pid and str(pid) in por_id:
            cat['padre_nombre'] = por_id[str(pid)].get('nombre', '')
        else:
            cat['padre_nombre'] = ''

    return categorias


def _get_marcas_para_form():
    """
    Devuelve marcas activas probando varios posibles estados.
    Si no encuentra ninguna, devuelve TODAS las marcas.
    """
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

    # Fallback: si no encuentra nada, cargar todas
    if not marcas:
        try:
            marcas = list(db.marcas.find({}).sort('nombre_comercial', 1))
        except Exception:
            marcas = []

    return marcas


def _get_temporadas_para_form():
    """Devuelve (temporadas, temporadas_dict) para los templates."""
    db = current_app.db
    try:
        temporadas = list(db.temporadas.find({}).sort('fecha_inicio', -1))
    except Exception:
        temporadas = []
    temporadas_dict = {str(t['_id']): t for t in temporadas}
    return temporadas, temporadas_dict


# ================================================================
# DASHBOARD PRINCIPAL (vendedor nativo)
# ================================================================

@vendedor_required
def dashboard():
    """Panel principal del vendedor."""
    vendedor = _get_usuario_actual()
    if not vendedor:
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for('web.login'))

    db = current_app.db

    # 1. PRODUCTOS
    productos = _get_productos_vendedor(vendedor['_id'])
    producto_ids = [str(p['_id']) for p in productos]

    total_productos = len(productos)
    productos_activos = sum(1 for p in productos if p.get('activo', True))
    productos_sin_stock = sum(1 for p in productos if int(p.get('stock', 0)) <= 0)
    productos_stock_bajo = sum(1 for p in productos if 0 < int(p.get('stock', 0)) <= 5)

    # 2. PEDIDOS
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

    # 3. VENTAS
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

    # 4. RESEÑAS
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

    # 5. TOP 5 PRODUCTOS
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

    # 6. PEDIDOS Y PRODUCTOS RECIENTES
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
        'admin/vendedor.html',
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
# PRODUCTOS (vendedor nativo)
# ================================================================

@vendedor_required
def lista_productos():
    """Lista de productos del vendedor con filtros."""
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
        'admin/vendedor_productos.html',
        vendedor=vendedor,
        productos=productos,
        stats=stats,
    )


@vendedor_required
def crear_producto():
    """Muestra y procesa el formulario de crear producto (vendedor nativo)."""
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

        producto = {
            'nombre': nombre,
            'descripcion': request.form.get('descripcion', '').strip(),
            'precio': precio,
            'stock': stock,
            'categoria': request.form.get('categoria', '').strip(),
            'marca': request.form.get('marca', '').strip(),
            'activo': True,
            'vendedor_id': str(vendedor['_id']),
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
    """Edita un producto del vendedor (nativo)."""
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
    """Elimina un producto del vendedor."""
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
    """Activa/Desactiva un producto del vendedor."""
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
    db.productos.update_one(
        {'_id': oid},
        {'$set': {'activo': nuevo, 'updated_at': datetime.utcnow()}}
    )
    flash(f'Producto {"activado" if nuevo else "desactivado"}', 'success')
    return redirect(url_for('web.vendedor_productos'))


# ================================================================
# PEDIDOS (vendedor nativo)
# ================================================================

@vendedor_required
def lista_pedidos():
    """Lista de pedidos que contienen productos del vendedor."""
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
        'admin/vendedor_pedidos.html',
        vendedor=vendedor,
        pedidos=pedidos,
        stats=stats,
    )


@vendedor_required
def ver_pedido(pedido_id):
    """Ver detalle de un pedido (solo items del vendedor)."""
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
        'admin/vendedor_pedido_detalle.html',
        vendedor=vendedor,
        pedido=pedido_fmt,
    )


@vendedor_required
def actualizar_estado_pedido(pedido_id):
    """Actualiza el estado de un pedido (solo si contiene productos del vendedor)."""
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
# RESEÑAS (vendedor nativo)
# ================================================================

@vendedor_required
def lista_resenas():
    """Lista de reseñas de los productos del vendedor."""
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
        'admin/vendedor_resenas.html',
        vendedor=vendedor,
        resenas=resenas,
        stats=stats,
    )


@vendedor_required
def responder_resena(resena_id):
    """Permite al vendedor responder a una reseña de su producto."""
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
# API (vendedor nativo)
# ================================================================

@vendedor_required
def api_stats():
    """Devuelve las estadísticas del vendedor en JSON."""
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
# ⭐⭐⭐ MARKETPLACE — HELPERS ⭐⭐⭐
# ================================================================

def _get_vendedor_marketplace():
    """
    Devuelve el documento del vendedor (colección 'vendedores') del usuario
    logueado, formateado. None si no tiene tienda aprobada.
    """
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
    """Productos del vendedor de marketplace."""
    db = current_app.db
    return list(db.productos.find({
        'vendedor_id': vendedor_id,
    }).sort('created_at', -1))


def _pedidos_del_vendedor_marketplace(vendedor_id):
    """Pedidos que incluyan productos de este vendedor de marketplace."""
    db = current_app.db
    return list(db.pedidos.find({
        'items.vendedor_id': vendedor_id,
    }).sort('created_at', -1))


def _procesar_variantes_form():
    """
    Extrae las variantes del formulario (arrays paralelos).
    Devuelve lista de dicts: {sku, color, tamano, precio, stock}
    """
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
    """Procesa archivos de imágenes subidos."""
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
    """Procesa archivos de video subidos."""
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
# VISTAS DEL PANEL DE VENDEDOR MARKETPLACE
# ================================================================

@vendedor_required
def dashboard_marketplace():
    """Panel principal del vendedor de marketplace."""
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
        'tienda/marketplace/dashboard.html',
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
    """Lista completa de productos del vendedor marketplace."""
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    productos = _productos_del_vendedor_marketplace(v['_id'])

    # ⭐ Usar helpers flexibles
    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'tienda/marketplace/mis_productos.html',
        vendedor=v,
        productos=productos,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
    )


@vendedor_required
def vendedor_nuevo_producto():
    """
    GET: formulario de crear producto
    POST: crea el producto con variantes, fotos, videos, temporada.
    """
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    db = current_app.db

    if request.method == 'POST':
        # ----- Campos básicos -----
        nombre        = (request.form.get('nombre') or '').strip()
        descripcion   = (request.form.get('descripcion') or '').strip()
        categoria_id  = (request.form.get('categoria_id') or '').strip() or None
        marca_id      = (request.form.get('marca_id') or '').strip() or None
        temporada_id  = (request.form.get('temporada_id') or '').strip() or None
        estado        = (request.form.get('estado') or 'activo').strip()

        # ----- Validaciones -----
        if not nombre:
            flash('El nombre del producto es obligatorio.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        if not categoria_id:
            flash('Debes seleccionar una categoría.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        if not marca_id:
            flash('Debes seleccionar una marca.', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        # ----- Variantes -----
        variantes = _procesar_variantes_form()
        if not variantes:
            flash('Debes agregar al menos una variante (color + talla + SKU + precio + stock).', 'danger')
            return redirect(url_for('web.marketplace_nuevo_producto'))

        # ----- Fotos y videos -----
        fotos  = _procesar_imagenes_form('fotos[]', 'mkt_')
        videos = _procesar_videos_form('videos[]', 'mkt_vid_')

        # ----- Precio/stock globales (fallback) -----
        precios_v = [x['precio'] for x in variantes if x['precio'] > 0]
        stocks_v  = [x['stock'] for x in variantes]
        precio_min = min(precios_v) if precios_v else 0
        stock_total = sum(stocks_v) if stocks_v else 0

        # ----- Documento -----
        nuevo_producto = {
            'nombre': nombre,
            'descripcion': descripcion,
            'vendedor_id': v['_id'],
            'vendedor_nombre': v.get('nombre_tienda', ''),
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

    # ----- GET: mostrar formulario -----
    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'tienda/marketplace/producto_form.html',
        vendedor=v,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
        producto=None,
    )


@vendedor_required
def vendedor_editar_producto(producto_id):
    """
    GET: formulario de edición
    POST: guarda cambios (variantes, fotos, videos)
    """
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
        # ----- Campos básicos -----
        nombre        = (request.form.get('nombre') or '').strip()
        descripcion   = (request.form.get('descripcion') or '').strip()
        categoria_id  = (request.form.get('categoria_id') or '').strip() or None
        marca_id      = (request.form.get('marca_id') or '').strip() or None
        temporada_id  = (request.form.get('temporada_id') or '').strip() or None
        estado        = (request.form.get('estado') or 'activo').strip()

        if not nombre:
            flash('El nombre del producto es obligatorio.', 'danger')
            return redirect(url_for('web.marketplace_editar_producto', producto_id=producto_id))

        # ----- Variantes -----
        variantes = _procesar_variantes_form()
        if not variantes:
            flash('Debes agregar al menos una variante.', 'danger')
            return redirect(url_for('web.marketplace_editar_producto', producto_id=producto_id))

        # ----- Fotos: existentes + nuevas -----
        fotos_existentes = request.form.getlist('fotos_existentes[]')
        fotos_nuevas = _procesar_imagenes_form('fotos[]', 'mkt_')
        fotos = list(fotos_existentes) + fotos_nuevas

        # ----- Videos: existentes + nuevos -----
        videos_existentes = request.form.getlist('videos_existentes[]')
        videos_nuevos = _procesar_videos_form('videos[]', 'mkt_vid_')
        videos = list(videos_existentes) + videos_nuevos

        # ----- Precio/stock globales (fallback) -----
        precios_v = [x['precio'] for x in variantes if x['precio'] > 0]
        stocks_v  = [x['stock'] for x in variantes]
        precio_min = min(precios_v) if precios_v else 0
        stock_total = sum(stocks_v) if stocks_v else 0

        # ----- Update -----
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
            'updated_at': datetime.now(timezone.utc),
        }

        db.productos.update_one({'_id': producto['_id']}, {'$set': update_data})
        flash('✅ Producto actualizado correctamente.', 'success')
        return redirect(url_for('web.marketplace_mis_productos'))

    # ----- GET: mostrar formulario con datos -----
    categorias = _get_categorias_para_form()
    marcas = _get_marcas_para_form()
    temporadas, temporadas_dict = _get_temporadas_para_form()

    return render_template(
        'tienda/marketplace/producto_form.html',
        vendedor=v,
        categorias=categorias,
        marcas=marcas,
        temporadas=temporadas,
        temporadas_dict=temporadas_dict,
        producto=producto,
    )


@vendedor_required
def vendedor_eliminar_producto(producto_id):
    """Elimina un producto del marketplace."""
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
    """Lista los pedidos del vendedor marketplace."""
    v = _get_vendedor_marketplace()
    if not v:
        flash('No tienes una tienda activa.', 'warning')
        return redirect(url_for('web.marketplace'))

    pedidos = _pedidos_del_vendedor_marketplace(v['_id'])

    return render_template(
        'tienda/marketplace/mis_pedidos.html',
        vendedor=v,
        pedidos=pedidos,
    )


@vendedor_required
def vendedor_ver_pedido(pedido_id):
    """Ver detalle de un pedido del vendedor marketplace."""
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
        # Filtra por vendedor_id del marketplace
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
        'tienda/marketplace/pedido_detalle.html',
        vendedor=v,
        pedido=pedido_fmt,
    )