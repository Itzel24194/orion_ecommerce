# app/controllers/monedero_controller.py
# ================================================================
# CONTROLADOR DEL MONEDERO DIGITAL ORION
# ================================================================

from flask import (
    render_template, jsonify, request, session,
    redirect, url_for, flash, current_app
)
from bson import ObjectId
from datetime import datetime

from app.models.monedero_model import Monedero


def _get_usuario_actual():
    if 'user_id' not in session:
        return None
    try:
        db = current_app.db
        return db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception:
        return None


def _serializar_fechas(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serializar_fechas(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serializar_fechas(v) for v in obj]
    return obj


# ================================================================
# VISTA PRINCIPAL
# ================================================================

def mi_monedero():
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Inicia sesión para ver tu monedero', 'warning')
        return redirect(url_for('web.login'))

    resumen = Monedero.obtener_resumen(usuario['_id'])
    if not resumen:
        flash('Error cargando tu monedero', 'danger')
        return redirect(url_for('web.perfil'))

    return render_template(
        'tienda/monedero.html',
        usuario=usuario,
        resumen=resumen,
    )


# ================================================================
# API
# ================================================================

def api_resumen():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    resumen = Monedero.obtener_resumen(usuario['_id'])
    if not resumen:
        return jsonify({'success': False, 'error': 'Monedero no encontrado'}), 404

    resumen = _serializar_fechas(resumen)
    return jsonify({'success': True, **resumen})


def api_transferir():
    """Recibe {monto, numero_serie, cvv} del drawer 'Transferir saldo'."""
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}

    try:
        monto = float(data.get('monto', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    numero_serie = str(data.get('numero_serie', '')).strip()
    cvv = str(data.get('cvv', '')).strip()

    if not numero_serie or not cvv:
        return jsonify({'success': False, 'error': 'Completa todos los campos'}), 400

    resultado = Monedero.transferir_saldo(
        usuario_id=usuario['_id'],
        monto=monto,
        numero_serie=numero_serie,
        cvv=cvv
    )
    return jsonify(resultado)


def api_recargar():
    """Solo para demo, sin validación de serie/cvv."""
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get('monto', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    if monto <= 0 or monto > 50000:
        return jsonify({'success': False, 'error': 'Monto fuera de rango'}), 400

    resultado = Monedero.recargar(usuario['_id'], monto)
    return jsonify(resultado)


def api_movimientos():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    monedero = Monedero.obtener_por_usuario(usuario['_id'])
    if not monedero:
        return jsonify({'success': True, 'movimientos': []})

    movimientos = _serializar_fechas(monedero.get('movimientos', [])[:50])
    return jsonify({'success': True, 'movimientos': movimientos})