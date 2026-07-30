# app/models/combo_model.py
from app.config.database_config import db
from bson import ObjectId
from datetime import datetime

class Combo:
    collection = db.combos

    @staticmethod
    def crear(data):
        data['fecha_creacion'] = datetime.now()
        result = Combo.collection.insert_one(data)
        return str(result.inserted_id)

    @staticmethod
    def obtener_por_id(id):
        try:
            return Combo.collection.find_one({'_id': ObjectId(id)})
        except:
            return None

    @staticmethod
    def obtener_todos(filtro=None):
        if filtro is None:
            filtro = {}
        try:
            return list(Combo.collection.find(filtro).sort('fecha_creacion', -1))
        except:
            return []

    @staticmethod
    def actualizar(id, data):
        data['fecha_actualizacion'] = datetime.now()
        try:
            result = Combo.collection.update_one(
                {'_id': ObjectId(id)},
                {'$set': data}
            )
            return result.modified_count > 0
        except:
            return False

    @staticmethod
    def eliminar(id):
        try:
            result = Combo.collection.delete_one({'_id': ObjectId(id)})
            return result.deleted_count > 0
        except:
            return False