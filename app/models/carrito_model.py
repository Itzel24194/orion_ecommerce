from mongoengine import Document, StringField, ObjectIdField, FloatField, IntField, BooleanField, ListField, DictField, DateTimeField
from datetime import datetime
from bson import ObjectId


class Carrito(Document):
    """
    Modelo de Carrito de compras para ORION
    Almacena el carrito de cada usuario en la base de datos
    """
    
    # ====== INFORMACIÓN DEL USUARIO ======
    usuario_id = ObjectIdField(required=True, unique=True)
    
    # ====== PRODUCTOS EN EL CARRITO ======
    items = ListField(DictField())
    # Cada item tiene:
    # {
    #   'producto_id': 'ObjectId',
    #   'nombre': 'string',
    #   'precio': float,
    #   'imagen': 'string',
    #   'cantidad': int,
    #   'atributos': {'color': 'string', 'tamano': 'string'},
    #   'fecha_agregado': datetime
    # }
    
    # ====== TOTALES ======
    subtotal = FloatField(default=0)
    iva = FloatField(default=0)
    total = FloatField(default=0)
    envio = FloatField(default=0)
    descuento = FloatField(default=0)
    
    # ====== CUPÓN APLICADO ======
    cupon_codigo = StringField()
    cupon_descuento = FloatField(default=0)
    
    # ====== FECHAS ======
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    # ====== META ======
    meta = {
        'collection': 'carritos',
        'indexes': [
            {'fields': ['usuario_id'], 'unique': True},
            {'fields': ['created_at']}
        ]
    }
    
    def __str__(self):
        return f"Carrito de {self.usuario_id}"
    
    def calcular_totales(self):
        """Calcula subtotal, IVA y total del carrito"""
        self.subtotal = sum(
            float(item.get('precio', 0)) * int(item.get('cantidad', 1)) 
            for item in self.items
        )
        self.iva = self.subtotal * 0.16
        self.total = self.subtotal + self.iva + self.envio - self.descuento
        return {
            'subtotal': self.subtotal,
            'iva': self.iva,
            'total': self.total,
            'envio': self.envio,
            'descuento': self.descuento
        }
    
    def agregar_item(self, producto_id, nombre, precio, imagen, cantidad=1, atributos=None):
        """Agrega un producto al carrito"""
        # Verificar si el producto ya existe con mismos atributos
        for item in self.items:
            if (str(item.get('producto_id')) == str(producto_id) and 
                item.get('atributos') == atributos):
                item['cantidad'] += cantidad
                self.updated_at = datetime.utcnow()
                self.calcular_totales()
                return True
        
        # Si no existe, agregar nuevo
        self.items.append({
            'producto_id': producto_id,
            'nombre': nombre,
            'precio': float(precio),
            'imagen': imagen,
            'cantidad': int(cantidad),
            'atributos': atributos or {},
            'fecha_agregado': datetime.utcnow()
        })
        self.updated_at = datetime.utcnow()
        self.calcular_totales()
        return True
    
    def eliminar_item(self, index):
        """Elimina un item del carrito por su índice"""
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self.updated_at = datetime.utcnow()
            self.calcular_totales()
            return True
        return False
    
    def eliminar_item_por_id(self, producto_id, atributos=None):
        """Elimina un producto del carrito por su ID y atributos"""
        for i, item in enumerate(self.items):
            if (str(item.get('producto_id')) == str(producto_id) and 
                item.get('atributos') == atributos):
                self.items.pop(i)
                self.updated_at = datetime.utcnow()
                self.calcular_totales()
                return True
        return False
    
    def actualizar_cantidad(self, producto_id, cantidad, atributos=None):
        """Actualiza la cantidad de un producto en el carrito"""
        for item in self.items:
            if (str(item.get('producto_id')) == str(producto_id) and 
                item.get('atributos') == atributos):
                if cantidad <= 0:
                    return self.eliminar_item_por_id(producto_id, atributos)
                item['cantidad'] = int(cantidad)
                self.updated_at = datetime.utcnow()
                self.calcular_totales()
                return True
        return False
    
    def vaciar(self):
        """Vacía todo el carrito"""
        self.items = []
        self.subtotal = 0
        self.iva = 0
        self.total = 0
        self.descuento = 0
        self.cupon_codigo = None
        self.cupon_descuento = 0
        self.updated_at = datetime.utcnow()
        self.save()
    
    def aplicar_cupon(self, codigo, descuento):
        """Aplica un cupón de descuento"""
        self.cupon_codigo = codigo
        self.cupon_descuento = float(descuento)
        self.descuento = float(descuento)
        self.updated_at = datetime.utcnow()
        self.calcular_totales()
    
    def contar_items(self):
        """Cuenta la cantidad total de items en el carrito"""
        return sum(item.get('cantidad', 0) for item in self.items)
    
    def obtener_productos_ids(self):
        """Obtiene los IDs de todos los productos en el carrito"""
        return [str(item.get('producto_id')) for item in self.items]
    
    def to_dict(self):
        """Convierte el carrito a diccionario para la API"""
        return {
            'id': str(self.id),
            'usuario_id': str(self.usuario_id),
            'items': self.items,
            'subtotal': self.subtotal,
            'iva': self.iva,
            'total': self.total,
            'envio': self.envio,
            'descuento': self.descuento,
            'cupon_codigo': self.cupon_codigo,
            'total_items': self.contar_items(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def obtener_o_crear(cls, usuario_id):
        """
        Obtiene el carrito de un usuario o crea uno nuevo si no existe
        """
        carrito = cls.objects(usuario_id=usuario_id).first()
        if not carrito:
            carrito = cls(usuario_id=usuario_id, items=[])
            carrito.save()
        return carrito
    
    @classmethod
    def obtener_items_con_detalles(cls, usuario_id, db):
        """
        Obtiene los items del carrito con detalles completos del producto
        """
        carrito = cls.objects(usuario_id=usuario_id).first()
        if not carrito:
            return []
        
        items_con_detalles = []
        for item in carrito.items:
            producto = db.productos.find_one({'_id': ObjectId(item.get('producto_id'))})
            if producto:
                item_completo = item.copy()
                item_completo['producto'] = {
                    'nombre': producto.get('nombre'),
                    'descripcion': producto.get('descripcion'),
                    'fotos': producto.get('fotos', []),
                    'categoria': producto.get('categoria'),
                    'empresa_nombre': producto.get('empresa_nombre')
                }
                items_con_detalles.append(item_completo)
        
        return items_con_detalles


# ================================================================
# FUNCIÓN DE UTILIDAD PARA CARRITO EN SESIÓN
# ================================================================

def carrito_session_to_dict(carrito_session):
    """
    Convierte el carrito de sesión al formato del modelo Carrito
    """
    if not carrito_session:
        return {'items': [], 'subtotal': 0, 'iva': 0, 'total': 0}
    
    subtotal = sum(
        float(item.get('precio', 0)) * int(item.get('cantidad', 1)) 
        for item in carrito_session
    )
    iva = subtotal * 0.16
    total = subtotal + iva
    
    return {
        'items': carrito_session,
        'subtotal': subtotal,
        'iva': iva,
        'total': total,
        'total_items': sum(item.get('cantidad', 0) for item in carrito_session)
    }


def carrito_session_to_db(usuario_id):
    """
    Migra el carrito de la sesión a la base de datos
    (Para cuando un usuario inicia sesión)
    """
    from flask import session
    
    # Obtener carrito de sesión
    carrito_session = session.get('carrito', [])
    if not carrito_session:
        return
    
    # Obtener o crear carrito en DB
    carrito_db = Carrito.obtener_o_crear(usuario_id)
    
    # Migrar items de sesión a DB
    for item in carrito_session:
        carrito_db.agregar_item(
            producto_id=item.get('id'),
            nombre=item.get('nombre', 'Producto'),
            precio=item.get('precio', 0),
            imagen=item.get('imagen', 'default.jpg'),
            cantidad=item.get('cantidad', 1),
            atributos=item.get('atributos', {})
        )
    
    carrito_db.save()
    
    # Limpiar carrito de sesión
    session['carrito'] = []
    session.modified = True


# ================================================================
# FUNCIÓN PARA INTEGRAR CON EL CONTROLADOR EXISTENTE
# ================================================================

def obtener_carrito_para_template(usuario_id=None):
    """
    Obtiene el carrito para mostrar en el template
    Si hay usuario autenticado, usa la DB, si no, usa la sesión
    """
    from flask import session
    
    if usuario_id:
        # Usuario autenticado - obtener de DB
        carrito = Carrito.obtener_o_crear(usuario_id)
        carrito.calcular_totales()
        carrito.save()
        return carrito.to_dict()
    else:
        # Usuario no autenticado - obtener de sesión
        carrito_session = session.get('carrito', [])
        return carrito_session_to_dict(carrito_session)