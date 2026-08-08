# app/models/usuarios_model.py
import pandas as pd
from bson.objectid import ObjectId
from app.config.database_config import usuarios_col
from flask_bcrypt import Bcrypt
from datetime import datetime
from flask import current_app

bcrypt = Bcrypt()


def normalizar_genero(valor):
    """Función auxiliar para normalizar género (también usada en el modelo)"""
    if not valor:
        return 'Indefinido'
    v = valor.strip().lower()
    if v in ['masculino', 'hombre', 'm', 'male', 'man']:
        return 'Masculino'
    if v in ['femenino', 'mujer', 'f', 'female', 'woman']:
        return 'Femenino'
    return 'Indefinido'


class Usuario:
    @staticmethod
    def _limpiar_valor(valor):
        return None if pd.isnull(valor) or valor == "" else valor

    @staticmethod
    def obtener_todos():
        return list(usuarios_col.find())

    @staticmethod
    def obtener_por_id(id):
        try:
            return usuarios_col.find_one({"_id": ObjectId(id)})
        except:
            return None

    @staticmethod
    def obtener_por_email(email):
        if pd.isnull(email): 
            return None
        return usuarios_col.find_one({"email": email})

    @staticmethod
    def verificar_password(email, password_plano):
        """Verifica si la contraseña coincide con el hash almacenado para el email dado."""
        if not email or not password_plano:
            return False
        
        usuario = Usuario.obtener_por_email(email)
        if not usuario:
            return False
        
        password_hash = usuario.get('password')
        if not password_hash or not isinstance(password_hash, str):
            return False
        
        try:
            return bcrypt.check_password_hash(password_hash, password_plano)
        except Exception as e:
            print(f"Error verificando contraseña: {e}")
            return False

    @staticmethod
    def crear_usuario(data):
        """Crea un nuevo usuario en la base de datos."""
        # Limpiar campos
        data['foto'] = Usuario._limpiar_valor(data.get('foto'))
        data['nombre'] = Usuario._limpiar_valor(data.get('nombre'))
        data['apellido_paterno'] = Usuario._limpiar_valor(data.get('apellido_paterno'))
        data['apellido_materno'] = Usuario._limpiar_valor(data.get('apellido_materno'))
        data['telefono'] = Usuario._limpiar_valor(data.get('telefono'))
        
        # Normalizar género (por si acaso)
        if 'sexo' in data:
            data['sexo'] = normalizar_genero(data['sexo'])
        if 'genero' in data:
            data['genero'] = normalizar_genero(data['genero'])  # por compatibilidad
        
        # Encriptar contraseña si existe
        if data.get('password'):
            data['password'] = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        # Agregar fechas si no existen
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow()
        if 'updated_at' not in data:
            data['updated_at'] = datetime.utcnow()
        if 'activo' not in data:
            data['activo'] = True
        if 'confirmado' not in data:
            data['confirmado'] = False
        
        # Inicializar direcciones si no existe
        if 'direcciones' not in data:
            data['direcciones'] = []
        
        # Inicializar favoritos si no existe
        if 'favoritos' not in data:
            data['favoritos'] = []
        
        # Inicializar notificaciones si no existe
        if 'notificaciones' not in data:
            data['notificaciones'] = []
        
        return usuarios_col.insert_one(data)

    @staticmethod
    def marcar_como_confirmado(email):
        """Marca al usuario como confirmado en la base de datos."""
        return usuarios_col.update_one(
            {"email": email}, 
            {"$set": {"confirmado": True, "updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def actualizar_por_email(email, data):
        """Actualiza campos específicos de un usuario identificado por email."""
        if 'password' in data and data['password']:
            data['password'] = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        elif 'password' in data:
            del data['password']
        
        # Normalizar género si se envía
        if 'sexo' in data:
            data['sexo'] = normalizar_genero(data['sexo'])
        if 'genero' in data:
            data['genero'] = normalizar_genero(data['genero'])
        
        data['updated_at'] = datetime.utcnow()
        return usuarios_col.update_one({"email": email}, {"$set": data})

    @staticmethod
    def actualizar(id, data):
        """Alias de actualizar_usuario."""
        return Usuario.actualizar_usuario(id, data)

    @staticmethod
    def actualizar_usuario(id, data):
        """Actualiza un usuario por su ID."""
        update_fields = data.copy()
        
        # Limpiar campos
        if 'foto' in update_fields:
            update_fields['foto'] = Usuario._limpiar_valor(update_fields.get('foto'))
        if 'nombre' in update_fields:
            update_fields['nombre'] = Usuario._limpiar_valor(update_fields.get('nombre'))
        if 'apellido_paterno' in update_fields:
            update_fields['apellido_paterno'] = Usuario._limpiar_valor(update_fields.get('apellido_paterno'))
        if 'apellido_materno' in update_fields:
            update_fields['apellido_materno'] = Usuario._limpiar_valor(update_fields.get('apellido_materno'))
        if 'telefono' in update_fields:
            update_fields['telefono'] = Usuario._limpiar_valor(update_fields.get('telefono'))
        
        # Normalizar género
        if 'sexo' in update_fields:
            update_fields['sexo'] = normalizar_genero(update_fields['sexo'])
        if 'genero' in update_fields:
            update_fields['genero'] = normalizar_genero(update_fields['genero'])
        
        # Manejar contraseña
        if 'password' in update_fields:
            pwd = update_fields['password']
            if pd.isnull(pwd) or str(pwd).strip() == "":
                update_fields.pop('password', None)
            else:
                update_fields['password'] = bcrypt.generate_password_hash(pwd).decode('utf-8')
        
        # Agregar fecha de actualización
        update_fields['updated_at'] = datetime.utcnow()
        
        return usuarios_col.update_one({"_id": ObjectId(id)}, {"$set": update_fields})

    @staticmethod
    def eliminar_usuario(id):
        return usuarios_col.delete_one({"_id": ObjectId(id)})

    # ============================================================
    # 🔥 MÉTODOS PARA SEGMENTACIÓN
    # ============================================================

    @staticmethod
    def calcular_segmento(usuario_id):
        """Calcula el segmento de un usuario basado en sus pedidos"""
        db = current_app.db
        pedidos = list(db.pedidos.find({"usuario_id": str(usuario_id)}))
        
        cantidad = len(pedidos)
        total_gastado = sum(float(p.get("total", 0)) for p in pedidos)
        
        if total_gastado >= 10000:
            return "VIP"
        elif cantidad >= 5:
            return "Frecuente"
        elif cantidad >= 1:
            return "Ocasional"
        else:
            return "Inactivo"

    @staticmethod
    def actualizar_segmento(usuario_id):
        """Actualiza el segmento del usuario en la base de datos"""
        segmento = Usuario.calcular_segmento(usuario_id)
        return Usuario.actualizar_usuario(usuario_id, {"segmento": segmento})

    @staticmethod
    def obtener_segmento(usuario_id):
        """Obtiene el segmento del usuario (de la BD o lo calcula)"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return "Inactivo"
        
        if usuario.get("segmento"):
            return usuario.get("segmento")
        
        segmento = Usuario.calcular_segmento(usuario_id)
        Usuario.actualizar_usuario(usuario_id, {"segmento": segmento})
        return segmento

    # ============================================================
    # MÉTODOS DE DIRECCIONES - COMPLETOS
    # ============================================================

    @staticmethod
    def agregar_direccion(usuario_id, data):
        """Agrega una nueva dirección al usuario con todos los campos"""
        if '_id' not in data:
            data['_id'] = ObjectId()
        
        data['calle'] = data.get('calle', '')
        data['numero'] = data.get('numero', '')
        data['colonia'] = data.get('colonia', '')
        data['cp'] = data.get('cp', '')
        data['ciudad'] = data.get('ciudad', '')
        data['estado'] = data.get('estado', '')
        data['referencias'] = data.get('referencias', '')
        data['nombre'] = data.get('nombre', '')
        data['predeterminada'] = data.get('predeterminada', False)
        
        if data['predeterminada']:
            usuarios_col.update_one(
                {"_id": ObjectId(usuario_id)},
                {"$set": {"direcciones.$[].predeterminada": False}}
            )
        
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id)}, 
            {"$push": {"direcciones": data}}
        )

    @staticmethod
    def editar_direccion(usuario_id, direccion_id, data):
        """Edita una dirección existente con todos los campos"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario or not usuario.get('direcciones'):
            return None
        
        direcciones = list(usuario.get('direcciones', []))
        if direccion_id >= len(direcciones):
            return None
        
        direccion_actualizada = direcciones[direccion_id].copy()
        direccion_actualizada.update({
            'calle': data.get('calle', direccion_actualizada.get('calle', '')),
            'numero': data.get('numero', direccion_actualizada.get('numero', '')),
            'colonia': data.get('colonia', direccion_actualizada.get('colonia', '')),
            'cp': data.get('cp', direccion_actualizada.get('cp', '')),
            'ciudad': data.get('ciudad', direccion_actualizada.get('ciudad', '')),
            'estado': data.get('estado', direccion_actualizada.get('estado', '')),
            'referencias': data.get('referencias', direccion_actualizada.get('referencias', '')),
            'nombre': data.get('nombre', direccion_actualizada.get('nombre', '')),
            'predeterminada': data.get('predeterminada', direccion_actualizada.get('predeterminada', False))
        })
        
        if data.get('predeterminada', False):
            for i, d in enumerate(direcciones):
                if i != direccion_id:
                    d['predeterminada'] = False
        
        direcciones[direccion_id] = direccion_actualizada
        
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id)},
            {"$set": {"direcciones": direcciones, "updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def borrar_direccion(usuario_id, direccion_id):
        """Elimina una dirección por ID o índice"""
        u_id = ObjectId(usuario_id)
        
        try:
            if isinstance(direccion_id, str) and ObjectId.is_valid(direccion_id):
                res = usuarios_col.update_one(
                    {"_id": u_id}, 
                    {"$pull": {"direcciones": {"_id": ObjectId(direccion_id)}}}
                )
                if res.modified_count > 0:
                    return res
        except:
            pass
        
        if str(direccion_id).isdigit():
            index = int(direccion_id)
            usuario = Usuario.obtener_por_id(usuario_id)
            if usuario and usuario.get('direcciones') and index < len(usuario['direcciones']):
                era_predeterminada = usuario['direcciones'][index].get('predeterminada', False)
                
                usuarios_col.update_one(
                    {"_id": u_id}, 
                    {"$unset": {f"direcciones.{index}": 1}}
                )
                result = usuarios_col.update_one(
                    {"_id": u_id}, 
                    {"$pull": {"direcciones": None}}
                )
                
                if era_predeterminada:
                    usuario_actualizado = Usuario.obtener_por_id(usuario_id)
                    if usuario_actualizado and usuario_actualizado.get('direcciones'):
                        nuevas_dirs = usuario_actualizado['direcciones']
                        if nuevas_dirs and not any(d.get('predeterminada') for d in nuevas_dirs):
                            nuevas_dirs[0]['predeterminada'] = True
                            usuarios_col.update_one(
                                {"_id": u_id},
                                {"$set": {"direcciones": nuevas_dirs, "updated_at": datetime.utcnow()}}
                            )
                
                return result
        
        return None

    @staticmethod
    def obtener_direccion_predeterminada(usuario_id):
        """Obtiene la dirección predeterminada del usuario"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario or not usuario.get('direcciones'):
            return None
        
        for dir in usuario['direcciones']:
            if dir.get('predeterminada', False):
                return dir
        
        return usuario['direcciones'][0] if usuario['direcciones'] else None

    @staticmethod
    def obtener_direcciones(usuario_id):
        """Obtiene todas las direcciones del usuario"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return []
        return usuario.get('direcciones', [])

    # ============================================================
    # MÉTODOS DE FAVORITOS
    # ============================================================

    @staticmethod
    def agregar_favorito(usuario_id, producto_id):
        """Agrega un producto a favoritos"""
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id)},
            {"$addToSet": {"favoritos": producto_id}, "$set": {"updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def eliminar_favorito(usuario_id, producto_id):
        """Elimina un producto de favoritos"""
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id)},
            {"$pull": {"favoritos": producto_id}, "$set": {"updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def obtener_favoritos(usuario_id):
        """Obtiene la lista de favoritos del usuario"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return []
        return usuario.get('favoritos', [])

    @staticmethod
    def es_favorito(usuario_id, producto_id):
        """Verifica si un producto está en favoritos"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return False
        return producto_id in usuario.get('favoritos', [])

    # ============================================================
    # MÉTODOS ESTADÍSTICOS
    # ============================================================

    @staticmethod
    def contar_por_rol(rol):
        """Contar usuarios por rol."""
        return usuarios_col.count_documents({"rol": rol})

    @staticmethod
    def obtener_por_rol(rol):
        """Obtener usuarios por rol."""
        return list(usuarios_col.find({"rol": rol}))

    @staticmethod
    def buscar(query):
        """Buscar usuarios por nombre o email."""
        return list(usuarios_col.find({
            '$or': [
                {'nombre': {'$regex': query, '$options': 'i'}},
                {'email': {'$regex': query, '$options': 'i'}},
                {'apellido_paterno': {'$regex': query, '$options': 'i'}}
            ]
        }))

    @staticmethod
    def toggle_activo(id):
        """Activar/Desactivar un usuario."""
        usuario = Usuario.obtener_por_id(id)
        if not usuario:
            return False
        
        nuevo_estado = not usuario.get('activo', True)
        result = usuarios_col.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"activo": nuevo_estado, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    @staticmethod
    def cambiar_password(id, nueva_password):
        """Cambiar la contraseña de un usuario."""
        hashed = bcrypt.generate_password_hash(nueva_password).decode('utf-8')
        result = usuarios_col.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"password": hashed, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    @staticmethod
    def obtener_estadisticas():
        """Obtiene estadísticas de usuarios"""
        db = usuarios_col.database
        total = usuarios_col.count_documents({})
        activos = usuarios_col.count_documents({"activo": True})
        inactivos = usuarios_col.count_documents({"activo": False})
        admins = usuarios_col.count_documents({"rol": "admin"})
        vendedores = usuarios_col.count_documents({"rol": "vendedor"})
        clientes = usuarios_col.count_documents({"rol": "cliente"})
        
        return {
            "total": total,
            "activos": activos,
            "inactivos": inactivos,
            "admins": admins,
            "vendedores": vendedores,
            "clientes": clientes
        }

    @staticmethod
    def obtener_ultimos_registrados(limite=5):
        """Obtiene los últimos usuarios registrados"""
        return list(usuarios_col.find().sort("created_at", -1).limit(limite))

    @staticmethod
    def obtener_por_mes(anio=None, mes=None):
        """Obtiene usuarios registrados en un mes específico"""
        if anio is None:
            anio = datetime.utcnow().year
        if mes is None:
            mes = datetime.utcnow().month
        
        mes_str = f"{anio}-{str(mes).zfill(2)}"
        return list(usuarios_col.find({
            'created_at': {'$regex': mes_str}
        }))

    @staticmethod
    def contar_por_mes(anio=None, mes=None):
        """Cuenta usuarios registrados en un mes específico"""
        if anio is None:
            anio = datetime.utcnow().year
        if mes is None:
            mes = datetime.utcnow().month
        
        mes_str = f"{anio}-{str(mes).zfill(2)}"
        return usuarios_col.count_documents({
            'created_at': {'$regex': mes_str}
        })

    # ============================================================
    # MÉTODOS DE NOTIFICACIONES
    # ============================================================

    @staticmethod
    def agregar_notificacion(usuario_id, notificacion):
        """Agrega una notificación al usuario"""
        notificacion['_id'] = ObjectId()
        notificacion['created_at'] = datetime.utcnow()
        notificacion['leida'] = False
        
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id)},
            {"$push": {"notificaciones": notificacion}, "$set": {"updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def marcar_notificacion_leida(usuario_id, notificacion_id):
        """Marca una notificación como leída"""
        return usuarios_col.update_one(
            {"_id": ObjectId(usuario_id), "notificaciones._id": ObjectId(notificacion_id)},
            {"$set": {"notificaciones.$.leida": True, "updated_at": datetime.utcnow()}}
        )

    @staticmethod
    def obtener_notificaciones_no_leidas(usuario_id):
        """Obtiene las notificaciones no leídas del usuario"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return []
        
        notificaciones = usuario.get('notificaciones', [])
        return [n for n in notificaciones if not n.get('leida', False)]

    @staticmethod
    def obtener_todas_notificaciones(usuario_id):
        """Obtiene todas las notificaciones del usuario"""
        usuario = Usuario.obtener_por_id(usuario_id)
        if not usuario:
            return []
        return usuario.get('notificaciones', [])