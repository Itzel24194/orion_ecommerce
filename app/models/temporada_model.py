from app.config.database_config import db
from bson import ObjectId
from datetime import datetime

class Temporada:
    """Modelo para gestionar temporadas (ej. Verano, Navidad, Rebajas)"""

    @staticmethod
    def obtener_todas():
        """Obtener todas las temporadas"""
        return list(db.temporadas.find().sort("fecha_inicio", -1))

    @staticmethod
    def obtener_activas():
        """Obtener temporadas activas (activa=True)"""
        return list(db.temporadas.find({"activa": True}))

    @staticmethod
    def obtener_por_id(id):
        """Obtener una temporada por ID"""
        try:
            return db.temporadas.find_one({"_id": ObjectId(id)})
        except:
            return None

    @staticmethod
    def crear(data):
        """Crear una nueva temporada"""
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()
        if 'activa' not in data:
            data['activa'] = True
        return db.temporadas.insert_one(data)

    @staticmethod
    def actualizar(id, data):
        """Actualizar una temporada existente"""
        data['updated_at'] = datetime.now()
        try:
            return db.temporadas.update_one(
                {"_id": ObjectId(id)},
                {"$set": data}
            )
        except:
            return None

    @staticmethod
    def eliminar(id):
        """Eliminar una temporada por ID"""
        try:
            result = db.temporadas.delete_one({"_id": ObjectId(id)})
            return result.deleted_count > 0
        except:
            return False

    @staticmethod
    def obtener_por_fecha(fecha=None):
        """Obtener temporadas vigentes en una fecha (por defecto hoy)"""
        if fecha is None:
            fecha = datetime.now().date()
        if isinstance(fecha, datetime):
            fecha_dt = fecha
        else:
            fecha_dt = datetime.combine(fecha, datetime.min.time())
        
        return list(db.temporadas.find({
            "fecha_inicio": {"$lte": fecha_dt},
            "fecha_fin": {"$gte": fecha_dt},
            "activa": True
        }))