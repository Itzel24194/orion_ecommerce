# app/models/promocion_model.py
# ================================================================
# Modelo para promociones estilo Liverpool
# ================================================================
from flask import current_app
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timezone, date


# ================================================================
# HELPERS
# ================================================================
def _safe_oid(value):
    """Devuelve ObjectId válido o None."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def _parse_fecha(value):
    """Convierte a datetime naive UTC o None. Acepta datetime, date, string ISO y 'YYYY-MM-DD'."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        try:
            ts = value / 1000 if value > 1e12 else value
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            if d.tzinfo is not None:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except ValueError:
            pass
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
            try:
                return datetime.strptime(s[:10], fmt)
            except ValueError:
                continue
    return None


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _string_id_seguro(valor):
    """Evita que caracteres como '.' o '$' rompan el update de Mongo en las claves."""
    if valor is None:
        return 'anonimo'
    v = str(valor).strip()
    if not v:
        return 'anonimo'
    return v.replace('.', '_').replace('$', '_')


# ================================================================
# MODELO
# ================================================================
class Promocion:
    """Modelo para promociones estilo Liverpool."""

    @staticmethod
    def get_collection():
        db = current_app.db
        try:
            nombres = db.list_collection_names()
            if 'promociones' not in nombres:
                db.create_collection('promociones')
        except Exception:
            # Algunos drivers fallan en list_collection_names con réplica sets
            pass
        return db.promociones

    # ================================================================
    # CRUD
    # ================================================================
    @staticmethod
    def crear(data):
        db = Promocion.get_collection()

        # Código único (solo si viene)
        codigo = data.get('codigo')
        if codigo and isinstance(codigo, str) and codigo.strip():
            codigo_upper = codigo.upper().strip()
            if db.find_one({'codigo': codigo_upper}):
                raise ValueError('El código de promoción ya existe')
        else:
            codigo_upper = None

        ahora = _now()

        promocion = {
            'nombre': (data.get('nombre') or '').strip(),
            'descripcion': (data.get('descripcion') or '').strip(),
            'tipo': data['tipo'],
            'activo': bool(data.get('activo', True)),
            'prioridad': int(data.get('prioridad', 0) or 0),
            'imagen': data.get('imagen', '') or '',
            'codigo': codigo_upper,
            'fecha_inicio': _parse_fecha(data.get('fecha_inicio')),
            'fecha_fin': _parse_fecha(data.get('fecha_fin')),
            'descuento_tipo': data.get('descuento_tipo'),
            'descuento_valor': float(data.get('descuento_valor', 0) or 0),
            'monto_minimo': float(data.get('monto_minimo', 0) or 0),
            'cantidad_requerida': int(data.get('cantidad_requerida', 0) or 0),
            'cantidad_gratis': int(data.get('cantidad_gratis', 0) or 0),
            'combo_productos': data.get('combo_productos', []) or [],
            'combo_descuento': float(data.get('combo_descuento', 0) or 0),
            'productos_aplicables': data.get('productos_aplicables', []) or [],
            'categorias_aplicables': data.get('categorias_aplicables', []) or [],
            'marcas_aplicables': data.get('marcas_aplicables', []) or [],
            'segmentos': data.get('segmentos') or ['todos'],
            'metodos_pago': data.get('metodos_pago', []) or [],
            'uso_maximo': int(data.get('uso_maximo', 0) or 0) or None,
            'usos_por_usuario': int(data.get('usos_por_usuario', 0) or 0) or None,
            'usos_actuales': 0,
            'usos_por_usuario_registro': {},
            'mostrar_en_home': bool(data.get('mostrar_en_home', False)),
            'mostrar_en_producto': bool(data.get('mostrar_en_producto', False)),
            'created_at': ahora,
            'updated_at': ahora,
        }
        result = db.insert_one(promocion)
        promocion['_id'] = str(result.inserted_id)
        return promocion

    @staticmethod
    def obtener_por_id(promocion_id):
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return None
        promocion = db.find_one({'_id': oid})
        if promocion:
            promocion['_id'] = str(promocion['_id'])
        return promocion

    @staticmethod
    def obtener_por_codigo(codigo):
        if not codigo:
            return None
        db = Promocion.get_collection()
        promocion = db.find_one({'codigo': str(codigo).upper().strip()})
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
                query['codigo'] = {'$regex': str(filtros['codigo']).upper(), '$options': 'i'}
            if filtros.get('nombre'):
                query['nombre'] = {'$regex': filtros['nombre'], '$options': 'i'}
            if filtros.get('segmento'):
                query['segmentos'] = filtros['segmento']
            if filtros.get('fecha_desde') or filtros.get('fecha_hasta'):
                rango = {}
                if filtros.get('fecha_desde'):
                    rango['$gte'] = _parse_fecha(filtros['fecha_desde'])
                if filtros.get('fecha_hasta'):
                    rango['$lte'] = _parse_fecha(filtros['fecha_hasta'])
                if rango:
                    query['fecha_inicio'] = rango

        promociones = list(
            db.find(query).sort([('prioridad', -1), ('created_at', -1)])
        )
        for p in promociones:
            p['_id'] = str(p['_id'])
        return promociones

    @staticmethod
    def actualizar(promocion_id, data):
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return False

        update_data = {}
        campos_permitidos = [
            'nombre', 'descripcion', 'tipo', 'activo', 'prioridad', 'imagen', 'codigo',
            'fecha_inicio', 'fecha_fin', 'descuento_tipo', 'descuento_valor',
            'monto_minimo', 'cantidad_requerida', 'cantidad_gratis',
            'combo_productos', 'combo_descuento',
            'productos_aplicables', 'categorias_aplicables', 'marcas_aplicables',
            'segmentos', 'metodos_pago', 'uso_maximo', 'usos_por_usuario',
            'mostrar_en_home', 'mostrar_en_producto',
        ]

        for campo in campos_permitidos:
            if campo not in data:
                continue
            valor = data[campo]

            if campo == 'codigo':
                if valor and isinstance(valor, str) and valor.strip():
                    codigo_upper = valor.upper().strip()
                    existente = db.find_one({
                        'codigo': codigo_upper,
                        '_id': {'$ne': oid},
                    })
                    if existente:
                        raise ValueError('El código de promoción ya existe en otra promoción')
                    update_data[campo] = codigo_upper
                else:
                    update_data[campo] = None

            elif campo in ('fecha_inicio', 'fecha_fin'):
                update_data[campo] = _parse_fecha(valor)

            elif campo in ('descuento_valor', 'combo_descuento', 'monto_minimo'):
                try:
                    update_data[campo] = float(valor or 0)
                except (ValueError, TypeError):
                    update_data[campo] = 0.0

            elif campo in ('cantidad_requerida', 'cantidad_gratis', 'uso_maximo',
                           'usos_por_usuario', 'prioridad'):
                try:
                    update_data[campo] = int(valor or 0) or None
                except (ValueError, TypeError):
                    update_data[campo] = None

            elif campo == 'activo':
                update_data[campo] = bool(valor)

            elif campo in ('mostrar_en_home', 'mostrar_en_producto'):
                update_data[campo] = bool(valor)

            else:
                update_data[campo] = valor

        update_data['updated_at'] = _now()

        try:
            result = db.update_one({'_id': oid}, {'$set': update_data})
            return result.modified_count > 0
        except Exception:
            return False

    @staticmethod
    def eliminar(promocion_id):
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return False
        result = db.delete_one({'_id': oid})
        return result.deleted_count > 0

    @staticmethod
    def toggle_activo(promocion_id, activo=None):
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return False

        if activo is None:
            promocion = db.find_one({'_id': oid})
            activo = not promocion.get('activo', True) if promocion else True

        result = db.update_one(
            {'_id': oid},
            {'$set': {'activo': bool(activo), 'updated_at': _now()}},
        )
        return result.modified_count > 0

    # ================================================================
    # VALIDACIÓN Y APLICACIÓN
    # ================================================================
    @staticmethod
    def es_valida(promocion, usuario_id=None, monto_carrito=0,
                  productos_carrito=None, metodo_pago=None):
        if not promocion:
            return False, 'Promoción no encontrada', None

        if not promocion.get('activo', True):
            return False, 'La promoción no está activa', None

        ahora = _now()
        fi = _parse_fecha(promocion.get('fecha_inicio'))
        ff = _parse_fecha(promocion.get('fecha_fin'))

        if fi and fi > ahora:
            return False, 'La promoción aún no está disponible', None
        if ff and ff < ahora:
            return False, 'La promoción ha expirado', None

        uso_maximo = promocion.get('uso_maximo')
        if uso_maximo and int(promocion.get('usos_actuales', 0) or 0) >= int(uso_maximo):
            return False, 'La promoción ya ha alcanzado su límite de usos', None

        if usuario_id and promocion.get('usos_por_usuario'):
            registro = promocion.get('usos_por_usuario_registro', {}) or {}
            # CORREGIDO: usamos _string_id_seguro para buscar en el registro
            uid_seguro = _string_id_seguro(usuario_id)
            usos_usuario = int(registro.get(uid_seguro, 0) or 0)
            if usos_usuario >= int(promocion.get('usos_por_usuario', 1) or 1):
                return False, 'Ya has utilizado esta promoción el número máximo de veces', None

        monto_minimo = float(promocion.get('monto_minimo', 0) or 0)
        if float(monto_carrito or 0) < monto_minimo:
            return False, f'El monto mínimo es de ${monto_minimo:,.0f}', None

        metodos = [str(m).strip().lower() for m in (promocion.get('metodos_pago') or []) if m]
        if metodos and metodo_pago:
            if str(metodo_pago).strip().lower() not in metodos:
                return False, 'La promoción no aplica para este método de pago', None

        descuento = Promocion.calcular_descuento(promocion, monto_carrito, productos_carrito)
        descuento = max(0, min(descuento, float(monto_carrito or 0)))
        detalles = {
            'descuento': round(descuento, 2),
            'monto_final': round(float(monto_carrito or 0) - descuento, 2),
            'tipo': promocion.get('tipo'),
        }
        return True, 'Promoción válida', detalles

    @staticmethod
    def calcular_descuento(promocion, monto_carrito, productos_carrito=None):
        tipo = promocion.get('tipo')
        monto_carrito = float(monto_carrito or 0)

        if tipo in ('descuento_directo', 'pago'):
            dv = float(promocion.get('descuento_valor', 0) or 0)
            if promocion.get('descuento_tipo') == 'porcentaje':
                return monto_carrito * (dv / 100)
            return min(dv, monto_carrito)

        if tipo == 'cantidad':
            if not productos_carrito:
                return 0
            cantidad_requerida = int(promocion.get('cantidad_requerida', 2) or 2)
            cantidad_gratis = int(promocion.get('cantidad_gratis', 1) or 1)
            if cantidad_requerida <= 0 or cantidad_gratis <= 0:
                return 0
            ordenados = sorted(productos_carrito, key=lambda x: float(x.get('precio', 0) or 0))
            total = 0.0
            for prod in ordenados:
                cantidad = int(prod.get('cantidad', 1) or 1)
                precio = float(prod.get('precio', 0) or 0)
                if cantidad >= cantidad_requerida:
                    veces = cantidad // cantidad_requerida
                    total += veces * cantidad_gratis * precio
            return total

        if tipo == 'combo':
            if not productos_carrito:
                return 0
            combo = {str(p) for p in (promocion.get('combo_productos') or []) if p is not None}
            if not combo:
                return 0
            en_carrito = {str(p.get('producto_id')) for p in productos_carrito if p.get('producto_id') is not None}
            if combo.issubset(en_carrito):
                descuento_pct = float(promocion.get('combo_descuento', 0) or 0) / 100
                return monto_carrito * descuento_pct
            return 0

        if tipo == 'envio_gratis':
            return 0

        return 0

    @staticmethod
    def registrar_uso(promocion_id, usuario_id, monto_aplicado=0):
        """Incrementa usos_actuales y el contador por usuario."""
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return False

        # CORREGIDO: Sanitizar el ID del usuario para que Mongo no falle si tiene puntos
        uid_seguro = _string_id_seguro(usuario_id)

        update = {
            '$inc': {
                'usos_actuales': 1,
                f'usos_por_usuario_registro.{uid_seguro}': 1,
            },
            '$set': {'updated_at': _now()},
        }
        try:
            db.update_one({'_id': oid}, update, upsert=False)
            return True
        except Exception:
            return False

    # ================================================================
    # CLIENTE
    # ================================================================
    @staticmethod
    def _filtro_vigente():
        """Filtro correcto sin $or duplicado."""
        ahora = _now()
        return {
            'activo': True,
            '$and': [
                {'$or': [{'fecha_inicio': {'$lte': ahora}}, {'fecha_inicio': None}]},
                {'$or': [{'fecha_fin': {'$gte': ahora}}, {'fecha_fin': None}]},
            ],
        }

    @staticmethod
    def obtener_promociones_disponibles(usuario_id=None, monto_carrito=0,
                                        productos_carrito=None, metodo_pago=None):
        """Compatibilidad legacy. El controlador usa su propia versión más completa."""
        db = Promocion.get_collection()
        try:
            promociones = list(db.find(Promocion._filtro_vigente()).sort('prioridad', -1))
        except Exception:
            return []

        disponibles = []
        for p in promociones:
            p['_id'] = str(p['_id'])
            valida, mensaje, detalles = Promocion.es_valida(
                p, usuario_id, monto_carrito, productos_carrito, metodo_pago,
            )
            if valida:
                p['detalles'] = detalles
                disponibles.append(p)
        return disponibles

    @staticmethod
    def obtener_promociones_destacadas(usuario_id=None, limite=6):
        db = Promocion.get_collection()
        filtro = Promocion._filtro_vigente()
        filtro['mostrar_en_home'] = True
        try:
            promociones = list(
                db.find(filtro).sort('prioridad', -1).limit(limite)
            )
        except Exception:
            return []

        for p in promociones:
            p['_id'] = str(p['_id'])

        if usuario_id:
            try:
                from app.models.usuarios_model import Usuario
                segmento = (Usuario.obtener_segmento(usuario_id) or '').lower()
            except Exception:
                segmento = ''
            promociones = [
                p for p in promociones
                if 'todos' in [s.lower() for s in (p.get('segmentos') or ['todos']) if s]
                or segmento in [s.lower() for s in (p.get('segmentos') or []) if s]
            ]
        return promociones

    @staticmethod
    def obtener_estadisticas(promocion_id):
        db = Promocion.get_collection()
        oid = _safe_oid(promocion_id)
        if not oid:
            return {}
        promocion = db.find_one({'_id': oid})
        if not promocion:
            return {}
        registro = promocion.get('usos_por_usuario_registro', {}) or {}
        return {
            'usos_actuales': int(promocion.get('usos_actuales', 0) or 0),
            'uso_maximo': promocion.get('uso_maximo'),
            'usos_por_usuario': registro,
            'total_usuarios': len(registro),
        }