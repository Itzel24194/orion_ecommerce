from datetime import datetime
from bson import ObjectId


class ProbadorVirtual:

    @staticmethod
    def crear_sesion(db, data):
        data["created_at"] = datetime.utcnow()
        data["updated_at"] = datetime.utcnow()

        resultado = db.probadores_virtuales.insert_one(data)

        return str(resultado.inserted_id)

    @staticmethod
    def obtener_por_id(db, probador_id):

        try:
            return db.probadores_virtuales.find_one({
                "_id": ObjectId(probador_id)
            })
        except Exception:
            return None

    @staticmethod
    def actualizar(db, probador_id, data):

        data["updated_at"] = datetime.utcnow()

        resultado = db.probadores_virtuales.update_one(
            {"_id": ObjectId(probador_id)},
            {"$set": data}
        )

        return resultado.modified_count > 0

    @staticmethod
    def eliminar(db, probador_id):

        try:
            resultado = db.probadores_virtuales.delete_one({
                "_id": ObjectId(probador_id)
            })

            return resultado.deleted_count > 0

        except Exception:
            return False