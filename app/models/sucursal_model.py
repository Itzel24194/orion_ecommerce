# app/models/sucursal_model.py
from bson.objectid import ObjectId
from app.config.database_config import db
from datetime import datetime, timezone

class Sucursal:
    collection = db['sucursales']
    
    @staticmethod
    def crear(data):
        sucursal = {
            "nombre": data.get('nombre'),
            "codigo": data.get('codigo'),
            "direccion": {
                "calle": data.get('calle', ''),
                "numero": data.get('numero', ''),
                "colonia": data.get('colonia', ''),
                "cp": data.get('cp', ''),
                "ciudad": data.get('ciudad', ''),
                "estado": data.get('estado', ''),
                "pais": data.get('pais', 'México'),
                "coordenadas": data.get('coordenadas', {})
            },
            "telefono": data.get('telefono', ''),
            "email": data.get('email', ''),
            "horario": data.get('horario', {}),
            "encargado_id": data.get('encargado_id'),
            "empleados": data.get('empleados', []),
            "estado": data.get('estado', 'activo'),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        return Sucursal.collection.insert_one(sucursal)
    
    @staticmethod
    def obtener_por_id(id):
        try:
            return Sucursal.collection.find_one({"_id": ObjectId(id)})
        except:
            return None
    
    @staticmethod
    def obtener_todas():
        return list(Sucursal.collection.find())
    
    @staticmethod
    def obtener_activas():
        return list(Sucursal.collection.find({"estado": "activo"}))
    
    @staticmethod
    def actualizar(id, data):
        data['updated_at'] = datetime.now(timezone.utc)
        return Sucursal.collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": data}
        )
    
    @staticmethod
    def eliminar(id):
        return Sucursal.collection.delete_one({"_id": ObjectId(id)})
    
    @staticmethod
    def asignar_encargado(sucursal_id, usuario_id):
        return Sucursal.collection.update_one(
            {"_id": ObjectId(sucursal_id)},
            {"$set": {"encargado_id": usuario_id, "updated_at": datetime.now(timezone.utc)}}
        )
    
    @staticmethod
    def agregar_empleado(sucursal_id, usuario_id):
        return Sucursal.collection.update_one(
            {"_id": ObjectId(sucursal_id)},
            {"$addToSet": {"empleados": usuario_id}, "$set": {"updated_at": datetime.now(timezone.utc)}}
        )
    
    @staticmethod
    def remover_empleado(sucursal_id, usuario_id):
        return Sucursal.collection.update_one(
            {"_id": ObjectId(sucursal_id)},
            {"$pull": {"empleados": usuario_id}, "$set": {"updated_at": datetime.now(timezone.utc)}}
        )