# ================================================================
# app/models/pedidos_model.py - MODELO CON PYMONGO (SIN MONGOENGINE)
# ================================================================

from datetime import datetime
from bson import ObjectId
import random
import string
from flask import current_app

class Pedido:
    """Modelo de pedidos usando PyMongo directamente"""
    
    collection_name = 'pedidos'
    
    @staticmethod
    def get_collection():
        """Obtiene la colección de pedidos"""
        db = current_app.db
        return db[Pedido.collection_name]
    
    @staticmethod
    def crear(data):
        """Crea un nuevo pedido"""
        collection = Pedido.get_collection()
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow()
        if 'updated_at' not in data:
            data['updated_at'] = datetime.utcnow()
        return collection.insert_one(data)
    
    @staticmethod
    def obtener_por_id(id):
        """Obtiene un pedido por su ID"""
        collection = Pedido.get_collection()
        try:
            return collection.find_one({'_id': ObjectId(id)})
        except:
            return collection.find_one({'_id': id})
    
    @staticmethod
    def obtener_por_usuario(usuario_id):
        """Obtiene todos los pedidos de un usuario"""
        collection = Pedido.get_collection()
        try:
            return list(collection.find({'usuario_id': usuario_id}).sort('created_at', -1))
        except:
            try:
                return list(collection.find({'usuario_id': ObjectId(usuario_id)}).sort('created_at', -1))
            except:
                return []
    
    @staticmethod
    def obtener_todos():
        """Obtiene todos los pedidos"""
        collection = Pedido.get_collection()
        return list(collection.find().sort('created_at', -1))
    
    @staticmethod
    def actualizar(id, data):
        """Actualiza un pedido"""
        collection = Pedido.get_collection()
        data['updated_at'] = datetime.utcnow()
        try:
            return collection.update_one({'_id': ObjectId(id)}, {'$set': data})
        except:
            return collection.update_one({'_id': id}, {'$set': data})
    
    @staticmethod
    def eliminar(id):
        """Elimina un pedido"""
        collection = Pedido.get_collection()
        try:
            return collection.delete_one({'_id': ObjectId(id)})
        except:
            return collection.delete_one({'_id': id})
    
    @staticmethod
    def contar_por_usuario(usuario_id):
        """Cuenta los pedidos de un usuario"""
        collection = Pedido.get_collection()
        try:
            return collection.count_documents({'usuario_id': usuario_id})
        except:
            try:
                return collection.count_documents({'usuario_id': ObjectId(usuario_id)})
            except:
                return 0
    
    @staticmethod
    def obtener_por_estado(estado):
        """Obtiene pedidos por estado"""
        collection = Pedido.get_collection()
        return list(collection.find({'estado': estado}).sort('created_at', -1))
    
    @staticmethod
    def generar_numero_pedido():
        """Genera un número de pedido legible (ej: ORION-2024-0001)"""
        collection = Pedido.get_collection()
        year = datetime.utcnow().year
        count = collection.count_documents({
            'created_at': {
                '$gte': datetime(year, 1, 1),
                '$lt': datetime(year + 1, 1, 1)
            }
        }) + 1
        return f"ORION-{year}-{str(count).zfill(4)}"
    
    @staticmethod
    def generar_codigo_recogida():
        """Genera un código único para Click & Collect"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    @staticmethod
    def get_estado_display(estado):
        """Retorna el estado en español con color"""
        estados = {
            'pendiente': {'label': 'Pendiente', 'color': 'secondary'},
            'confirmado': {'label': 'Confirmado', 'color': 'primary'},
            'preparando': {'label': 'Preparando', 'color': 'warning'},
            'enviado': {'label': 'Enviado', 'color': 'info'},
            'entregado': {'label': 'Entregado', 'color': 'success'},
            'cancelado': {'label': 'Cancelado', 'color': 'danger'},
            'reembolsado': {'label': 'Reembolsado', 'color': 'dark'}
        }
        return estados.get(estado, {'label': estado, 'color': 'secondary'})
    
    @staticmethod
    def puede_cancelar(estado):
        """Verifica si el pedido puede ser cancelado"""
        return estado in ['pendiente', 'confirmado']
    
    @staticmethod
    def get_progreso(estado):
        """Retorna el porcentaje de progreso del pedido"""
        progreso = {
            'pendiente': 0,
            'confirmado': 25,
            'preparando': 50,
            'enviado': 75,
            'entregado': 100
        }
        return progreso.get(estado, 0)
    
    @staticmethod
    def to_dict(pedido):
        """Convierte un pedido a diccionario con strings"""
        if not pedido:
            return None
        pedido['_id'] = str(pedido['_id'])
        if 'usuario_id' in pedido and pedido['usuario_id']:
            pedido['usuario_id'] = str(pedido['usuario_id'])
        if 'items' not in pedido or not isinstance(pedido['items'], list):
            pedido['items'] = []
        return pedido