# ================================================================
# app/controllers/temporadas_controller.py
# Controlador de Temporadas — con campos extendidos
# ================================================================
from flask import render_template, request, redirect, url_for, flash
from app.models.temporada_model import Temporada
from datetime import datetime


# ================================================================
# HELPERS
# ================================================================

def _parse_fecha(s):
    """Convierte 'YYYY-MM-DD' a datetime. Devuelve None si es inválida."""
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def _payload_from_request():
    """Extrae todos los campos del form (soporta los nuevos)."""
    return {
        'nombre':       (request.form.get('nombre') or '').strip(),
        'descripcion':  (request.form.get('descripcion') or '').strip(),
        'imagen':       (request.form.get('imagen') or '').strip(),
        'color':        (request.form.get('color') or '#7C3AED').strip(),
        'destacada':    request.form.get('destacada') == 'on',
        'fecha_inicio': request.form.get('fecha_inicio'),
        'fecha_fin':    request.form.get('fecha_fin'),
        'activa':       request.form.get('activa') == 'on',
    }


def _validar(payload):
    """Devuelve (ok, mensaje_error, payload_procesado)."""
    if not payload['nombre'] or not payload['fecha_inicio'] or not payload['fecha_fin']:
        return False, 'Todos los campos son obligatorios', None

    fi = _parse_fecha(payload['fecha_inicio'])
    ff = _parse_fecha(payload['fecha_fin'])

    if not fi or not ff:
        return False, 'Formato de fecha inválido', None

    if fi > ff:
        return False, 'La fecha de inicio no puede ser mayor que la fecha de fin', None

    payload['fecha_inicio'] = fi
    payload['fecha_fin'] = ff
    return True, None, payload


# ================================================================
# VISTAS
# ================================================================

def listar_temporadas():
    temporadas = Temporada.obtener_todas()

    from app.models.productos_model import Producto
    productos_por_temporada = {}
    for temp in temporadas:
        count = len(Producto.obtener_por_temporada(str(temp['_id'])))
        productos_por_temporada[str(temp['_id'])] = count

    stats = Temporada.estadisticas()

    return render_template(
        'admin/temporadas.html',
        temporadas=temporadas,
        productos_por_temporada=productos_por_temporada,
        stats=stats,
    )


def crear_temporada():
    if request.method != 'POST':
        return redirect(url_for('web.listar_temporadas'))

    payload = _payload_from_request()
    ok, err, payload = _validar(payload)

    if not ok:
        flash(err, 'danger')
        return redirect(url_for('web.listar_temporadas'))

    # Evitar duplicados por nombre
    if Temporada.buscar_por_nombre(payload['nombre']):
        flash(f"Ya existe una temporada llamada '{payload['nombre']}'", 'danger')
        return redirect(url_for('web.listar_temporadas'))

    Temporada.crear(payload)
    flash('Temporada creada exitosamente', 'success')
    return redirect(url_for('web.listar_temporadas'))


def editar_temporada(id):
    if request.method != 'POST':
        return redirect(url_for('web.listar_temporadas'))

    temporada = Temporada.obtener_por_id(id)
    if not temporada:
        flash('Temporada no encontrada', 'danger')
        return redirect(url_for('web.listar_temporadas'))

    payload = _payload_from_request()
    ok, err, payload = _validar(payload)

    if not ok:
        flash(err, 'danger')
        return redirect(url_for('web.listar_temporadas'))

    Temporada.actualizar(id, payload)
    flash('Temporada actualizada exitosamente', 'success')
    return redirect(url_for('web.listar_temporadas'))


def eliminar_temporada(id):
    from app.models.productos_model import Producto
    productos = Producto.obtener_por_temporada(id)

    if productos and len(productos) > 0:
        flash(f'No se puede eliminar la temporada porque tiene {len(productos)} productos asociados.', 'danger')
        return redirect(url_for('web.listar_temporadas'))

    if Temporada.eliminar(id):
        flash('Temporada eliminada correctamente', 'success')
    else:
        flash('Error al eliminar la temporada', 'danger')

    return redirect(url_for('web.listar_temporadas'))