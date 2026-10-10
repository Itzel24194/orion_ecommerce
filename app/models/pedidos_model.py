# ================================================================
# app/models/pedidos_model.py - MODELO CON PYMONGO (SIN MONGOENGINE)
# ================================================================

from datetime import datetime
from bson import ObjectId
import random
import string
import time
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

    # ------------------------------------------------------------
    # ⭐ GENERADOR DE NÚMERO DE PEDIDO ÚNICO (atómico)
    # ------------------------------------------------------------
    # Antes se usaba count_documents(...) + 1, que produce números
    # duplicados cuando dos compras se procesan simultáneamente.
    #
    # Ahora se usa un contador atómico en la colección 'contadores',
    # con formato: ORION-{año}-{secuencia 4 dígitos}.
    #
    # Si el contador del año no existe, se inicializa a partir del
    # número más alto ya registrado para ese año (por ejemplo,
    # ORION-2026-0015), evitando colisiones con pedidos previos.
    # ------------------------------------------------------------
    @staticmethod
    def generar_numero_pedido():
        """Genera un número de pedido legible y ÚNICO (ej: ORION-2024-0001)"""
        db = current_app.db
        year = datetime.utcnow().year
        contador_id = f'contador_pedidos_{year}'

        # --------------------------------------------------------
        # 1. Inicializar el contador si no existe, partiendo del
        #    máximo número ya registrado para ese año.
        # --------------------------------------------------------
        try:
            if not db.contadores.find_one({'_id': contador_id}):
                ultimo = db.pedidos.find_one(
                    {'numero_pedido': {'$regex': f'^ORION-{year}-'}},
                    sort=[('numero_pedido', -1)]
                )
                inicial = 0
                if ultimo and ultimo.get('numero_pedido'):
                    try:
                        inicial = int(ultimo['numero_pedido'].rsplit('-', 1)[-1])
                    except (ValueError, IndexError):
                        inicial = 0
                db.contadores.update_one(
                    {'_id': contador_id},
                    {'$setOnInsert': {'secuencia': inicial}},
                    upsert=True
                )
        except Exception:
            # Si falla la inicialización, seguimos con el flujo
            # normal: el siguiente paso intentará incrementar.
            pass

        # --------------------------------------------------------
        # 2. Incremento atómico del contador
        # --------------------------------------------------------
        try:
            resultado = db.contadores.find_one_and_update(
                {'_id': contador_id},
                {'$inc': {'secuencia': 1}},
                upsert=True,
                return_document=True
            )
            if resultado and 'secuencia' in resultado:
                numero = f"ORION-{year}-{str(resultado['secuencia']).zfill(4)}"
                # Defensa extra: verificar que no exista
                if not db.pedidos.find_one({'numero_pedido': numero}):
                    return numero

                # Si por alguna razón ya existe, seguir incrementando
                for _ in range(50):
                    resultado = db.contadores.find_one_and_update(
                        {'_id': contador_id},
                        {'$inc': {'secuencia': 1}},
                        return_document=True
                    )
                    numero = f"ORION-{year}-{str(resultado['secuencia']).zfill(4)}"
                    if not db.pedidos.find_one({'numero_pedido': numero}):
                        return numero
        except Exception:
            # Si falla el contador atómico, caemos al fallback
            pass

        # --------------------------------------------------------
        # 3. Fallback: método clásico con verificación de existencia
        # --------------------------------------------------------
        for _ in range(100):
            count = db.pedidos.count_documents({}) + 1
            numero = f"ORION-{year}-{str(count).zfill(4)}"
            if not db.pedidos.find_one({'numero_pedido': numero}):
                return numero

        # --------------------------------------------------------
        # 4. Último recurso: timestamp
        # --------------------------------------------------------
        return f"ORION-{year}-{int(time.time() * 1000) % 1000000:06d}"
    
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