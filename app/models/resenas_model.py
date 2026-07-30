# app/models/resenas_model.py
from app.config.database_config import db
from bson import ObjectId
from datetime import datetime
import os
from flask import current_app

class Resena:
    @staticmethod
    def crear(data):
        """Crear una nueva reseña"""
        if 'producto_id' in data and not isinstance(data['producto_id'], ObjectId):
            data['producto_id'] = ObjectId(data['producto_id'])
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow()
        if 'updated_at' not in data:
            data['updated_at'] = datetime.utcnow()
        if 'votos_utiles' not in data:
            data['votos_utiles'] = []
        if 'reportes' not in data:
            data['reportes'] = 0
        # CAMPOS DE ADMIN (MODERACIÓN)
        if 'estado' not in data:
            data['estado'] = 'pendiente'  # pendiente, aprobado, rechazado
        if 'respuesta_admin' not in data:
            data['respuesta_admin'] = None
        if 'fecha_respuesta' not in data:
            data['fecha_respuesta'] = None
        return db.resenas.insert_one(data)

    @staticmethod
    def obtener_por_producto(producto_id):
        """Obtener todas las reseñas de un producto (solo aprobadas)"""
        try:
            query = {
                "producto_id": ObjectId(producto_id),
                "estado": "aprobado"
            }
            return list(db.resenas.find(query).sort('created_at', -1))
        except:
            return []

    @staticmethod
    def obtener_por_producto_admin(producto_id):
        """Obtener todas las reseñas de un producto (sin filtrar estado)"""
        try:
            return list(db.resenas.find({"producto_id": ObjectId(producto_id)}).sort('created_at', -1))
        except:
            return []

    @staticmethod
    def obtener_por_id(id):
        """Obtener una reseña por su ID"""
        try:
            return db.resenas.find_one({"_id": ObjectId(id)})
        except:
            return None

    @staticmethod
    def obtener_por_usuario(usuario_id):
        """Obtener todas las reseñas de un usuario (solo aprobadas)"""
        try:
            query = {
                "usuario_id": usuario_id,
                "estado": "aprobado"
            }
            return list(db.resenas.find(query).sort('created_at', -1))
        except:
            return []

    @staticmethod
    def obtener_todas():
        """Obtener todas las reseñas (para admin)"""
        return list(db.resenas.find().sort('created_at', -1))

    @staticmethod
    def editar(opinion_id, usuario_id, cambios, nuevas_fotos=None, eliminar_fotos=None):
        """Editar una reseña existente"""
        try:
            resena = db.resenas.find_one({"_id": ObjectId(opinion_id), "usuario_id": usuario_id})
        except:
            return None
        
        if not resena:
            return None
        
        update_data = {
            'titulo': cambios.get('titulo'),
            'comentario': cambios.get('comentario'),
            'calificacion': cambios.get('calificacion'),
            'updated_at': datetime.utcnow()
        }
        
        fotos_actuales = resena.get('foto_path', [])
        if eliminar_fotos:
            fotos_actuales = [f for f in fotos_actuales if f not in eliminar_fotos]
        if nuevas_fotos:
            fotos_actuales.extend(nuevas_fotos)
        update_data['foto_path'] = fotos_actuales
        
        try:
            result = db.resenas.update_one(
                {"_id": ObjectId(opinion_id), "usuario_id": usuario_id},
                {"$set": update_data}
            )
            return result
        except:
            return None

    @staticmethod
    def eliminar(opinion_id, usuario_id=None):
        """Eliminar una reseña (admin puede pasar usuario_id=None)"""
        query = {}
        if usuario_id:
            query["usuario_id"] = usuario_id
        
        try:
            resena = db.resenas.find_one({"_id": ObjectId(opinion_id)})
        except:
            return None
        
        if not resena:
            return None
        
        # Si se pasó usuario_id, verificar que coincida
        if usuario_id and resena.get('usuario_id') != usuario_id:
            return None
        
        # Eliminar fotos físicas
        fotos = resena.get('foto_path', [])
        if fotos:
            folder = os.path.join(current_app.root_path, 'static', 'uploads', 'resenas')
            for foto in fotos:
                ruta = os.path.join(folder, foto)
                if os.path.exists(ruta):
                    try:
                        os.remove(ruta)
                    except:
                        pass
        
        try:
            result = db.resenas.delete_one({"_id": ObjectId(opinion_id)})
            return result
        except:
            return None

    @staticmethod
    def toggle_voto_util(opinion_id, usuario_id):
        """Agregar o quitar voto útil de una reseña"""
        try:
            resena = db.resenas.find_one({"_id": ObjectId(opinion_id)})
        except:
            return 0
        
        if not resena:
            return 0
        
        votos_utiles = resena.get('votos_utiles', [])
        if usuario_id in votos_utiles:
            votos_utiles.remove(usuario_id)
        else:
            votos_utiles.append(usuario_id)
        
        db.resenas.update_one(
            {"_id": ObjectId(opinion_id)},
            {"$set": {"votos_utiles": votos_utiles, "updated_at": datetime.utcnow()}}
        )
        return len(votos_utiles)

    @staticmethod
    def reportar(opinion_id):
        """Reportar una reseña como inapropiada"""
        try:
            resena = db.resenas.find_one({"_id": ObjectId(opinion_id)})
        except:
            return None
        
        if not resena:
            return None
        
        reportes = resena.get('reportes', 0) + 1
        db.resenas.update_one(
            {"_id": ObjectId(opinion_id)},
            {"$set": {"reportes": reportes, "updated_at": datetime.utcnow()}}
        )
        return reportes

    @staticmethod
    def contar_por_producto(producto_id):
        """Contar reseñas aprobadas de un producto"""
        try:
            return db.resenas.count_documents({"producto_id": ObjectId(producto_id), "estado": "aprobado"})
        except:
            return 0

    @staticmethod
    def promedio_por_producto(producto_id):
        """Calcular promedio de calificaciones de un producto (solo aprobadas)"""
        reseñas = Resena.obtener_por_producto(producto_id)
        if not reseñas:
            return 0
        total = sum(r.get('calificacion', 0) for r in reseñas)
        return round(total / len(reseñas), 1)

    @staticmethod
    def obtener_recientes(limit=10):
        """Obtener las reseñas más recientes (solo aprobadas)"""
        return list(db.resenas.find({"estado": "aprobado"}).sort('created_at', -1).limit(limit))

    # ================================================================
    # MÉTODOS DE ADMINISTRACIÓN
    # ================================================================

    @staticmethod
    def actualizar_estado(opinion_id, estado):
        """Actualizar estado de una reseña (admin)"""
        try:
            result = db.resenas.update_one(
                {"_id": ObjectId(opinion_id)},
                {"$set": {"estado": estado, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except:
            return False

    @staticmethod
    def responder_admin(opinion_id, respuesta):
        """Agregar respuesta de administrador"""
        try:
            result = db.resenas.update_one(
                {"_id": ObjectId(opinion_id)},
                {"$set": {
                    "respuesta_admin": respuesta,
                    "fecha_respuesta": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            return result.modified_count > 0
        except:
            return False

    @staticmethod
    def contar_por_estado():
        """Contar reseñas por estado (admin)"""
        try:
            return {
                'total': db.resenas.count_documents({}),
                'pendiente': db.resenas.count_documents({"estado": "pendiente"}),
                'aprobado': db.resenas.count_documents({"estado": "aprobado"}),
                'rechazado': db.resenas.count_documents({"estado": "rechazado"})
            }
        except:
            return {'total': 0, 'pendiente': 0, 'aprobado': 0, 'rechazado': 0}