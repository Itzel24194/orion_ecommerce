# app/models/monedero_model.py
# ================================================================
# MONEDERO DIGITAL ORION — CLIENTE
# Fuente única de verdad: colección `monedero`
# ================================================================

from bson import ObjectId
from datetime import datetime, timezone
import random
import string

from app.models.monedero_utils import (
    COL_MONEDERO, uid_filtro, buscar_usuario,
    leer_config, sincronizar_cache,
    nuevo_movimiento, serializar_fechas,
    ahora_utc, safe_oid,
)

try:
    from flask import current_app
except Exception:
    current_app = None


def _col():
    return current_app.db[COL_MONEDERO]


def _generar_numero_tarjeta():
    digitos = ''.join(random.choices(string.digits, k=16))
    return f"{digitos[0]} {digitos[1:5]} {digitos[5:9]} {digitos[9:13]}"


def _generar_cvv():
    return ''.join(random.choices(string.digits, k=3))


def _serializar_fechas(obj):
    return serializar_fechas(obj)


class Monedero:

    @staticmethod
    def obtener_o_crear(usuario_id):
        if not usuario_id:
            return None

        uid_str = str(usuario_id)
        col = _col()

        doc = col.find_one(uid_filtro(uid_str))
        if doc:
            return doc

        usuario = buscar_usuario(uid_str)
        if usuario:
            doc = col.find_one({'usuario_id': usuario['_id']})
            if doc:
                return doc

        ahora = ahora_utc()
        nuevo = {
            'usuario_id': uid_str,
            'saldo': 0.0,
            'numero_tarjeta': _generar_numero_tarjeta(),
            'cvv': _generar_cvv(),
            'saldo_pendiente_transferir': 0.0,
            'bloqueado': False,
            'motivo_bloqueo': None,
            'movimientos': [],
            'created_at': ahora,
            'updated_at': ahora,
        }
        try:
            result = col.insert_one(nuevo)
            nuevo['_id'] = result.inserted_id
            sincronizar_cache(uid_str, 0.0)
            return nuevo
        except Exception:
            return None

    @staticmethod
    def obtener_por_usuario(usuario_id):
        if not usuario_id:
            return None
        return _col().find_one(uid_filtro(str(usuario_id)))

    @staticmethod
    def _push_movimiento(doc, movimiento, saldo_nuevo):
        _col().update_one(
            {'_id': doc['_id']},
            {
                '$set': {
                    'saldo': round(float(saldo_nuevo), 2),
                    'updated_at': ahora_utc(),
                },
                '$push': {
                    'movimientos': {'$each': [movimiento], '$position': 0}
                },
            }
        )

    @staticmethod
    def transferir_saldo(usuario_id, monto, numero_serie, cvv):
        try:
            monto = float(monto)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Monto inválido'}

        if monto <= 0:
            return {'success': False, 'message': 'El monto debe ser mayor a 0'}

        numero_serie = str(numero_serie or '').strip()
        cvv = str(cvv or '').strip()

        if len(numero_serie) != 4 or not numero_serie.isdigit():
            return {'success': False, 'message': 'Número de serie debe tener 4 dígitos'}
        if len(cvv) != 3 or not cvv.isdigit():
            return {'success': False, 'message': 'CVV debe tener 3 dígitos'}

        doc = Monedero.obtener_o_crear(usuario_id)
        if not doc:
            return {'success': False, 'message': 'No se pudo crear el monedero'}

        if doc.get('bloqueado'):
            return {'success': False, 'message': 'Tu monedero está bloqueado. Contacta a soporte.'}

        cfg = leer_config()

        if not cfg['permitir_transferencias']:
            return {'success': False, 'message': 'Las transferencias están deshabilitadas.'}

        # ⭐ NO se valida numero_serie ni cvv contra la tarjeta virtual.
        # Son datos de la tarjeta externa del banco.

        saldo_actual = float(doc.get('saldo') or 0)

        if monto < cfg['saldo_minimo_recarga']:
            return {'success': False, 'message': f'La recarga mínima es ${cfg["saldo_minimo_recarga"]:.2f}'}
        if monto > cfg['recarga_maxima']:
            return {'success': False, 'message': f'La recarga máxima por operación es ${cfg["recarga_maxima"]:.2f}'}
        if saldo_actual + monto > cfg['saldo_maximo']:
            return {'success': False, 'message': f'El saldo máximo permitido es ${cfg["saldo_maximo"]:.2f}'}

        comision = monto * (cfg['comision_transferencia'] / 100.0)
        saldo_nuevo = saldo_actual + monto - comision

        mov = nuevo_movimiento(
            tipo='transferencia',
            monto=monto,
            saldo_anterior=saldo_actual,
            saldo_nuevo=saldo_nuevo,
            descripcion=f'Recarga desde tarjeta externa ••{numero_serie}',
        )
        Monedero._push_movimiento(doc, mov, saldo_nuevo)

        if comision > 0:
            mov_c = nuevo_movimiento(
                tipo='comision_transferencia',
                monto=-comision,
                saldo_anterior=saldo_nuevo,
                saldo_nuevo=saldo_nuevo,
                descripcion=f'Comisión {cfg["comision_transferencia"]}% por transferencia',
            )
            Monedero._push_movimiento(doc, mov_c, saldo_nuevo)

        sincronizar_cache(usuario_id, saldo_nuevo)

        msg = f'Se transfirieron ${monto:.2f} a tu monedero'
        if comision > 0:
            msg += f' (comisión: ${comision:.2f})'

        return {'success': True, 'message': msg, 'saldo': saldo_nuevo, 'comision': comision}

    @staticmethod
    def recargar(usuario_id, monto, descripcion='Recarga de saldo'):
        try:
            monto = float(monto)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Monto inválido'}

        if monto <= 0:
            return {'success': False, 'message': 'El monto debe ser mayor a 0'}

        doc = Monedero.obtener_o_crear(usuario_id)
        if not doc:
            return {'success': False, 'message': 'No se pudo crear el monedero'}

        if doc.get('bloqueado'):
            return {'success': False, 'message': 'Tu monedero está bloqueado. Contacta a soporte.'}

        cfg = leer_config()

        if monto < cfg['saldo_minimo_recarga']:
            return {'success': False, 'message': f'La recarga mínima es ${cfg["saldo_minimo_recarga"]:.2f}'}
        if monto > cfg['recarga_maxima']:
            return {'success': False, 'message': f'La recarga máxima por operación es ${cfg["recarga_maxima"]:.2f}'}

        saldo_actual = float(doc.get('saldo') or 0)
        saldo_nuevo = saldo_actual + monto

        if saldo_nuevo > cfg['saldo_maximo']:
            return {'success': False, 'message': f'El saldo máximo permitido es ${cfg["saldo_maximo"]:.2f}'}

        mov = nuevo_movimiento(
            tipo='recarga',
            monto=monto,
            saldo_anterior=saldo_actual,
            saldo_nuevo=saldo_nuevo,
            descripcion=descripcion,
        )
        Monedero._push_movimiento(doc, mov, saldo_nuevo)
        sincronizar_cache(usuario_id, saldo_nuevo)

        return {'success': True, 'message': f'Se agregaron ${monto:.2f}', 'saldo': saldo_nuevo}

    @staticmethod
    def pagar(usuario_id, monto, descripcion='Pago con monedero', referencia=''):
        try:
            monto = float(monto)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Monto inválido'}

        if monto <= 0:
            return {'success': False, 'message': 'Monto inválido'}

        doc = Monedero.obtener_o_crear(usuario_id)
        if not doc:
            return {'success': False, 'message': 'No se pudo crear el monedero'}

        if doc.get('bloqueado'):
            return {'success': False, 'message': 'Tu monedero está bloqueado. Contacta a soporte.'}

        saldo_actual = float(doc.get('saldo') or 0)
        if saldo_actual < monto:
            return {'success': False, 'message': 'Saldo insuficiente en el monedero', 'saldo': saldo_actual}

        saldo_nuevo = saldo_actual - monto

        mov = nuevo_movimiento(
            tipo='compra',
            monto=-monto,
            saldo_anterior=saldo_actual,
            saldo_nuevo=saldo_nuevo,
            descripcion=descripcion,
            referencia=referencia,
        )
        Monedero._push_movimiento(doc, mov, saldo_nuevo)
        sincronizar_cache(usuario_id, saldo_nuevo)

        return {'success': True, 'message': f'Pago realizado por ${monto:.2f}', 'saldo': saldo_nuevo}

    CASHBACK_POR_NIVEL = {
        'Bronce':   0.01,
        'Plata':    0.02,
        'Oro':      0.04,
        'Diamante': 0.07,
    }

    @staticmethod
    def aplicar_cashback(usuario_id, monto_compra, nivel_cliente, pedido_id=None):
        try:
            monto_compra = float(monto_compra)
        except (TypeError, ValueError):
            return 0.0

        if monto_compra <= 0:
            return 0.0

        porcentaje = Monedero.CASHBACK_POR_NIVEL.get(nivel_cliente, 0.01)
        cashback = round(monto_compra * porcentaje, 2)
        if cashback <= 0:
            return 0.0

        doc = Monedero.obtener_o_crear(usuario_id)
        if not doc or doc.get('bloqueado'):
            return 0.0

        cfg = leer_config()
        saldo_actual = float(doc.get('saldo') or 0)

        if saldo_actual + cashback > cfg['saldo_maximo']:
            cashback = max(0.0, cfg['saldo_maximo'] - saldo_actual)
            if cashback <= 0:
                return 0.0

        saldo_nuevo = saldo_actual + cashback

        mov = nuevo_movimiento(
            tipo='cashback',
            monto=cashback,
            saldo_anterior=saldo_actual,
            saldo_nuevo=saldo_nuevo,
            descripcion=f'Cashback {int(porcentaje * 100)}% por compra',
            referencia=pedido_id,
        )
        Monedero._push_movimiento(doc, mov, saldo_nuevo)
        sincronizar_cache(usuario_id, saldo_nuevo)

        return cashback

    @staticmethod
    def obtener_resumen(usuario_id):
        doc = Monedero.obtener_o_crear(usuario_id)
        if not doc:
            return None

        movs = doc.get('movimientos') or []
        try:
            movs = sorted(
                movs,
                key=lambda x: x.get('fecha') if isinstance(x.get('fecha'), datetime) else datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
        except Exception:
            pass

        return {
            'saldo': round(float(doc.get('saldo') or 0), 2),
            'numero_tarjeta': doc.get('numero_tarjeta') or '',
            'cvv': doc.get('cvv') or '',
            'bloqueado': bool(doc.get('bloqueado', False)),
            'motivo_bloqueo': doc.get('motivo_bloqueo'),
            'movimientos': serializar_fechas(movs[:50]),
        }