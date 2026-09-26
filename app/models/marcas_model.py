# ================================================================
# app/models/marcas_model.py
# ================================================================

from bson.objectid import ObjectId
from datetime import datetime
from app.config.database_config import db

marcas_col = db['marcas']


class Marca:

    # ============================================================
    # LECTURA
    # ============================================================

    @staticmethod
    def obtener_todas(filtros=None):
        query = {}
        filtros = filtros or {}

        if filtros.get('status'):
            query['status'] = filtros['status']

        if filtros.get('activa') is not None:
            query['activa'] = filtros['activa']

        if filtros.get('q'):
            import re
            q = re.escape(filtros['q'])
            query['$or'] = [
                {'nombre_comercial': {'$regex': q, '$options': 'i'}},
                {'rfc': {'$regex': q, '$options': 'i'}},
                {'nombre_normalizado': {'$regex': q, '$options': 'i'}},
            ]

        return list(marcas_col.find(query).sort('nombre_comercial', 1))

    @staticmethod
    def obtener_por_id(marca_id):
        try:
            return marcas_col.find_one({"_id": ObjectId(marca_id)})
        except Exception:
            return None

    @staticmethod
    def buscar_por_nombre(nombre, parcial=False, limit=None):
        if not nombre:
            return None if not parcial else []

        if parcial:
            import re
            q = re.escape(nombre)
            cursor = marcas_col.find({
                'nombre_comercial': {'$regex': q, '$options': 'i'}
            })
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)

        return marcas_col.find_one({
            'nombre_normalizado': nombre.upper().replace(' ', '')
        })

    @staticmethod
    def buscar_por_rfc(rfc):
        if not rfc:
            return None
        return marcas_col.find_one({'rfc': rfc.upper().strip()})

    @staticmethod
    def estadisticas():
        return {
            'total': marcas_col.count_documents({}),
            'activas': marcas_col.count_documents({'status': 'activo'}),
            'pendientes': marcas_col.count_documents({'status': 'pendiente'}),
            'negadas': marcas_col.count_documents({'status': 'negado'}),
            'con_impi': marcas_col.count_documents({'datos_impi': {'$ne': []}}),
        }

    # ============================================================
    # ESCRITURA
    # ============================================================

    @staticmethod
    def crear(data):
        data.setdefault('created_at', datetime.utcnow())
        data.setdefault('updated_at', datetime.utcnow())
        return marcas_col.insert_one(data)

    @staticmethod
    def actualizar_datos(marca_id, data):
        try:
            return marcas_col.update_one(
                {"_id": ObjectId(marca_id)},
                {"$set": data}
            )
        except Exception as e:
            print(f"[Marca] Error actualizar_datos: {e}")
            return None

    @staticmethod
    def actualizar_con_notas(marca_id, nuevo_status, notas):
        try:
            return marcas_col.update_one(
                {"_id": ObjectId(marca_id)},
                {"$set": {
                    "status": nuevo_status,
                    "notas_admin": notas,
                    "updated_at": datetime.utcnow()
                }}
            )
        except Exception as e:
            print(f"[Marca] Error actualizar_con_notas: {e}")
            return None

    @staticmethod
    def actualizar_resultados_impi(marca_id, resultados):
        try:
            return marcas_col.update_one(
                {"_id": ObjectId(marca_id)},
                {"$set": {
                    "datos_impi": resultados,
                    "impi_actualizado": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
        except Exception as e:
            print(f"[Marca] Error actualizar_resultados_impi: {e}")
            return None

    @staticmethod
    def borrar(marca_id):
        try:
            return marcas_col.delete_one({"_id": ObjectId(marca_id)})
        except Exception as e:
            print(f"[Marca] Error borrar: {e}")
            return None

    # ============================================================
    # BÚSQUEDA FONÉTICA (SOUNDEX SIMPLIFICADO)
    # ============================================================

    @staticmethod
    def _soundex_simple(texto):
        """
        Algoritmo fonético simplificado para español.
        Convierte 'Nike' → 'NIK', 'Naik' → 'NAK', etc.
        """
        if not texto:
            return ""
        texto = texto.upper().strip()
        # Reemplazos fonéticos comunes en español
        texto = texto.replace('PH', 'F').replace('QU', 'K').replace('C', 'K')
        texto = texto.replace('Z', 'S').replace('X', 'KS').replace('V', 'B')
        texto = texto.replace('LL', 'Y').replace('H', '')
        # Conservar solo letras
        texto = ''.join(c for c in texto if c.isalpha())
        return texto[:6]

    @staticmethod
    def buscar_fonetica(nombre, limit=20):
        """
        Busca marcas con nombres fonéticamente similares.
        Ej: 'Naik' → encuentra 'Nike'
        """
        if not nombre:
            return []

        clave = Marca._soundex_simple(nombre)

        # Buscar todas y filtrar por soundex en Python (para bases pequeñas)
        todas = list(marcas_col.find({'activa': True}))
        resultados = []
        for m in todas:
            m_clave = Marca._soundex_simple(m.get('nombre_comercial', ''))
            if m_clave == clave or m_clave.startswith(clave[:3]):
                resultados.append(m)
                if len(resultados) >= limit:
                    break

        return resultados