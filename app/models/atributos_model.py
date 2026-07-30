from bson.objectid import ObjectId
from app.config.database_config import db

atributos_col = db['atributos']

class Atributo:
    @staticmethod
    def obtener_todos():
        return list(atributos_col.find())

    @staticmethod
    def crear(data):
        # Convertimos la cadena de valores en una lista limpia
        if 'valores' in data and isinstance(data['valores'], str):
            data['valores'] = [v.strip() for v in data['valores'].split(',')]
        return atributos_col.insert_one(data)

    @staticmethod
    def actualizar(id, data):
        if 'valores' in data and isinstance(data['valores'], str):
            data['valores'] = [v.strip() for v in data['valores'].split(',')]
        return atributos_col.update_one({"_id": ObjectId(id)}, {"$set": data})

    @staticmethod
    def borrar(id):
        return atributos_col.delete_one({"_id": ObjectId(id)})