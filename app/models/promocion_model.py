# app/models/promocion_model.py

from flask import current_app
from bson import ObjectId
from datetime import datetime, timezone

class Promocion:
    """Modelo para promociones estilo Liverpool."""

    @staticmethod
    def get_collection():
        db = current_app.db
        if 'promociones' not in db.list_collection_names():
            db.create_collection('promociones')
        return db.promociones

    # ================================================================
    # CRUD
    # ================================================================

    @staticmethod
    def crear(data):
        db = Promocion.get_collection()
        
        # 🔥 Manejo seguro del código: solo validar si no es None ni cadena vacía
        codigo = data.get('codigo')
        if codigo and isinstance(codigo, str) and codigo.strip():
            codigo_upper = codigo.upper().strip()
            # Verificar que no exista otra promoción con el mismo código (ignorando las que tengan código None o vacío)
            if db.find_one({'codigo': codigo_upper}):
                raise ValueError('El código de promoción ya existe')
        else:
            codigo_upper = None  # Guardamos None para códigos vacíos

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)

        promocion = {
            'nombre': data.get('nombre', '').strip(),
            'descripcion': data.get('descripcion', '').strip(),
            'tipo': data['tipo'],
            'activo': data.get('activo', True),
            'prioridad': int(data.get('prioridad', 0)),
            'imagen': data.get('imagen', ''),
            'codigo': codigo_upper,
            'fecha_inicio': data.get('fecha_inicio'),
            'fecha_fin': data.get('fecha_fin'),
            'descuento_tipo': data.get('descuento_tipo'),
            'descuento_valor': float(data.get('descuento_valor', 0)),
            'monto_minimo': float(data.get('monto_minimo', 0)),
            'cantidad_requerida': int(data.get('cantidad_requerida', 0)),
            'cantidad_gratis': int(data.get('cantidad_gratis', 0)),
            'combo_productos': data.get('combo_productos', []),
            'combo_descuento': float(data.get('combo_descuento', 0)),
            'productos_aplicables': data.get('productos_aplicables', []),
            'categorias_aplicables': data.get('categorias_aplicables', []),
            'empresas_aplicables': data.get('empresas_aplicables', []),
            'segmentos': data.get('segmentos', ['todos']),
            'metodos_pago': data.get('metodos_pago', []),
            'uso_maximo': int(data.get('uso_maximo', 0)) or None,
            'usos_por_usuario': int(data.get('usos_por_usuario', 0)) or None,
            'usos_actuales': 0,
            'usos_por_usuario_registro': {},
            'mostrar_en_home': data.get('mostrar_en_home', False),
            'mostrar_en_producto': data.get('mostrar_en_producto', False),
            'created_at': ahora,
            'updated_at': ahora
        }
        result = db.insert_one(promocion)
        promocion['_id'] = str(result.inserted_id)
        return promocion

    @staticmethod
    def obtener_por_id(promocion_id):
        db = Promocion.get_collection()
        try:
            promocion = db.find_one({'_id': ObjectId(promocion_id)})
        except:
            return None
        if promocion:
            promocion['_id'] = str(promocion['_id'])
        return promocion

    @staticmethod
    def obtener_por_codigo(codigo):
        if not codigo:
            return None
        db = Promocion.get_collection()
        promocion = db.find_one({'codigo': codigo.upper()})
        if promocion:
            promocion['_id'] = str(promocion['_id'])
        return promocion

    @staticmethod
    def obtener_todos(filtros=None):
        db = Promocion.get_collection()
        query = {}
        if filtros:
            if filtros.get('activo') is not None:
                query['activo'] = filtros['activo']
            if filtros.get('tipo'):
                query['tipo'] = filtros['tipo']
            if filtros.get('codigo'):
                query['codigo'] = {'$regex': filtros['codigo'].upper(), '$options': 'i'}
            if filtros.get('nombre'):
                query['nombre'] = {'$regex': filtros['nombre'], '$options': 'i'}
        promociones = list(db.find(query).sort('prioridad', -1).sort('created_at', -1))
        for p in promociones:
            p['_id'] = str(p['_id'])
        return promociones

    @staticmethod
    def actualizar(promocion_id, data):
        db = Promocion.get_collection()
        update_data = {}
        campos_permitidos = [
            'nombre', 'descripcion', 'tipo', 'activo', 'prioridad', 'imagen', 'codigo',
            'fecha_inicio', 'fecha_fin', 'descuento_tipo', 'descuento_valor',
            'monto_minimo', 'cantidad_requerida', 'cantidad_gratis',
            'combo_productos', 'combo_descuento',
            'productos_aplicables', 'categorias_aplicables', 'empresas_aplicables',
            'segmentos', 'metodos_pago', 'uso_maximo', 'usos_por_usuario',
            'mostrar_en_home', 'mostrar_en_producto'
        ]
        for campo in campos_permitidos:
            if campo in data:
                if campo == 'codigo':
                    codigo_valor = data[campo]
                    if codigo_valor and isinstance(codigo_valor, str) and codigo_valor.strip():
                        codigo_upper = codigo_valor.upper().strip()
                        # Verificar que no exista otro con el mismo código (excepto la propia promoción)
                        existente = db.find_one({
                            'codigo': codigo_upper,
                            '_id': {'$ne': ObjectId(promocion_id)}
                        })
                        if existente:
                            raise ValueError('El código de promoción ya existe en otra promoción')
                        update_data[campo] = codigo_upper
                    else:
                        update_data[campo] = None  # Guardar None si está vacío
                elif campo in ['descuento_valor', 'combo_descuento', 'monto_minimo']:
                    update_data[campo] = float(data[campo] or 0)
                elif campo in ['cantidad_requerida', 'cantidad_gratis', 'uso_maximo', 'usos_por_usuario', 'prioridad']:
                    update_data[campo] = int(data[campo] or 0) or None
                else:
                    update_data[campo] = data[campo]
        update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
        result = db.update_one(
            {'_id': ObjectId(promocion_id)},
            {'$set': update_data}
        )
        return result.modified_count > 0

    @staticmethod
    def eliminar(promocion_id):
        db = Promocion.get_collection()
        result = db.delete_one({'_id': ObjectId(promocion_id)})
        return result.deleted_count > 0

    @staticmethod
    def toggle_activo(promocion_id, activo=None):
        db = Promocion.get_collection()
        if activo is None:
            promocion = db.find_one({'_id': ObjectId(promocion_id)})
            activo = not promocion.get('activo', True) if promocion else True
        result = db.update_one(
            {'_id': ObjectId(promocion_id)},
            {'$set': {'activo': activo, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)}}
        )
        return result.modified_count > 0

    # ================================================================
    # MÉTODOS DE VALIDACIÓN Y APLICACIÓN
    # ================================================================

    @staticmethod
    def es_valida(promocion, usuario_id=None, monto_carrito=0, productos_carrito=None, metodo_pago=None):
        if not promocion:
            return False, 'Promoción no encontrada', None

        if not promocion.get('activo', True):
            return False, 'La promoción no está activa', None

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        if promocion.get('fecha_inicio') and promocion['fecha_inicio'] > ahora:
            return False, 'La promoción aún no está disponible', None

        if promocion.get('fecha_fin') and promocion['fecha_fin'] < ahora:
            return False, 'La promoción ha expirado', None

        uso_maximo = promocion.get('uso_maximo')
        if uso_maximo and promocion.get('usos_actuales', 0) >= uso_maximo:
            return False, 'La promoción ya ha alcanzado su límite de usos', None

        if usuario_id and promocion.get('usos_por_usuario'):
            usos_usuario = promocion.get('usos_por_usuario_registro', {}).get(str(usuario_id), 0)
            if usos_usuario >= promocion.get('usos_por_usuario', 1):
                return False, 'Ya has utilizado esta promoción el número máximo de veces', None

        monto_minimo = promocion.get('monto_minimo', 0)
        if monto_carrito < monto_minimo:
            return False, f'El monto mínimo es de ${monto_minimo:,.0f}', None

        if promocion.get('metodos_pago') and metodo_pago:
            if metodo_pago not in promocion['metodos_pago']:
                return False, 'La promoción no aplica para este método de pago', None

        descuento = Promocion.calcular_descuento(promocion, monto_carrito, productos_carrito)
        detalles = {
            'descuento': descuento,
            'monto_final': monto_carrito - descuento,
            'tipo': promocion.get('tipo')
        }
        return True, 'Promoción válida', detalles

    @staticmethod
    def calcular_descuento(promocion, monto_carrito, productos_carrito=None):
        tipo = promocion.get('tipo')
        if tipo == 'descuento_directo':
            if promocion.get('descuento_tipo') == 'porcentaje':
                return monto_carrito * (promocion.get('descuento_valor', 0) / 100)
            else:
                return min(promocion.get('descuento_valor', 0), monto_carrito)
        elif tipo == 'cantidad':
            if not productos_carrito:
                return 0
            cantidad_requerida = promocion.get('cantidad_requerida', 2)
            cantidad_gratis = promocion.get('cantidad_gratis', 1)
            productos_ordenados = sorted(productos_carrito, key=lambda x: x.get('precio', 0))
            total_gratis = 0
            for producto in productos_ordenados:
                cantidad = producto.get('cantidad', 1)
                if cantidad >= cantidad_requerida:
                    veces = cantidad // cantidad_requerida
                    total_gratis += veces * cantidad_gratis * producto.get('precio', 0)
            return total_gratis
        elif tipo == 'combo':
            if not productos_carrito:
                return 0
            combo_productos = [str(p) for p in promocion.get('combo_productos', [])]
            ids_carrito = [str(p.get('producto_id')) for p in productos_carrito]
            if all(p in ids_carrito for p in combo_productos):
                descuento_porcentaje = promocion.get('combo_descuento', 0) / 100
                return monto_carrito * descuento_porcentaje
            return 0
        elif tipo == 'envio_gratis':
            return 0
        elif tipo == 'pago':
            if promocion.get('descuento_tipo') == 'porcentaje':
                return monto_carrito * (promocion.get('descuento_valor', 0) / 100)
            else:
                return min(promocion.get('descuento_valor', 0), monto_carrito)
        else:
            return 0

    @staticmethod
    def registrar_uso(promocion_id, usuario_id, monto_aplicado):
        db = Promocion.get_collection()
        db.update_one(
            {'_id': ObjectId(promocion_id)},
            {
                '$inc': {'usos_actuales': 1},
                '$inc': {f'usos_por_usuario_registro.{usuario_id}': 1}
            }
        )

    # ================================================================
    # MÉTODOS PARA EL CLIENTE
    # ================================================================

    @staticmethod
    def obtener_promociones_disponibles(usuario_id=None, monto_carrito=0, productos_carrito=None, metodo_pago=None):
        # Este método está obsoleto, se usa el controlador para obtener con lógica mejorada
        # Se mantiene por compatibilidad, pero no se usa en el flujo principal
        db = Promocion.get_collection()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        promociones = list(db.find({
            'activo': True,
            '$or': [
                {'fecha_inicio': {'$lte': ahora}},
                {'fecha_inicio': None}
            ],
            '$or': [
                {'fecha_fin': {'$gte': ahora}},
                {'fecha_fin': None}
            ]
        }).sort('prioridad', -1))

        disponibles = []
        for p in promociones:
            p['_id'] = str(p['_id'])
            valida, mensaje, detalles = Promocion.es_valida(
                p, usuario_id, monto_carrito, productos_carrito, metodo_pago
            )
            if valida:
                p['detalles'] = detalles
                disponibles.append(p)
        return disponibles

    @staticmethod
    def obtener_promociones_destacadas(usuario_id=None):
        db = Promocion.get_collection()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        promociones = list(db.find({
            'activo': True,
            'mostrar_en_home': True,
            '$or': [
                {'fecha_inicio': {'$lte': ahora}},
                {'fecha_inicio': None}
            ],
            '$or': [
                {'fecha_fin': {'$gte': ahora}},
                {'fecha_fin': None}
            ]
        }).sort('prioridad', -1).limit(6))
        for p in promociones:
            p['_id'] = str(p['_id'])
        return promociones

    @staticmethod
    def obtener_estadisticas(promocion_id):
        db = Promocion.get_collection()
        promocion = db.find_one({'_id': ObjectId(promocion_id)})
        if not promocion:
            return {}
        return {
            'usos_actuales': promocion.get('usos_actuales', 0),
            'uso_maximo': promocion.get('uso_maximo'),
            'usos_por_usuario': promocion.get('usos_por_usuario_registro', {}),
            'total_usuarios': len(promocion.get('usos_por_usuario_registro', {}))
        }