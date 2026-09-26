# app/models/monedero_model.py
# ================================================================
# MONEDERO DIGITAL ORION - Réplica del monedero de Liverpool
# ================================================================

from app.config.database_config import db
from bson import ObjectId
from datetime import datetime, timezone
import random
import string


def _to_utc(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _generar_numero_tarjeta():
    """Genera un número tipo '8 7902 2814 3307' (16 dígitos agrupados)."""
    digitos = ''.join(random.choices(string.digits, k=16))
    return f"{digitos[0]} {digitos[1:5]} {digitos[5:9]} {digitos[9:13]}"


def _generar_cvv():
    return ''.join(random.choices(string.digits, k=3))


class Monedero:
    collection = db.monedero

    # ============================================================
    # CREAR / OBTENER
    # ============================================================

    @staticmethod
    def obtener_o_crear(usuario_id):
        if not usuario_id:
            return None

        uid = str(usuario_id)
        monedero = Monedero.collection.find_one({'usuario_id': uid})

        if monedero:
            return monedero

        ahora = datetime.now(timezone.utc)
        nuevo = {
            'usuario_id': uid,
            'saldo': 0.0,
            'numero_tarjeta': _generar_numero_tarjeta(),  # "8 7902 2814 3307"
            'cvv': _generar_cvv(),
            'saldo_pendiente_transferir': 0.0,            # saldo externo disponible
            'movimientos': [],
            'created_at': ahora,
            'updated_at': ahora,
        }

        result = Monedero.collection.insert_one(nuevo)
        nuevo['_id'] = result.inserted_id
        return nuevo

    @staticmethod
    def obtener_por_usuario(usuario_id):
        if not usuario_id:
            return None
        return Monedero.collection.find_one({'usuario_id': str(usuario_id)})

    # ============================================================
    # MOVIMIENTOS
    # ============================================================

    @staticmethod
    def _registrar_movimiento(usuario_id, tipo, monto, descripcion, referencia=None):
        movimiento = {
            'tipo': tipo,
            'monto': round(monto, 2),
            'descripcion': descripcion,
            'referencia': referencia or '',
            'fecha': datetime.now(timezone.utc),
        }
        Monedero.collection.update_one(
            {'usuario_id': str(usuario_id)},
            {
                '$push': {'movimientos': {'$each': [movimiento], '$position': 0, '$slice': 100}},
                '$set': {'updated_at': datetime.now(timezone.utc)}
            }
        )

    # ============================================================
    # TRANSFERIR SALDO (formulario del drawer)
    # ============================================================

    @staticmethod
    def transferir_saldo(usuario_id, monto, numero_serie, cvv):
        """
        Simula la transferencia de un monedero electrónico externo al monedero digital.
        Valida el número de serie (últimos 4 dígitos de la tarjeta) y el CVV.
        """
        if monto <= 0:
            return {'success': False, 'message': 'Monto inválido'}

        monedero = Monedero.obtener_o_crear(usuario_id)
        if not monedero:
            return {'success': False, 'message': 'Monedero no encontrado'}

        # Validar últimos 4 dígitos de la tarjeta
        numero_tarjeta = monedero.get('numero_tarjeta', '').replace(' ', '')
        ultimos_4 = numero_tarjeta[-4:] if len(numero_tarjeta) >= 4 else ''

        if str(numero_serie).strip() != ultimos_4:
            return {'success': False, 'message': 'Número de serie incorrecto'}

        if str(cvv).strip() != str(monedero.get('cvv', '')).strip():
            return {'success': False, 'message': 'CVV incorrecto'}

        # Acreditar
        Monedero.collection.update_one(
            {'usuario_id': str(usuario_id)},
            {
                '$inc': {'saldo': round(monto, 2)},
                '$set': {'updated_at': datetime.now(timezone.utc)}
            }
        )
        Monedero._registrar_movimiento(
            usuario_id, 'transferencia', monto,
            'Transferencia de saldo a mi monedero digital'
        )

        return {'success': True, 'message': f'Se transfirieron ${monto:.2f} a tu monedero'}

    # ============================================================
    # RECARGAR (para demo rápido)
    # ============================================================

    @staticmethod
    def recargar(usuario_id, monto, descripcion='Recarga de saldo'):
        if monto <= 0:
            return {'success': False, 'message': 'Monto inválido'}

        Monedero.obtener_o_crear(usuario_id)
        Monedero.collection.update_one(
            {'usuario_id': str(usuario_id)},
            {
                '$inc': {'saldo': round(monto, 2)},
                '$set': {'updated_at': datetime.now(timezone.utc)}
            }
        )
        Monedero._registrar_movimiento(usuario_id, 'recarga', monto, descripcion)

        return {'success': True, 'message': f'Se agregaron ${monto:.2f}'}

    # ============================================================
    # CASHBACK (opcional: integrado con checkout)
    # ============================================================

    CASHBACK_POR_NIVEL = {
        'Bronce':   0.01,
        'Plata':    0.02,
        'Oro':      0.04,
        'Diamante': 0.07,
    }

    @staticmethod
    def aplicar_cashback(usuario_id, monto_compra, nivel_cliente, pedido_id=None):
        if monto_compra <= 0:
            return 0

        porcentaje = Monedero.CASHBACK_POR_NIVEL.get(nivel_cliente, 0.01)
        cashback = round(monto_compra * porcentaje, 2)

        Monedero.obtener_o_crear(usuario_id)
        Monedero.collection.update_one(
            {'usuario_id': str(usuario_id)},
            {
                '$inc': {'saldo': cashback},
                '$set': {'updated_at': datetime.now(timezone.utc)}
            }
        )
        Monedero._registrar_movimiento(
            usuario_id, 'cashback', cashback,
            f'Cashback {int(porcentaje * 100)}% por compra',
            referencia=pedido_id
        )
        return cashback

    # ============================================================
    # RESUMEN
    # ============================================================

    @staticmethod
    def obtener_resumen(usuario_id):
        monedero = Monedero.obtener_o_crear(usuario_id)
        if not monedero:
            return None

        return {
            'saldo': round(monedero.get('saldo', 0), 2),
            'numero_tarjeta': monedero.get('numero_tarjeta', ''),
            'cvv': monedero.get('cvv', ''),
            'movimientos': monedero.get('movimientos', [])[:30],
        }