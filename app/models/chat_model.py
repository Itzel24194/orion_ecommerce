# app/models/chat_model.py
from app.config.database_config import db
from bson import ObjectId
from datetime import datetime, timezone

class Chat:
    collection = db.chats

    @staticmethod
    def crear_sesion(usuario_id, nombre_usuario="Cliente"):
        session = {
            "usuario_id": str(usuario_id) if usuario_id else None,
            "nombre_usuario": nombre_usuario,
            "estado": "activo",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "mensajes": []
        }
        result = Chat.collection.insert_one(session)
        return str(result.inserted_id)

    @staticmethod
    def obtener_sesion_activa(usuario_id):
        if not usuario_id:
            return None
        return Chat.collection.find_one({
            "usuario_id": str(usuario_id),
            "estado": "activo"
        })

    @staticmethod
    def obtener_o_crear_sesion(usuario_id, nombre_usuario="Cliente"):
        session = Chat.obtener_sesion_activa(usuario_id)
        if not session:
            session_id = Chat.crear_sesion(usuario_id, nombre_usuario)
            return Chat.obtener_por_id(session_id)
        return session

    @staticmethod
    def obtener_por_id(session_id):
        if not ObjectId.is_valid(session_id):
            return None
        return Chat.collection.find_one({"_id": ObjectId(session_id)})

    @staticmethod
    def agregar_mensaje(session_id, mensaje, es_admin=False):
        if not ObjectId.is_valid(session_id):
            return False
        mensaje_data = {
            "texto": mensaje,
            "es_admin": es_admin,
            "fecha": datetime.now(timezone.utc)
        }
        result = Chat.collection.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$push": {"mensajes": mensaje_data},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0

    @staticmethod
    def obtener_mensajes(session_id, desde_fecha=None, limite=50):
        session = Chat.obtener_por_id(session_id)
        if not session:
            return []
        mensajes = session.get("mensajes", [])
        if desde_fecha:
            try:
                desde = datetime.fromisoformat(desde_fecha)
                mensajes = [m for m in mensajes if m.get("fecha", datetime.now()) >= desde]
            except:
                pass
        mensajes.sort(key=lambda x: x.get("fecha", datetime.now()))
        return mensajes[-limite:]

    @staticmethod
    def cerrar_sesion(session_id):
        if not ObjectId.is_valid(session_id):
            return False
        result = Chat.collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"estado": "cerrado", "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    @staticmethod
    def obtener_sesiones_activas():
        return list(Chat.collection.find({"estado": "activo"}).sort("updated_at", -1))

    @staticmethod
    def obtener_todas_sesiones(limite=50):
        return list(Chat.collection.find().sort("updated_at", -1).limit(limite))

    @staticmethod
    def contar_no_leidos(session_id):
        session = Chat.obtener_por_id(session_id)
        if not session:
            return 0
        mensajes = session.get("mensajes", [])
        if mensajes and not mensajes[-1].get("es_admin", False):
            return 1
        return 0

    @staticmethod
    def marcar_como_visto(session_id):
        pass  # No almacenamos estado de "visto" por simplicidad