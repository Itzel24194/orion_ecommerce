# app/models/monedero_admin_model.py
# ================================================================
# MODELO ADMIN — MONEDERO DIGITAL ORION
# Misma colección `monedero` que el cliente, misma estructura.
# UTC aware, respeta config, sincroniza caché usuarios.monedero_saldo.
# ================================================================

from datetime import datetime, timezone, timedelta
from bson import ObjectId
from flask import current_app

from app.models.monedero_utils import (
    COL_MONEDERO, COL_CONFIG, uid_filtro, buscar_usuario,
    leer_config, sincronizar_cache,
    nuevo_movimiento, serializar_fechas, ahora_utc, safe_oid,
)


class MonederoAdmin:
    COLECCION = COL_MONEDERO
    COLECCION_CONFIG = COL_CONFIG

    # ---------- Helpers ----------

    @staticmethod
    def _col():
        return current_app.db[MonederoAdmin.COLECCION]

    @staticmethod
    def _col_config():
        return current_app.db[MonederoAdmin.COLECCION_CONFIG]

    @staticmethod
    def _uid_filtro(usuario_id):
        return uid_filtro(usuario_id)

    @staticmethod
    def _buscar_usuario(db, usuario_id):
        return buscar_usuario(usuario_id)

    # ============================================================
    # ESTADÍSTICAS GLOBALES
    # ============================================================
    @staticmethod
    def estadisticas_globales():
        col = MonederoAdmin._col()

        total_monederos = col.count_documents({})
        bloqueados = col.count_documents({'bloqueado': True})

        agg = list(col.aggregate([
            {'$group': {
                '_id': None,
                'total': {'$sum': '$saldo'},
                'maximo': {'$max': '$saldo'},
            }}
        ]))
        saldo_total = float(agg[0]['total']) if agg else 0.0
        saldo_maximo = float(agg[0].get('maximo') or 0) if agg else 0.0
        saldo_promedio = (saldo_total / total_monederos) if total_monederos else 0.0

        hoy_ini = ahora_utc().replace(hour=0, minute=0, second=0, microsecond=0)
        agg_hoy = list(col.aggregate([
            {'$unwind': '$movimientos'},
            {'$match': {'movimientos.fecha': {'$gte': hoy_ini}}},
            {'$count': 'n'},
        ]))
        movimientos_hoy = int(agg_hoy[0]['n']) if agg_hoy else 0

        return {
            'total_monederos': total_monederos,
            'bloqueados': bloqueados,
            'saldo_total': round(saldo_total, 2),
            'saldo_promedio': round(saldo_promedio, 2),
            'saldo_maximo': round(saldo_maximo, 2),
            'movimientos_hoy': movimientos_hoy,
        }

    # ============================================================
    # GRÁFICO
    # ============================================================
    @staticmethod
    def datos_grafico_movimientos(dias=30):
        col = MonederoAdmin._col()
        desde = ahora_utc() - timedelta(days=dias)

        pipeline = [
            {'$unwind': '$movimientos'},
            {'$match': {'movimientos.fecha': {'$gte': desde}}},
            {'$group': {
                '_id': {
                    'anio': {'$year': '$movimientos.fecha'},
                    'mes': {'$month': '$movimientos.fecha'},
                    'dia': {'$dayOfMonth': '$movimientos.fecha'},
                },
                'abonos': {'$sum': {'$cond': [{'$gt': ['$movimientos.monto', 0]}, '$movimientos.monto', 0]}},
                'cargos': {'$sum': {'$cond': [{'$lt': ['$movimientos.monto', 0]}, {'$abs': '$movimientos.monto'}, 0]}},
            }},
            {'$sort': {'_id.anio': 1, '_id.mes': 1, '_id.dia': 1}},
        ]
        resultados = list(col.aggregate(pipeline))

        etiquetas, abonos, cargos = [], [], []
        for r in resultados:
            etiquetas.append(f"{r['_id']['anio']}-{r['_id']['mes']:02d}-{r['_id']['dia']:02d}")
            abonos.append(round(float(r.get('abonos') or 0), 2))
            cargos.append(round(float(r.get('cargos') or 0), 2))

        saldo_acumulado = []
        acumulado = 0.0
        for a, c in zip(abonos, cargos):
            acumulado += (a - c)
            saldo_acumulado.append(round(acumulado, 2))

        return {
            'etiquetas': etiquetas,
            'abonos': abonos,
            'cargos': cargos,
            'saldo_acumulado': saldo_acumulado,
        }

    # ============================================================
    # LISTADO / BÚSQUEDA
    # ============================================================
    @staticmethod
    def listar_todos(limite=25, skip=0):
        col = MonederoAdmin._col()
        db = current_app.db
        docs = list(col.find({}).sort('updated_at', -1).skip(skip).limit(limite))

        salida = []
        for m in docs:
            u = MonederoAdmin._buscar_usuario(db, m.get('usuario_id'))
            movs = m.get('movimientos') or []
            salida.append({
                '_id': str(m.get('_id')),
                'usuario_id': str(m.get('usuario_id') or ''),
                'nombre': (u or {}).get('nombre', 'Sin nombre'),
                'email': (u or {}).get('email', ''),
                'saldo': float(m.get('saldo') or 0),
                'numero_tarjeta': m.get('numero_tarjeta', ''),
                'bloqueado': bool(m.get('bloqueado', False)),
                'motivo_bloqueo': m.get('motivo_bloqueo'),
                'total_movimientos': len(movs),
                'updated_at': serializar_fechas(m.get('updated_at')),
            })
        return salida

    @staticmethod
    def contar_todos():
        return MonederoAdmin._col().count_documents({})

    @staticmethod
    def buscar_por_email_o_nombre(q):
        db = current_app.db
        col = MonederoAdmin._col()
        regex = {'$regex': q, '$options': 'i'}
        usuarios = list(db.usuarios.find({'$or': [{'email': regex}, {'nombre': regex}]}).limit(200))

        resultados = []
        for u in usuarios:
            m = col.find_one(MonederoAdmin._uid_filtro(u['_id']))
            if not m:
                continue
            movs = m.get('movimientos') or []
            resultados.append({
                '_id': str(m.get('_id')),
                'usuario_id': str(m.get('usuario_id') or ''),
                'nombre': u.get('nombre', 'Sin nombre'),
                'email': u.get('email', ''),
                'saldo': float(m.get('saldo') or 0),
                'numero_tarjeta': m.get('numero_tarjeta', ''),
                'bloqueado': bool(m.get('bloqueado', False)),
                'motivo_bloqueo': m.get('motivo_bloqueo'),
                'total_movimientos': len(movs),
                'updated_at': serializar_fechas(m.get('updated_at')),
            })
        return resultados

    # ============================================================
    # DETALLE
    # ============================================================
    @staticmethod
    def obtener_detalle_admin(usuario_id):
        db = current_app.db
        col = MonederoAdmin._col()
        m = col.find_one(MonederoAdmin._uid_filtro(usuario_id))
        if not m:
            return None
        u = MonederoAdmin._buscar_usuario(db, m.get('usuario_id'))

        movimientos = m.get('movimientos') or []
        try:
            movimientos = sorted(
                movimientos,
                key=lambda x: x.get('fecha') if isinstance(x.get('fecha'), datetime) else datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )[:100]
        except Exception:
            pass

        return {
            'monedero_id': str(m.get('_id')),
            'usuario_id': str(m.get('usuario_id') or ''),
            'usuario': {
                'nombre': (u or {}).get('nombre', 'Sin nombre'),
                'email': (u or {}).get('email', ''),
                'rol': (u or {}).get('rol', 'cliente'),
            },
            'saldo': float(m.get('saldo') or 0),
            'numero_tarjeta': m.get('numero_tarjeta', ''),
            'cvv': m.get('cvv', ''),
            'bloqueado': bool(m.get('bloqueado', False)),
            'motivo_bloqueo': m.get('motivo_bloqueo'),
            'movimientos': serializar_fechas(movimientos),
            'total_movimientos': len(m.get('movimientos') or []),
            'created_at': serializar_fechas(m.get('created_at')),
            'updated_at': serializar_fechas(m.get('updated_at')),
        }

    # ============================================================
    # AJUSTAR SALDO
    # ============================================================
    @staticmethod
    def ajustar_saldo(usuario_id, monto, motivo, admin_id):
        col = MonederoAdmin._col()
        m = col.find_one(MonederoAdmin._uid_filtro(usuario_id))
        if not m:
            return {'success': False, 'error': 'Monedero no encontrado'}

        try:
            monto = float(monto)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'Monto inválido'}

        if monto == 0:
            return {'success': False, 'error': 'El monto no puede ser cero'}

        motivo = (motivo or '').strip()
        if not motivo:
            return {'success': False, 'error': 'El motivo es obligatorio'}

        saldo_anterior = float(m.get('saldo') or 0)
        saldo_nuevo = saldo_anterior + monto

        if saldo_nuevo < 0:
            return {'success': False, 'error': 'El saldo no puede quedar negativo'}

        cfg = leer_config()
        if saldo_nuevo > cfg['saldo_maximo']:
            return {
                'success': False,
                'error': f'El saldo máximo permitido es ${cfg["saldo_maximo"]:.2f}',
            }

        mov = nuevo_movimiento(
            tipo='ajuste_admin',
            monto=monto,
            saldo_anterior=saldo_anterior,
            saldo_nuevo=saldo_nuevo,
            descripcion=f'Ajuste admin: {motivo}',
            admin_id=admin_id,
            motivo=motivo,
        )

        col.update_one(
            {'_id': m['_id']},
            {
                '$set': {'saldo': round(saldo_nuevo, 2), 'updated_at': ahora_utc()},
                '$push': {'movimientos': {'$each': [mov], '$position': 0}},
            },
        )

        sincronizar_cache(usuario_id, saldo_nuevo)

        return {
            'success': True,
            'saldo_nuevo': saldo_nuevo,
            'mensaje': f'Ajuste aplicado: ${monto:+.2f}',
        }

    # ============================================================
    # BLOQUEAR / DESBLOQUEAR
    # ============================================================
    @staticmethod
    def bloquear(usuario_id, motivo):
        ahora = ahora_utc()
        res = MonederoAdmin._col().update_one(
            MonederoAdmin._uid_filtro(usuario_id),
            {'$set': {'bloqueado': True, 'motivo_bloqueo': motivo, 'updated_at': ahora}},
        )
        if res.matched_count == 0:
            return {'success': False, 'error': 'Monedero no encontrado'}
        return {'success': True, 'mensaje': 'Monedero bloqueado'}

    @staticmethod
    def desbloquear(usuario_id):
        ahora = ahora_utc()
        res = MonederoAdmin._col().update_one(
            MonederoAdmin._uid_filtro(usuario_id),
            {'$set': {'bloqueado': False, 'motivo_bloqueo': None, 'updated_at': ahora}},
        )
        if res.matched_count == 0:
            return {'success': False, 'error': 'Monedero no encontrado'}
        return {'success': True, 'mensaje': 'Monedero desbloqueado'}

    # ============================================================
    # CONFIG
    # ============================================================
    @staticmethod
    def obtener_config():
        return leer_config()

    @staticmethod
    def guardar_config(config):
        MonederoAdmin._col_config().update_one(
            {'_id': 'global'}, {'$set': config}, upsert=True
        )
        return True

    # ============================================================
    # CSV
    # ============================================================
    @staticmethod
    def exportar_csv():
        db = current_app.db
        filas = []
        for m in MonederoAdmin._col().find({}):
            u = MonederoAdmin._buscar_usuario(db, m.get('usuario_id'))
            filas.append({
                'usuario_id': str(m.get('usuario_id') or ''),
                'nombre': (u or {}).get('nombre', ''),
                'email': (u or {}).get('email', ''),
                'saldo': float(m.get('saldo') or 0),
                'numero_tarjeta': m.get('numero_tarjeta', ''),
                'bloqueado': 'Sí' if m.get('bloqueado') else 'No',
                'motivo_bloqueo': m.get('motivo_bloqueo') or '',
                'total_movimientos': len(m.get('movimientos') or []),
                'creado': serializar_fechas(m.get('created_at')) or '',
                'actualizado': serializar_fechas(m.get('updated_at')) or '',
            })
        return filas