# app/models/cupon_model.py - VERSIÓN DEFINITIVA CON SEGMENTACIÓN Y CORRECCIÓN DE DATETIME
# ================================================================

from flask import current_app
from bson import ObjectId
from datetime import datetime, timezone
import random
import string
import sys


def get_db():
    """Obtener la base de datos desde la aplicación actual"""
    return current_app.db


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

        # Siempre mostrar en tienda por defecto
        mostrar_en_tienda = datos.get("mostrar_en_tienda")
        if mostrar_en_tienda is None:
            mostrar_en_tienda = True
        elif isinstance(mostrar_en_tienda, str):
            mostrar_en_tienda = mostrar_en_tienda.lower() in ['true', '1', 'on']

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO

        cupon = {
            "codigo": codigo,
            "nombre": datos.get("nombre", "").strip(),
            "descripcion": datos.get("descripcion", "").strip(),
            "tipo": datos.get("tipo", "porcentaje"),
            "valor": float(datos.get("valor", 0)),
            "fecha_inicio": datos.get("fecha_inicio"),
            "fecha_fin": datos.get("fecha_fin"),
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
            "updated_at": ahora
        }

        if cupon["tipo"] == "porcentaje" and cupon["valor"] > 100:
            cupon["valor"] = 100
        if cupon["valor"] < 0:
            cupon["valor"] = 0

        if cupon["fecha_inicio"] and cupon["fecha_fin"]:
            if cupon["fecha_inicio"] > cupon["fecha_fin"]:
                cupon["fecha_inicio"], cupon["fecha_fin"] = cupon["fecha_fin"], cupon["fecha_inicio"]

        return collection.insert_one(cupon)

    @classmethod
    def generar_codigo(cls, longitud=8):
        caracteres = string.ascii_uppercase + string.digits
        while True:
            codigo = ''.join(random.choices(caracteres, k=longitud))
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
        except:
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

        datos["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO
        try:
            return collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": datos}
            )
        except:
            return None

    @classmethod
    def eliminar(cls, id):
        collection = cls.get_collection()
        try:
            return collection.delete_one({"_id": ObjectId(id)})
        except:
            return None

    @classmethod
    def incrementar_uso(cls, codigo):
        collection = cls.get_collection()
        try:
            return collection.update_one(
                {"codigo": codigo.upper()},
                {"$inc": {"usos_actuales": 1}, "$set": {"updated_at": datetime.now(timezone.utc).replace(tzinfo=None)}}  # <-- CORREGIDO
            )
        except:
            return None

    @classmethod
    def es_valido(cls, codigo, usuario_id=None, segmento=None, total_carrito=0):
        """Verificar si un cupón es válido"""
        codigo = codigo.upper()
        cupon = cls.obtener_por_codigo(codigo)

        if not cupon:
            return {"valido": False, "mensaje": "Cupón no válido"}

        if not cupon.get("activo", True):
            return {"valido": False, "mensaje": "Este cupón ya no está activo"}

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO
        fecha_inicio = cupon.get("fecha_inicio")
        fecha_fin = cupon.get("fecha_fin")

        if fecha_inicio and fecha_inicio > ahora:
            return {"valido": False, "mensaje": f"Este cupón estará disponible a partir del {fecha_inicio.strftime('%d/%m/%Y')}"}

        if fecha_fin and fecha_fin < ahora:
            return {"valido": False, "mensaje": "Este cupón ya expiró"}

        uso_maximo = cupon.get("uso_maximo", 0)
        usos_actuales = cupon.get("usos_actuales", 0)
        if uso_maximo > 0 and usos_actuales >= uso_maximo:
            return {"valido": False, "mensaje": "Este cupón ya alcanzó su límite de usos"}

        if usuario_id and segmento:
            # Verificar uso por usuario
            uso_por_usuario = cupon.get("uso_por_usuario", 1)
            usos_usuario = CuponUsuario.contar_usos_usuario(usuario_id, codigo)
            if usos_usuario >= uso_por_usuario:
                return {"valido": False, "mensaje": f"Ya has usado este cupón {usos_usuario} vez/veces"}

            segmentos_permitidos = cupon.get("segmentos", [])
            if segmentos_permitidos and "todos" not in segmentos_permitidos:
                # Comparación insensible a mayúsculas
                segmentos_lower = [s.lower() for s in segmentos_permitidos]
                if segmento.lower() not in segmentos_lower:
                    return {"valido": False, "mensaje": "Este cupón no aplica para tu perfil"}

        minimo_compra = cupon.get("minimo_compra", 0)
        if minimo_compra > 0 and total_carrito < minimo_compra:
            return {
                "valido": False,
                "mensaje": f"El monto mínimo para este cupón es de ${minimo_compra:.2f}",
                "minimo_compra": minimo_compra,
                "cupon": cupon
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
            "valor": valor
        }

    @classmethod
    def obtener_cupones_cliente(cls, usuario_id, segmento, total_carrito=0):
        """Obtener cupones disponibles para un cliente según su segmento - CON SEGMENTACIÓN Y DEPURACIÓN"""
        collection = cls.get_collection()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO
        
        print("=" * 80, file=sys.stderr)
        print("🔍 obtener_cupones_cliente - DEPURACIÓN", file=sys.stderr)
        print(f"👤 Usuario ID: {usuario_id}", file=sys.stderr)
        print(f"🏷️ Segmento del usuario: '{segmento}'", file=sys.stderr)
        print(f"💰 Total carrito: ${total_carrito}", file=sys.stderr)
        
        # Obtener TODOS los cupones activos
        filtro = {"activo": True}
        cupones = list(collection.find(filtro))
        
        print(f"\n📋 Cupones activos en BD: {len(cupones)}", file=sys.stderr)
        for c in cupones:
            print(f"  - {c.get('codigo')}: segmentos={c.get('segmentos')}", file=sys.stderr)
        
        resultado = []

        for cupon in cupones:
            codigo = cupon.get('codigo')
            print(f"\n🔍 Procesando cupón: {codigo}", file=sys.stderr)
            
            # Verificar fechas
            fecha_inicio = cupon.get("fecha_inicio")
            fecha_fin = cupon.get("fecha_fin")
            
            if fecha_inicio and fecha_inicio > ahora:
                print(f"  ❌ Fecha inicio futura: {fecha_inicio}", file=sys.stderr)
                continue
                
            if fecha_fin and fecha_fin < ahora:
                print(f"  ❌ Fecha fin expirada: {fecha_fin}", file=sys.stderr)
                continue
                
            # Verificar límite global de usos
            uso_maximo = cupon.get("uso_maximo", 0)
            usos_actuales = cupon.get("usos_actuales", 0)
            if uso_maximo > 0 and usos_actuales >= uso_maximo:
                print(f"  ❌ Límite global alcanzado: {usos_actuales}/{uso_maximo}", file=sys.stderr)
                continue

            # Verificar límite por usuario
            if usuario_id:
                uso_por_usuario = cupon.get("uso_por_usuario", 1)
                usos_usuario = CuponUsuario.contar_usos_usuario(usuario_id, codigo)
                if usos_usuario >= uso_por_usuario:
                    print(f"  ❌ Límite por usuario alcanzado: {usos_usuario}/{uso_por_usuario}", file=sys.stderr)
                    continue

            # VERIFICAR SEGMENTO
            segmentos_permitidos = cupon.get("segmentos", [])
            print(f"  📋 Segmentos permitidos por el cupón: {segmentos_permitidos}", file=sys.stderr)
            
            if not segmentos_permitidos or "todos" in segmentos_permitidos:
                print(f"  ✅ Cupón disponible para todos los segmentos", file=sys.stderr)
            else:
                segmentos_lower = [s.lower() for s in segmentos_permitidos]
                segmento_usuario_lower = segmento.lower() if segmento else ""
                
                print(f"  📋 Segmentos permitidos (minúsculas): {segmentos_lower}", file=sys.stderr)
                print(f"  📋 Segmento usuario (minúsculas): '{segmento_usuario_lower}'", file=sys.stderr)
                
                if segmento and segmento_usuario_lower in segmentos_lower:
                    print(f"  ✅ Segmento '{segmento}' permitido", file=sys.stderr)
                elif not segmento:
                    print(f"  ⚠️ Usuario sin segmento, pero cupón requiere segmento", file=sys.stderr)
                    print(f"  ❌ Segmento no permitido - usuario sin segmento", file=sys.stderr)
                    continue
                else:
                    print(f"  ❌ Segmento '{segmento}' NO permitido", file=sys.stderr)
                    continue

            # Verificar monto mínimo
            minimo_compra = cupon.get("minimo_compra", 0)
            cumple_minimo = total_carrito >= minimo_compra if minimo_compra > 0 else True
            print(f"  📋 Monto mínimo: ${minimo_compra}, Total carrito: ${total_carrito}, Cumple: {cumple_minimo}", file=sys.stderr)

            # TODAS las validaciones pasaron, agregar el cupón
            cupon["_id"] = str(cupon["_id"])
            cupon["cumple_minimo"] = cumple_minimo
            cupon["total_carrito_actual"] = total_carrito
            resultado.append(cupon)
            print(f"  ✅ AÑADIDO al resultado", file=sys.stderr)

        print(f"\n📋 Total cupones para cliente: {len(resultado)}", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        return resultado

    @classmethod
    def obtener_cupones_activos(cls):
        """Obtener todos los cupones activos y vigentes"""
        collection = cls.get_collection()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO
        filtro = {
            "activo": True,
            "$and": [
                {
                    "$or": [
                        {"fecha_inicio": {"$exists": False}},
                        {"fecha_inicio": None},
                        {"fecha_inicio": {"$lte": ahora}}
                    ]
                },
                {
                    "$or": [
                        {"fecha_fin": {"$exists": False}},
                        {"fecha_fin": None},
                        {"fecha_fin": {"$gte": ahora}}
                    ]
                }
            ]
        }
        return list(collection.find(filtro).sort("created_at", -1))

    @classmethod
    def obtener_estadisticas(cls, id):
        """Obtener estadísticas de uso de un cupón"""
        cupon = cls.obtener_por_id(id)
        if not cupon:
            return None

        usos = CuponUsuario.obtener_usos_por_cupon(cupon.get("codigo"))

        estadisticas = {
            "total_usos": len(usos),
            "usos_unicos": len(set(u.get("usuario_id") for u in usos if u.get("usuario_id"))),
            "total_descuento": sum(u.get("descuento_aplicado", 0) for u in usos),
            "promedio_descuento": sum(u.get("descuento_aplicado", 0) for u in usos) / len(usos) if usos else 0,
            "usos_por_dia": {},
            "usos_por_mes": {},
            "usuarios": []
        }

        for uso in usos:
            fecha = uso.get("fecha_uso")
            if fecha:
                if isinstance(fecha, datetime):
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

        # Verificar uso por usuario
        uso_por_usuario = cupon.get("uso_por_usuario", 1)
        usos_usuario = cls.contar_usos_usuario(usuario_id, cupon_codigo)
        if usos_usuario >= uso_por_usuario:
            return None

        registro = {
            "usuario_id": str(usuario_id),
            "cupon_codigo": cupon_codigo.upper(),
            "pedido_id": str(pedido_id) if pedido_id else None,
            "descuento_aplicado": float(descuento_aplicado),
            "fecha_uso": datetime.now(timezone.utc).replace(tzinfo=None)  # <-- CORREGIDO
        }

        Cupon.incrementar_uso(cupon_codigo)
        return collection.insert_one(registro)

    @classmethod
    def cupon_usado(cls, usuario_id, cupon_codigo):
        collection = cls.get_collection()
        if not usuario_id or not cupon_codigo:
            return False
        return collection.find_one({
            "usuario_id": str(usuario_id),
            "cupon_codigo": cupon_codigo.upper()
        }) is not None

    @classmethod
    def contar_usos_usuario(cls, usuario_id, cupon_codigo):
        """Contar cuántas veces un usuario ha usado un cupón"""
        collection = cls.get_collection()
        if not usuario_id or not cupon_codigo:
            return 0
        return collection.count_documents({
            "usuario_id": str(usuario_id),
            "cupon_codigo": cupon_codigo.upper()
        })

    @classmethod
    def obtener_usos_por_cupon(cls, cupon_codigo):
        collection = cls.get_collection()
        if not cupon_codigo:
            return []
        return list(collection.find({"cupon_codigo": cupon_codigo.upper()}).sort("fecha_uso", -1))

    @classmethod
    def obtener_usos_por_usuario(cls, usuario_id):
        collection = cls.get_collection()
        if not usuario_id:
            return []
        return list(collection.find({"usuario_id": str(usuario_id)}).sort("fecha_uso", -1))

    @classmethod
    def obtener_historial_usuario(cls, usuario_id, limite=20):
        collection = cls.get_collection()
        if not usuario_id:
            return []
        return list(collection.find(
            {"usuario_id": str(usuario_id)}
        ).sort("fecha_uso", -1).limit(limite))


# ================================================================
# FUNCIONES AUXILIARES
# ================================================================

def calcular_descuento_cupon(codigo_cupon, total_carrito, usuario_id=None, segmento=None):
    """
    Calcula el descuento que aplica un cupón al carrito
    """
    if not codigo_cupon:
        return {
            "aplica": False,
            "descuento": 0,
            "mensaje": "No hay cupón aplicado"
        }

    resultado = Cupon.es_valido(codigo_cupon, usuario_id, segmento, total_carrito)

    if not resultado["valido"]:
        return {
            "aplica": False,
            "descuento": 0,
            "mensaje": resultado["mensaje"],
            "cupon": resultado.get("cupon")
        }

    if resultado["tipo"] == "envio_gratis":
        return {
            "aplica": True,
            "descuento": 0,
            "tipo": "envio_gratis",
            "mensaje": "¡Envío gratis aplicado!",
            "cupon": resultado["cupon"],
            "minimo_compra": resultado["cupon"].get("minimo_compra", 0)
        }

    return {
        "aplica": True,
        "descuento": resultado["descuento"],
        "tipo": resultado["tipo"],
        "valor": resultado["valor"],
        "mensaje": f"Descuento de {resultado['valor']}{'%' if resultado['tipo'] == 'porcentaje' else ''} aplicado",
        "cupon": resultado["cupon"],
        "minimo_compra": resultado["cupon"].get("minimo_compra", 0)
    }


def aplicar_cupon_pedido(usuario_id, codigo_cupon, pedido_id, total_carrito, segmento=None):
    """
    Aplica un cupón a un pedido y registra el uso
    """
    resultado = Cupon.es_valido(codigo_cupon, usuario_id, segmento, total_carrito)

    if not resultado["valido"]:
        return {
            "success": False,
            "mensaje": resultado["mensaje"]
        }

    registro = CuponUsuario.registrar_uso(
        usuario_id=usuario_id,
        cupon_codigo=codigo_cupon,
        pedido_id=pedido_id,
        descuento_aplicado=resultado["descuento"]
    )

    if not registro:
        return {
            "success": False,
            "mensaje": "Error al registrar el uso del cupón"
        }

    return {
        "success": True,
        "mensaje": "Cupón aplicado correctamente",
        "descuento": resultado["descuento"],
        "tipo": resultado["tipo"],
        "valor": resultado["valor"],
        "cupon": resultado["cupon"]
    }


def obtener_cupon_aplicado_sesion():
    """Obtener el cupón aplicado en la sesión actual"""
    from flask import session
    return session.get('cupon_aplicado', None)


def limpiar_cupon_sesion():
    """Limpiar el cupón de la sesión"""
    from flask import session
    if 'cupon_aplicado' in session:
        session.pop('cupon_aplicado', None)
        return True
    return False