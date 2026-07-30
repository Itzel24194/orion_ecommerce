from bson import ObjectId
from app.config.database_config import db
from pymongo.errors import DuplicateKeyError

class Categoria:
    @staticmethod
    def obtener_todas():
        """Retorna todas las categorías como una lista"""
        return list(db.categorias.find())

    @staticmethod
    def buscar_por_nombre(nombre):
        """Busca una categoría por su nombre"""
        return db.categorias.find_one({'nombre': nombre})

    @staticmethod
    def crear(data):
        try:
            # Asegurar que el id de padre sea correcto (None o ObjectId)
            if data.get('padre_id') and data['padre_id'] not in ['', 'None', 'null']:
                data['padre_id'] = ObjectId(data['padre_id'])
            else:
                data['padre_id'] = None
                
            return db.categorias.insert_one(data)
        except DuplicateKeyError:
            print("Error: El nombre de la categoría ya existe.")
            return None

    @staticmethod
    def actualizar(id, data):
        """Actualiza una categoría existente"""
        # Limpiar data antes de actualizar
        data.pop('_id', None)
        
        # Convertir padre_id si existe
        if data.get('padre_id') and data['padre_id'] not in ['', 'None', 'null']:
            data['padre_id'] = ObjectId(data['padre_id'])
        else:
            data['padre_id'] = None
            
        try:
            return db.categorias.update_one({'_id': ObjectId(id)}, {'$set': data})
        except:
            return None

    @staticmethod
    def borrar(id):
        """Borra una categoría por su ID"""
        try:
            return db.categorias.delete_one({'_id': ObjectId(id)})
        except:
            return None

    @staticmethod
    def eliminar(id):
        """Alias de borrar"""
        return Categoria.borrar(id)

    @staticmethod
    def obtener_por_id(id):
        """Obtiene una categoría por su ID"""
        try:
            return db.categorias.find_one({'_id': ObjectId(id)})
        except:
            return None

    @staticmethod
    def obtener_hijos(padre_id):
        """Obtiene las categorías hijas de un padre"""
        try:
            return list(db.categorias.find({'padre_id': ObjectId(padre_id)}))
        except:
            return []

    @staticmethod
    def obtener_raices():
        """Obtiene las categorías raíz (sin padre)"""
        return list(db.categorias.find({'padre_id': None}))