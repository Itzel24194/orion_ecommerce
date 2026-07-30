# models/productos_model.py
from app.config.database_config import db 
from bson import ObjectId
from datetime import datetime

class Producto:
    """Modelo de Producto para MongoDB"""
    
    @staticmethod
    def obtener_todos():
        """Obtener todos los productos"""
        return list(db.productos.find())
    
    @staticmethod
    def obtener_por_id(id):
        """Obtener un producto por ID"""
        try:
            return db.productos.find_one({"_id": ObjectId(id)})
        except:
            return None
    
    @staticmethod
    def crear(data):
        """Crear un nuevo producto"""
        if 'categoria_id' in data:
            data['categoria_id'] = str(data['categoria_id'])
        if 'empresa_id' in data:
            data['empresa_id'] = str(data['empresa_id'])
        
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()
        
        return db.productos.insert_one(data)
    
    @staticmethod
    def actualizar(id, data):
        """Actualizar un producto existente"""
        if 'categoria_id' in data:
            data['categoria_id'] = str(data['categoria_id'])
        if 'empresa_id' in data:
            data['empresa_id'] = str(data['empresa_id'])
        
        data['updated_at'] = datetime.now()
        
        try:
            return db.productos.update_one(
                {"_id": ObjectId(id)}, 
                {"$set": data}
            )
        except:
            return None
    
    @staticmethod
    def eliminar(id):
        """Eliminar un producto por ID"""
        try:
            result = db.productos.delete_one({"_id": ObjectId(id)})
            return result.deleted_count > 0
        except:
            return False
    
    @staticmethod
    def borrar(id):
        """Eliminar un producto por ID (alias de eliminar)"""
        return Producto.eliminar(id)
    
    @staticmethod
    def obtener_activos():
        """Obtener productos activos"""
        return list(db.productos.find({"estado": "activo"}))
    
    @staticmethod
    def obtener_por_empresa(empresa_id):
        """Obtener productos por empresa"""
        try:
            return list(db.productos.find({"empresa_id": str(empresa_id)}))
        except:
            return []
    
    @staticmethod
    def filtrar_por_categoria(categoria_id):
        """Filtrar productos por categoría"""
        try:
            return list(db.productos.find({"categoria_id": str(categoria_id)}))
        except:
            return []
    
    @staticmethod
    def filtrar_por_categoria_y_descendientes(categoria_id):
        """
        Busca productos en la categoría seleccionada y sus descendientes (hijos y nietos).
        """
        from app.models.categorias_model import Categoria
        
        todas_las_categorias = Categoria.obtener_todas()
        categoria_id_str = str(categoria_id)
        
        def obtener_ids_hijos(parent_id, lista_categorias):
            ids = [str(parent_id)]
            for cat in lista_categorias:
                if str(cat.get('padre_id')) == str(parent_id):
                    ids.extend(obtener_ids_hijos(cat.get('_id'), lista_categorias))
            return ids

        lista_ids = obtener_ids_hijos(categoria_id_str, todas_las_categorias)
        
        try:
            return list(db.productos.find({'categoria_id': {'$in': lista_ids}}))
        except:
            return []
    
    @staticmethod
    def buscar(termino):
        """Buscar productos por nombre o descripción"""
        try:
            return list(db.productos.find({
                '$or': [
                    {'nombre': {'$regex': termino, '$options': 'i'}},
                    {'descripcion': {'$regex': termino, '$options': 'i'}}
                ]
            }))
        except:
            return []
    
    @staticmethod
    def obtener_destacados(limite=8):
        """Obtener productos destacados (los más vendidos)"""
        try:
            return list(db.productos.find({"estado": "activo"}).limit(limite))
        except:
            return []
    
    @staticmethod
    def contar_productos():
        """Contar el total de productos"""
        try:
            return db.productos.count_documents({})
        except:
            return 0
    
    @staticmethod
    def contar_activos():
        """Contar productos activos"""
        try:
            return db.productos.count_documents({"estado": "activo"})
        except:
            return 0
    
    @staticmethod
    def obtener_recientes(limite=5):
        """Obtener productos recientes"""
        try:
            return list(db.productos.find().sort("created_at", -1).limit(limite))
        except:
            return []
    
    @staticmethod
    def actualizar_stock(id, variantes_actualizadas):
        """Actualizar el stock de un producto"""
        try:
            return db.productos.update_one(
                {"_id": ObjectId(id)},
                {"$set": {"variables": variantes_actualizadas, "updated_at": datetime.now()}}
            )
        except:
            return None
    
    @staticmethod
    def obtener_por_sku(sku):
        """Obtener un producto por SKU"""
        try:
            return db.productos.find_one({"variables.sku": sku})
        except:
            return None
    
    @staticmethod
    def obtener_por_rango_precios(min_precio, max_precio):
        """Obtener productos en un rango de precios"""
        try:
            return list(db.productos.find({
                "variables.precio": {"$gte": float(min_precio), "$lte": float(max_precio)}
            }))
        except:
            return []

    # ================================================================
    # NUEVO MÉTODO: Obtener productos por lista de IDs
    # ================================================================
    @staticmethod
    def obtener_por_ids(ids):
        """
        Obtener múltiples productos por una lista de IDs (strings o ObjectId).
        Retorna una lista de productos (documentos) que coinciden con los IDs válidos.
        """
        if not ids:
            return []
        
        object_ids = []
        for id in ids:
            if ObjectId.is_valid(id):
                object_ids.append(ObjectId(id))
        
        if not object_ids:
            return []
        
        try:
            return list(db.productos.find({'_id': {'$in': object_ids}}))
        except:
            return []