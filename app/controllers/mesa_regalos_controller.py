# ================================================================
# CONTROLLER: MESA DE REGALOS
# ================================================================
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, jsonify, flash, abort
from app.models.mesa_regalos_model import MesaRegalos
from app.models.productos_model import Producto
from app.models.marcas_model import Marca


def _db():
    from flask import current_app
    return current_app.db


def _usuario_id():
    return session.get('usuario_id') or session.get('user_id')


def _usuario_email():
    return session.get('email', '')


# ------------------------------------------------------------
# HELPER: extraer precio de un producto (de variables si existe)
# ------------------------------------------------------------
def _precio_producto(p):
    """
    Extrae el precio del producto.
    Orden de prioridad:
      1. Primera variante CON stock
      2. Primera variante
      3. Campo 'precio' o 'precio_base' del producto
      4. 0.0
    """
    variables = p.get('variables') or p.get('variantes') or []

    if variables:
        con_stock = [v for v in variables if (v.get('stock') or 0) > 0]
        if con_stock:
            try:
                return float(con_stock[0].get('precio') or 0)
            except (ValueError, TypeError):
                pass
        try:
            return float(variables[0].get('precio') or 0)
        except (ValueError, TypeError):
            pass

    for key in ('precio', 'precio_base', 'precio_venta'):
        try:
            val = p.get(key)
            if val is not None and val != '':
                return float(val)
        except (ValueError, TypeError):
            continue

    return 0.0


# ------------------------------------------------------------
# CREAR
# ------------------------------------------------------------
def crear_mesa():
    if not session.get('nombre'):
        flash('Inicia sesión para crear tu Mesa de Regalos', 'warning')
        return redirect(url_for('web.login'))

    # ✅ Obtener productos
    productos = list(Producto.obtener_todos())[:24]

    # ✅ Mapa de marcas para no ir a la DB dentro del loop
    marcas = Marca.obtener_todas()
    marcas_map = {str(m['_id']): m.get('nombre_comercial', '') for m in marcas}

    productos_normalizados = []
    for p in productos:
        # Imagen principal
        imagen = 'default.jpg'
        if p.get('fotos'):
            imagen = p['fotos'][0]
        elif p.get('imagen'):
            imagen = p['imagen']

        # Marca
        marca_nombre = marcas_map.get(str(p.get('marca_id') or ''), '')

        productos_normalizados.append({
            '_id':    str(p['_id']),
            'nombre': p.get('nombre', 'Producto'),
            'precio': _precio_producto(p),   # ✅ precio real de la variante
            'marca':  marca_nombre,
            'imagen': imagen,
        })

    return render_template(
        'tienda/mesa_regalos/crear.html',
        productos_regalo=productos_normalizados,
    )


def guardar_mesa():
    if not session.get('nombre'):
        return jsonify({'success': False, 'error': 'No autorizado'}), 401

    data = request.get_json() or {}

    if not data.get('event_name', '').strip():
        return jsonify({'success': False, 'error': 'Falta el nombre del evento'}), 400
    if not data.get('event_date'):
        return jsonify({'success': False, 'error': 'Falta la fecha del evento'}), 400
    if not data.get('gifts'):
        return jsonify({'success': False, 'error': 'Selecciona al menos un regalo'}), 400

    for g in data['gifts']:
        if not g.get('imagen'):
            g['imagen'] = 'default.jpg'

    try:
        mesa_id = MesaRegalos.crear(_db(), data, _usuario_id())
        mesa = MesaRegalos.obtener_por_id(_db(), mesa_id)
        return jsonify({
            'success': True,
            'mesa_id': mesa_id,
            'slug':    mesa['slug'],
            'url':     url_for('web.ver_mesa_regalos', slug=mesa['slug'], _external=True),
        })
    except Exception as e:
        print(f"❌ Error creando mesa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ------------------------------------------------------------
# VER MESA (PÚBLICA)
# ------------------------------------------------------------
def ver_mesa(slug):
    mesa = MesaRegalos.obtener_por_slug(_db(), slug)
    if not mesa:
        abort(404)

    mesa = MesaRegalos.formatear_mesa(mesa)

    es_dueno = (
        session.get('usuario_id') and
        str(mesa.get('owner_id')) == str(_usuario_id())
    )

    return render_template(
        'tienda/mesa_regalos/ver.html',
        mesa=mesa,
        es_dueno=es_dueno,
    )


# ------------------------------------------------------------
# MIS MESAS
# ------------------------------------------------------------
def mis_mesas():
    if not session.get('nombre'):
        flash('Inicia sesión para ver tus mesas', 'warning')
        return redirect(url_for('web.login'))

    mesas_raw = MesaRegalos.obtener_por_owner(_db(), _usuario_id())
    mesas = [MesaRegalos.formatear_mesa(m) for m in mesas_raw]

    return render_template('tienda/mesa_regalos/mis_mesas.html', mesas=mesas)


# ------------------------------------------------------------
# RESERVAR REGALO
# ------------------------------------------------------------
def reservar_regalo(mesa_id):
    data = request.get_json() or {}
    gift_index = data.get('gift_index')
    nombre     = data.get('nombre', '').strip()
    email      = data.get('email', '').strip()

    if gift_index is None or not nombre:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400

    ok = MesaRegalos.reservar_regalo(_db(), mesa_id, int(gift_index), nombre, email)
    if ok:
        return jsonify({'success': True, 'message': '¡Gracias por tu regalo!'})
    return jsonify({'success': False, 'error': 'Este regalo ya fue reservado'}), 409


# ------------------------------------------------------------
# CONTRIBUIR AL FONDO
# ------------------------------------------------------------
def contribuir_fondo(mesa_id):
    data = request.get_json() or {}
    monto  = data.get('monto')
    nombre = data.get('nombre', '').strip()
    email  = data.get('email', '').strip()

    if not monto or float(monto) <= 0 or not nombre:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400

    ok = MesaRegalos.contribuir_efectivo(_db(), mesa_id, monto, nombre, email)
    if ok:
        return jsonify({'success': True, 'message': '¡Gracias por tu contribución!'})
    return jsonify({'success': False, 'error': 'No se pudo procesar'}), 500


# ------------------------------------------------------------
# ELIMINAR MESA
# ------------------------------------------------------------
def eliminar_mesa(mesa_id):
    if not session.get('nombre'):
        return jsonify({'success': False, 'error': 'No autorizado'}), 401

    ok = MesaRegalos.eliminar(_db(), mesa_id, _usuario_id())
    if ok:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'No se encontró la mesa'}), 404