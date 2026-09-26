# ================================================================
# MODELO: MARKETPLACE (Vendedores terceros)
# ================================================================
import re
import secrets
from datetime import datetime, timezone
from bson import ObjectId


class Vendedor:
    """Modelo de vendedores terceros del marketplace."""

    COLLECTION = 'vendedores'

    ESTADOS = {
        'pendiente':  {'label': 'Pendiente',  'color': '#f59e0b', 'icon': '⏳'},
        'aprobado':   {'label': 'Aprobado',   'color': '#10b981', 'icon': '✅'},
        'rechazado':  {'label': 'Rechazado',  'color': '#ef4444', 'icon': '❌'},
        'suspendido': {'label': 'Suspendido', 'color': '#64748b', 'icon': '⏸️'},
    }

    # ------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------
    @classmethod
    def crear(cls, db, data, user_id):
        ahora = datetime.now(timezone.utc)

        doc = {
            'user_id':           ObjectId(user_id) if isinstance(user_id, str) else user_id,
            'slug':              cls._generar_slug(data.get('nombre_tienda', 'tienda')),
            'nombre_tienda':     (data.get('nombre_tienda') or '').strip(),
            'descripcion':       (data.get('descripcion') or '').strip(),
            'logo':              data.get('logo', ''),
            'banner':            data.get('banner', ''),
            'rfc':               (data.get('rfc') or '').strip().upper(),
            'razon_social':      (data.get('razon_social') or '').strip(),
            'telefono':          (data.get('telefono') or '').strip(),
            'email_contacto':    (data.get('email_contacto') or '').strip(),
            'direccion':         data.get('direccion', {}),
            'banco': {
                'banco':     (data.get('banco_nombre') or '').strip(),
                'clabe':     (data.get('banco_clabe') or '').strip(),
                'titular':   (data.get('banco_titular') or '').strip(),
            },
            'comision_pct':      float(data.get('comision_pct', 15.0)),
            'categorias':        data.get('categorias', []),
            'estado':            'pendiente',
            'motivo_rechazo':    '',
            'notas_admin':       '',
            'activo':            True,
            'destacado':         False,
            'metricas': {
                'productos':   0,
                'ventas':      0,
                'ingresos':    0.0,
                'comisiones':  0.0,
                'rating':      0.0,
            },
            'created_at':        ahora,
            'updated_at':        ahora,
        }

        result = db[cls.COLLECTION].insert_one(doc)
        return str(result.inserted_id)

    # ------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------
    @staticmethod
    def _generar_slug(nombre):
        base = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-') or 'tienda'
        return f"{base}-{secrets.token_hex(3)}"

    @staticmethod
    def _to_oid(val):
        try:
            return ObjectId(str(val))
        except Exception:
            return None

    # ------------------------------------------------------------
    # OBTENER
    # ------------------------------------------------------------
    @classmethod
    def obtener_por_id(cls, db, vid):
        oid = cls._to_oid(vid)
        return db[cls.COLLECTION].find_one({'_id': oid}) if oid else None

    @classmethod
    def obtener_por_slug(cls, db, slug):
        return db[cls.COLLECTION].find_one({'slug': slug})

    @classmethod
    def obtener_por_user(cls, db, user_id):
        oid = cls._to_oid(user_id)
        return db[cls.COLLECTION].find_one({'user_id': oid}) if oid else None

    @classmethod
    def listar(cls, db, estado=None, solo_activos=True, limite=100):
        query = {}
        if estado and estado != 'todos':
            query['estado'] = estado
        if solo_activos:
            query['activo'] = True
        return list(db[cls.COLLECTION].find(query).sort('created_at', -1).limit(limite))

    # ------------------------------------------------------------
    # ACTUALIZAR ESTADO
    # ------------------------------------------------------------
    @classmethod
    def cambiar_estado(cls, db, vid, nuevo_estado, motivo=''):
        oid = cls._to_oid(vid)
        if not oid:
            return False

        update = {
            'estado':       nuevo_estado,
            'updated_at':   datetime.now(timezone.utc),
        }
        if nuevo_estado == 'rechazado':
            update['motivo_rechazo'] = motivo

        r = db[cls.COLLECTION].update_one({'_id': oid}, {'$set': update})
        return r.modified_count > 0

    @classmethod
    def actualizar(cls, db, vid, data):
        oid = cls._to_oid(vid)
        if not oid:
            return False
        data['updated_at'] = datetime.now(timezone.utc)
        r = db[cls.COLLECTION].update_one({'_id': oid}, {'$set': data})
        return r.modified_count > 0

    @classmethod
    def eliminar(cls, db, vid):
        oid = cls._to_oid(vid)
        if not oid:
            return False
        r = db[cls.COLLECTION].delete_one({'_id': oid})
        return r.deleted_count > 0

    # ------------------------------------------------------------
    # FORMATEO PARA TEMPLATES
    # ------------------------------------------------------------
    @staticmethod
    def formatear(v):
        if not v:
            return None

        estado = v.get('estado', 'pendiente')
        info = Vendedor.ESTADOS.get(estado, Vendedor.ESTADOS['pendiente'])

        v['_id'] = str(v['_id'])
        v['user_id'] = str(v.get('user_id') or '')
        v['estado_label'] = info['label']
        v['estado_color'] = info['color']
        v['estado_icon'] = info['icon']

        # Fechas formateadas
        for k in ('created_at', 'updated_at'):
            f = v.get(k)
            if hasattr(f, 'strftime'):
                v[k + '_fmt'] = f.strftime('%d/%m/%Y %H:%M')

        # Métricas
        m = v.get('metricas') or {}
        v['metricas'] = {
            'productos':  int(m.get('productos', 0)),
            'ventas':     int(m.get('ventas', 0)),
            'ingresos':   float(m.get('ingresos', 0)),
            'comisiones': float(m.get('comisiones', 0)),
            'rating':     float(m.get('rating', 0)),
        }

        return v