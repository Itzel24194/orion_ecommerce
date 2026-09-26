# app/models/chat_model.py
# ================================================================
# MODELO DE CHAT ESTILO LIVERPOOL
# - No se cierran conversaciones: solo se archivan
# - El cliente siempre retoma su hilo activo
# - Se archivan automáticamente por inactividad (30 días)
# - Se anonimizan automáticamente a los 180 días
# - Se eliminan automáticamente a los 365 días (retención)
# ================================================================

from app.config.database_config import db
from bson import ObjectId
from datetime import datetime, timezone, timedelta


class Chat:
    collection = db.chats

    # Días de inactividad antes de archivar una conversación
    DIAS_PARA_ARCHIVAR = 30

    # Días antes de anonimizar una conversación archivada
    DIAS_PARA_ANONIMIZAR = 180

    # Días que se conservan las archivadas antes de eliminarlas
    DIAS_RETENCION_ARCHIVADAS = 365

    # ============================================================
    # CREAR SESIÓN
    # ============================================================

    @staticmethod
    def crear_sesion(usuario_id, nombre_usuario="Cliente"):
        """Crea una nueva conversación activa."""
        session = {
            "usuario_id": str(usuario_id) if usuario_id else None,
            "nombre_usuario": nombre_usuario,
            "estado": "activo",  # 'activo' | 'archivada'
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "mensajes": [],
            "anonimizada": False
        }
        result = Chat.collection.insert_one(session)
        return str(result.inserted_id)

    # ============================================================
    # OBTENER SESIÓN ACTIVA
    # ============================================================

    @staticmethod
    def obtener_sesion_activa(usuario_id):
        """Busca la conversación ACTIVA del usuario."""
        if not usuario_id:
            return None
        return Chat.collection.find_one(
            {"usuario_id": str(usuario_id), "estado": "activo"},
            sort=[("updated_at", -1)]
        )

    @staticmethod
    def obtener_o_crear_sesion(usuario_id, nombre_usuario="Cliente"):
        """Estilo Liverpool: reutiliza la activa, o crea una nueva."""
        session = Chat.obtener_sesion_activa(usuario_id)
        if not session:
            session_id = Chat.crear_sesion(usuario_id, nombre_usuario)
            return Chat.obtener_por_id(session_id)
        return session

    @staticmethod
    def forzar_nueva_sesion(usuario_id, nombre_usuario="Cliente"):
        """Fuerza una sesión nueva archivando la anterior."""
        activa = Chat.obtener_sesion_activa(usuario_id)
        if activa:
            Chat.archivar_sesion(str(activa["_id"]))
        session_id = Chat.crear_sesion(usuario_id, nombre_usuario)
        return Chat.obtener_por_id(session_id)

    # ============================================================
    # OBTENER POR ID
    # ============================================================

    @staticmethod
    def obtener_por_id(session_id):
        if not session_id or not ObjectId.is_valid(session_id):
            return None
        return Chat.collection.find_one({"_id": ObjectId(session_id)})

    @staticmethod
    def obtener_sesion_completa(session_id):
        """Devuelve la sesión completa (con todos los mensajes) para exportar."""
        sesion = Chat.obtener_por_id(session_id)
        if not sesion:
            return None
        mensajes = sesion.get('mensajes', [])
        mensajes.sort(key=lambda x: Chat._normalizar_fecha(x.get("fecha")))
        sesion['mensajes'] = mensajes
        return sesion

    # ============================================================
    # AGREGAR MENSAJE
    # ============================================================

    @staticmethod
    def agregar_mensaje(session_id, mensaje, es_admin=False, es_ia=False):
        if not session_id or not ObjectId.is_valid(session_id):
            return False

        mensaje_data = {
            "texto": mensaje,
            "es_admin": es_admin,
            "es_ia": es_ia,
            "fecha": datetime.now(timezone.utc)
        }

        result = Chat.collection.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$push": {"mensajes": mensaje_data},
                "$set": {
                    "updated_at": datetime.now(timezone.utc),
                    "estado": "activo"  # reactiva si estaba archivada
                }
            }
        )
        return result.modified_count > 0

    # ============================================================
    # NORMALIZACIÓN DE FECHAS
    # ============================================================

    @staticmethod
    def _normalizar_fecha(fecha):
        """Convierte cualquier fecha a datetime AWARE en UTC."""
        if fecha is None:
            return datetime.now(timezone.utc)

        if isinstance(fecha, str):
            try:
                fecha_limpia = fecha.replace('Z', '+00:00')
                dt = datetime.fromisoformat(fecha_limpia)
            except Exception:
                return datetime.now(timezone.utc)
        elif isinstance(fecha, datetime):
            dt = fecha
        else:
            return datetime.now(timezone.utc)

        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    # ============================================================
    # OBTENER MENSAJES
    # ============================================================

    @staticmethod
    def obtener_mensajes(session_id, desde_fecha=None, limite=50):
        session = Chat.obtener_por_id(session_id)
        if not session:
            return []

        mensajes = session.get("mensajes", [])

        if desde_fecha:
            try:
                desde = Chat._normalizar_fecha(desde_fecha)
                mensajes = [
                    m for m in mensajes
                    if Chat._normalizar_fecha(m.get("fecha")) >= desde
                ]
            except Exception as e:
                print(f"[Chat] Error filtrando mensajes por fecha: {e}")

        mensajes.sort(key=lambda x: Chat._normalizar_fecha(x.get("fecha")))
        return mensajes[-limite:]

    # ============================================================
    # ARCHIVAR / REACTIVAR
    # ============================================================

    @staticmethod
    def archivar_sesion(session_id):
        if not session_id or not ObjectId.is_valid(session_id):
            return False
        result = Chat.collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "estado": "archivada",
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        return result.modified_count > 0

    @staticmethod
    def reactivar_sesion(session_id):
        if not session_id or not ObjectId.is_valid(session_id):
            return False
        result = Chat.collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "estado": "activo",
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        return result.modified_count > 0

    @staticmethod
    def cerrar_sesion(session_id):
        return Chat.archivar_sesion(session_id)

    # ============================================================
    # ARCHIVADO AUTOMÁTICO POR INACTIVIDAD
    # ============================================================

    @staticmethod
    def archivar_sesiones_inactivas(dias=None):
        """Archiva conversaciones sin actividad en los últimos X días."""
        if dias is None:
            dias = Chat.DIAS_PARA_ARCHIVAR

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        result = Chat.collection.update_many(
            {"estado": "activo", "updated_at": {"$lt": limite}},
            {"$set": {"estado": "archivada"}}
        )
        return result.modified_count

    # ============================================================
    # POLÍTICA DE RETENCIÓN
    # ============================================================

    @staticmethod
    def eliminar_sesiones_archivadas(dias=None):
        """Elimina permanentemente las archivadas con más de X días."""
        if dias is None:
            dias = Chat.DIAS_RETENCION_ARCHIVADAS

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        total_a_eliminar = Chat.collection.count_documents({
            "estado": "archivada",
            "updated_at": {"$lt": limite}
        })

        if total_a_eliminar == 0:
            print(f"[Chat] Retención: no hay conversaciones archivadas con más de {dias} días.")
            return 0

        result = Chat.collection.delete_many({
            "estado": "archivada",
            "updated_at": {"$lt": limite}
        })

        print(f"[Chat] Retención: {result.deleted_count} conversaciones eliminadas "
              f"(más de {dias} días sin actividad).")
        return result.deleted_count

    @staticmethod
    def previsualizar_retencion(dias=None):
        """Devuelve cuántas conversaciones se eliminarían."""
        if dias is None:
            dias = Chat.DIAS_RETENCION_ARCHIVADAS

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        total = Chat.collection.count_documents({
            "estado": "archivada",
            "updated_at": {"$lt": limite}
        })

        return {
            "dias_retencion": dias,
            "limite_fecha": limite.isoformat(),
            "total_a_eliminar": total
        }

    # ============================================================
    # ANONIMIZACIÓN
    # ============================================================

    @staticmethod
    def anonimizar_sesion(session_id):
        """Anonimiza los datos personales de una conversación."""
        if not session_id or not ObjectId.is_valid(session_id):
            return False
        try:
            result = Chat.collection.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {
                    "nombre_usuario": "Cliente Anónimo",
                    "email": "anonimo@orion.com",
                    "anonimizada": True,
                    "fecha_anonimizacion": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[Chat] Error anonimizando: {e}")
            return False

    @staticmethod
    def anonimizar_sesiones_inactivas(dias=None):
        """Anonimiza automáticamente las archivadas con más de X días."""
        if dias is None:
            dias = Chat.DIAS_PARA_ANONIMIZAR

        limite = datetime.now(timezone.utc) - timedelta(days=dias)

        try:
            result = Chat.collection.update_many(
                {
                    "estado": "archivada",
                    "anonimizada": {"$ne": True},
                    "updated_at": {"$lt": limite}
                },
                {"$set": {
                    "nombre_usuario": "Cliente Anónimo",
                    "email": "anonimo@orion.com",
                    "anonimizada": True,
                    "fecha_anonimizacion": datetime.now(timezone.utc)
                }}
            )
            return result.modified_count
        except Exception as e:
            print(f"[Chat] Error anonimizando inactivas: {e}")
            return 0

    @staticmethod
    def previsualizar_anonimizacion(dias=None):
        """Devuelve cuántas conversaciones se anonimizarían."""
        if dias is None:
            dias = Chat.DIAS_PARA_ANONIMIZAR

        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        total = Chat.collection.count_documents({
            "estado": "archivada",
            "anonimizada": {"$ne": True},
            "updated_at": {"$lt": limite}
        })

        return {
            "dias_anonimizacion": dias,
            "limite_fecha": limite.isoformat(),
            "total_a_anonimizar": total
        }

    # ============================================================
    # LISTADOS PARA EL PANEL ADMIN
    # ============================================================

    @staticmethod
    def obtener_sesiones_activas():
        return list(
            Chat.collection.find({"estado": "activo"}).sort("updated_at", -1)
        )

    @staticmethod
    def obtener_sesiones_archivadas(limite=50):
        return list(
            Chat.collection.find({"estado": "archivada"})
            .sort("updated_at", -1)
            .limit(limite)
        )

    @staticmethod
    def obtener_todas_sesiones(limite=50):
        return list(
            Chat.collection.find()
            .sort("updated_at", -1)
            .limit(limite)
        )

    # ============================================================
    # CONTADORES Y ESTADOS
    # ============================================================

    @staticmethod
    def contar_no_leidos(session_id):
        session = Chat.obtener_por_id(session_id)
        if not session:
            return 0

        mensajes = session.get("mensajes", [])
        if not mensajes:
            return 0

        no_leidos = 0
        for m in reversed(mensajes):
            if m.get("es_admin", False):
                break
            no_leidos += 1
        return no_leidos

    @staticmethod
    def marcar_como_visto(session_id):
        pass

    # ============================================================
    # ESTADÍSTICAS
    # ============================================================

    @staticmethod
    def estadisticas():
        total_activas = Chat.collection.count_documents({"estado": "activo"})
        total_archivadas = Chat.collection.count_documents({"estado": "archivada"})
        total_anonimizadas = Chat.collection.count_documents({"anonimizada": True})
        total = Chat.collection.count_documents({})

        return {
            "total": total,
            "activas": total_activas,
            "archivadas": total_archivadas,
            "anonimizadas": total_anonimizadas,
            "dias_retencion": Chat.DIAS_RETENCION_ARCHIVADAS,
            "dias_anonimizacion": Chat.DIAS_PARA_ANONIMIZAR,
            "dias_para_archivar": Chat.DIAS_PARA_ARCHIVAR
        }

    @staticmethod
    def buscar_sesiones_por_nombre(texto, limite=20):
        if not texto:
            return []
        return list(
            Chat.collection.find({
                "nombre_usuario": {"$regex": texto, "$options": "i"}
            })
            .sort("updated_at", -1)
            .limit(limite)
        )