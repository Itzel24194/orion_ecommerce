from app.config.database_config import db
from bson import ObjectId
from bson.errors import InvalidId

class Marketing:
    @staticmethod
    def obtener_todo(coleccion):
        """Retorna todos los documentos de una colección, ordenados por prioridad si aplica."""
        # Si es la colección de cupones, podríamos querer ordenarlos por prioridad
        if coleccion == 'cupones':
            return list(db[coleccion].find().sort("prioridad", -1))
        return list(db[coleccion].find())

    @staticmethod
    def guardar(coleccion, data):
        """Inserta un nuevo documento en la colección."""
        return db[coleccion].insert_one(data)

    @staticmethod
    def actualizar(coleccion, id, data):
        """Actualiza un documento mediante su ID."""
        try:
            return db[coleccion].update_one({"_id": ObjectId(id)}, {"$set": data})
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def borrar(coleccion, id):
        """Elimina un documento mediante su ID."""
        try:
            return db[coleccion].delete_one({"_id": ObjectId(id)})
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def buscar_por_codigo(codigo):
        """Busca un cupón específico por su código string."""
        return db.cupones.find_one({"codigo": codigo})

    @staticmethod
    def incrementar_uso_cupon(id):
        """Incrementa el contador de usos de forma atómica."""
        try:
            return db.cupones.update_one(
                {"_id": ObjectId(id)}, 
                {"$inc": {"usos_actuales": 1}}
            )
        except (InvalidId, TypeError):
            return None