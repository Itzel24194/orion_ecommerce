# models/productos_model.py
from app.config.database_config import db 
from bson import ObjectId
from datetime import datetime, date


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
        if 'categoria_id' in data and data['categoria_id']:
            data['categoria_id'] = str(data['categoria_id'])
        if 'marca_id' in data and data['marca_id']:
            data['marca_id'] = str(data['marca_id'])
        if 'temporada_id' in data and data['temporada_id']:
            data['temporada_id'] = str(data['temporada_id'])
        
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()
        
        return db.productos.insert_one(data)
    
    @staticmethod
    def actualizar(id, data):
        """Actualizar un producto existente"""
        if 'categoria_id' in data and data['categoria_id']:
            data['categoria_id'] = str(data['categoria_id'])
        if 'marca_id' in data and data['marca_id']:
            data['marca_id'] = str(data['marca_id'])
        if 'temporada_id' in data and data['temporada_id']:
            data['temporada_id'] = str(data['temporada_id'])
        elif 'temporada_id' in data and not data['temporada_id']:
            data['temporada_id'] = None
        
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
        """
        Obtener productos activos.
        Usa el campo 'activo' (booleano) para filtrar.
        
        ⭐ IMPORTANTE: NO filtra por vendedor_id, así que INCLUYE
        los productos del marketplace automáticamente.
        """
        return list(db.productos.find({"activo": True}).sort("created_at", -1))

    @staticmethod
    def obtener_activos_por_estado():
        """
        Obtener productos por campo 'estado' (legado).
        Se mantiene por compatibilidad.
        """
        return list(db.productos.find({"estado": "activo"}))
    
    @staticmethod
    def obtener_por_marca(marca_id):
        """
        Obtener productos por marca (soporta string y ObjectId).
        ⭐ Fix: busca tanto en string como en ObjectId.
        """
        try:
            marca_str = str(marca_id)
            filtro = {
                '$or': [
                    {'marca_id': marca_str},
                    {'marca_id': ObjectId(marca_str)} if ObjectId.is_valid(marca_str) else {'marca_id': marca_str},
                ]
            }
            return list(db.productos.find(filtro))
        except:
            return []
    
    @staticmethod
    def filtrar_por_categoria(categoria_id):
        """
        Filtrar productos por categoría (solo activos).
        ⭐ Fix: soporta string y ObjectId.
        """
        try:
            cat_str = str(categoria_id)
            filtro = {
                '$or': [
                    {'categoria_id': cat_str},
                    {'categoria_id': ObjectId(cat_str)} if ObjectId.is_valid(cat_str) else {'categoria_id': cat_str},
                ],
                'activo': True
            }
            return list(db.productos.find(filtro))
        except:
            return []
    
    @staticmethod
    def filtrar_por_categoria_y_descendientes(categoria_id):
        """
        Busca productos en la categoría seleccionada y sus descendientes (hijos y nietos).
        Solo devuelve productos activos (activo=True).
        
        ⭐ FIX CRÍTICO: Los productos del marketplace guardan categoria_id como
        ObjectId, mientras que los del admin lo guardan como string. Esta función
        ahora busca en AMBOS formatos para que ambos aparezcan.
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

        lista_ids_str = obtener_ids_hijos(categoria_id_str, todas_las_categorias)
        
        # ⭐ Crear también la lista como ObjectId
        lista_ids_oid = []
        for i in lista_ids_str:
            if ObjectId.is_valid(i):
                lista_ids_oid.append(ObjectId(i))
        
        try:
            # ⭐ Buscar en AMBOS formatos (string y ObjectId)
            return list(db.productos.find({
                '$or': [
                    {'categoria_id': {'$in': lista_ids_str}},
                    {'categoria_id': {'$in': lista_ids_oid}},
                ],
                'activo': True
            }).sort("created_at", -1))
        except:
            return []
    
    @staticmethod
    def buscar(termino):
        """Buscar productos por nombre o descripción (solo activos)"""
        try:
            return list(db.productos.find({
                '$or': [
                    {'nombre': {'$regex': termino, '$options': 'i'}},
                    {'descripcion': {'$regex': termino, '$options': 'i'}}
                ],
                'activo': True
            }))
        except:
            return []
    
    @staticmethod
    def obtener_destacados(limite=8):
        """Obtener productos destacados (los más vendidos) - solo activos"""
        try:
            return list(db.productos.find({"activo": True}).limit(limite))
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
        """Contar productos activos (campo activo=True)"""
        try:
            return db.productos.count_documents({"activo": True})
        except:
            return 0

    @staticmethod
    def contar_activos_por_estado():
        """Contar productos activos por campo 'estado' (legado)"""
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
        """Obtener productos en un rango de precios (solo activos)"""
        try:
            return list(db.productos.find({
                "variables.precio": {"$gte": float(min_precio), "$lte": float(max_precio)},
                "activo": True
            }))
        except:
            return []

    # ================================================================
    # Obtener productos por lista de IDs
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

    # ================================================================
    # Obtener productos por temporada
    # ================================================================
    @staticmethod
    def obtener_por_temporada(temporada_id):
        """
        Obtener productos asociados a una temporada.
        ⭐ Fix: soporta string y ObjectId.
        """
        try:
            temp_str = str(temporada_id)
            filtro = {
                '$or': [
                    {'temporada_id': temp_str},
                    {'temporada_id': ObjectId(temp_str)} if ObjectId.is_valid(temp_str) else {'temporada_id': temp_str},
                ]
            }
            return list(db.productos.find(filtro))
        except:
            return []

    # ================================================================
    # ACTUALIZACIÓN AUTOMÁTICA DE ESTADOS (SCHEDULER)
    # ================================================================
    @staticmethod
    def actualizar_estado_segun_temporadas():
        """
        Actualiza el campo 'activo' de todos los productos según las temporadas vigentes.
        Se ejecuta automáticamente con el scheduler (diariamente a las 00:00).
        
        Un producto está activo si:
        - Tiene temporada_id asignado
        - Su temporada está activa (activa=True)
        - La fecha actual está dentro del rango [fecha_inicio, fecha_fin]
        
        Si un producto no tiene temporada_id, su estado NO se modifica.
        """
        from app.models.temporada_model import Temporada
        
        hoy = datetime.now().date()
        
        # Obtener temporadas activas en la fecha actual
        temporadas_vigentes = Temporada.obtener_por_fecha(hoy)
        ids_temporadas_vigentes_str = [str(t['_id']) for t in temporadas_vigentes]
        ids_temporadas_vigentes_oid = [t['_id'] for t in temporadas_vigentes]

        # 1. ACTIVAR productos cuyas temporadas están vigentes
        if ids_temporadas_vigentes_str:
            db.productos.update_many(
                {'$or': [
                    {"temporada_id": {"$in": ids_temporadas_vigentes_str}},
                    {"temporada_id": {"$in": ids_temporadas_vigentes_oid}},
                ]},
                {"$set": {"activo": True, "updated_at": datetime.now()}}
            )
        
        # 2. DESACTIVAR productos cuyas temporadas NO están vigentes
        db.productos.update_many(
            {'$or': [
                {"temporada_id": {"$nin": ids_temporadas_vigentes_str + [None, '']}},
                {"temporada_id": {"$nin": ids_temporadas_vigentes_oid + [None, '']}},
            ], "temporada_id": {"$exists": True, "$ne": None}},
            {"$set": {"activo": False, "updated_at": datetime.now()}}
        )

        return True

    # ================================================================
    # Alias de obtener_por_temporada
    # ================================================================
    @staticmethod
    def obtener_por_temporada_id(temporada_id):
        """Alias de obtener_por_temporada"""
        return Producto.obtener_por_temporada(temporada_id)