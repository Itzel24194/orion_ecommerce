# ================================================================
# MODELO: MESA DE REGALOS
# ================================================================
import re
from datetime import datetime
from bson import ObjectId


class MesaRegalos:
    """Modelo de mesas de regalos (bodas, baby showers, XV, etc.)"""

    COLLECTION = 'mesas_regalos'

    TIPOS_EVENTO = {
        'boda':             {'emoji': '💍', 'nombre': 'Boda'},
        'baby_shower':      {'emoji': '🍼', 'nombre': 'Baby Shower'},
        'xv_anos':          {'emoji': '✨', 'nombre': 'XV Años'},
        'cumpleanos':       {'emoji': '🎂', 'nombre': 'Cumpleaños'},
        'bautizo':          {'emoji': '💧', 'nombre': 'Bautizo'},
        'primera_comunion': {'emoji': '📖', 'nombre': 'Primera Comunión'},
        'graduacion':       {'emoji': '🎓', 'nombre': 'Graduación'},
        'otro':             {'emoji': '🎁', 'nombre': 'Otro'},
    }

    # ------------------------------------------------------------
    # UTILIDADES
    # ------------------------------------------------------------
    @staticmethod
    def _generar_slug(nombre_evento):
        base = re.sub(r'[^a-z0-9]+', '-', nombre_evento.lower()).strip('-')
        sufijo = datetime.now().strftime('%y%m%d%H%M%S')
        return f"{base}-{sufijo}"

    @staticmethod
    def _to_object_id(id_str):
        try:
            return ObjectId(id_str)
        except Exception:
            return None

    # ------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------
    @classmethod
    def crear(cls, db, data, owner_id):
        ahora = datetime.utcnow()

        gifts = []
        for g in data.get('gifts', []):
            gifts.append({
                'producto_id':   g.get('id'),
                'nombre':        g.get('nombre', ''),
                'precio':        float(g.get('precio', 0)),
                'imagen':        g.get('imagen', 'default.jpg'),
                'reservado':     False,
                'reservado_por': None,
                'reservado_at':  None,
            })

        doc = {
            'slug':          cls._generar_slug(data['event_name']),
            'owner_id':      ObjectId(owner_id) if isinstance(owner_id, str) else owner_id,
            'owner_email':   data.get('owner_email', ''),
            'event_type':    data.get('event_type', 'otro'),
            'event_name':    data.get('event_name', ''),
            'event_date':    data.get('event_date', ''),
            'honoree_name':  data.get('honoree_name', ''),
            'message':       data.get('message', ''),
            'gifts':         gifts,
            'gifts_total':   len(gifts),
            'gifts_claimed': 0,
            'fund_goal':     float(data.get('fund_goal', 0)),
            'fund_raised':   0.0,
            'guests':        [],
            'activa':        True,
            'created_at':    ahora,
            'updated_at':    ahora,
        }

        result = db[cls.COLLECTION].insert_one(doc)
        return str(result.inserted_id)

    # ------------------------------------------------------------
    # OBTENER
    # ------------------------------------------------------------
    @classmethod
    def obtener_por_id(cls, db, mesa_id):
        oid = cls._to_object_id(mesa_id)
        if not oid:
            return None
        return db[cls.COLLECTION].find_one({'_id': oid})

    @classmethod
    def obtener_por_slug(cls, db, slug):
        return db[cls.COLLECTION].find_one({'slug': slug})

    @classmethod
    def obtener_por_owner(cls, db, owner_id):
        oid = ObjectId(owner_id) if isinstance(owner_id, str) else owner_id
        return list(
            db[cls.COLLECTION]
              .find({'owner_id': oid})
              .sort('created_at', -1)
        )

    # ------------------------------------------------------------
    # RESERVAR REGALO
    # ------------------------------------------------------------
    @classmethod
    def reservar_regalo(cls, db, mesa_id, gift_index, nombre_invitado, email_invitado=None):
        oid = cls._to_object_id(mesa_id)
        if not oid:
            return False

        ahora = datetime.utcnow()

        result = db[cls.COLLECTION].update_one(
            {
                '_id': oid,
                f'gifts.{gift_index}.reservado': False
            },
            {
                '$set': {
                    f'gifts.{gift_index}.reservado': True,
                    f'gifts.{gift_index}.reservado_por': nombre_invitado,
                    f'gifts.{gift_index}.reservado_at': ahora,
                    'updated_at': ahora,
                },
                '$inc': {'gifts_claimed': 1},
                '$push': {
                    'guests': {
                        'nombre': nombre_invitado,
                        'email':  email_invitado,
                        'tipo':   'regalo',
                        'regalo': f'gifts.{gift_index}',
                        'monto':  0,
                        'fecha':  ahora,
                    }
                }
            }
        )
        return result.modified_count > 0

    # ------------------------------------------------------------
    # CONTRIBUIR AL FONDO DE EFECTIVO
    # ------------------------------------------------------------
    @classmethod
    def contribuir_efectivo(cls, db, mesa_id, monto, nombre_invitado, email_invitado=None):
        oid = cls._to_object_id(mesa_id)
        if not oid:
            return False

        ahora = datetime.utcnow()
        monto = float(monto)

        result = db[cls.COLLECTION].update_one(
            {'_id': oid},
            {
                '$inc': {'fund_raised': monto},
                '$set': {'updated_at': ahora},
                '$push': {
                    'guests': {
                        'nombre': nombre_invitado,
                        'email':  email_invitado,
                        'tipo':   'efectivo',
                        'regalo': 'Fondo de efectivo',
                        'monto':  monto,
                        'fecha':  ahora,
                    }
                }
            }
        )
        return result.modified_count > 0

    # ------------------------------------------------------------
    # ELIMINAR
    # ------------------------------------------------------------
    @classmethod
    def eliminar(cls, db, mesa_id, owner_id):
        oid = cls._to_object_id(mesa_id)
        owner_oid = ObjectId(owner_id) if isinstance(owner_id, str) else owner_id
        if not oid:
            return False
        result = db[cls.COLLECTION].delete_one({'_id': oid, 'owner_id': owner_oid})
        return result.deleted_count > 0

    # ------------------------------------------------------------
    # HELPERS DE PRESENTACIÓN
    # ------------------------------------------------------------
    @staticmethod
    def formatear_mesa(mesa):
        if not mesa:
            return None

        tipo = mesa.get('event_type', 'otro')
        info = MesaRegalos.TIPOS_EVENTO.get(tipo, MesaRegalos.TIPOS_EVENTO['otro'])

        fecha_str = mesa.get('event_date', '')
        try:
            dt = datetime.strptime(fecha_str, '%Y-%m-%d')
            meses = {
                'January': 'enero', 'February': 'febrero', 'March': 'marzo',
                'April': 'abril', 'May': 'mayo', 'June': 'junio',
                'July': 'julio', 'August': 'agosto', 'September': 'septiembre',
                'October': 'octubre', 'November': 'noviembre', 'December': 'diciembre'
            }
            fecha_fmt = dt.strftime('%d de %B, %Y')
            for en, es in meses.items():
                fecha_fmt = fecha_fmt.replace(en, es)
        except Exception:
            fecha_fmt = fecha_str

        mesa['_id'] = str(mesa['_id'])
        mesa['event_date_formatted'] = fecha_fmt
        mesa['emoji'] = info['emoji']
        mesa['tipo_nombre'] = info['nombre']
        mesa['bonificacion_estimada'] = round(
            (sum(g.get('precio', 0) for g in mesa.get('gifts', [])) +
             mesa.get('fund_raised', 0)) * 0.10, 2
        )
        return mesa