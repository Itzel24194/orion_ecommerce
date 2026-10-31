# app/controllers/cupon_controller.py - COMPLETO Y CORREGIDO
# ================================================================
# Incluye:
#   - Asignación automática de segmentos (regla real del negocio)
#   - Vistas HTML de admin (listar, crear, editar, eliminar, estadísticas)
#   - Vistas HTML de cliente (mis cupones, aplicar, quitar, validar)
#   - Helpers JSON para React Native:
#       serializar_cupon, api_crear_cupon, api_actualizar_cupon,
#       api_toggle_cupon, api_eliminar_cupon
#   - Generación automática por segmentos:
#       listar_segmentos_disponibles, previsualizar_segmento,
#       generar_cupones_automaticos_por_segmento
#   - Conteo real de usos (lealtad + cupones_usuarios)
#   - Detalle de quién usó cada cupón
#   - Cliente solo puede tener 1 cupón activo a la vez.
#     MODELO LIVERPOOL ESTRICTO: si ya hay un cupón aplicado,
#     el sistema RECHAZA aplicar otro. El usuario debe QUITAR
#     el actual primero. No hay reemplazo automático.
#   - ⭐ CUPÓN DE LEALTAD: se marca como usado al aplicarlo,
#     garantizando 1 solo uso por cupón (no reuso).
#   - Marca cuál está activo en sesión para el template
# ================================================================

from flask import (
    render_template, request, redirect, url_for, session, flash,
    jsonify, current_app,
)
from app.models.cupon_model import (
    Cupon,
    CuponUsuario,
    calcular_descuento_cupon,
    aplicar_cupon_pedido,
    calcular_segmentos_automaticos,
)
from app.models.usuarios_model import Usuario
from bson import ObjectId
from datetime import datetime, timezone, timedelta, date
import random
import string
import sys
import json


# ================================================================
# ⭐ FIX — Helpers de fecha tolerantes a string / date / datetime / número
# ================================================================
def _parse_fecha(value):
    """Convierte cualquier representación de fecha a datetime naive UTC (o None)."""
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)

    if isinstance(value, (int, float)):
        ts = value / 1000.0 if value > 1e12 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (OSError, ValueError, OverflowError):
            return None

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None

        s_iso = s.replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s_iso)
            if d.tzinfo is not None:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except ValueError:
            pass

        candidatos = [s[:19], s[:10]]
        formatos = (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
        )
        for cand in candidatos:
            for fmt in formatos:
                try:
                    return datetime.strptime(cand, fmt)
                except ValueError:
                    continue

    return None


def _normalizar_cupon_fechas(c):
    """Devuelve copia del cupón con fechas como datetime o None."""
    if not c:
        return c
    c = dict(c)
    c["fecha_inicio"] = _parse_fecha(c.get("fecha_inicio"))
    c["fecha_fin"] = _parse_fecha(c.get("fecha_fin") or c.get("fecha_expiracion"))
    if c.get("fecha_expiracion") is not None and c["fecha_fin"] is None:
        c["fecha_fin"] = _parse_fecha(c.get("fecha_expiracion"))
    c["created_at"] = _parse_fecha(c.get("created_at") or c.get("fecha_creacion"))
    c["updated_at"] = _parse_fecha(c.get("updated_at") or c.get("fecha_actualizacion"))
    return c


# ================================================================
# ⭐ HELPER: detectar si un cupón (dict de Mongo) está usado
# ================================================================
def _esta_usado(c):
    """Devuelve True si el cupón tiene cualquier marca de 'usado'."""
    if not isinstance(c, dict):
        return False
    return bool(
        c.get("usado", False)
        or c.get("utilizado", False)
        or c.get("canjeado", False)
        or c.get("usado_en")
        or c.get("fecha_uso")
    )


# ================================================================
# ⭐ CONTEO REAL DE USOS (lealtad + cupones_usuarios)
# ================================================================
def _contar_usos_reales(cupon):
    """
    Cuenta los usos reales de un cupón sumando:
      - db.cupones_usuarios (registros generales / legacy)
      - db.lealtad.cupones_personalizados[].usado == True (lealtad)
    """
    db = current_app.db
    codigo = (cupon.get("codigo") or "").strip().upper()
    if not codigo:
        return 0

    total = 0

    try:
        total += db.cupones_usuarios.count_documents({"cupon_codigo": codigo})
    except Exception:
        pass

    try:
        cursor = db.lealtad.find(
            {"cupones_personalizados": {"$elemMatch": {"usado": True}}},
            {"cupones_personalizados": 1},
        )
        for reg in cursor:
            for c in reg.get("cupones_personalizados") or []:
                if not _esta_usado(c):
                    continue
                cid = (str(c.get("id") or c.get("codigo") or "")).strip().upper()
                if cid == codigo:
                    total += 1
    except Exception:
        pass

    return total


def _usos_por_usuario(usuario_id, cupon):
    """
    Cuenta cuántas veces un usuario específico ha usado un cupón.
    Suma cupones_usuarios + lealtad (usado == True).
    """
    db = current_app.db
    codigo = (cupon.get("codigo") or "").strip().upper()
    if not codigo or not usuario_id:
        return 0

    uid_str = str(usuario_id)
    total = 0

    try:
        filtros = [{"usuario_id": uid_str, "cupon_codigo": codigo}]
        try:
            filtros.append({"usuario_id": ObjectId(uid_str), "cupon_codigo": codigo})
        except Exception:
            pass
        for f in filtros:
            total += db.cupones_usuarios.count_documents(f)
    except Exception:
        pass

    try:
        filtros_lealtad = [{"usuario_id": uid_str}, {"usuario_id": usuario_id}]
        try:
            filtros_lealtad.append({"usuario_id": ObjectId(uid_str)})
        except Exception:
            pass
        visto = False
        for f in filtros_lealtad:
            if visto:
                break
            reg = db.lealtad.find_one(f)
            if reg:
                visto = True
                for c in reg.get("cupones_personalizados") or []:
                    if not _esta_usado(c):
                        continue
                    cid = (str(c.get("id") or c.get("codigo") or "")).strip().upper()
                    if cid == codigo:
                        total += 1
    except Exception:
        pass

    return total


def _enriquecer_cupon_admin(cupon):
    """Adjunta usos_reales, agotado y porcentaje_uso para la tabla admin."""
    usos_reales = _contar_usos_reales(cupon)
    uso_maximo = int(cupon.get("uso_maximo", 0) or 0)

    cupon["usos_reales"] = usos_reales
    cupon["usos_actuales"] = usos_reales
    cupon["agotado"] = uso_maximo > 0 and usos_reales >= uso_maximo
    cupon["porcentaje_uso"] = round(
        (usos_reales / uso_maximo * 100) if uso_maximo > 0 else 0, 1
    )
    return cupon


def _detalle_usos(cupon_id):
    """Listado de quién usó un cupón (para el modal del admin)."""
    db = current_app.db
    cupon = Cupon.obtener_por_id(cupon_id)
    if not cupon:
        return None

    codigo = (cupon.get("codigo") or "").strip().upper()
    detalle = []

    try:
        for uso in db.cupones_usuarios.find({"cupon_codigo": codigo}).sort("fecha_uso", -1):
            uid = str(uso.get("usuario_id", ""))
            user = None
            try:
                user = db.usuarios.find_one({"_id": ObjectId(uid)})
            except Exception:
                pass
            detalle.append(
                {
                    "usuario_id": uid,
                    "nombre": (user or {}).get("nombre", ""),
                    "email": (user or {}).get("email", ""),
                    "fecha_uso": str(uso.get("fecha_uso", ""))[:19].replace("T", " "),
                    "descuento": uso.get("descuento_aplicado", 0),
                    "pedido_id": uso.get("pedido_id"),
                    "origen": "general",
                }
            )
    except Exception:
        pass

    try:
        cursor = db.lealtad.find(
            {"cupones_personalizados": {"$elemMatch": {"usado": True}}},
            {"usuario_id": 1, "cupones_personalizados": 1, "nombre_usuario": 1},
        )
        for reg in cursor:
            for c in reg.get("cupones_personalizados") or []:
                if not _esta_usado(c):
                    continue
                cid = (str(c.get("id") or c.get("codigo") or "")).strip().upper()
                if cid != codigo:
                    continue
                uid = str(reg.get("usuario_id", ""))
                user = None
                try:
                    user = db.usuarios.find_one({"_id": ObjectId(uid)})
                except Exception:
                    pass
                detalle.append(
                    {
                        "usuario_id": uid,
                        "nombre": (user or {}).get("nombre") or reg.get("nombre_usuario", ""),
                        "email": (user or {}).get("email", ""),
                        "fecha_uso": str(c.get("usado_en", ""))[:19].replace("T", " "),
                        "descuento": c.get("valor", 0),
                        "pedido_id": c.get("pedido_id"),
                        "origen": "lealtad",
                    }
                )
    except Exception:
        pass

    return {
        "cupon_id": str(cupon["_id"]),
        "codigo": codigo,
        "nombre": cupon.get("nombre", ""),
        "uso_maximo": int(cupon.get("uso_maximo", 0) or 0),
        "usos_totales": len(detalle),
        "usos": detalle,
    }


# ================================================================
# ⭐ MARCAR CUPÓN DE LEALTAD COMO USADO (1 uso por cupón)
# ================================================================
def _marcar_cupon_lealtad_usado(usuario_id, codigo_cupon, pedido_id=None):
    """
    Marca un cupón de lealtad como usado en db.lealtad y registra
    el uso en db.cupones_usuarios. Idempotente: si ya estaba usado,
    no hace nada y devuelve False.

    Devuelve True si lo marcó ahora, False si no lo encontró o ya estaba usado.
    """
    if not usuario_id or not codigo_cupon:
        return False

    codigo = str(codigo_cupon).strip().upper()
    if not codigo:
        return False

    try:
        db = current_app.db
    except Exception:
        return False

    now = datetime.now(timezone.utc)
    uid_str = str(usuario_id)

    filtros_usuario = [{"usuario_id": uid_str}]
    try:
        filtros_usuario.append({"usuario_id": ObjectId(uid_str)})
    except Exception:
        pass

    marcado = False

    for filtro_usuario in filtros_usuario:
        try:
            reg = db.lealtad.find_one(filtro_usuario)
            if not reg:
                continue

            cupones = reg.get("cupones_personalizados") or []
            if not isinstance(cupones, list):
                continue

            cambio = False
            for c in cupones:
                if not isinstance(c, dict):
                    continue
                cid = str(
                    c.get("id") or c.get("codigo") or c.get("cupon_codigo") or ""
                ).strip().upper()
                if cid != codigo:
                    continue

                # ⭐ Si ya estaba usado, no hacer nada (idempotente)
                if _esta_usado(c):
                    return False

                c["usado"] = True
                c["usado_en"] = now
                if pedido_id:
                    c["pedido_id"] = str(pedido_id)
                cambio = True
                break

            if cambio:
                db.lealtad.update_one(
                    {"_id": reg["_id"]},
                    {"$set": {"cupones_personalizados": cupones}}
                )
                marcado = True
                break
        except Exception as e:
            print(f"[_marcar_cupon_lealtad_usado] Error filtro={filtro_usuario}: {e}", flush=True)

    # Registrar también en cupones_usuarios (doble protección)
    if marcado:
        try:
            db.cupones_usuarios.insert_one({
                "usuario_id": uid_str,
                "cupon_codigo": codigo,
                "pedido_id": str(pedido_id) if pedido_id else None,
                "fecha_uso": now,
                "origen": "lealtad",
            })
        except Exception as e:
            print(f"[_marcar_cupon_lealtad_usado] Error insertando cupones_usuarios: {e}", flush=True)

    return marcado


# ================================================================
# ⭐ ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS (regla del negocio)
# ================================================================
def asignar_segmento_automatico(data):
    """Asigna segmentos según tipo/valor/minimo_compra."""
    return calcular_segmentos_automaticos(
        data.get("tipo", "porcentaje"),
        data.get("valor", 0),
        data.get("minimo_compra", 0),
    )


# ================================================================
# CONFIGURACIÓN POR SEGMENTO PARA GENERACIÓN AUTOMÁTICA
# ================================================================
CONFIG_SEGMENTOS = {
    "vip": {
        "nombre": "Descuento VIP Exclusivo",
        "descripcion": "Generado automáticamente · Segmento VIP",
        "tipo": "porcentaje",
        "valor": 20,
        "minimo_compra": 500,
        "dias_vigencia": 30,
        "uso_por_usuario": 1,
    },
    "frecuente": {
        "nombre": "Recompensa Cliente Frecuente",
        "descripcion": "Generado automáticamente · Segmento Frecuente",
        "tipo": "porcentaje",
        "valor": 15,
        "minimo_compra": 300,
        "dias_vigencia": 45,
        "uso_por_usuario": 2,
    },
    "ocasional": {
        "nombre": "Incentivo Segunda Compra",
        "descripcion": "Generado automáticamente · Segmento Ocasional",
        "tipo": "monto_fijo",
        "valor": 100,
        "minimo_compra": 500,
        "dias_vigencia": 30,
        "uso_por_usuario": 1,
    },
    "inactivo": {
        "nombre": "Te Extrañamos - Regreso",
        "descripcion": "Generado automáticamente · Segmento Inactivo",
        "tipo": "porcentaje",
        "valor": 15,
        "minimo_compra": 200,
        "dias_vigencia": 15,
        "uso_por_usuario": 1,
    },
    "nuevo": {
        "nombre": "Bienvenida Cliente Nuevo",
        "descripcion": "Generado automáticamente · Segmento Nuevo",
        "tipo": "porcentaje",
        "valor": 10,
        "minimo_compra": 0,
        "dias_vigencia": 60,
        "uso_por_usuario": 1,
    },
    "todos": {
        "nombre": "Campaña General",
        "descripcion": "Generado automáticamente · Todos los clientes",
        "tipo": "porcentaje",
        "valor": 5,
        "minimo_compra": 0,
        "dias_vigencia": 30,
        "uso_por_usuario": 1,
    },
}


# ================================================================
# ⭐ HELPERS DE SERIALIZACIÓN PARA JSON
# ================================================================
def serializar_cupon(c):
    """Convierte un cupón de Mongo a un dict JSON limpio."""
    if not c:
        return None

    c = _normalizar_cupon_fechas(dict(c))
    c["_id"] = str(c.get("_id", ""))

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    fecha_ini = c.get("fecha_inicio")
    fecha_fin = c.get("fecha_fin")

    for k in ("fecha_inicio", "fecha_fin", "created_at", "updated_at"):
        v = c.get(k)
        if isinstance(v, datetime):
            c[k] = v.isoformat()

    activo = c.get("activo", True)
    if not activo:
        estado = "inactivo"
    elif fecha_fin and fecha_fin < ahora:
        estado = "expirado"
    elif fecha_ini and fecha_ini > ahora:
        estado = "programado"
    else:
        estado = "activo"

    c["estado"] = estado
    c["activo"] = bool(activo)

    c["tipo"] = c.get("tipo", "porcentaje")
    c["valor"] = float(c.get("valor", 0) or 0)
    c["minimo_compra"] = float(c.get("minimo_compra", 0) or 0)

    uso_maximo = int(c.get("uso_maximo", 0) or 0)
    c["uso_maximo"] = uso_maximo
    c["usos_max"] = uso_maximo

    c["usos_actuales"] = _contar_usos_reales(c)
    c["uso_por_usuario"] = int(c.get("uso_por_usuario", 1) or 1)
    c["segmentos"] = c.get("segmentos", []) or []
    c["agotado"] = uso_maximo > 0 and c["usos_actuales"] >= uso_maximo

    c["id"] = c["_id"]

    return c


# ================================================================
# ⭐ GENERACIÓN AUTOMÁTICA
# ================================================================
def listar_segmentos_disponibles():
    """Lista segmentos con conteo real de usuarios."""
    db = current_app.db
    conteo = {k: 0 for k in CONFIG_SEGMENTOS.keys()}

    for u in db.usuarios.find({"rol": "cliente"}, {"_id": 1}):
        try:
            seg = (Usuario.obtener_segmento(str(u["_id"])) or "").lower()
            if seg in conteo:
                conteo[seg] += 1
        except Exception:
            pass

    return [
        {
            "id": seg,
            "nombre": cfg["nombre"],
            "descripcion": cfg["descripcion"],
            "usuarios": conteo.get(seg, 0),
            "cupon": {
                "tipo": cfg["tipo"],
                "valor": cfg["valor"],
                "minimo_compra": cfg["minimo_compra"],
                "dias_vigencia": cfg["dias_vigencia"],
            },
        }
        for seg, cfg in CONFIG_SEGMENTOS.items()
    ]


def previsualizar_segmento(segmento_id):
    """Cuenta usuarios del segmento y devuelve muestra de 5."""
    db = current_app.db
    items = []

    for u in db.usuarios.find(
        {"rol": "cliente"},
        {"_id": 1, "nombre": 1, "apellido_paterno": 1, "email": 1},
    ):
        try:
            seg = (Usuario.obtener_segmento(str(u["_id"])) or "").lower()
            if segmento_id == "todos" or seg == segmento_id:
                items.append(
                    {
                        "_id": str(u["_id"]),
                        "nombre": u.get("nombre", ""),
                        "apellido_paterno": u.get("apellido_paterno", ""),
                        "email": u.get("email", ""),
                    }
                )
        except Exception:
            pass

    return {"segmento": segmento_id, "total": len(items), "muestra": items[:5]}


def generar_cupones_automaticos_por_segmento(solo=None):
    """Genera un cupón por cada segmento solicitado."""
    db = current_app.db

    if not solo:
        elegidos = list(CONFIG_SEGMENTOS.keys())
    else:
        elegidos = [s for s in solo if s in CONFIG_SEGMENTOS]

    resultados = []

    for seg in elegidos:
        cfg = CONFIG_SEGMENTOS[seg]

        usuarios_ids = []
        for u in db.usuarios.find({"rol": "cliente"}, {"_id": 1}):
            try:
                s = (Usuario.obtener_segmento(str(u["_id"])) or "").lower()
                if seg == "todos" or s == seg:
                    usuarios_ids.append(str(u["_id"]))
            except Exception:
                pass

        if not usuarios_ids:
            resultados.append(
                {
                    "id": seg,
                    "segmento": cfg["nombre"],
                    "creados": 0,
                    "usuarios_beneficiados": 0,
                    "mensaje": "Sin usuarios en este segmento",
                }
            )
            continue

        try:
            res = Cupon.generar_cupon_para_segmento(seg, cfg, usuarios_ids)
            resultados.append(res)
        except Exception as e:
            resultados.append(
                {
                    "id": seg,
                    "segmento": cfg["nombre"],
                    "creados": 0,
                    "usuarios_beneficiados": 0,
                    "error": str(e),
                }
            )

    return resultados


# ================================================================
# ⭐ HELPERS JSON PARA CREAR / EDITAR / TOGGLE / ELIMINAR
# ================================================================
def api_crear_cupon(data):
    """Crea un cupón desde JSON."""
    try:
        codigo = (data.get("codigo") or "").strip().upper()
        if not codigo:
            codigo = Cupon.generar_codigo()

        if Cupon.obtener_por_codigo(codigo):
            return False, {"ok": False, "error": "El código ya existe"}, 409

        tipo = data.get("tipo", "porcentaje")
        valor = float(data.get("valor", 0) or 0)
        minimo_compra = float(data.get("minimo_compra", 0) or 0)

        segmentos = asignar_segmento_automatico(
            {"tipo": tipo, "valor": valor, "minimo_compra": minimo_compra}
        )

        datos = {
            "codigo": codigo,
            "nombre": (data.get("nombre") or "").strip(),
            "descripcion": (data.get("descripcion") or "").strip(),
            "tipo": tipo,
            "valor": valor,
            "fecha_inicio": _parse_fecha(data.get("fecha_inicio")),
            "fecha_fin": _parse_fecha(data.get("fecha_fin")),
            "uso_maximo": int(data.get("uso_maximo") or data.get("usos_max") or 0),
            "uso_por_usuario": int(data.get("uso_por_usuario") or 1),
            "minimo_compra": minimo_compra,
            "segmentos": segmentos,
            "categorias": data.get("categorias") or [],
            "productos": data.get("productos") or [],
            "activo": bool(data.get("activo", True)),
            "mostrar_en_tienda": bool(data.get("mostrar_en_tienda", True)),
        }

        if not datos["nombre"]:
            return False, {"ok": False, "error": "El nombre es obligatorio"}, 400

        if datos["valor"] <= 0 and datos["tipo"] != "envio_gratis":
            return False, {"ok": False, "error": "El valor debe ser mayor a 0"}, 400

        if datos["tipo"] == "porcentaje" and datos["valor"] > 100:
            return False, {"ok": False, "error": "El descuento no puede superar 100%"}, 400

        r = Cupon.crear(datos)
        nuevo = Cupon.obtener_por_id(str(r.inserted_id))
        return True, {"ok": True, "data": serializar_cupon(nuevo)}, 201

    except Exception as e:
        return False, {"ok": False, "error": str(e)}, 500


def api_actualizar_cupon(id, data):
    """Actualiza un cupón desde JSON."""
    try:
        existente = Cupon.obtener_por_id(id)
        if not existente:
            return False, {"ok": False, "error": "Cupón no encontrado"}, 404

        tipo = data.get("tipo", existente.get("tipo", "porcentaje"))
        valor = float(data.get("valor", existente.get("valor", 0)) or 0)
        minimo_compra = float(
            data.get("minimo_compra", existente.get("minimo_compra", 0)) or 0
        )

        segmentos = asignar_segmento_automatico(
            {"tipo": tipo, "valor": valor, "minimo_compra": minimo_compra}
        )

        fecha_ini = (
            _parse_fecha(data.get("fecha_inicio"))
            if "fecha_inicio" in data
            else _parse_fecha(existente.get("fecha_inicio"))
        )
        fecha_fin = (
            _parse_fecha(data.get("fecha_fin"))
            if "fecha_fin" in data
            else _parse_fecha(existente.get("fecha_fin") or existente.get("fecha_expiracion"))
        )

        datos = {
            "nombre": (data.get("nombre") or existente.get("nombre", "")).strip(),
            "descripcion": (data.get("descripcion") or existente.get("descripcion", "")).strip(),
            "tipo": tipo,
            "valor": valor,
            "fecha_inicio": fecha_ini,
            "fecha_fin": fecha_fin,
            "uso_maximo": int(
                data.get("uso_maximo", data.get("usos_max", existente.get("uso_maximo", 0))) or 0
            ),
            "uso_por_usuario": int(
                data.get("uso_por_usuario", existente.get("uso_por_usuario", 1)) or 1
            ),
            "minimo_compra": minimo_compra,
            "segmentos": segmentos,
            "categorias": data.get("categorias", existente.get("categorias", [])),
            "productos": data.get("productos", existente.get("productos", [])),
            "activo": bool(data.get("activo", existente.get("activo", True))),
            "mostrar_en_tienda": bool(
                data.get("mostrar_en_tienda", existente.get("mostrar_en_tienda", True))
            ),
        }

        if not datos["nombre"]:
            return False, {"ok": False, "error": "El nombre es obligatorio"}, 400

        if datos["valor"] <= 0 and datos["tipo"] != "envio_gratis":
            return False, {"ok": False, "error": "El valor debe ser mayor a 0"}, 400

        if datos["tipo"] == "porcentaje" and datos["valor"] > 100:
            return False, {"ok": False, "error": "El descuento no puede superar 100%"}, 400

        Cupon.actualizar(id, datos)
        actualizado = Cupon.obtener_por_id(id)
        return True, {"ok": True, "data": serializar_cupon(actualizado)}, 200

    except Exception as e:
        return False, {"ok": False, "error": str(e)}, 500


def api_toggle_cupon(id):
    """Alterna activo/inactivo."""
    try:
        c = Cupon.obtener_por_id(id)
        if not c:
            return False, {"ok": False, "error": "Cupón no encontrado"}, 404

        nuevo_estado = not bool(c.get("activo", True))
        Cupon.actualizar(id, {"activo": nuevo_estado})
        return True, {"ok": True, "activo": nuevo_estado}, 200

    except Exception as e:
        return False, {"ok": False, "error": str(e)}, 500


def api_eliminar_cupon(id):
    """Elimina un cupón."""
    try:
        r = Cupon.eliminar(id)
        return True, {"ok": bool(r and r.deleted_count > 0)}, 200
    except Exception as e:
        return False, {"ok": False, "error": str(e)}, 500


# ================================================================
# ADMIN — VISTAS HTML
# ================================================================
def admin_listar_cupones():
    """Listar todos los cupones (Admin) con conteo real de usos."""
    if "user_id" not in session:
        flash("Inicia sesión para acceder", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.dashboard"))

    rol_usuario = usuario.get("rol", "").lower().strip()
    if rol_usuario not in ["admin", "administrador"]:
        flash("No tienes permisos para acceder a esta sección", "danger")
        return redirect(url_for("web.dashboard"))

    cupones_raw = Cupon.obtener_todos()
    cupones = [_normalizar_cupon_fechas(c) for c in cupones_raw]

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    cupones_activos = 0
    cupones_inactivos = 0
    cupones_expirados = 0
    cupones_proximos = 0
    total_usos = 0

    for cupon in cupones:
        _enriquecer_cupon_admin(cupon)
        total_usos += cupon["usos_reales"]

        if cupon.get("activo", False) and not cupon.get("agotado"):
            fecha_fin = cupon.get("fecha_fin")
            fecha_ini = cupon.get("fecha_inicio")

            if fecha_fin and fecha_fin < ahora:
                cupones_expirados += 1
            elif fecha_ini and fecha_ini > ahora:
                cupones_proximos += 1
            else:
                cupones_activos += 1
        else:
            cupones_inactivos += 1

    return render_template(
        "admin/cupones.html",
        cupones=cupones,
        datetime=datetime,
        ahora=ahora,
        cupones_activos=cupones_activos,
        cupones_inactivos=cupones_inactivos,
        cupones_expirados=cupones_expirados,
        cupones_proximos=cupones_proximos,
        total_usos=total_usos,
    )


def admin_crear_cupon():
    """Crear un nuevo cupón (Admin)."""
    if "user_id" not in session:
        flash("Inicia sesión para acceder", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.dashboard"))

    rol_usuario = usuario.get("rol", "").lower().strip()
    if rol_usuario not in ["admin", "administrador"]:
        flash("No tienes permisos", "danger")
        return redirect(url_for("web.dashboard"))

    db = current_app.db
    categorias = list(db.categorias.find({}).sort("nombre", 1))
    productos = list(db.productos.find({}).sort("nombre", 1))

    if request.method == "POST":
        try:
            codigo = request.form.get("codigo", "").strip().upper()
            if not codigo:
                codigo = Cupon.generar_codigo()

            if Cupon.obtener_por_codigo(codigo):
                flash("El código ya existe. Genera uno diferente.", "danger")
                return redirect(url_for("web.admin_crear_cupon"))

            tipo = request.form.get("tipo", "porcentaje")
            valor = float(request.form.get("valor", 0))
            minimo_compra = float(request.form.get("minimo_compra", 0))

            segmentos = asignar_segmento_automatico(
                {"tipo": tipo, "valor": valor, "minimo_compra": minimo_compra}
            )

            fecha_inicio = request.form.get("fecha_inicio")
            fecha_fin = request.form.get("fecha_fin")

            categorias_seleccionadas = [
                c for c in request.form.getlist("categorias") if c and c.strip()
            ]
            productos_seleccionados = [
                p for p in request.form.getlist("productos") if p and p.strip()
            ]

            datos = {
                "codigo": codigo,
                "nombre": request.form.get("nombre", "").strip(),
                "descripcion": request.form.get("descripcion", "").strip(),
                "tipo": tipo,
                "valor": valor,
                "fecha_inicio": (
                    datetime.strptime(fecha_inicio, "%Y-%m-%d") if fecha_inicio else None
                ),
                "fecha_fin": (
                    datetime.strptime(fecha_fin, "%Y-%m-%d") if fecha_fin else None
                ),
                "uso_maximo": int(request.form.get("uso_maximo", 0)),
                "uso_por_usuario": int(request.form.get("uso_por_usuario", 1)),
                "minimo_compra": minimo_compra,
                "segmentos": segmentos,
                "categorias": categorias_seleccionadas,
                "productos": productos_seleccionados,
                "activo": request.form.get("activo") == "1",
                "mostrar_en_tienda": request.form.get("mostrar_en_tienda") == "1",
            }

            if not datos["nombre"]:
                flash("El nombre es obligatorio", "danger")
                return redirect(url_for("web.admin_crear_cupon"))

            if datos["valor"] <= 0 and datos["tipo"] != "envio_gratis":
                flash("El valor debe ser mayor a 0", "danger")
                return redirect(url_for("web.admin_crear_cupon"))

            if datos["tipo"] == "porcentaje" and datos["valor"] > 100:
                flash("El descuento porcentual no puede superar el 100%", "danger")
                return redirect(url_for("web.admin_crear_cupon"))

            Cupon.crear(datos)
            flash(
                f'Cupón {codigo} creado correctamente con segmentos: {", ".join(segmentos)}',
                "success",
            )
            return redirect(url_for("web.admin_listar_cupones"))

        except Exception as e:
            flash(f"Error al crear cupón: {str(e)}", "danger")
            return redirect(url_for("web.admin_crear_cupon"))

    return render_template(
        "admin/crear_cupon.html", categorias=categorias, productos=productos
    )


def admin_editar_cupon(id):
    """Editar un cupón existente (Admin)."""
    if "user_id" not in session:
        flash("Inicia sesión para acceder", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.dashboard"))

    rol_usuario = usuario.get("rol", "").lower().strip()
    if rol_usuario not in ["admin", "administrador"]:
        flash("No tienes permisos", "danger")
        return redirect(url_for("web.dashboard"))

    cupon_raw = Cupon.obtener_por_id(id)
    if not cupon_raw:
        flash("Cupón no encontrado", "danger")
        return redirect(url_for("web.admin_listar_cupones"))

    cupon = _normalizar_cupon_fechas(cupon_raw)

    db = current_app.db
    categorias = list(db.categorias.find({}).sort("nombre", 1))
    productos = list(db.productos.find({}).sort("nombre", 1))

    if request.method == "POST":
        try:
            tipo = request.form.get("tipo", "porcentaje")
            valor = float(request.form.get("valor", 0))
            minimo_compra = float(request.form.get("minimo_compra", 0))

            segmentos = asignar_segmento_automatico(
                {"tipo": tipo, "valor": valor, "minimo_compra": minimo_compra}
            )

            fecha_inicio = request.form.get("fecha_inicio")
            fecha_fin = request.form.get("fecha_fin")

            categorias_seleccionadas = [
                c for c in request.form.getlist("categorias") if c and c.strip()
            ]
            productos_seleccionados = [
                p for p in request.form.getlist("productos") if p and p.strip()
            ]

            datos = {
                "nombre": request.form.get("nombre", "").strip(),
                "descripcion": request.form.get("descripcion", "").strip(),
                "tipo": tipo,
                "valor": valor,
                "fecha_inicio": (
                    datetime.strptime(fecha_inicio, "%Y-%m-%d") if fecha_inicio else None
                ),
                "fecha_fin": (
                    datetime.strptime(fecha_fin, "%Y-%m-%d") if fecha_fin else None
                ),
                "uso_maximo": int(request.form.get("uso_maximo", 0)),
                "uso_por_usuario": int(request.form.get("uso_por_usuario", 1)),
                "minimo_compra": minimo_compra,
                "segmentos": segmentos,
                "categorias": categorias_seleccionadas,
                "productos": productos_seleccionados,
                "activo": request.form.get("activo") == "1",
                "mostrar_en_tienda": request.form.get("mostrar_en_tienda") == "1",
            }

            if not datos["nombre"]:
                flash("El nombre es obligatorio", "danger")
                return redirect(url_for("web.admin_editar_cupon", id=id))

            if datos["valor"] <= 0 and datos["tipo"] != "envio_gratis":
                flash("El valor debe ser mayor a 0", "danger")
                return redirect(url_for("web.admin_editar_cupon", id=id))

            if datos["tipo"] == "porcentaje" and datos["valor"] > 100:
                flash("El descuento porcentual no puede superar el 100%", "danger")
                return redirect(url_for("web.admin_editar_cupon", id=id))

            Cupon.actualizar(id, datos)
            flash(
                f'Cupón actualizado correctamente con segmentos: {", ".join(segmentos)}',
                "success",
            )
            return redirect(url_for("web.admin_listar_cupones"))

        except Exception as e:
            flash(f"Error al actualizar cupón: {str(e)}", "danger")
            return redirect(url_for("web.admin_editar_cupon", id=id))

    return render_template(
        "admin/editar_cupon.html",
        cupon=cupon,
        datetime=datetime,
        categorias=categorias,
        productos=productos,
    )


def admin_eliminar_cupon(id):
    """Eliminar un cupón (Admin)."""
    if "user_id" not in session:
        flash("Inicia sesión para acceder", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.dashboard"))

    rol_usuario = usuario.get("rol", "").lower().strip()
    if rol_usuario not in ["admin", "administrador"]:
        flash("No tienes permisos", "danger")
        return redirect(url_for("web.dashboard"))

    try:
        Cupon.eliminar(id)
        flash("Cupón eliminado correctamente", "success")
    except Exception as e:
        flash(f"Error al eliminar cupón: {str(e)}", "danger")

    return redirect(url_for("web.admin_listar_cupones"))


def admin_cupon_estadisticas(id):
    """Ver estadísticas de uso de un cupón (Admin)."""
    if "user_id" not in session:
        flash("Inicia sesión para acceder", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.dashboard"))

    rol_usuario = usuario.get("rol", "").lower().strip()
    if rol_usuario not in ["admin", "administrador"]:
        flash("No tienes permisos", "danger")
        return redirect(url_for("web.dashboard"))

    cupon_raw = Cupon.obtener_por_id(id)
    if not cupon_raw:
        flash("Cupón no encontrado", "danger")
        return redirect(url_for("web.admin_listar_cupones"))

    cupon = _normalizar_cupon_fechas(cupon_raw)

    usos = CuponUsuario.obtener_usos_por_cupon(cupon.get("codigo"))
    estadisticas = Cupon.obtener_estadisticas(id)

    usuarios_usaron = []
    for uso in usos:
        usuario_id = uso.get("usuario_id")
        if usuario_id:
            user = Usuario.obtener_por_id(usuario_id)
            if user:
                usuarios_usaron.append(
                    {
                        "nombre": user.get("nombre", "Usuario"),
                        "email": user.get("email", ""),
                        "fecha_uso": uso.get("fecha_uso"),
                        "pedido_id": uso.get("pedido_id"),
                        "descuento_aplicado": uso.get("descuento_aplicado", 0),
                    }
                )

    # ⭐ Enriquecer con conteo real + detalle
    _enriquecer_cupon_admin(cupon)
    cupon["detalle_usos"] = _detalle_usos(id)["usos"] if _detalle_usos(id) else []

    return render_template(
        "admin/cupon_estadisticas.html",
        cupon=cupon,
        usos=usos,
        usuarios_usaron=usuarios_usaron,
        estadisticas=estadisticas,
        datetime=datetime,
    )


# ================================================================
# CLIENTE — VISTAS HTML
# ================================================================
def clientes_mis_cupones():
    """Ver cupones del cliente con conteo de usos propios y cupón activo marcado."""
    if "user_id" not in session:
        flash("Inicia sesión para ver tus cupones", "warning")
        return redirect(url_for("web.login"))

    usuario = Usuario.obtener_por_id(session["user_id"])
    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("web.login"))

    segmento = Usuario.obtener_segmento(session["user_id"])
    session["segmento"] = segmento

    carrito_items = session.get("carrito", [])
    total_carrito = 0.0

    if not carrito_items:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {"usuario_id": session["user_id"]}, sort=[("created_at", -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get("total", 0))
    else:
        for item in carrito_items:
            precio = float(item.get("precio", 0))
            cantidad = int(item.get("cantidad", 1))
            total_carrito += precio * cantidad

    session["total_carrito"] = total_carrito
    session.modified = True

    cupones = Cupon.obtener_cupones_cliente(session["user_id"], segmento, total_carrito)
    cupones = [_normalizar_cupon_fechas(c) for c in cupones]

    # ⭐ Conteo de usos por usuario + global
    for c in cupones:
        usos_mios = _usos_por_usuario(session["user_id"], c)
        uso_por_usuario = int(c.get("uso_por_usuario", 1) or 1)
        c["usos_usuario"] = usos_mios
        c["usos_permitidos"] = uso_por_usuario
        c["usos_restantes"] = max(0, uso_por_usuario - usos_mios)
        c["ya_usado_por_mi"] = usos_mios >= uso_por_usuario
        c["usos_globales"] = _contar_usos_reales(c)
        c["uso_maximo_global"] = int(c.get("uso_maximo", 0) or 0)

    # ⭐ Marcar cuál está activo en sesión
    cupon_activo_sesion = session.get("cupon_aplicado") or {}
    codigo_activo = (cupon_activo_sesion.get("codigo") or "").strip().upper()

    for c in cupones:
        c["es_cupon_activo"] = (c.get("codigo", "").upper() == codigo_activo)

    # Ordenar: activo primero, luego disponibles, luego usados
    cupones.sort(
        key=lambda c: (
            0 if c.get("es_cupon_activo") else
            1 if not c.get("ya_usado_por_mi") else
            2
        )
    )

    historial = CuponUsuario.obtener_historial_usuario(session["user_id"])

    db = current_app.db
    categorias = list(db.categorias.find({}))
    productos = list(db.productos.find({}))

    return render_template(
        "tienda/mis_cupones.html",
        cupones=cupones,
        historial=historial,
        segmento=segmento,
        usuario=usuario,
        total_carrito=total_carrito,
        categorias=categorias,
        productos=productos,
        hay_cupon_activo=codigo_activo != "",
        codigo_cupon_activo=codigo_activo,
    )


def cliente_aplicar_cupon():
    """
    Aplica UN cupón al carrito.

    MODELO LIVERPOOL ESTRICTO:
    - Si ya hay un cupón aplicado en sesión, RECHAZA la solicitud.
    - El usuario debe QUITAR el cupón actual antes de aplicar otro.
    - No acumula, no reemplaza automáticamente.

    ⭐ CUPÓN DE LEALTAD:
    - Al aplicarlo se marca como `usado: True` en db.lealtad
      (y se registra en db.cupones_usuarios), garantizando
      1 solo uso por cupón. No se puede reusar.
    """
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Inicia sesión"}), 401

    data = request.get_json() or {}
    codigo = data.get("codigo", "").strip().upper()

    if not codigo:
        return jsonify({"success": False, "message": "Ingresa un código de cupón"})

    # ⭐ BLOQUEO LIVERPOOL: si ya hay cupón, no dejar aplicar otro
    cupon_actual = session.get("cupon_aplicado")
    if cupon_actual:
        codigo_actual = (cupon_actual.get("codigo") or "").strip().upper()
        if codigo_actual == codigo:
            return jsonify({
                "success": False,
                "message": f"El cupón {codigo} ya está aplicado a tu carrito",
                "debug": "cupon_mismo_ya_aplicado",
            }), 400
        return jsonify({
            "success": False,
            "message": (
                f"Ya tienes el cupón {codigo_actual} aplicado. "
                "Quítalo primero para poder usar otro cupón."
            ),
            "debug": "cupon_ya_aplicado",
            "cupon_actual": codigo_actual,
        }), 400

    cupon_doc = Cupon.obtener_por_codigo(codigo)
    if not cupon_doc:
        return jsonify({"success": False, "message": "Cupón no encontrado"}), 404

    # ⭐ Rechaza solo si ESTE usuario ya lo usó hasta su límite
    usos_mios = _usos_por_usuario(session["user_id"], cupon_doc)
    uso_por_usuario = int(cupon_doc.get("uso_por_usuario", 1) or 1)
    if uso_por_usuario > 0 and usos_mios >= uso_por_usuario:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Ya usaste este cupón {usos_mios} de {uso_por_usuario} vez/veces permitidas",
                    "debug": "cupon_usado",
                }
            ),
            400,
        )

    segmento = Usuario.obtener_segmento(session["user_id"])

    carrito_items = session.get("carrito", [])
    total_carrito = 0.0

    if carrito_items:
        for item in carrito_items:
            precio = float(item.get("precio", 0))
            cantidad = int(item.get("cantidad", 1))
            total_carrito += precio * cantidad
    else:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {"usuario_id": session["user_id"]}, sort=[("created_at", -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get("total", 0))

    resultado = Cupon.es_valido(codigo, session["user_id"], segmento, total_carrito)

    if not resultado["valido"]:
        return jsonify({"success": False, "message": resultado["mensaje"]})

    if resultado["tipo"] == "porcentaje":
        descuento_aplicado = (total_carrito * resultado["valor"]) / 100
    elif resultado["tipo"] == "monto_fijo":
        descuento_aplicado = min(resultado["valor"], total_carrito)
    else:
        descuento_aplicado = 0

    # ⭐ Aplica el cupón en sesión (aquí ya sabemos que no había otro)
    session["cupon_aplicado"] = {
        "codigo": codigo,
        "tipo": resultado["tipo"],
        "valor": resultado["valor"],
        "descuento": descuento_aplicado,
        "minimo_compra": resultado["cupon"].get("minimo_compra", 0),
        "nombre": resultado["cupon"].get("nombre"),
    }
    session["descuento_aplicado"] = descuento_aplicado
    session["total_con_descuento"] = total_carrito - descuento_aplicado
    session.modified = True

    # ⭐ MARCAR CUPÓN DE LEALTAD COMO USADO (1 solo uso por cupón)
    try:
        _marcar_cupon_lealtad_usado(session["user_id"], codigo)
    except Exception as e:
        print(f"[cliente_aplicar_cupon] Error marcando cupón lealtad como usado: {e}", flush=True)

    return jsonify(
        {
            "success": True,
            "message": f"Cupón {codigo} aplicado correctamente",
            "descuento": descuento_aplicado,
            "total_con_descuento": total_carrito - descuento_aplicado,
            "redirect": url_for("web.ver_carrito"),
            "cupon": {
                "codigo": codigo,
                "nombre": resultado["cupon"].get("nombre"),
                "tipo": resultado["tipo"],
                "valor": resultado["valor"],
                "descuento": descuento_aplicado,
                "minimo_compra": resultado["cupon"].get("minimo_compra", 0),
            },
        }
    )


def cliente_quitar_cupon():
    """Quitar cupón del carrito (API)."""
    if "cupon_aplicado" in session:
        session.pop("cupon_aplicado", None)
        session.pop("descuento_aplicado", None)
        session.pop("total_con_descuento", None)
        session.modified = True
        return jsonify({"success": True, "message": "Cupón eliminado"})

    return jsonify({"success": False, "message": "No hay cupón aplicado"})


def cliente_validar_cupon():
    """Validar cupón sin aplicarlo (API para checkout)."""
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Inicia sesión"}), 401

    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jsonify({"success": False, "message": "Ingresa un código de cupón"})

    segmento = Usuario.obtener_segmento(session["user_id"])

    carrito_items = session.get("carrito", [])
    total_carrito = 0.0

    if carrito_items:
        for item in carrito_items:
            precio = float(item.get("precio", 0))
            cantidad = int(item.get("cantidad", 1))
            total_carrito += precio * cantidad
    else:
        db = current_app.db
        ultimo_pedido = db.pedidos.find_one(
            {"usuario_id": session["user_id"]}, sort=[("created_at", -1)]
        )
        if ultimo_pedido:
            total_carrito = float(ultimo_pedido.get("total", 0))

    resultado = Cupon.es_valido(codigo, session["user_id"], segmento, total_carrito)

    return jsonify(
        {
            "success": resultado["valido"],
            "message": resultado["mensaje"],
            "cupon": (
                {
                    "codigo": codigo,
                    "nombre": resultado["cupon"].get("nombre") if resultado.get("cupon") else None,
                    "tipo": resultado["tipo"] if resultado.get("tipo") else None,
                    "valor": resultado["valor"] if resultado.get("valor") else None,
                    "descuento": resultado["descuento"] if resultado.get("descuento") else 0,
                    "minimo_compra": (
                        resultado["cupon"].get("minimo_compra") if resultado.get("cupon") else 0
                    ),
                }
                if resultado["valido"]
                else None
            ),
        }
    )


def cliente_cupon_info():
    """Obtener información del cupón aplicado actualmente."""
    if "cupon_aplicado" in session:
        return jsonify({"success": True, "cupon": session["cupon_aplicado"]})
    return jsonify({"success": False, "message": "No hay cupón aplicado"})