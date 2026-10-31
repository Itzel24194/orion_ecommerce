# ================================================================
# app/models/temporada_model.py
# Modelo de Temporadas - MongoDB
# Usa current_app.db (igual que el resto de tus modelos)
# ================================================================
from flask import current_app
from bson import ObjectId
from datetime import datetime


class Temporada:
    COLLECTION = 'temporadas'

    @staticmethod
    def _col():
        return current_app.db[Temporada.COLLECTION]

    # ============================================================
    # LECTURA
    # ============================================================

    @staticmethod
    def obtener_todas(filtros=None):
        filtros = filtros or {}
        q = {}
        if 'activa' in filtros:
            q['activa'] = bool(filtros['activa'])
        if 'destacada' in filtros:
            q['destacada'] = bool(filtros['destacada'])

        cursor = Temporada._col().find(q).sort([('fecha_inicio', -1), ('nombre', 1)])
        return [Temporada._serialize(t) for t in cursor]

    @staticmethod
    def obtener_por_id(temp_id):
        try:
            doc = Temporada._col().find_one({'_id': ObjectId(temp_id)})
        except Exception:
            return None
        return Temporada._serialize(doc) if doc else None

    @staticmethod
    def obtener_activa():
        """Devuelve la temporada vigente hoy (activa y dentro de fechas)."""
        hoy = datetime.utcnow()
        doc = Temporada._col().find_one({
            'activa': True,
            'fecha_inicio': {'$lte': hoy},
            'fecha_fin': {'$gte': hoy},
        })
        return Temporada._serialize(doc) if doc else None

    # ============================================================
    # ESCRITURA
    # ============================================================

    @staticmethod
    def crear(data):
        data.setdefault('descripcion', '')
        data.setdefault('imagen', '')
        data.setdefault('color', '#7C3AED')
        data.setdefault('destacada', False)
        data.setdefault('activa', True)
        data['created_at'] = datetime.utcnow()
        data['updated_at'] = datetime.utcnow()
        res = Temporada._col().insert_one(data)
        return str(res.inserted_id)

    @staticmethod
    def actualizar(temp_id, data):
        try:
            data['updated_at'] = datetime.utcnow()
            Temporada._col().update_one(
                {'_id': ObjectId(temp_id)},
                {'$set': data}
            )
            return True
        except Exception:
            return False

    @staticmethod
    def eliminar(temp_id):
        try:
            res = Temporada._col().delete_one({'_id': ObjectId(temp_id)})
            return res.deleted_count > 0
        except Exception:
            return False

    # ============================================================
    # UTILIDADES
    # ============================================================

    @staticmethod
    def buscar_por_nombre(nombre):
        return Temporada._col().find_one({
            'nombre': {'$regex': f'^{nombre}$', '$options': 'i'}
        })

    @staticmethod
    def estadisticas():
        col = Temporada._col()
        return {
            'total': col.count_documents({}),
            'activas': col.count_documents({'activa': True}),
            'inactivas': col.count_documents({'activa': False}),
            'destacadas': col.count_documents({'destacada': True}),
        }

    @staticmethod
    def _serialize(doc):
        if not doc:
            return None
        out = dict(doc)
        out['_id'] = str(out['_id'])
        out['descripcion'] = out.get('descripcion', '') or ''
        out['imagen'] = out.get('imagen', '') or ''
        out['color'] = out.get('color', '#7C3AED') or '#7C3AED'
        out['destacada'] = bool(out.get('destacada', False))
        out['activa'] = out.get('activa', True) is not False
        return out