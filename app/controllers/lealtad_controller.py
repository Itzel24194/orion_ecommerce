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


def _verificar_admin():
    if 'user_id' not in session:
        return None
    try:
        return current_app.db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception:
        return None


# ⭐ FUNCIÓN CORREGIDA: busca en 'mesas_regalos' (plural)
def _obtener_mesas_regalo(usuario_id):
    """
    Devuelve (mesas_regalo, bonificacion_total).
    Bonificación = 10% del fondo recaudado (fund_raised) de cada mesa activa.
    """
    mesas = []
    bonificacion_total = 0.0
    try:
        db = current_app.db
        uid_str = str(usuario_id)
        uid_obj = _to_oid(uid_str)

        query = {
            '$or': [
                {'owner_id': uid_obj},
                {'owner_id': uid_str},
                {'usuario_id': uid_obj},
                {'usuario_id': uid_str},
            ]
        }

        # ✅ CORREGIDO: mesas_regalos (PLURAL)
        mesas = list(db.mesas_regalos.find(query))

        for mesa in mesas:
            if not mesa.get('activa', True):
                continue

            try:
                fondo = float(mesa.get('fund_raised') or 0)
            except (ValueError, TypeError):
                fondo = 0.0

            if fondo > 0:
                bonificacion_total += fondo * 0.10

    except Exception as e:
        print(f'[lealtad] Error obteniendo mesas_regalo: {e}', flush=True)
        mesas = []
        bonificacion_total = 0.0

    return mesas, bonificacion_total


# ================================================================
# CÁLCULO REAL DE GASTO Y COMPRAS DESDE db.pedidos
# ================================================================

_ESTADOS_INVALIDOS = (
    'cancelado', 'cancelada', 'cancelled',
    'rechazado', 'rechazada', 'rejected',
    'devuelto', 'devuelta', 'refunded',
)


def _calcular_gasto_real(usuario_id):
    try:
        db = current_app.db
    except Exception:
        return 0.0, 0

    uid_str = str(usuario_id)
    uid_obj = _to_oid(uid_str)

    filtro_usuario = {'$or': [
        {'usuario_id': uid_obj},
        {'usuario_id': uid_str},
        {'user_id': uid_obj},
        {'user_id': uid_str},
        {'cliente_id': uid_obj},
        {'cliente_id': uid_str},
    ]}

    filtro_estado = {
        '$nor': [
            {'estado': {'$in': list(_ESTADOS_INVALIDOS)}},
            {'estado': {'$in': [e.upper() for e in _ESTADOS_INVALIDOS]}},
            {'estado': {'$in': [e.capitalize() for e in _ESTADOS_INVALIDOS]}},
            {'estado': 'Cancelado'},
            {'estado': 'CANCELADO'},
        ]
    }

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
            return gasto, compras
    except Exception as e:
        print(f'[lealtad] Error agregación pedidos: {e}', flush=True)

    try:
        gasto = 0.0
        compras = 0
        for p in db.pedidos.find(filtro_usuario):
            estado = str(p.get('estado', '') or '').lower()
            if estado in _ESTADOS_INVALIDOS:
                continue
            gasto += float(p.get('total', 0) or 0)
            compras += 1
        return gasto, compras
    except Exception as e:
        print(f'[lealtad] Error iterando pedidos: {e}', flush=True)
        return 0.0, 0


def _calcular_nivel(gasto):
    if gasto >= 50000:
        return 'Diamante', 3.0
    if gasto >= 20000:
        return 'Oro', 2.0
    if gasto >= 5000:
        return 'Plata', 1.5
    return 'Bronce', 1.0


def _calcular_progreso(gasto, nivel_actual):
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

    return {
        'nivel_actual':         'Diamante',
        'siguiente_nivel':      None,
        'gasto_actual':         round(gasto, 2),
        'gasto_para_siguiente': None,
        'gasto_restante':       0,
        'progreso_pct':         100.0,
    }


# ================================================================
# ⭐ SINCRONIZACIÓN DEL REGISTRO
# ================================================================

def _sincronizar_registro(registro, usuario_id):
    if not registro:
        return registro

    gasto_registro   = float(registro.get('gasto_total', 0) or 0)
    compras_registro = int(registro.get('compras_realizadas', 0) or 0)

    gasto_real, compras_real = _calcular_gasto_real(usuario_id)

    gasto_total = max(gasto_registro, gasto_real)
    compras     = max(compras_registro, compras_real)

    nivel_correcto, multiplicador = _calcular_nivel(gasto_total)
    nivel_registro = registro.get('nivel') or 'Bronce'

    necesita_update = (
        gasto_real > gasto_registro
        or compras_real > compras_registro
        or nivel_registro != nivel_correcto
    )

    if necesita_update:
        try:
            filtro = (
                {'_id': registro['_id']}
                if '_id' in registro and isinstance(registro['_id'], ObjectId)
                else {'usuario_id': usuario_id}
            )
            Lealtad.collection.update_one(
                filtro,
                {'$set': {
                    'gasto_total':          gasto_total,
                    'compras_realizadas':   compras,
                    'nivel':                nivel_correcto,
                    'multiplicador_puntos': multiplicador,
                    'updated_at':           datetime.now(timezone.utc),
                }}
            )
            print(f'[lealtad] Registro sincronizado uid={usuario_id} '
                  f'gasto={gasto_total} compras={compras} nivel={nivel_correcto}',
                  flush=True)
        except Exception as e:
            print(f'[lealtad] Error sincronizando registro: {e}', flush=True)

    registro['gasto_total'] = gasto_total
    registro['compras_realizadas'] = compras
    registro['nivel'] = nivel_correcto
    registro['multiplicador_puntos'] = multiplicador
    return registro


def _sincronizar_todos_los_clientes():
    """Recorre la colección completa y sincroniza cada registro."""
    try:
        todos = list(Lealtad.collection.find({}))
    except Exception as e:
        print(f'[lealtad] Error listando clientes para sincronizar: {e}', flush=True)
        return
    for c in todos:
        uid = c.get('usuario_id')
        if uid:
            _sincronizar_registro(c, uid)


# ================================================================
# ⭐ SERIALIZADOR DE CUPÓN — con flag "usado" correcto
# ================================================================

_COLORES_POR_REGLA = {
    'bienvenida':    '#00A650',
    'nivel':         '#C99B2E',
    'reactivacion':  '#FF9900',
    'proximo_nivel': '#E6007E',
    'leal':          '#00A650',
    'manual':        '#E6007E',
}


def _serializar_cupon(c):
    if not isinstance(c, dict):
        return None

    cupon_id = c.get('id') or c.get('codigo') or c.get('cupon_codigo') or ''
    if isinstance(cupon_id, ObjectId):
        cupon_id = str(cupon_id)

    tipo_regla = c.get('tipo_regla') or 'manual'
    color = c.get('color') or _COLORES_POR_REGLA.get(tipo_regla, '#E6007E')

    tipo_descuento = c.get('tipo') or 'porcentaje'
    valor = c.get('valor')
    if valor is None:
        valor = c.get('descuento') or c.get('monto') or ''
        if isinstance(valor, str) and valor.endswith('%'):
            try:
                valor = float(valor.strip('%'))
            except Exception:
                pass

    valido_hasta = (
        c.get('valido_hasta')
        or c.get('fecha_expiracion')
        or c.get('expiracion')
        or c.get('vigencia')
        or ''
    )
    if hasattr(valido_hasta, 'isoformat'):
        valido_hasta = valido_hasta.isoformat()

    usado = bool(
        c.get('usado', False)
        or c.get('utilizado', False)
        or c.get('canjeado', False)
        or c.get('usado_en')
        or c.get('fecha_uso')
    )

    return {
        'id':            cupon_id,
        'codigo':        cupon_id,
        'tipo_regla':    tipo_regla,
        'motivo':        c.get('motivo') or '',
        'titulo':        c.get('titulo') or c.get('nombre') or 'Cupón ORION',
        'descripcion':   c.get('descripcion') or '',
        'info':          c.get('info') or c.get('condiciones') or '',
        'color':         color,
        'tipo':          tipo_descuento,
        'valor':         valor,
        'descuento':     c.get('descuento') or (
                            f"{valor}%" if tipo_descuento == 'porcentaje' and valor != '' else
                            f"${valor}" if valor != '' else ''
                         ),
        'valido_hasta':  str(valido_hasta)[:19] if valido_hasta else '',
        'fecha_expiracion': str(valido_hasta)[:19] if valido_hasta else '',
        'min_compra':    c.get('min_compra', 0),
        'envio_gratis':  bool(c.get('envio_gratis', False)),
        'regalo':        bool(c.get('regalo', False)),
        'usado':         usado,
        'usado_en':      str(c.get('usado_en') or c.get('fecha_uso') or '')[:19],
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


def _cupones_activos_de_registro(registro):
    """Filtra cupones NO usados y los serializa."""
    raw = registro.get('cupones_personalizados') or []
    if not isinstance(raw, list):
        raw = []

    activos = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        usado = bool(
            c.get('usado', False)
            or c.get('utilizado', False)
            or c.get('canjeado', False)
            or c.get('usado_en')
            or c.get('fecha_uso')
        )
        if usado:
            continue
        serializado = _serializar_cupon(c)
        if serializado:
            activos.append(serializado)
    return activos


def _cupones_usados_de_registro(registro):
    """Devuelve los cupones ya usados (para historial)."""
    raw = registro.get('cupones_personalizados') or []
    if not isinstance(raw, list):
        return []

    usados = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        usado = bool(
            c.get('usado', False)
            or c.get('utilizado', False)
            or c.get('canjeado', False)
            or c.get('usado_en')
            or c.get('fecha_uso')
        )
        if not usado:
            continue
        serializado = _serializar_cupon(c)
        if serializado:
            usados.append(serializado)
    return usados


# ================================================================
# VISTA CLIENTE (HTML)
# ================================================================

def mi_lealtad():
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus beneficios', 'warning')
        return redirect(url_for('web.login'))

    usuario_id = session['user_id']
    nombre = session.get('nombre', 'Cliente')

    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(usuario_id)

    Lealtad.obtener_o_crear(usuario_id, nombre)

    try:
        registro = _obtener_registro_o_crear(usuario_id, nombre)
        if registro:
            _sincronizar_registro(registro, usuario_id)
    except Exception as e:
        print(f'[mi_lealtad] Error sincronizando: {e}', flush=True)

    try:
        LealtadService.generar_cupones_para_cliente(usuario_id)
    except Exception as e:
        print(f'[mi_lealtad] No se pudieron generar cupones: {e}', flush=True)

    registro = Lealtad.obtener_por_usuario(usuario_id)
    if not registro:
        flash('Error cargando tu información de lealtad', 'danger')
        return redirect(url_for('web.dashboard'))

    registro = _sincronizar_registro(registro, usuario_id)

    info_nivel = Lealtad.obtener_info_nivel(registro.get('nivel', 'Bronce')) or {}
    progreso   = Lealtad.obtener_progreso_nivel(registro.get('gasto_total', 0)) or {}

    try:
        beneficios = LealtadService.calcular_beneficios_checkout(usuario_id, 0)
    except Exception:
        beneficios = {}

    registro['_id'] = str(registro['_id'])

    cupones_activos = _cupones_activos_de_registro(registro)
    cupones_usados  = _cupones_usados_de_registro(registro)

    categorias = []
    try:
        db = current_app.db
        categorias = list(db.categorias.find({}))
    except Exception:
        pass

    # ⭐ Obtener mesas de regalo y bonificación del 10%
    mesas_regalo, bonificacion_mesas = _obtener_mesas_regalo(usuario_id)

    return render_template(
        'tienda/lealtad_cliente.html',
        registro=registro,
        info_nivel=info_nivel,
        progreso=progreso,
        beneficios=beneficios,
        cupones=cupones_activos,
        cupones_usados=cupones_usados,
        niveles=Lealtad.NIVELES,
        total_cupones=len(cupones_activos),
        total_usados=len(cupones_usados),
        nombre=nombre,
        usuario=usuario,
        carrito_items=session.get('carrito', []) or [],
        categorias=categorias,
        mesas_regalo=mesas_regalo,
        bonificacion_mesas=bonificacion_mesas,
    )


# ================================================================
# API JSON — Cliente Consentido (perfil.html)
# ================================================================

def api_mi_lealtad():
    if 'user_id' not in session:
        return _no_cache({"success": False, "error": "No autenticado"}, 401)

    usuario_id = session['user_id']
    nombre = session.get('nombre', 'Cliente')

    try:
        registro = _obtener_registro_o_crear(usuario_id, nombre)
    except Exception as e:
        return _no_cache({"success": False, "error": f"Error obteniendo registro: {e}"}, 500)

    if not registro:
        return _no_cache({"success": False, "error": "No encontrado"}, 404)

    registro = _sincronizar_registro(registro, usuario_id)

    gasto_total = float(registro.get('gasto_total', 0) or 0)
    compras     = int(registro.get('compras_realizadas', 0) or 0)

    nivel_actual, _ = _calcular_nivel(gasto_total)
    info_nivel = Lealtad.obtener_info_nivel(nivel_actual) or {}
    progreso = _calcular_progreso(gasto_total, nivel_actual)

    beneficios = info_nivel.get('beneficios') or []
    if not beneficios:
        beneficios = _beneficios_default(nivel_actual)

    cupones         = _cupones_activos_de_registro(registro)
    cupones_usados  = _cupones_usados_de_registro(registro)

    puntos = int(registro.get('puntos_disponibles', 0) or 0)
    if puntos == 0 and gasto_total > 0:
        _, mult = _calcular_nivel(gasto_total)
        puntos = int((gasto_total / 10) * mult)

    valor_punto = float(getattr(Lealtad, 'VALOR_PUNTO', 0.01) or 0.01)

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
        print(f'[api_mi_lealtad] Error historial: {e}', flush=True)

    _, bonificacion_mesas = _obtener_mesas_regalo(usuario_id)

    return _no_cache({
        "success": True,
        "nivel":       nivel_actual,
        "emoji_nivel": info_nivel.get('emoji', '🥉'),
        "color_nivel": info_nivel.get('color', '#CD7F32'),
        "puntos_disponibles": puntos,
        "puntos_historicos":  int(registro.get('puntos_historicos', 0) or puntos),
        "valor_puntos":       round(puntos * valor_punto, 2),
        "gasto_total":        round(gasto_total, 2),
        "compras_realizadas": compras,
        "progreso": progreso,
        "cupones":       cupones,
        "total_cupones": len(cupones),
        "cupones_usados": cupones_usados,
        "total_usados":   len(cupones_usados),
        "beneficios_actuales": beneficios,
        "historial_puntos": historial,
        "bonificacion_mesas": round(bonificacion_mesas, 2),
    })


# ================================================================
# CANJE DE PUNTOS (cliente)
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

    _sincronizar_todos_los_clientes()

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

    _sincronizar_todos_los_clientes()

    clientes = Lealtad.listar_por_nivel(nivel=nivel, limite=limite)

    data = []
    for c in clientes:
        info_nivel = Lealtad.obtener_info_nivel(c.get('nivel', 'Bronce')) or {}

        raw_cupones = c.get('cupones_personalizados') or []
        cupones_activos = []
        if isinstance(raw_cupones, list):
            for x in raw_cupones:
                if not isinstance(x, dict):
                    continue
                usado = bool(
                    x.get('usado', False)
                    or x.get('utilizado', False)
                    or x.get('canjeado', False)
                    or x.get('usado_en')
                    or x.get('fecha_uso')
                )
                if usado:
                    continue
                cupones_activos.append({
                    "id":         x.get('id') or x.get('codigo') or '',
                    "titulo":     x.get('titulo') or '',
                    "tipo_regla": x.get('tipo_regla') or 'manual',
                    "motivo":     x.get('motivo') or '',
                })

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
            "cupones_activos": len(cupones_activos),
            "cupones_personalizados": cupones_activos,
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


# ================================================================
# ⭐ GENERACIÓN AUTOMÁTICA DE CUPONES (FIX COMPLETO)
# ================================================================

def admin_generar_cupones_masivos():
    data = request.get_json(silent=True) or {}
    nivel = data.get('nivel')
    monto_minimo = data.get('monto_minimo')

    if nivel in (None, '', 'null', 'None', 'undefined'):
        nivel = None
    if monto_minimo in (None, '', 'null', 'None', 'undefined', 0, '0'):
        monto_minimo = None
    else:
        try:
            monto_minimo = float(monto_minimo)
            if monto_minimo <= 0:
                monto_minimo = None
        except (ValueError, TypeError):
            monto_minimo = None

    _sincronizar_todos_los_clientes()

    resultado = {}
    error_service = None
    try:
        resultado = LealtadService.generar_cupones_masivos(nivel, monto_minimo) or {}
    except Exception as e:
        error_service = str(e)
        print(f'[admin_generar_cupones_masivos] Service error: {e}', flush=True)
        resultado = {}

    generados = (
        resultado.get('cupones_generados')
        or resultado.get('total_generados')
        or resultado.get('generados')
        or 0
    )
    omitidos = (
        resultado.get('cupones_omitidos')
        or resultado.get('total_omitidos')
        or resultado.get('omitidos')
        or 0
    )
    procesados = (
        resultado.get('clientes_procesados')
        or resultado.get('procesados')
        or len(resultado.get('detalle') or [])
    )
    detalle = resultado.get('detalle') or []

    if int(generados or 0) == 0 and not detalle:
        try:
            print('[admin_generar_cupones_masivos] Aplicando fallback por segmento', flush=True)
            solo = [str(nivel).lower()] if nivel else None
            resultados_fb = generar_cupones_automaticos_por_segmento(solo=solo)

            detalle_fb = []
            total_gen_fb = 0
            total_omi_fb = 0
            for r in resultados_fb:
                creados = int(r.get('creados', 0) or 0)
                benef = int(r.get('usuarios_beneficiados', 0) or 0)
                total_gen_fb += creados

                if creados > 0:
                    gen_list = [
                        {
                            'tipo_regla': r.get('id', 'nivel'),
                            'motivo': f"Segmento {r.get('segmento', '')} · {benef} usuarios",
                        }
                    ] * creados
                    omi_list = []
                else:
                    gen_list = []
                    omi_list = [{
                        'tipo_regla': r.get('id', 'nivel'),
                        'motivo': r.get('mensaje') or r.get('error') or 'Sin usuarios en el segmento',
                    }]
                    total_omi_fb += 1

                detalle_fb.append({
                    'nombre': r.get('segmento', 'Segmento'),
                    'nivel': nivel or 'todos',
                    'generados': gen_list,
                    'omitidos': omi_list,
                })

            resultado = {
                'clientes_procesados': len(resultados_fb),
                'cupones_generados': total_gen_fb,
                'cupones_omitidos': total_omi_fb,
                'detalle': detalle_fb,
                'error': None,
            }
            generados = total_gen_fb
            omitidos = total_omi_fb
            procesados = len(resultados_fb)
            detalle = detalle_fb
        except Exception as e:
            print(f'[admin_generar_cupones_masivos] Fallback error: {e}', flush=True)

    if error_service and int(generados or 0) == 0 and not detalle:
        return _no_cache({
            'success': False,
            'error': f'Error generando cupones: {error_service}',
            'clientes_procesados': 0,
            'cupones_generados': 0,
            'cupones_omitidos': 0,
            'total_generados': 0,
            'total_omitidos': 0,
            'detalle': [],
            'data': {
                'clientes_procesados': 0,
                'cupones_generados': 0,
                'cupones_omitidos': 0,
                'detalle': [],
            },
        }, 500)

    payload = {
        'success': True,
        'clientes_procesados': int(procesados or 0),
        'cupones_generados':   int(generados or 0),
        'cupones_omitidos':    int(omitidos or 0),
        'total_generados':     int(generados or 0),
        'total_omitidos':      int(omitidos or 0),
        'detalle':             detalle,
        'error':               resultado.get('error'),
    }
    payload['data'] = {
        'clientes_procesados': payload['clientes_procesados'],
        'cupones_generados':   payload['cupones_generados'],
        'cupones_omitidos':    payload['cupones_omitidos'],
        'detalle':             payload['detalle'],
    }
    return _no_cache(payload)


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
    if nivel and nivel not in ('todos', 'null', '', None):
        filtro['nivel'] = nivel

    clientes = list(Lealtad.collection.find(filtro))
    afectados = []

    for c in clientes:
        uid = c.get('usuario_id')
        if not uid:
            continue
        try:
            Lealtad.ajustar_puntos(uid, puntos, motivo)
            afectados.append({
                "usuario_id": str(uid),
                "nombre": c.get('nombre_usuario', 'Cliente'),
                "nivel": c.get('nivel', 'Bronce'),
            })
        except Exception:
            continue

    return _no_cache({
        "success": True,
        "clientes_afectados": len(afectados),
        "puntos_por_cliente": puntos,
        "puntos_totales_otorgados": len(afectados) * puntos,
        "detalle": afectados,
    })


# ================================================================
# ⭐ MARCAR CUPÓN DE LEALTAD COMO USADO
# ================================================================

def marcar_cupon_lealtad_usado(usuario_id, codigo_cupon, pedido_id=None):
    if not usuario_id or not codigo_cupon:
        return False

    codigo = str(codigo_cupon).strip().upper()
    if not codigo:
        return False

    db = current_app.db
    now = datetime.now(timezone.utc)

    uid_str = str(usuario_id)
    filtros_usuario = [{'usuario_id': uid_str}]
    try:
        filtros_usuario.append({'usuario_id': ObjectId(uid_str)})
    except Exception:
        pass

    marcado = False

    for filtro_usuario in filtros_usuario:
        try:
            res = db.lealtad.update_one(
                {
                    **filtro_usuario,
                    'cupones_personalizados': {
                        '$elemMatch': {
                            '$or': [
                                {'id': codigo},
                                {'codigo': codigo},
                                {'cupon_codigo': codigo},
                            ],
                            '$or_2': None,
                        }
                    }
                },
                {
                    '$set': {
                        'cupones_personalizados.$.usado': True,
                        'cupones_personalizados.$.usado_en': now,
                        'cupones_personalizados.$.pedido_id': str(pedido_id) if pedido_id else None,
                    }
                }
            )
            if res.modified_count > 0:
                marcado = True
                break
        except Exception:
            pass

        try:
            reg = db.lealtad.find_one(filtro_usuario)
            if not reg:
                continue
            cupones = reg.get('cupones_personalizados') or []
            if not isinstance(cupones, list):
                continue

            cambio = False
            for c in cupones:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get('id') or c.get('codigo') or c.get('cupon_codigo') or '').strip().upper()
                if cid != codigo:
                    continue
                ya_usado = bool(
                    c.get('usado', False)
                    or c.get('utilizado', False)
                    or c.get('canjeado', False)
                    or c.get('usado_en')
                )
                if ya_usado:
                    return False
                c['usado'] = True
                c['usado_en'] = now
                if pedido_id:
                    c['pedido_id'] = str(pedido_id)
                cambio = True
                break

            if cambio:
                db.lealtad.update_one(
                    {'_id': reg['_id']},
                    {'$set': {'cupones_personalizados': cupones}}
                )
                marcado = True
                break
        except Exception as e:
            print(f'[marcar_cupon_lealtad_usado] Error fallback: {e}', flush=True)

    if marcado:
        try:
            db.cupones_usuarios.insert_one({
                'usuario_id': uid_str,
                'cupon_codigo': codigo,
                'pedido_id': str(pedido_id) if pedido_id else None,
                'fecha_uso': now,
                'origen': 'lealtad',
            })
        except Exception as e:
            print(f'[marcar_cupon_lealtad_usado] Error insertando cupones_usuarios: {e}', flush=True)

    return marcado