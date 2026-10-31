# app/models/cupon_model.py - VERSIÓN DEFINITIVA CON SEGMENTACIÓN AUTOMÁTICA
# ================================================================
# NO importar app.models.cupon_model desde aquí (sería circular).
# Este archivo SOLO define clases y funciones auxiliares.
# ================================================================

from flask import current_app
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import random
import string
import sys


def get_db():
    """Obtener la base de datos desde la aplicación actual"""
    return current_app.db


# ================================================================
# ⭐ HELPER: convertir str/datetime/None a datetime naive UTC
# Acepta todos los formatos que se guardan en Mongo:
#   - datetime (naive o aware)
#   - str ISO 8601: "2026-01-01T00:00:00", "2026-01-01T00:00:00Z",
#     "2026-01-01T00:00:00+00:00", "2026-01-01 00:00:00"
#   - str simple: "2026-01-01", "01/01/2026", "2026/01/01"
# Devuelve None si no se puede parsear (para que el llamador lo trate como "sin fecha").
# ================================================================
def _to_datetime(valor):
    """Convierte str/datetime/None a datetime naive UTC. Devuelve None si falla."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(timezone.utc).replace(tzinfo=None)
        return valor
    if isinstance(valor, str):
        s = valor.strip()
        if not s:
            return None
        # ISO 8601 con T o espacio, con o sin Z, con o sin microsegundos
        s_iso = s.replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(s_iso)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            pass
        # Fallbacks para formatos comunes
        for fmt in (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y',
            '%Y/%m/%d',
        ):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None
    return None


def _ahora_utc_naive():
    """Devuelve datetime.utcnow() naive (consistente con el resto del archivo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ================================================================
# ⭐ REGLAS DE ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS
# Devuelve lista de segmentos según tipo/valor/minimo_compra.
# Debe coincidir con los segmentos que usa Usuario.obtener_segmento:
# 'vip', 'frecuente', 'ocasional', 'inactivo', 'nuevo', 'todos'
# ================================================================
def calcular_segmentos_automaticos(tipo, valor, minimo_compra):
    tipo = (tipo or "porcentaje").lower()
    valor = float(valor or 0)
    minimo_compra = float(minimo_compra or 0)

    if tipo == "envio_gratis":
        if minimo_compra >= 200:
            return ["frecuente", "vip"]
        elif minimo_compra >= 100:
            return ["frecuente", "todos"]
        return ["todos"]

    if tipo == "porcentaje":
        if valor >= 20:
            if minimo_compra >= 500:
                return ["vip"]
            return ["frecuente", "vip"]
        elif valor >= 10:
            if minimo_compra < 200:
                return ["inactivo", "todos"]
            return ["frecuente", "todos"]
        return ["todos"]

    # monto_fijo
    if valor >= 200 and minimo_compra >= 500:
        return ["vip"]
    elif valor >= 50:
        return ["frecuente", "todos"]
    return ["todos"]


class Cupon:
    """Modelo para gestionar cupones de descuento"""

    @classmethod
    def get_collection(cls):
        return get_db().cupones

    @classmethod
    def crear(cls, datos):
        """Crear un nuevo cupón"""
        collection = cls.get_collection()

        codigo = datos.get("codigo", "").strip().upper()
        if not codigo:
            codigo = cls.generar_codigo()
            datos["codigo"] = codigo

        if cls.obtener_por_codigo(codigo):
            codigo = cls.generar_codigo()
            datos["codigo"] = codigo

        segmentos = datos.get("segmentos", [])
        if isinstance(segmentos, list):
            segmentos = [s for s in segmentos if s and s.strip()]
        else:
            segmentos = []

        mostrar_en_tienda = datos.get("mostrar_en_tienda")
        if mostrar_en_tienda is None:
            mostrar_en_tienda = True
        elif isinstance(mostrar_en_tienda, str):
            mostrar_en_tienda = mostrar_en_tienda.lower() in ["true", "1", "on"]

        ahora = _ahora_utc_naive()

        # ⭐ Normalizar fechas a datetime (acepta str o datetime)
        fecha_inicio_dt = _to_datetime(datos.get("fecha_inicio"))
        fecha_fin_dt = _to_datetime(datos.get("fecha_fin"))

        cupon = {
            "codigo": codigo,
            "nombre": datos.get("nombre", "").strip(),
            "descripcion": datos.get("descripcion", "").strip(),
            "tipo": datos.get("tipo", "porcentaje"),
            "valor": float(datos.get("valor", 0)),
            "fecha_inicio": fecha_inicio_dt,
            "fecha_fin": fecha_fin_dt,
            "uso_maximo": int(datos.get("uso_maximo", 0)),
            "uso_por_usuario": int(datos.get("uso_por_usuario", 1)),
            "usos_actuales": int(datos.get("usos_actuales", 0)),
            "minimo_compra": float(datos.get("minimo_compra", 0)),
            "segmentos": segmentos,
            "categorias": datos.get("categorias", []),
            "productos": datos.get("productos", []),
            "activo": datos.get("activo", True),
            "mostrar_en_tienda": mostrar_en_tienda,
            "created_at": ahora,
            "updated_at": ahora,
        }

        if datos.get("creado_automaticamente"):
            cupon["creado_automaticamente"] = True
            cupon["segmento"] = datos.get("segmento")
            cupon["usuarios_asignados"] = datos.get("usuarios_asignados", [])
            cupon["total_asignados"] = len(cupon["usuarios_asignados"])

        if cupon["tipo"] == "porcentaje" and cupon["valor"] > 100:
            cupon["valor"] = 100
        if cupon["valor"] < 0:
            cupon["valor"] = 0

        # ⭐ Comparar datetime con datetime (ambos normalizados)
        if fecha_inicio_dt and fecha_fin_dt:
            if fecha_inicio_dt > fecha_fin_dt:
                cupon["fecha_inicio"], cupon["fecha_fin"] = (
                    cupon["fecha_fin"],
                    cupon["fecha_inicio"],
                )

        return collection.insert_one(cupon)

    @classmethod
    def generar_cupon_para_segmento(cls, segmento, config, usuarios_ids=None):
        """
        Genera un cupón dirigido a un segmento con la lógica real de Python.
        """
        ahora = _ahora_utc_naive()
        dias = int(config.get("dias_vigencia", 30))
        fecha_fin = ahora + timedelta(days=dias)

        codigo = f"AUTO-{str(segmento).upper()[:6]}-{int(ahora.timestamp())}"

        segmentos_auto = calcular_segmentos_automaticos(
            config.get("tipo", "porcentaje"),
            config.get("valor", 0),
            config.get("minimo_compra", 0),
        )
        if segmento and segmento != "todos" and segmento not in segmentos_auto:
            segmentos_auto = [segmento]

        usuarios = list(usuarios_ids or [])

        datos = {
            "codigo": codigo,
            "nombre": config.get("nombre", f"Cupón {segmento}"),
            "descripcion": config.get(
                "descripcion", f"Generado automáticamente · Segmento {segmento}"
            ),
            "tipo": config.get("tipo", "porcentaje"),
            "valor": float(config.get("valor", 0)),
            "fecha_inicio": ahora,
            "fecha_fin": fecha_fin,
            "uso_maximo": int(config.get("uso_maximo", 0)),
            "uso_por_usuario": int(config.get("uso_por_usuario", 1)),
            "minimo_compra": float(config.get("minimo_compra", 0)),
            "segmentos": segmentos_auto,
            "categorias": [],
            "productos": [],
            "activo": True,
            "mostrar_en_tienda": True,
            "creado_automaticamente": True,
            "segmento": segmento,
            "usuarios_asignados": usuarios,
        }

        r = cls.crear(datos)

        return {
            "id": segmento,
            "segmento": datos["nombre"],
            "creados": 1,
            "codigo": codigo,
            "usuarios_beneficiados": len(usuarios),
            "cupon": {
                "tipo": datos["tipo"],
                "valor": datos["valor"],
                "minimo_compra": datos["minimo_compra"],
            },
        }

    @classmethod
    def generar_codigo(cls, longitud=8):
        caracteres = string.ascii_uppercase + string.digits
        while True:
            codigo = "".join(random.choices(caracteres, k=longitud))
            if not cls.obtener_por_codigo(codigo):
                return codigo

    @classmethod
    def obtener_todos(cls, filtro=None):
        collection = cls.get_collection()
        if filtro is None:
            filtro = {}
        return list(collection.find(filtro).sort("created_at", -1))

    @classmethod
    def obtener_por_id(cls, id):
        collection = cls.get_collection()
        try:
            return collection.find_one({"_id": ObjectId(id)})
        except Exception:
            return None

    @classmethod
    def obtener_por_codigo(cls, codigo):
        collection = cls.get_collection()
        if not codigo:
            return None
        return collection.find_one({"codigo": codigo.upper()})

    @classmethod
    def actualizar(cls, id, datos):
        collection = cls.get_collection()

        segmentos = datos.get("segmentos", [])
        if isinstance(segmentos, list):
            segmentos = [s for s in segmentos if s and s.strip()]
        else:
            segmentos = []
        datos["segmentos"] = segmentos

        if datos.get("tipo") == "porcentaje" and datos.get("valor", 0) > 100:
            datos["valor"] = 100
        if datos.get("valor", 0) < 0:
            datos["valor"] = 0

        # ⭐ Normalizar fechas si vienen en el update
        if "fecha_inicio" in datos:
            datos["fecha_inicio"] = _to_datetime(datos.get("fecha_inicio"))
        if "fecha_fin" in datos:
            datos["fecha_fin"] = _to_datetime(datos.get("fecha_fin"))

        datos["updated_at"] = _ahora_utc_naive()
        try:
            return collection.update_one({"_id": ObjectId(id)}, {"$set": datos})
        except Exception:
            return None

    @classmethod
    def eliminar(cls, id):
        collection = cls.get_collection()
        try:
            return collection.delete_one({"_id": ObjectId(id)})
        except Exception:
            return None

    @classmethod
    def incrementar_uso(cls, codigo):
        collection = cls.get_collection()
        try:
            return collection.update_one(
                {"codigo": codigo.upper()},
                {
                    "$inc": {"usos_actuales": 1},
                    "$set": {"updated_at": _ahora_utc_naive()},
                },
            )
        except Exception:
            return None

    @classmethod
    def es_valido(cls, codigo, usuario_id=None, segmento=None, total_carrito=0):
        codigo = codigo.upper()
        cupon = cls.obtener_por_codigo(codigo)

        if not cupon:
            return {"valido": False, "mensaje": "Cupón no válido"}

        if not cupon.get("activo", True):
            return {"valido": False, "mensaje": "Este cupón ya no está activo"}

        ahora = _ahora_utc_naive()
        # ⭐ Normalizar fechas antes de comparar (acepta str o datetime)
        fecha_inicio = _to_datetime(cupon.get("fecha_inicio"))
        fecha_fin = _to_datetime(cupon.get("fecha_fin"))

        if fecha_inicio and fecha_inicio > ahora:
            return {
                "valido": False,
                "mensaje": f"Este cupón estará disponible a partir del {fecha_inicio.strftime('%d/%m/%Y')}",
            }
        if fecha_fin and fecha_fin < ahora:
            return {"valido": False, "mensaje": "Este cupón ya expiró"}

        uso_maximo = cupon.get("uso_maximo", 0)
        usos_actuales = cupon.get("usos_actuales", 0)
        if uso_maximo > 0 and usos_actuales >= uso_maximo:
            return {"valido": False, "mensaje": "Este cupón ya alcanzó su límite de usos"}

        if usuario_id and segmento:
            uso_por_usuario = cupon.get("uso_por_usuario", 1)
            usos_usuario = CuponUsuario.contar_usos_usuario(usuario_id, codigo)
            if usos_usuario >= uso_por_usuario:
                return {"valido": False, "mensaje": f"Ya has usado este cupón {usos_usuario} vez/veces"}

            segmentos_permitidos = cupon.get("segmentos", [])
            if segmentos_permitidos and "todos" not in segmentos_permitidos:
                segmentos_lower = [s.lower() for s in segmentos_permitidos]
                if segmento.lower() not in segmentos_lower:
                    return {"valido": False, "mensaje": "Este cupón no aplica para tu perfil"}

        minimo_compra = cupon.get("minimo_compra", 0)
        if minimo_compra > 0 and total_carrito < minimo_compra:
            return {
                "valido": False,
                "mensaje": f"El monto mínimo para este cupón es de ${minimo_compra:.2f}",
                "minimo_compra": minimo_compra,
                "cupon": cupon,
            }

        descuento = 0
        tipo = cupon.get("tipo")
        valor = cupon.get("valor", 0)
        if tipo == "porcentaje":
            descuento = (total_carrito * valor) / 100
        elif tipo == "monto_fijo":
            descuento = min(valor, total_carrito)
        elif tipo == "envio_gratis":
            descuento = 0

        return {
            "valido": True,
            "mensaje": "Cupón válido",
            "cupon": cupon,
            "descuento": descuento,
            "tipo": tipo,
            "valor": valor,
        }

    @classmethod
    def obtener_cupones_cliente(cls, usuario_id, segmento, total_carrito=0):
        collection = cls.get_collection()
        ahora = _ahora_utc_naive()

        filtro = {"activo": True}
        cupones = list(collection.find(filtro))
        resultado = []

        for cupon in cupones:
            codigo = cupon.get("codigo")

            # ⭐ Normalizar fechas antes de comparar (acepta str o datetime)
            fecha_inicio = _to_datetime(cupon.get("fecha_inicio"))
            fecha_fin = _to_datetime(cupon.get("fecha_fin"))
            if fecha_inicio and fecha_inicio > ahora:
                continue
            if fecha_fin and fecha_fin < ahora:
                continue

            uso_maximo = cupon.get("uso_maximo", 0)
            usos_actuales = cupon.get("usos_actuales", 0)
            if uso_maximo > 0 and usos_actuales >= uso_maximo:
                continue

            if usuario_id:
                uso_por_usuario = cupon.get("uso_por_usuario", 1)
                usos_usuario = CuponUsuario.contar_usos_usuario(usuario_id, codigo)
                if usos_usuario >= uso_por_usuario:
                    continue

            asignados = cupon.get("usuarios_asignados") or []
            if cupon.get("creado_automaticamente") and asignados:
                if str(usuario_id) not in [str(x) for x in asignados]:
                    continue

            segmentos_permitidos = cupon.get("segmentos", [])
            if not segmentos_permitidos or "todos" in segmentos_permitidos:
                pass
            else:
                segmentos_lower = [s.lower() for s in segmentos_permitidos]
                segmento_usuario_lower = (segmento or "").lower()
                if not segmento or segmento_usuario_lower not in segmentos_lower:
                    continue

            minimo_compra = cupon.get("minimo_compra", 0)
            cumple_minimo = total_carrito >= minimo_compra if minimo_compra > 0 else True

            cupon["_id"] = str(cupon["_id"])
            cupon["cumple_minimo"] = cumple_minimo
            cupon["total_carrito_actual"] = total_carrito
            resultado.append(cupon)

        return resultado

    @classmethod
    def obtener_cupones_activos(cls):
        collection = cls.get_collection()
        ahora = _ahora_utc_naive()
        filtro = {
            "activo": True,
            "$and": [
                {
                    "$or": [
                        {"fecha_inicio": {"$exists": False}},
                        {"fecha_inicio": None},
                        {"fecha_inicio": {"$lte": ahora}},
                    ]
                },
                {
                    "$or": [
                        {"fecha_fin": {"$exists": False}},
                        {"fecha_fin": None},
                        {"fecha_fin": {"$gte": ahora}},
                    ]
                },
            ],
        }
        return list(collection.find(filtro).sort("created_at", -1))

    @classmethod
    def obtener_estadisticas(cls, id):
        cupon = cls.obtener_por_id(id)
        if not cupon:
            return None

        usos = CuponUsuario.obtener_usos_por_cupon(cupon.get("codigo"))

        estadisticas = {
            "total_usos": len(usos),
            "usos_unicos": len(set(u.get("usuario_id") for u in usos if u.get("usuario_id"))),
            "total_descuento": sum(u.get("descuento_aplicado", 0) for u in usos),
            "promedio_descuento": (
                sum(u.get("descuento_aplicado", 0) for u in usos) / len(usos) if usos else 0
            ),
            "usos_por_dia": {},
            "usos_por_mes": {},
            "usuarios": [],
        }

        for uso in usos:
            fecha = uso.get("fecha_uso")
            if fecha and isinstance(fecha, datetime):
                dia = fecha.strftime("%Y-%m-%d")
                mes = fecha.strftime("%Y-%m")
                estadisticas["usos_por_dia"][dia] = estadisticas["usos_por_dia"].get(dia, 0) + 1
                estadisticas["usos_por_mes"][mes] = estadisticas["usos_por_mes"].get(mes, 0) + 1

        return estadisticas


class CuponUsuario:
    """Modelo para registrar el uso de cupones por usuario"""

    @classmethod
    def get_collection(cls):
        return get_db().cupones_usuarios

    @classmethod
    def registrar_uso(cls, usuario_id, cupon_codigo, pedido_id=None, descuento_aplicado=0):
        collection = cls.get_collection()

        cupon = Cupon.obtener_por_codigo(cupon_codigo)
        if not cupon:
            return None

        uso_por_usuario = cupon.get("uso_por_usuario", 1)
        usos_usuario = cls.contar_usos_usuario(usuario_id, cupon_codigo)
        if usos_usuario >= uso_por_usuario:
            return None

        registro = {
            "usuario_id": str(usuario_id),
            "cupon_codigo": cupon_codigo.upper(),
            "pedido_id": str(pedido_id) if pedido_id else None,
            "descuento_aplicado": float(descuento_aplicado),
            "fecha_uso": _ahora_utc_naive(),
        }

        Cupon.incrementar_uso(cupon_codigo)
        return collection.insert_one(registro)

    @classmethod
    def cupon_usado(cls, usuario_id, cupon_codigo):
        collection = cls.get_collection()
        if not usuario_id or not cupon_codigo:
            return False
        return (
            collection.find_one(
                {"usuario_id": str(usuario_id), "cupon_codigo": cupon_codigo.upper()}
            )
            is not None
        )

    @classmethod
    def contar_usos_usuario(cls, usuario_id, cupon_codigo):
        collection = cls.get_collection()
        if not usuario_id or not cupon_codigo:
            return 0
        return collection.count_documents(
            {"usuario_id": str(usuario_id), "cupon_codigo": cupon_codigo.upper()}
        )

    @classmethod
    def obtener_usos_por_cupon(cls, cupon_codigo):
        collection = cls.get_collection()
        if not cupon_codigo:
            return []
        return list(
            collection.find({"cupon_codigo": cupon_codigo.upper()}).sort("fecha_uso", -1)
        )

    @classmethod
    def obtener_usos_por_usuario(cls, usuario_id):
        collection = cls.get_collection()
        if not usuario_id:
            return []
        return list(
            collection.find({"usuario_id": str(usuario_id)}).sort("fecha_uso", -1)
        )

    @classmethod
    def obtener_historial_usuario(cls, usuario_id, limite=20):
        collection = cls.get_collection()
        if not usuario_id:
            return []
        return list(
            collection.find({"usuario_id": str(usuario_id)})
            .sort("fecha_uso", -1)
            .limit(limite)
        )


# ================================================================
# FUNCIONES AUXILIARES
# ================================================================

def calcular_descuento_cupon(codigo_cupon, total_carrito, usuario_id=None, segmento=None):
    if not codigo_cupon:
        return {"aplica": False, "descuento": 0, "mensaje": "No hay cupón aplicado"}

    resultado = Cupon.es_valido(codigo_cupon, usuario_id, segmento, total_carrito)
    if not resultado["valido"]:
        return {
            "aplica": False,
            "descuento": 0,
            "mensaje": resultado["mensaje"],
            "cupon": resultado.get("cupon"),
        }

    if resultado["tipo"] == "envio_gratis":
        return {
            "aplica": True,
            "descuento": 0,
            "tipo": "envio_gratis",
            "mensaje": "¡Envío gratis aplicado!",
            "cupon": resultado["cupon"],
            "minimo_compra": resultado["cupon"].get("minimo_compra", 0),
        }

    return {
        "aplica": True,
        "descuento": resultado["descuento"],
        "tipo": resultado["tipo"],
        "valor": resultado["valor"],
        "mensaje": f"Descuento de {resultado['valor']}"
        f"{'%' if resultado['tipo'] == 'porcentaje' else ''} aplicado",
        "cupon": resultado["cupon"],
        "minimo_compra": resultado["cupon"].get("minimo_compra", 0),
    }


def aplicar_cupon_pedido(usuario_id, codigo_cupon, pedido_id, total_carrito, segmento=None):
    resultado = Cupon.es_valido(codigo_cupon, usuario_id, segmento, total_carrito)
    if not resultado["valido"]:
        return {"success": False, "mensaje": resultado["mensaje"]}

    registro = CuponUsuario.registrar_uso(
        usuario_id=usuario_id,
        cupon_codigo=codigo_cupon,
        pedido_id=pedido_id,
        descuento_aplicado=resultado["descuento"],
    )
    if not registro:
        return {"success": False, "mensaje": "Error al registrar el uso del cupón"}

    return {
        "success": True,
        "mensaje": "Cupón aplicado correctamente",
        "descuento": resultado["descuento"],
        "tipo": resultado["tipo"],
        "valor": resultado["valor"],
        "cupon": resultado["cupon"],
    }


def obtener_cupon_aplicado_sesion():
    from flask import session
    return session.get("cupon_aplicado", None)


def limpiar_cupon_sesion():
    from flask import session
    if "cupon_aplicado" in session:
        session.pop("cupon_aplicado", None)
        return True
    return False