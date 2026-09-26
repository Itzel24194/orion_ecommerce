# ================================================================
# app/controllers/complexion_controller.py
# Complexión y Tallas del cliente - Estilo Liverpool
# ================================================================

from flask import jsonify, request, session, current_app, flash, redirect, url_for
from bson import ObjectId
from datetime import datetime, timezone


# ================================================================
# OPCIONES DISPONIBLES (para el frontend)
# ================================================================

OPCIONES_COMPLEXION = [
    {'valor': 'delgada',  'etiqueta': 'Delgada',  'icono': 'bi-person'},
    {'valor': 'media',    'etiqueta': 'Media',    'icono': 'bi-person-fill'},
    {'valor': 'robusta',  'etiqueta': 'Robusta',  'icono': 'bi-person-plus-fill'},
    {'valor': 'extra',    'etiqueta': 'Extra',    'icono': 'bi-person-badge'},
]

TALLAS_CAMISA = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL']
TALLAS_PANTALON = ['26', '28', '30', '32', '34', '36', '38', '40', '42', '44']
TALLAS_CALZADO = [str(n) for n in range(22, 34)]  # 22 a 33 MX
TALLAS_SUJETADOR = ['32A', '32B', '32C', '34A', '34B', '34C', '34D',
                    '36A', '36B', '36C', '36D', '38B', '38C', '38D']

ESTILOS = [
    {'valor': 'casual',   'etiqueta': 'Casual'},
    {'valor': 'formal',   'etiqueta': 'Formal'},
    {'valor': 'deportivo', 'etiqueta': 'Deportivo'},
    {'valor': 'elegante', 'etiqueta': 'Elegante'},
    {'valor': 'bohemio',  'etiqueta': 'Bohemio'},
    {'valor': 'minimalista', 'etiqueta': 'Minimalista'},
    {'valor': 'streetwear', 'etiqueta': 'Streetwear'},
    {'valor': 'vintage',  'etiqueta': 'Vintage'},
]

COLORES = [
    'negro', 'blanco', 'gris', 'azul', 'rojo', 'verde',
    'amarillo', 'rosa', 'morado', 'naranja', 'beige',
    'café', 'dorado', 'plateado',
]


# ================================================================
# HELPERS
# ================================================================

def _get_usuario_actual():
    if 'user_id' not in session:
        return None
    try:
        db = current_app.db
        return db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception:
        return None


def _to_int(valor, default=None):
    try:
        if valor is None or valor == '':
            return default
        return int(float(valor))
    except (ValueError, TypeError):
        return default


def _to_float(valor, default=None):
    try:
        if valor is None or valor == '':
            return default
        return float(valor)
    except (ValueError, TypeError):
        return default


def _limpiar_string(valor, max_len=80):
    if valor is None:
        return ''
    s = str(valor).strip()
    return s[:max_len]


def _limpiar_lista(valor, max_items=20):
    if not isinstance(valor, list):
        return []
    return [_limpiar_string(v, 40) for v in valor if v][:max_items]


def _error(mensaje, status=400):
    """
    Helper para devolver errores SIEMPRE con 'success', 'error' y 'message'
    para que el frontend funcione con cualquiera de los dos campos.
    """
    return jsonify({
        'success': False,
        'error': mensaje,
        'message': mensaje,
    }), status


def _leer_complexion(usuario):
    """
    Lee la complexión priorizando la colección 'complexion'.
    Si no existe ahí, cae al espejo dentro del doc del usuario.
    """
    db = current_app.db

    # 1) Colección dedicada
    try:
        doc = db.complexion.find_one({'usuario_id': usuario['_id']})
        if doc:
            return doc
    except Exception:
        pass

    # 2) Espejo en el documento del usuario
    return usuario.get('complexion') or {}


def _guardar_complexion(usuario, complexion):
    """
    Guarda la complexión en:
      1. Colección 'complexion' (fuente de verdad, upsert por usuario_id)
      2. Espejo en db.usuarios.complexion (compatibilidad)
    Devuelve (ok, error_message)
    """
    db = current_app.db
    ahora = datetime.now(timezone.utc)

    # ---- 1) Colección dedicada ----
    try:
        db.complexion.update_one(
            {'usuario_id': usuario['_id']},
            {
                '$set': {
                    **complexion,
                    'usuario_id': usuario['_id'],
                    'updated_at': ahora,
                },
                '$setOnInsert': {'created_at': ahora},
            },
            upsert=True
        )
    except Exception as e:
        print(f"[Complexion] Error guardando en colección: {e}")
        return False, f'Error al guardar en colección: {str(e)}'

    # ---- 2) Espejo en usuario ----
    try:
        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {
                'complexion': complexion,
                'updated_at': ahora,
            }}
        )
    except Exception as e:
        # No abortamos: la colección ya quedó bien
        print(f"[Complexion] Error guardando espejo en usuario: {e}")

    return True, None


def _borrar_complexion(usuario):
    """Borra de la colección dedicada Y del espejo del usuario."""
    db = current_app.db
    try:
        db.complexion.delete_one({'usuario_id': usuario['_id']})
    except Exception as e:
        print(f"[Complexion] Error borrando colección: {e}")
    try:
        db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$unset': {'complexion': ''},
             '$set': {'updated_at': datetime.now(timezone.utc)}}
        )
    except Exception as e:
        print(f"[Complexion] Error borrando espejo: {e}")


# ================================================================
# VISTA (opcional, por si quieres una página dedicada)
# ================================================================

def mi_complexion():
    """Página dedicada (opcional). En el perfil se carga vía API."""
    from flask import render_template

    usuario = _get_usuario_actual()
    if not usuario:
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for('web.login'))

    complexion = _leer_complexion(usuario)

    return render_template(
        'tienda/complexion.html',
        usuario=usuario,
        complexion=complexion,
        opciones_complexion=OPCIONES_COMPLEXION,
        tallas_camisa=TALLAS_CAMISA,
        tallas_pantalon=TALLAS_PANTALON,
        tallas_calzado=TALLAS_CALZADO,
        tallas_sujetador=TALLAS_SUJETADOR,
        estilos=ESTILOS,
        colores=COLORES,
    )


# ================================================================
# API - OBTENER (formato COMPLETO, para la vista de perfil)
# ================================================================

def api_obtener_complexion():
    """Devuelve la complexión y tallas del usuario (formato completo)."""
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    complexion = _leer_complexion(usuario)

    datos = {
        'altura_cm':        complexion.get('altura_cm'),
        'peso_kg':          complexion.get('peso_kg'),
        'complexion':       complexion.get('complexion'),
        'talla_camisa':     complexion.get('talla_camisa'),
        'talla_pantalon':   complexion.get('talla_pantalon'),
        'talla_calzado':    complexion.get('talla_calzado'),
        'talla_sujetador':  complexion.get('talla_sujetador'),
        'medidas': {
            'pecho_cm':   (complexion.get('medidas') or {}).get('pecho_cm'),
            'cintura_cm': (complexion.get('medidas') or {}).get('cintura_cm'),
            'cadera_cm':  (complexion.get('medidas') or {}).get('cadera_cm'),
        },
        'estilos_preferidos': complexion.get('estilos_preferidos') or [],
        'colores_favoritos':  complexion.get('colores_favoritos') or [],
        'actualizado': complexion.get('actualizado') or complexion.get('updated_at'),
    }

    if hasattr(datos['actualizado'], 'isoformat'):
        datos['actualizado'] = datos['actualizado'].isoformat()

    return jsonify({
        'success': True,
        'complexion': datos,
        'genero': (usuario.get('genero') or usuario.get('sexo') or '').lower(),
        'opciones': {
            'complexion':       OPCIONES_COMPLEXION,
            'tallas_camisa':    TALLAS_CAMISA,
            'tallas_pantalon':  TALLAS_PANTALON,
            'tallas_calzado':   TALLAS_CALZADO,
            'tallas_sujetador': TALLAS_SUJETADOR,
            'estilos':          ESTILOS,
            'colores':          COLORES,
        },
    })


# ================================================================
# API - OBTENER MEDIDAS (formato PLANO para el modal PDP)
# Endpoint: GET /api/complexion/obtener
# ================================================================

def api_obtener_medidas():
    """
    Devuelve las medidas en formato plano, tal como las espera
    el modal de 'Mis medidas' del detalle de producto.
    """
    usuario = _get_usuario_actual()
    if not usuario:
        # Devolvemos 200 con success=False para que el JS no lo trate como error
        return jsonify({'success': False, 'medidas': None}), 200

    complexion = _leer_complexion(usuario)

    medidas = {
        'altura':         complexion.get('altura_cm'),
        'peso':           complexion.get('peso_kg'),
        'complexion':     complexion.get('complexion'),
        'talla_camisa':   complexion.get('talla_camisa'),
        'talla_pantalon': complexion.get('talla_pantalon'),
        'talla_calzado':  complexion.get('talla_calzado'),
    }

    return jsonify({
        'success': True,
        'medidas': medidas,
    })


# ================================================================
# API - GUARDAR (formato COMPLETO, para la vista de perfil)
# ================================================================

def api_guardar_complexion():
    """Guarda o actualiza la complexión y tallas del usuario."""
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}

    # ============================================================
    # VALIDACIONES
    # ============================================================
    altura = _to_int(data.get('altura_cm'))
    if altura is not None and (altura < 100 or altura > 250):
        return _error('La altura debe estar entre 100 y 250 cm', 400)

    peso = _to_float(data.get('peso_kg'))
    if peso is not None and (peso < 30 or peso > 300):
        return _error('El peso debe estar entre 30 y 300 kg', 400)

    complexion_val = _limpiar_string(data.get('complexion'), 20).lower()
    valores_complexion = [c['valor'] for c in OPCIONES_COMPLEXION]
    if complexion_val and complexion_val not in valores_complexion:
        complexion_val = ''

    talla_camisa = _limpiar_string(data.get('talla_camisa'), 5).upper()
    if talla_camisa and talla_camisa not in TALLAS_CAMISA:
        talla_camisa = ''

    talla_pantalon = _limpiar_string(data.get('talla_pantalon'), 5)
    if talla_pantalon and talla_pantalon not in TALLAS_PANTALON:
        talla_pantalon = ''

    talla_calzado = _limpiar_string(data.get('talla_calzado'), 5)
    if talla_calzado and talla_calzado not in TALLAS_CALZADO:
        talla_calzado = ''

    talla_sujetador = _limpiar_string(data.get('talla_sujetador'), 6).upper()
    if talla_sujetador and talla_sujetador not in TALLAS_SUJETADOR:
        talla_sujetador = ''

    medidas_in = data.get('medidas') or {}
    pecho = _to_int(medidas_in.get('pecho_cm'))
    cintura = _to_int(medidas_in.get('cintura_cm'))
    cadera = _to_int(medidas_in.get('cadera_cm'))

    for nombre, valor in [('pecho', pecho), ('cintura', cintura), ('cadera', cadera)]:
        if valor is not None and (valor < 40 or valor > 200):
            return _error(f'La medida de {nombre} debe estar entre 40 y 200 cm', 400)

    estilos = _limpiar_lista(data.get('estilos_preferidos'), 10)
    colores_fav = _limpiar_lista(data.get('colores_favoritos'), 15)

    # ============================================================
    # ARMAR DOCUMENTO
    # ============================================================
    complexion = {
        'altura_cm':         altura,
        'peso_kg':           peso,
        'complexion':        complexion_val or None,
        'talla_camisa':      talla_camisa or None,
        'talla_pantalon':    talla_pantalon or None,
        'talla_calzado':     talla_calzado or None,
        'talla_sujetador':   talla_sujetador or None,
        'medidas': {
            'pecho_cm':   pecho,
            'cintura_cm': cintura,
            'cadera_cm':  cadera,
        },
        'estilos_preferidos': estilos,
        'colores_favoritos':  colores_fav,
        'actualizado': datetime.now(timezone.utc),
    }

    # ============================================================
    # GUARDAR (colección 'complexion' + espejo en usuario)
    # ============================================================
    ok, err = _guardar_complexion(usuario, complexion)
    if not ok:
        return _error(err, 500)

    complexion_resp = dict(complexion)
    complexion_resp['actualizado'] = complexion_resp['actualizado'].isoformat()

    return jsonify({
        'success': True,
        'message': 'Complexión guardada correctamente',
        'complexion': complexion_resp,
    })


# ================================================================
# API - GUARDAR MEDIDAS (formato PLANO para el modal PDP)
# Endpoint: POST /api/complexion/guardar
# ================================================================

def api_guardar_medidas():
    """
    Guarda las medidas enviadas desde el modal del detalle de producto.
    Acepta el payload plano: {altura, peso, complexion, talla_camisa,
    talla_pantalon, talla_calzado}
    """
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado. Inicia sesión para guardar tus medidas.', 401)

    data = request.get_json(silent=True) or {}

    # ── LOG DE DEBUG: imprime en consola lo que llega del frontend ──
    print(f"[Complexion] POST /guardar payload: {data}")
    print(f"[Complexion] Usuario: {usuario.get('email') or usuario.get('nombre') or usuario['_id']}")

    # ============================================================
    # VALIDACIONES
    # ============================================================
    altura = _to_int(data.get('altura'))
    if altura is None or altura < 100 or altura > 250:
        print(f"[Complexion] Altura inválida: {altura}")
        return _error('La altura debe estar entre 100 y 250 cm', 400)

    peso = _to_float(data.get('peso'))
    if peso is None or peso < 30 or peso > 300:
        print(f"[Complexion] Peso inválido: {peso}")
        return _error('El peso debe estar entre 30 y 300 kg', 400)

    complexion_val = _limpiar_string(data.get('complexion'), 20).lower()
    valores_complexion = [c['valor'] for c in OPCIONES_COMPLEXION]
    if complexion_val not in valores_complexion:
        print(f"[Complexion] Complexión inválida: '{complexion_val}' (válidas: {valores_complexion})")
        return _error('Complexión inválida', 400)

    talla_camisa = _limpiar_string(data.get('talla_camisa'), 5).upper()
    talla_pantalon = _limpiar_string(data.get('talla_pantalon'), 5)
    talla_calzado = _limpiar_string(data.get('talla_calzado'), 5)

    # ============================================================
    # PRESERVAR datos existentes que no vienen en este payload
    # ============================================================
    complexion_existente = _leer_complexion(usuario)
    medidas_existentes = complexion_existente.get('medidas') or {}

    complexion_nueva = {
        'altura_cm':         altura,
        'peso_kg':           peso,
        'complexion':        complexion_val,
        'talla_camisa':      talla_camisa or complexion_existente.get('talla_camisa'),
        'talla_pantalon':    talla_pantalon or complexion_existente.get('talla_pantalon'),
        'talla_calzado':     talla_calzado or complexion_existente.get('talla_calzado'),
        'talla_sujetador':   complexion_existente.get('talla_sujetador'),
        'medidas': {
            'pecho_cm':   medidas_existentes.get('pecho_cm'),
            'cintura_cm': medidas_existentes.get('cintura_cm'),
            'cadera_cm':  medidas_existentes.get('cadera_cm'),
        },
        'estilos_preferidos': complexion_existente.get('estilos_preferidos') or [],
        'colores_favoritos':  complexion_existente.get('colores_favoritos') or [],
        'actualizado': datetime.now(timezone.utc),
    }

    # ============================================================
    # GUARDAR (colección 'complexion' + espejo en usuario)
    # ============================================================
    ok, err = _guardar_complexion(usuario, complexion_nueva)
    if not ok:
        return _error(err, 500)

    print(f"[Complexion] Guardado OK en colección 'complexion' y espejo en usuario")

    return jsonify({
        'success': True,
        'message': 'Medidas guardadas correctamente',
        'medidas': {
            'altura':         altura,
            'peso':           peso,
            'complexion':     complexion_val,
            'talla_camisa':   complexion_nueva['talla_camisa'],
            'talla_pantalon': complexion_nueva['talla_pantalon'],
            'talla_calzado':  complexion_nueva['talla_calzado'],
        },
    })


# ================================================================
# API - LIMPIAR
# ================================================================

def api_limpiar_complexion():
    """Elimina los datos de complexión del usuario."""
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    _borrar_complexion(usuario)
    return jsonify({'success': True, 'message': 'Complexión eliminada'})


# ================================================================
# API - RECOMENDACIÓN DE TALLA (siempre devuelve HTTP 200)
# ================================================================

def api_recomendar_talla():
    """
    Sugiere una talla de camisa basándose en las medidas del usuario.
    Siempre devuelve HTTP 200, aunque no haya medidas (success=False),
    para que el fetch del frontend no falle con 400.
    """
    usuario = _get_usuario_actual()
    if not usuario:
        return jsonify({'success': False, 'message': 'No autenticado'}), 200

    complexion = _leer_complexion(usuario)
    medidas = complexion.get('medidas') or {}
    pecho = medidas.get('pecho_cm')
    complexion_val = complexion.get('complexion')

    # Si no hay pecho pero sí complexión, usamos la complexión como aproximación
    if not pecho and complexion_val:
        tabla_complexion = {'delgada': 'S', 'media': 'M', 'robusta': 'L', 'extra': 'XL'}
        return jsonify({
            'success': True,
            'talla_sugerida': tabla_complexion.get(complexion_val, 'M'),
            'basado_en': 'complexion',
            'valor': complexion_val,
        }), 200

    # Si no hay medidas, devolvemos success=False pero con HTTP 200
    if not pecho:
        return jsonify({
            'success': False,
            'message': 'Sin medidas registradas',
        }), 200

    # Tabla simple de referencia (cm → talla)
    tabla = [
        (86, 'XS'), (91, 'S'), (97, 'M'), (102, 'L'),
        (107, 'XL'), (112, 'XXL'), (120, '3XL'),
    ]

    talla_sugerida = '3XL'
    for cm_max, talla in tabla:
        if pecho <= cm_max:
            talla_sugerida = talla
            break

    return jsonify({
        'success': True,
        'talla_sugerida': talla_sugerida,
        'basado_en': 'pecho_cm',
        'valor': pecho,
    }), 200