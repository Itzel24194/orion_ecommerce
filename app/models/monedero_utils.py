# app/models/monedero_utils.py
# ================================================================
# Helpers compartidos por Monedero (cliente) y MonederoAdmin
# ================================================================

from datetime import datetime, timezone
from bson import ObjectId
from flask import current_app

COL_MONEDERO = 'monedero'
COL_CONFIG = 'monedero_config'


def ahora_utc():
    return datetime.now(timezone.utc)


def safe_oid(val):
    try:
        return ObjectId(str(val))
    except Exception:
        return None


def uid_filtro(usuario_id):
    """Filtro que acepta usuario_id como str u ObjectId."""
    opciones = [{'usuario_id': str(usuario_id)}]
    oid = safe_oid(usuario_id)
    if oid:
        opciones.append({'usuario_id': oid})
    return {'$or': opciones}


def get_db():
    return current_app.db


def buscar_usuario(usuario_id):
    try:
        return get_db().usuarios.find_one({'_id': safe_oid(usuario_id)})
    except Exception:
        return None


def config_default():
    return {
        'saldo_maximo': 50000.0,
        'saldo_minimo_recarga': 50.0,
        'recarga_maxima': 20000.0,
        'permitir_transferencias': True,
        'comision_transferencia': 0.0,
        'cashback_porcentaje': 0.0,
    }


def leer_config():
    defaults = config_default()
    try:
        doc = get_db()[COL_CONFIG].find_one({'_id': 'global'})
        if doc:
            doc.pop('_id', None)
            defaults.update(doc)
    except Exception:
        pass
    return defaults


def sincronizar_cache(usuario_id, saldo):
    try:
        get_db().usuarios.update_one(
            {'_id': safe_oid(usuario_id)},
            {'$set': {'monedero_saldo': float(saldo or 0)}}
        )
    except Exception:
        pass


def nuevo_movimiento(tipo, monto, saldo_anterior, saldo_nuevo,
                     descripcion='', referencia='', admin_id=None, motivo=None):
    mov = {
        'tipo': tipo,
        'monto': round(float(monto), 2),
        'descripcion': descripcion,
        'referencia': referencia or '',
        'fecha': ahora_utc(),
        'saldo_anterior': round(float(saldo_anterior), 2),
        'saldo_nuevo': round(float(saldo_nuevo), 2),
    }
    if admin_id is not None:
        mov['admin_id'] = str(admin_id)
    if motivo is not None:
        mov['motivo'] = motivo
    return mov


def serializar_fechas(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serializar_fechas(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serializar_fechas(v) for v in obj]
    return obj