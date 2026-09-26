# app/models/auditoria_model.py
# ================================================================
# MODELO DE AUDITORÍA DE ACCESOS
# Registra todas las acciones sobre conversaciones de chat.
# ================================================================

from app.config.database_config import db
from datetime import datetime, timezone
from bson import ObjectId


class AuditoriaChat:
    collection = db.auditoria_chat

    # Tipos de acciones
    ACCIONES = {
        'ver_conversacion': 'Ver conversación',
        'enviar_mensaje': 'Enviar mensaje',
        'archivar': 'Archivar conversación',
        'reactivar': 'Reactivar conversación',
        'eliminar': 'Eliminar conversación',
        'exportar': 'Exportar historial',
        'previsualizar_retencion': 'Previsualizar retención',
        'ejecutar_retencion': 'Ejecutar retención',
        'entrenar_nlp': 'Entrenar modelo NLP',
        'anonimizar': 'Anonimizar conversación'
    }

    @staticmethod
    def registrar(usuario_id, usuario_nombre, accion, session_id=None,
                  detalles=None, ip=None, user_agent=None):
        """
        Registra una acción de auditoría.
        """
        try:
            registro = {
                "usuario_id": str(usuario_id) if usuario_id else None,
                "usuario_nombre": usuario_nombre or 'Anónimo',
                "accion": accion,
                "accion_label": AuditoriaChat.ACCIONES.get(accion, accion),
                "session_id": str(session_id) if session_id else None,
                "detalles": detalles or {},
                "ip": ip,
                "user_agent": user_agent,
                "fecha": datetime.now(timezone.utc)
            }
            result = AuditoriaChat.collection.insert_one(registro)
            return str(result.inserted_id)
        except Exception as e:
            print(f"[Auditoria] Error registrando: {e}")
            return None

    @staticmethod
    def listar(filtros=None, limite=100):
        """
        Lista registros de auditoría con filtros opcionales.
        Filtros posibles: usuario_id, session_id, accion, desde, hasta
        """
        filtros = filtros or {}
        query = {}

        if filtros.get('usuario_id'):
            query['usuario_id'] = str(filtros['usuario_id'])
        if filtros.get('session_id'):
            query['session_id'] = str(filtros['session_id'])
        if filtros.get('accion'):
            query['accion'] = filtros['accion']
        if filtros.get('desde') or filtros.get('hasta'):
            query['fecha'] = {}
            if filtros.get('desde'):
                query['fecha']['$gte'] = filtros['desde']
            if filtros.get('hasta'):
                query['fecha']['$lte'] = filtros['hasta']

        try:
            registros = list(
                AuditoriaChat.collection.find(query)
                .sort("fecha", -1)
                .limit(limite)
            )
            # Serializar
            for r in registros:
                r['_id'] = str(r['_id'])
                if r.get('fecha'):
                    r['fecha'] = r['fecha'].isoformat()
            return registros
        except Exception as e:
            print(f"[Auditoria] Error listando: {e}")
            return []

    @staticmethod
    def estadisticas():
        """Estadísticas de auditoría por acción."""
        pipeline = [
            {"$group": {"_id": "$accion", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}}
        ]
        try:
            return list(AuditoriaChat.collection.aggregate(pipeline))
        except Exception as e:
            print(f"[Auditoria] Error estadísticas: {e}")
            return []

    @staticmethod
    def limpiar_antiguos(dias=180):
        """Elimina registros de auditoría con más de X días."""
        from datetime import timedelta
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        try:
            result = AuditoriaChat.collection.delete_many({"fecha": {"$lt": limite}})
            return result.deleted_count
        except Exception as e:
            print(f"[Auditoria] Error limpiando: {e}")
            return 0