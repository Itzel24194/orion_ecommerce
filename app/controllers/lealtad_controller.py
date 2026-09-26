# app/controllers/lealtad_controller.py
# ================================================================
# CONTROLADOR DE LEALTAD - CLIENTE CONSENTIDO
# ================================================================

from flask import (render_template, jsonify, request, session,
                   redirect, url_for, flash, current_app)
from bson import ObjectId
from datetime import datetime, timezone

from app.models.lealtad_model import Lealtad
from app.services.lealtad_service import LealtadService


# ================================================================
# HELPERS
# ================================================================

def normalizar_rol(rol):
    if not rol or not isinstance(rol, str):
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ('administrador', 'admin', 'superadmin', 'root'):
        return 'admin'
    return rol


def _no_cache(payload, status=200):
    """JSON con headers anti-caché."""
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _to_oid(v):
    if isinstance(v, ObjectId):
        return v
    try:
        return ObjectId(str(v))
    except Exception:
        return None


# ================================================================
# ⭐ CÁLCULO REAL DE GASTO Y COMPRAS DESDE db.pedidos
# ================================================================

# Estados que NO cuentan como compra válida
_ESTADOS_INVALIDOS = (
    'cancelado', 'cancelada', 'cancelled',
    'rechazado', 'rechazada', 'rejected',
    'devuelto', 'devuelta', 'refunded',
)


def _calcular_gasto_real(usuario_id):
    """
    Calcula gasto_total y compras_realizadas contando los pedidos
    del usuario en `db.pedidos` (excluyendo cancelados/rechazados).

    Devuelve (gasto, compras).
    """
    try:
        db = current_app.db
    except Exception:
        return 0.0, 0

    uid = usuario_id
    uid_str = str(usuario_id)

    # ObjectId para comparar
    uid_obj = _to_oid(uid) if not isinstance(uid, ObjectId) else uid

    # Filtro: pedidos del usuario
    filtro_usuario = {'$or': [
        {'usuario_id': uid_obj},
        {'usuario_id': uid_str},
        {'user_id': uid_obj},
        {'user_id': uid_str},
        {'cliente_id': uid_obj},
        {'cliente_id': uid_str},
    ]}

    # Excluir cancelados
    filtro_estado = {
        '$nor': [
            {'estado': {'$in': list(_ESTADOS_INVALIDOS)}},
            {'estado': {'$in': [e.upper() for e in _ESTADOS_INVALIDOS]}},
            {'estado': {'$in': [e.capitalize() for e in _ESTADOS_INVALIDOS]}},
            {'estado': 'Cancelado'},
            {'estado': 'CANCELADO'},
        ]
    }

    # Intentar con agregación
    try:
        pipeline = [
            {'$match': {**filtro_usuario, **filtro_estado}},
            {'$group': {
                '_id': None,
                'total': {'$sum': '$total'},
                'cantidad': {'$sum': 1},
            }},
        ]
        res = list(db.pedidos.aggregate(pipeline))
        if res:
            gasto = float(res[0].get('total', 0) or 0)
            compras = int(res[0].get('cantidad', 0) or 0)
            print(f'[lealtad] pedidos reales uid={uid_str}: '
                  f'gasto=${gasto:.2f} compras={compras}', flush=True)
            return gasto, compras
    except Exception as e:
        print(f'[lealtad] Error agregación pedidos: {e}', flush=True)

    # Fallback: iterar a mano por si la agregación falla
    try:
        gasto = 0.0
        compras = 0
        for p in db.pedidos.find(filtro_usuario):
            estado = str(p.get('estado', '') or '').lower()
            if estado in _ESTADOS_INVALIDOS:
                continue
            gasto += float(p.get('total', 0) or 0)
            compras += 1
        print(f'[lealtad] pedidos (fallback) uid={uid_str}: '
              f'gasto=${gasto:.2f} compras={compras}', flush=True)
        return gasto, compras
    except Exception as e:
        print(f'[lealtad] Error iterando pedidos: {e}', flush=True)
        return 0.0, 0


def _calcular_nivel(gasto):
    """Nivel según gasto."""
    if gasto >= 50000:
        return 'Diamante', 3.0
    if gasto >= 20000:
        return 'Oro', 2.0
    if gasto >= 5000:
        return 'Plata', 1.5
    return 'Bronce', 1.0


def _calcular_progreso(gasto, nivel_actual):
    """Progreso hacia el siguiente nivel."""
    niveles = [('Plata', 5000), ('Oro', 20000), ('Diamante', 50000)]

    for nombre, umbral in niveles:
        if gasto < umbral:
            restante = max(0, umbral - gasto)
            pct = min(100, int((gasto / umbral) * 100)) if umbral else 0
            return {
                'nivel_actual':         nivel_actual,
                'siguiente_nivel':      nombre,
                'gasto_actual':         round(gasto, 2),
                'gasto_para_siguiente': umbral,
                'gasto_restante':       round(restante, 2),
                'progreso_pct':         round(float(pct), 1),
            }

    # Ya es Diamante
    return {
        'nivel_actual':         'Diamante',
        'siguiente_nivel':      None,
        'gasto_actual':         round(gasto, 2),
        'gasto_para_siguiente': None,
        'gasto_restante':       0,
        'progreso_pct':         100.0,
    }


def _normalizar_progreso(progreso_raw, gasto_total, nivel_actual):
    """Normaliza el progreso que venga del modelo."""
    p = dict(progreso_raw or {})

    siguiente = p.get('siguiente_nivel') or p.get('next_level') or p.get('siguiente')
    restante  = p.get('gasto_restante')  or p.get('restante')    or p.get('falta')
    pct       = p.get('progreso_pct')    or p.get('porcentaje')  or p.get('pct')
    umbral    = p.get('gasto_para_siguiente') or p.get('umbral') or p.get('siguiente_monto')

    if siguiente and restante is None and umbral is not None:
        try:
            restante = max(0, float(umbral) - float(gasto_total or 0))
        except Exception:
            restante = 0

    if siguiente and pct is None and umbral:
        try:
            pct = min(100, int((float(gasto_total or 0) / float(umbral)) * 100))
        except Exception:
            pct = 0

    return {
        'nivel_actual':         nivel_actual,
        'siguiente_nivel':      siguiente,
        'gasto_actual':         round(float(gasto_total or 0), 2),
        'gasto_para_siguiente': umbral,
        'gasto_restante':       round(float(restante or 0), 2),
        'progreso_pct':         round(float(pct or 0), 1),
    }


def _serializar_cupon(c):
    if not isinstance(c, dict):
        return None
    return {
        'codigo':           c.get('codigo') or c.get('cupon_codigo') or '',
        'titulo':           c.get('titulo') or c.get('nombre') or 'Cupón ORION',
        'descuento':        c.get('descuento') or c.get('valor') or c.get('monto') or '',
        'descripcion':      c.get('descripcion') or '',
        'info':             c.get('info') or c.get('condiciones') or '',
        'fecha_expiracion': c.get('fecha_expiracion')
                            or c.get('expiracion')
                            or c.get('vigencia')
                            or '',
    }


def _beneficios_default(nivel):
    mapa = {
        'Bronce':   ['1 punto por cada $10 de compra',
                     'Acceso a promociones generales'],
        'Plata':    ['Envío gratis en compras +$299',
                     '5% de descuento adicional',
                     'Puntos x1.5 en todas tus compras'],
        'Oro':      ['Envío gratis sin mínimo',
                     '10% de descuento adicional',
                     'Puntos x2 en todas tus compras',
                     'Acceso anticipado a rebajas'],
        'Diamante': ['Envío gratis sin mínimo',
                     '15% de descuento adicional',
                     'Puntos x3 en todas tus compras',
                     'Atención personalizada 24/7',
                     'Regalos exclusivos'],
    }
    return mapa.get(nivel, mapa['Bronce'])


def _obtener_registro_o_crear(usuario_id, nombre):
    registro = Lealtad.obtener_por_usuario(usuario_id)
    if not registro:
        Lealtad.obtener_o_crear(usuario_id, nombre)
        registro = Lealtad.obtener_por_usuario(usuario_id)
    return registro


# ================================================================
# VISTA CLIENTE (HTML)
# ================================================================

def mi_lealtad():
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus beneficios', 'warning')
        return redirect(url_for('web.login'))

    usuario_id = session['user_id']
    nombre = session.get('nombre', 'Cliente')

    Lealtad.obtener_o_crear(usuario_id, nombre)

    try:
        LealtadService.generar_cupones_para_cliente(usuario_id)
    except Exception:
        pass

    registro = Lealtad.obtener_por_usuario(usuario_id)
    if not registro:
        flash('Error cargando tu información de lealtad', 'danger')
        return redirect(url_for('web.dashboard'))

    info_nivel = Lealtad.obtener_info_nivel(registro.get('nivel', 'Bronce')) or {}
    progreso   = Lealtad.obtener_progreso_nivel(registro.get('gasto_total', 0)) or {}

    try:
        beneficios = LealtadService.calcular_beneficios_checkout(usuario_id, 0)
    except Exception:
        beneficios = {}

    registro['_id'] = str(registro['_id'])

    cupones_activos = [
        _serializar_cupon(c)
        for c in registro.get('cupones_personalizados', [])
        if isinstance(c, dict) and not c.get('usado', False)
    ]
    cupones_activos = [c for c in cupones_activos if c]

    return render_template(
        'tienda/lealtad_cliente.html',
        registro=registro,
        info_nivel=info_nivel,
        progreso=progreso,
        beneficios=beneficios,
        cupones=cupones_activos,
        niveles=Lealtad.NIVELES,
        total_cupones=len(cupones_activos),
        nombre=nombre
    )


# ================================================================
# ⭐ API JSON — Cliente Consentido (perfil.html)
# ================================================================

def api_mi_lealtad():
    """
    GET /api/lealtad/mi-info

    ⭐ AHORA CALCULA gasto_total y compras_realizadas desde db.pedidos
       en tiempo real, en lugar de confiar solo en el registro de lealtad.
    """
    if 'user_id' not in session:
        return _no_cache({"success": False, "error": "No autenticado"}, 401)

    usuario_id = session['user_id']
    nombre = session.get('nombre', 'Cliente')

    try:
        registro = _obtener_registro_o_crear(usuario_id, nombre)
    except Exception as e:
        return _no_cache({
            "success": False,
            "error": f"Error obteniendo registro: {e}"
        }, 500)

    if not registro:
        return _no_cache({"success": False, "error": "No encontrado"}, 404)

    # ------------------------------------------------------------
    # ⭐ GASTO Y COMPRAS — calculados en tiempo real desde pedidos
    # ------------------------------------------------------------
    gasto_registro   = float(registro.get('gasto_total', 0) or 0)
    compras_registro = int(registro.get('compras_realizadas', 0) or 0)

    # Calcular desde pedidos
    gasto_real, compras_real = _calcular_gasto_real(usuario_id)

    # Usar el mayor de los dos (por si el registro ya tiene datos buenos)
    gasto_total = max(gasto_registro, gasto_real)
    compras     = max(compras_registro, compras_real)

    print(f'[lealtad] uid={usuario_id} | '
          f'registro(gasto=${gasto_registro:.2f}, compras={compras_registro}) | '
          f'real(gasto=${gasto_real:.2f}, compras={compras_real}) | '
          f'FINAL(gasto=${gasto_total:.2f}, compras={compras})', flush=True)

    # Si el registro tiene datos desactualizados, sincronizarlo
    if gasto_real > gasto_registro or compras_real > compras_registro:
        try:
            Lealtad.collection.update_one(
                {'_id': registro['_id']} if '_id' in registro and isinstance(registro['_id'], ObjectId)
                else {'usuario_id': usuario_id},
                {'$set': {
                    'gasto_total':        gasto_total,
                    'compras_realizadas': compras,
                    'updated_at':         datetime.now(timezone.utc),
                }}
            )
            print(f'[lealtad] Registro sincronizado para uid={usuario_id}', flush=True)
        except Exception as e:
            print(f'[lealtad] No se pudo sincronizar registro: {e}', flush=True)

    # ------------------------------------------------------------
    # NIVEL, PROGRESO, BENEFICIOS
    # ------------------------------------------------------------
    nivel_actual, _ = _calcular_nivel(gasto_total)

    info_nivel = Lealtad.obtener_info_nivel(nivel_actual) or {}

    # Progreso calculado directamente (ignoramos el del modelo porque
    # puede estar desactualizado)
    progreso = _calcular_progreso(gasto_total, nivel_actual)

    # Beneficios
    beneficios = info_nivel.get('beneficios') or []
    if not beneficios:
        beneficios = _beneficios_default(nivel_actual)

    # ------------------------------------------------------------
    # CUPONES
    # ------------------------------------------------------------
    cupones_raw = [
        c for c in registro.get('cupones_personalizados', [])
        if isinstance(c, dict) and not c.get('usado', False)
    ]
    cupones = [_serializar_cupon(c) for c in cupones_raw]
    cupones = [c for c in cupones if c]

    # ------------------------------------------------------------
    # PUNTOS
    # ------------------------------------------------------------
    puntos = int(registro.get('puntos_disponibles', 0) or 0)

    # Si no hay puntos guardados pero sí gasto, calcularlos
    # (1 punto por cada $10 * multiplicador del nivel)
    if puntos == 0 and gasto_total > 0:
        _, mult = _calcular_nivel(gasto_total)
        puntos = int((gasto_total / 10) * mult)

    valor_punto = float(getattr(Lealtad, 'VALOR_PUNTO', 0.01) or 0.01)

    # ------------------------------------------------------------
    # HISTORIAL DE PUNTOS
    # ------------------------------------------------------------
    historial = []
    try:
        raw_hist = registro.get('historial_puntos') or registro.get('historial') or []
        for h in raw_hist:
            if not isinstance(h, dict):
                continue
            fecha = h.get('fecha') or h.get('created_at')
            historial.append({
                'descripcion': h.get('descripcion') or h.get('motivo') or 'Movimiento',
                'puntos':      int(h.get('puntos', 0) or 0),
                'fecha':       fecha.isoformat()
                               if hasattr(fecha, 'isoformat')
                               else (str(fecha) if fecha else ''),
            })
    except Exception as e:
        print(f'[lealtad] Error historial: {e}', flush=True)

    # ------------------------------------------------------------
    # RESPUESTA FINAL
    # ------------------------------------------------------------
    return _no_cache({
        "success": True,

        # Nivel
        "nivel":       nivel_actual,
        "emoji_nivel": info_nivel.get('emoji', '🥉'),
        "color_nivel": info_nivel.get('color', '#CD7F32'),

        # Puntos
        "puntos_disponibles": puntos,
        "puntos_historicos":  int(registro.get('puntos_historicos', 0) or puntos),
        "valor_puntos":       round(puntos * valor_punto, 2),

        # ⭐ Gasto y compras — AHORA SÍ VIENEN DE PEDIDOS
        "gasto_total":        round(gasto_total, 2),
        "compras_realizadas": compras,

        # Progreso
        "progreso": progreso,

        # Cupones
        "cupones":       cupones,
        "total_cupones": len(cupones),

        # Beneficios
        "beneficios_actuales": beneficios,

        # Historial
        "historial_puntos": historial,
    })


# ================================================================
# CANJE DE PUNTOS
# ================================================================

def canjear_puntos_cliente():
    if 'user_id' not in session:
        return _no_cache({"success": False, "error": "No autenticado"}, 401)

    data = request.get_json(silent=True) or {}
    try:
        puntos = int(data.get('puntos', 0))
    except (ValueError, TypeError):
        puntos = 0

    if puntos <= 0:
        return _no_cache({"success": False, "error": "Cantidad inválida"}, 400)

    resultado = Lealtad.canjear_puntos(
        session['user_id'],
        puntos,
        motivo="Canje desde mi cuenta"
    )

    if not resultado:
        return _no_cache({"success": False, "error": "Error al canjear"}, 500)

    return _no_cache(resultado)


# ================================================================
# VISTA ADMIN
# ================================================================

def admin_lealtad_panel():
    if 'user_id' not in session:
        return redirect(url_for('web.login'))

    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No autorizado', 'danger')
        return redirect(url_for('web.dashboard'))

    stats = Lealtad.estadisticas()
    clientes = Lealtad.listar_por_nivel(limite=200)

    for c in clientes:
        c['_id'] = str(c['_id'])

    return render_template(
        'admin/lealtad_admin.html',
        stats=stats,
        clientes=clientes,
        niveles=Lealtad.NIVELES
    )


def api_admin_stats():
    stats = Lealtad.estadisticas()
    return _no_cache({"success": True, **(stats or {})})


def api_admin_listar_clientes():
    nivel = request.args.get('nivel')
    try:
        limite = int(request.args.get('limite', 100))
    except (ValueError, TypeError):
        limite = 100

    clientes = Lealtad.listar_por_nivel(nivel=nivel, limite=limite)

    data = []
    for c in clientes:
        info_nivel = Lealtad.obtener_info_nivel(c.get('nivel', 'Bronce')) or {}
        data.append({
            "_id": str(c['_id']),
            "usuario_id": c.get('usuario_id'),
            "nombre": c.get('nombre_usuario', 'Cliente'),
            "nivel": c.get('nivel', 'Bronce'),
            "emoji_nivel": info_nivel.get('emoji', '🥉'),
            "puntos_disponibles": c.get('puntos_disponibles', 0),
            "puntos_historicos": c.get('puntos_historicos', 0),
            "gasto_total": round(float(c.get('gasto_total', 0) or 0), 2),
            "compras_realizadas": c.get('compras_realizadas', 0),
            "cupones_activos": len([
                x for x in c.get('cupones_personalizados', [])
                if isinstance(x, dict) and not x.get('usado')
            ])
        })

    return _no_cache({"success": True, "clientes": data})


def admin_ajustar_puntos():
    data = request.get_json(silent=True) or {}
    usuario_id = data.get('usuario_id')
    try:
        puntos = int(data.get('puntos', 0))
    except (ValueError, TypeError):
        puntos = 0
    motivo = data.get('motivo', 'Ajuste admin')

    if not usuario_id or puntos == 0:
        return _no_cache({"success": False, "error": "Datos inválidos"}, 400)

    resultado = Lealtad.ajustar_puntos(usuario_id, puntos, motivo)
    if not resultado:
        return _no_cache({"success": False, "error": "Error al ajustar"}, 500)

    return _no_cache(resultado)


def admin_generar_cupones_masivos():
    data = request.get_json(silent=True) or {}
    nivel = data.get('nivel')
    monto_minimo = data.get('monto_minimo')

    resultado = LealtadService.generar_cupones_masivos(nivel, monto_minimo)
    return _no_cache({"success": True, **(resultado or {})})


def admin_otorgar_puntos_masivos():
    data = request.get_json(silent=True) or {}
    nivel = data.get('nivel')
    try:
        puntos = int(data.get('puntos', 0))
    except (ValueError, TypeError):
        puntos = 0
    motivo = data.get('motivo', 'Campaña especial')

    if puntos <= 0:
        return _no_cache({"success": False, "error": "Puntos inválidos"}, 400)

    filtro = {}
    if nivel and nivel != 'todos':
        filtro['nivel'] = nivel

    clientes = list(Lealtad.collection.find(filtro))
    total_otorgados = 0

    for c in clientes:
        try:
            Lealtad.ajustar_puntos(c['usuario_id'], puntos, motivo)
            total_otorgados += 1
        except Exception:
            continue

    return _no_cache({
        "success": True,
        "clientes_afectados": total_otorgados,
        "puntos_por_cliente": puntos,
        "puntos_totales_otorgados": total_otorgados * puntos
    })