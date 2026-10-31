# app/controllers/monedero_controller.py
# ================================================================

from flask import (
    render_template, jsonify, request, session,
    redirect, url_for, flash, current_app
)
from bson import ObjectId
from datetime import datetime, timezone
import secrets

COL_MONEDERO = 'monedero'
COL_MOVS = 'monedero_movimientos'


def _get_usuario_actual():
    if 'user_id' not in session:
        return None
    try:
        return current_app.db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
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


def _safe_oid(val):
    try:
        return ObjectId(str(val))
    except Exception:
        return None


def _monedero_doc(usuario, crear_si_falta=True):
    if not usuario:
        return None
    db = current_app.db
    uid = usuario['_id']
    uid_str = str(uid)

    try:
        doc = db[COL_MONEDERO].find_one({'usuario_id': uid_str})
        if doc: return doc
        doc = db[COL_MONEDERO].find_one({'usuario_id': uid})
        if doc: return doc
    except Exception:
        return None

    if not crear_si_falta:
        return None

    numero = '**** **** **** ' + f'{secrets.randbelow(10000):04d}'
    cvv = f'{secrets.randbelow(1000):03d}'

    nuevo = {
        'usuario_id': uid_str,
        'saldo': 0.0,
        'numero_tarjeta': numero,
        'cvv': cvv,
        'bloqueado': False,
        'motivo_bloqueo': None,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    try:
        db[COL_MONEDERO].insert_one(nuevo)
        return nuevo
    except Exception:
        return None


def _sincronizar_cache(usuario_id, saldo):
    try:
        current_app.db.usuarios.update_one(
            {'_id': _safe_oid(usuario_id) or usuario_id},
            {'$set': {'monedero_saldo': float(saldo or 0)}}
        )
    except Exception:
        pass


def _registrar_movimiento(usuario_id, tipo, monto, saldo_nuevo,
                          descripcion='', referencia=None):
    try:
        current_app.db[COL_MOVS].insert_one({
            'usuario_id': str(usuario_id),
            'tipo': tipo,
            'monto': float(monto),
            'saldo_nuevo': float(saldo_nuevo),
            'descripcion': descripcion,
            'referencia': referencia,
            'fecha': datetime.now(timezone.utc),
        })
    except Exception:
        pass


def _leer_config():
    defaults = {
        'saldo_maximo': 50000.0,
        'saldo_minimo_recarga': 50.0,
        'recarga_maxima': 20000.0,
        'permitir_transferencias': True,
        'comision_transferencia': 0.0,
        'cashback_porcentaje': 0.0,
    }
    try:
        from app.models.monedero_admin_model import MonederoAdmin
        cfg = MonederoAdmin.obtener_config() or {}
        return {**defaults, **cfg}
    except Exception:
        return defaults


def _resumen(usuario):
    doc = _monedero_doc(usuario, crear_si_falta=True)
    if not doc:
        return None

    saldo = float(doc.get('saldo') or 0)
    _sincronizar_cache(usuario['_id'], saldo)

    uid_str = str(usuario['_id'])
    movs = []
    try:
        for m in current_app.db[COL_MOVS].find({'usuario_id': uid_str}).sort('fecha', -1).limit(50):
            fecha = m.get('fecha')
            movs.append({
                'tipo': m.get('tipo', ''),
                'monto': float(m.get('monto') or 0),
                'saldo_nuevo': float(m.get('saldo_nuevo') or 0),
                'descripcion': m.get('descripcion', ''),
                'referencia': m.get('referencia'),
                'fecha': fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha or ''),
            })
    except Exception:
        pass

    return {
        'saldo': float(saldo),
        'numero_tarjeta': doc.get('numero_tarjeta') or '—',
        'cvv': doc.get('cvv') or '—',
        'bloqueado': bool(doc.get('bloqueado', False)),
        'motivo_bloqueo': doc.get('motivo_bloqueo') or None,
        'total_movimientos': len(movs),
        'movimientos': movs,
        'created_at': _serializar_fechas(doc.get('created_at')),
        'updated_at': _serializar_fechas(doc.get('updated_at')),
    }


# ⭐ FUNCIÓN CORREGIDA: busca en 'mesas_regalos' (plural)
def _obtener_mesas_regalo(usuario):
    """
    Devuelve (mesas_regalo, bonificacion_total).
    Bonificación = 10% del fondo recaudado (fund_raised) de cada mesa activa.
    """
    mesas = []
    bonificacion_total = 0.0
    try:
        uid = usuario['_id']
        uid_str = str(uid)
        uid_obj = uid if isinstance(uid, ObjectId) else _safe_oid(uid_str)

        query = {
            '$or': [
                {'owner_id': uid_obj},
                {'owner_id': uid_str},
                {'usuario_id': uid_obj},
                {'usuario_id': uid_str},
            ]
        }

        # ✅ CORREGIDO: mesas_regalos (PLURAL)
        mesas = list(current_app.db.mesas_regalos.find(query))

        for mesa in mesas:
            if not mesa.get('activa', True):
                continue

            try:
                fondo = float(mesa.get('fund_raised') or 0)
            except (ValueError, TypeError):
                fondo = 0.0

            if fondo > 0:
                bonificacion_total += fondo * 0.10

    except Exception as e:
        print(f'[monedero] Error obteniendo mesas_regalo: {e}', flush=True)
        mesas = []
        bonificacion_total = 0.0

    return mesas, bonificacion_total


def mi_monedero():
    usuario = _get_usuario_actual()
    if not usuario:
        flash('Inicia sesión para ver tu monedero', 'warning')
        return redirect(url_for('web.login'))

    resumen = _resumen(usuario)
    if not resumen:
        flash('Error cargando tu monedero', 'danger')
        return redirect(url_for('web.perfil'))

    mesas_regalo, bonificacion_mesas = _obtener_mesas_regalo(usuario)

    return render_template(
        'tienda/monedero.html',
        usuario=usuario,
        resumen=resumen,
        mesas_regalo=mesas_regalo,
        bonificacion_mesas=bonificacion_mesas
    )


def api_resumen():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401
    resumen = _resumen(usuario)
    if not resumen:
        return jsonify({'success': False, 'error': 'No se pudo crear el monedero'}), 500

    _, bonificacion_mesas = _obtener_mesas_regalo(usuario)
    resumen['bonificacion_mesas'] = bonificacion_mesas
    resumen['saldo_con_bonificacion'] = float(resumen.get('saldo', 0)) + bonificacion_mesas

    return jsonify({'success': True, **resumen})


def api_recargar():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get('monto', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    if monto <= 0:
        return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400

    doc = _monedero_doc(usuario, crear_si_falta=True)
    if not doc:
        return jsonify({'success': False, 'error': 'No se pudo crear el monedero'}), 500

    if doc.get('bloqueado'):
        return jsonify({'success': False, 'error': 'Tu monedero está bloqueado.'}), 403

    cfg = _leer_config()
    if monto < cfg['saldo_minimo_recarga']:
        return jsonify({'success': False, 'error': f'La recarga mínima es ${cfg["saldo_minimo_recarga"]:.2f}'}), 400
    if monto > cfg['recarga_maxima']:
        return jsonify({'success': False, 'error': f'La recarga máxima por operación es ${cfg["recarga_maxima"]:.2f}'}), 400

    saldo_actual = float(doc.get('saldo') or 0)
    saldo_nuevo = saldo_actual + monto
    if saldo_nuevo > cfg['saldo_maximo']:
        return jsonify({'success': False, 'error': f'El saldo máximo permitido es ${cfg["saldo_maximo"]:.2f}'}), 400

    try:
        current_app.db[COL_MONEDERO].update_one(
            {'_id': doc['_id']},
            {'$set': {'saldo': saldo_nuevo, 'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'No se pudo actualizar: {e}'}), 500

    _registrar_movimiento(usuario['_id'], 'recarga', monto, saldo_nuevo, descripcion='Recarga con tarjeta')
    _sincronizar_cache(usuario['_id'], saldo_nuevo)

    return jsonify({'success': True, 'message': f'Recarga exitosa por ${monto:.2f}', 'saldo': saldo_nuevo})


def api_transferir():
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
    if len(numero_serie) != 4 or not numero_serie.isdigit():
        return jsonify({'success': False, 'error': 'Número de serie debe tener 4 dígitos'}), 400
    if len(cvv) != 3 or not cvv.isdigit():
        return jsonify({'success': False, 'error': 'CVV debe tener 3 dígitos'}), 400
    if monto <= 0:
        return jsonify({'success': False, 'error': 'El monto debe ser mayor a 0'}), 400

    doc = _monedero_doc(usuario, crear_si_falta=True)
    if not doc:
        return jsonify({'success': False, 'error': 'No se pudo crear el monedero'}), 500

    if doc.get('bloqueado'):
        return jsonify({'success': False, 'error': 'Tu monedero está bloqueado.'}), 403

    cfg = _leer_config()

    if not cfg['permitir_transferencias']:
        return jsonify({'success': False, 'error': 'Las transferencias están deshabilitadas.'}), 403

    saldo_actual = float(doc.get('saldo') or 0)

    if monto < cfg['saldo_minimo_recarga']:
        return jsonify({'success': False, 'error': f'La recarga mínima es ${cfg["saldo_minimo_recarga"]:.2f}'}), 400
    if monto > cfg['recarga_maxima']:
        return jsonify({'success': False, 'error': f'La recarga máxima por operación es ${cfg["recarga_maxima"]:.2f}'}), 400

    saldo_nuevo = saldo_actual + monto
    if saldo_nuevo > cfg['saldo_maximo']:
        return jsonify({'success': False, 'error': f'El saldo máximo permitido es ${cfg["saldo_maximo"]:.2f}'}), 400

    comision = 0.0
    if cfg['comision_transferencia'] > 0:
        comision = monto * (cfg['comision_transferencia'] / 100.0)
        saldo_nuevo = saldo_nuevo - comision

    try:
        current_app.db[COL_MONEDERO].update_one(
            {'_id': doc['_id']},
            {'$set': {'saldo': saldo_nuevo, 'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'No se pudo actualizar: {e}'}), 500

    _registrar_movimiento(
        usuario['_id'], 'transferencia_recibida', monto, saldo_actual + monto,
        descripcion=f'Recarga desde tarjeta externa ••{numero_serie}'
    )
    if comision > 0:
        _registrar_movimiento(
            usuario['_id'], 'comision_transferencia', -comision, saldo_nuevo,
            descripcion=f'Comisión {cfg["comision_transferencia"]}% sobre transferencia'
        )

    _sincronizar_cache(usuario['_id'], saldo_nuevo)

    mensaje = f'Transferencia exitosa por ${monto:.2f}'
    if comision > 0:
        mensaje += f' (comisión: ${comision:.2f})'

    return jsonify({
        'success': True,
        'message': mensaje,
        'saldo': saldo_nuevo,
        'comision': comision,
    })


def api_movimientos():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    uid_str = str(usuario['_id'])
    movs = []
    try:
        for m in current_app.db[COL_MOVS].find({'usuario_id': uid_str}).sort('fecha', -1).limit(50):
            fecha = m.get('fecha')
            movs.append({
                'tipo': m.get('tipo', ''),
                'monto': float(m.get('monto') or 0),
                'saldo_nuevo': float(m.get('saldo_nuevo') or 0),
                'descripcion': m.get('descripcion', ''),
                'referencia': m.get('referencia'),
                'fecha': fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha or ''),
            })
    except Exception:
        pass

    return jsonify({'success': True, 'movimientos': movs})


def api_pagar_con_monedero():
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get('monto', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    referencia = (data.get('referencia') or '').strip() or None

    if monto <= 0:
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    doc = _monedero_doc(usuario, crear_si_falta=True)
    if not doc:
        return jsonify({'success': False, 'error': 'No se pudo crear el monedero'}), 500

    if doc.get('bloqueado'):
        return jsonify({'success': False, 'error': 'Tu monedero está bloqueado.'}), 403

    saldo_actual = float(doc.get('saldo') or 0)
    if saldo_actual < monto:
        return jsonify({'success': False, 'error': 'Saldo insuficiente en el monedero', 'saldo': saldo_actual}), 402

    saldo_nuevo = saldo_actual - monto

    try:
        current_app.db[COL_MONEDERO].update_one(
            {'_id': doc['_id']},
            {'$set': {'saldo': saldo_nuevo, 'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'No se pudo actualizar: {e}'}), 500

    _registrar_movimiento(
        usuario['_id'], 'compra', -monto, saldo_nuevo,
        descripcion=f'Pago con monedero{(" · " + referencia) if referencia else ""}',
        referencia=referencia,
    )
    _sincronizar_cache(usuario['_id'], saldo_nuevo)

    return jsonify({'success': True, 'message': f'Pago realizado por ${monto:.2f}', 'saldo': saldo_nuevo})