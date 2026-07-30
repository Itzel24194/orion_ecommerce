from bson.objectid import ObjectId
from app.config.database_config import db

empresas_col = db['empresas']

class Empresa:
    @staticmethod
    def obtener_todas():
        return list(empresas_col.find())

    @staticmethod
    def obtener_por_id(empresa_id):
        return empresas_col.find_one({"_id": ObjectId(empresa_id)})

    @staticmethod
    def actualizar_resultados_impi(empresa_id, resultados):
        empresas_col.update_one(
            {"_id": ObjectId(empresa_id)},
            {"$set": {"datos_impi": resultados}}
        )

    @staticmethod
    def crear(data):
        return empresas_col.insert_one(data)

    @staticmethod
    def actualizar_datos(empresa_id, data):
        empresas_col.update_one({"_id": ObjectId(empresa_id)}, {"$set": data})

    @staticmethod
    def actualizar_con_notas(empresa_id, nuevo_status, notas):
        empresas_col.update_one(
            {"_id": ObjectId(empresa_id)}, 
            {"$set": {"status": nuevo_status, "notas_admin": notas}}
        )

    @staticmethod
    def borrar(empresa_id):
        empresas_col.delete_one({"_id": ObjectId(empresa_id)})