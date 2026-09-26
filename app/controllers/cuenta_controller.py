# ================================================================
# app/controllers/cuenta_controller.py
# Preferencias + Lealtad + 2FA + Complexión + Intereses + Monedero
# + Direcciones + Facturación + Métodos de pago + Perfil
# ================================================================

from datetime import datetime, timezone
from flask import (jsonify, request, session, current_app,
                   render_template, redirect, url_for, send_file)
from bson import ObjectId
import secrets
import uuid
import math
import re
import io
import base64

# --- Dependencias opcionales ---
try:
    import pyotp
    _PYOTP_OK = True
except ImportError:
    _PYOTP_OK = False

try:
    import qrcode
    _QR_OK = True
except ImportError:
    _QR_OK = False


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


def _error(msg, status=400):
    return jsonify({'success': False, 'error': msg, 'message': msg}), status


def _flag(data, key):
    v = data.get(key)
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).lower() in ('1', 'true', 'on', 'yes', 'si', 'sí')


def _json_no_cache(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def _safe_oid(val):
    try:
        return ObjectId(str(val))
    except Exception:
        return None


def _to_oid(val):
    """Convierte a ObjectId si no lo es ya."""
    if isinstance(val, ObjectId):
        return val
    return _safe_oid(val)


def _verificar_password(stored, plain):
    """Verifica contra texto plano / Werkzeug / bcrypt / MD5 / SHA."""
    if not stored or not plain:
        return False
    stored_str = str(stored)

    if stored_str == plain:
        return True

    if stored_str.startswith(('pbkdf2:', 'scrypt:')):
        try:
            from werkzeug.security import check_password_hash
            if check_password_hash(stored_str, plain):
                return True
        except Exception:
            pass

    if stored_str.startswith(('$2a$', '$2b$', '$2y$')):
        try:
            import bcrypt
            if bcrypt.checkpw(plain.encode('utf-8'), stored_str.encode('utf-8')):
                return True
        except Exception:
            pass

    if len(stored_str) in (32, 40, 64):
        try:
            import hashlib
            if hashlib.md5(plain.encode()).hexdigest() == stored_str:
                return True
            if hashlib.sha1(plain.encode()).hexdigest() == stored_str:
                return True
            if hashlib.sha256(plain.encode()).hexdigest() == stored_str:
                return True
        except Exception:
            pass

    try:
        from werkzeug.security import check_password_hash
        return check_password_hash(stored_str, plain)
    except Exception:
        return False


def _normalizar_pedido(p):
    """Convierte ObjectId y fechas para que el template las use."""
    p['_id'] = str(p['_id'])
    p['total'] = float(p.get('total', 0) or 0)

    if isinstance(p.get('created_at'), str):
        try:
            p['created_at'] = datetime.fromisoformat(
                p['created_at'].replace('Z', '+00:00')
            )
        except Exception:
            p['created_at'] = None

    p['items_list'] = p.get('items') or p.get('productos') or p.get('detalles') or []
    return p


# Colores por nivel (usado por la vista Cliente Consentido)
_COLOR_NIVEL = {
    'Bronce':   '#CD7F32',
    'Plata':    '#A9AFBC',
    'Oro':      '#C99B2E',
    'Diamante': '#7A5FE0',
}


# ⭐ Colección REAL de favoritos (confirmado en tu Mongo)
_COLECCION_FAVORITOS = 'favoritos'

# Posibles colecciones de productos (por si acaso)
_COLECCIONES_PRODUCTOS = ('productos', 'producto', 'items', 'articles')


# ================================================================
# ⭐ VISTA PRINCIPAL: /perfil y /mi-cuenta  →  renderiza perfil.html
# ================================================================

def vista_perfil():
    """Renderiza perfil.html (en carpeta tienda/)."""
    if 'user_id' not in session:
        return redirect(url_for('web.login'))

    db = current_app.db
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    uid = usuario['_id']
    uid_str = str(uid)

    # ============================================================
    # PEDIDOS
    # ============================================================
    pedidos = []
    try:
        pedidos_cursor = db.pedidos.find({
            '$or': [
                {'usuario_id': uid},
                {'usuario_id': uid_str},
                {'user_id': uid},
                {'user_id': uid_str},
                {'cliente_id': uid},
                {'cliente_id': uid_str},
            ]
        }).sort('created_at', -1)
        pedidos = [_normalizar_pedido(p) for p in pedidos_cursor]
    except Exception as e:
        current_app.logger.error(f'[perfil] pedidos: {e}')

    # ============================================================
    # ⭐ FAVORITOS — fuente PRINCIPAL: colección `db.favoritos`
    # Estructura confirmada:
    #   { _id: ObjectId, usuario_id: ObjectId, producto_id: ObjectId, created_at }
    # ============================================================
    favoritos = []
    fav_oids = set()

    # -------- FUENTE 1: colección `db.favoritos` (LA QUE USAS) --------
    try:
        cursor_favs = db[_COLECCION_FAVORITOS].find({
            '$or': [
                {'usuario_id': uid},
                {'usuario_id': uid_str},
            ]
        })
        raw_docs = list(cursor_favs)

        current_app.logger.info(
            f'[perfil] uid={uid_str} | coleccion `{_COLECCION_FAVORITOS}` '
            f'devolvio {len(raw_docs)} documentos'
        )

        for doc in raw_docs:
            pid = doc.get('producto_id') or doc.get('productoId') or doc.get('producto')
            oid = _to_oid(pid)
            if oid:
                fav_oids.add(oid)

    except Exception as e:
        current_app.logger.error(f'[perfil] ERROR leyendo {_COLECCION_FAVORITOS}: {e}')

    # -------- FUENTE 2: array `usuario.favoritos` (por compatibilidad) --------
    try:
        arr = usuario.get('favoritos') or []
        if isinstance(arr, list) and arr:
            for f in arr:
                if isinstance(f, dict):
                    for k in ('producto_id', 'productoId', '_id', 'id'):
                        if f.get(k):
                            oid = _to_oid(f[k])
                            if oid:
                                fav_oids.add(oid)
                                break
                else:
                    oid = _to_oid(f)
                    if oid:
                        fav_oids.add(oid)
    except Exception as e:
        current_app.logger.error(f'[perfil] favoritos array usuario: {e}')

    current_app.logger.info(
        f'[perfil] uid={uid_str} | ObjectIds unicos de favoritos: {len(fav_oids)}'
    )

    # -------- Cargar los productos por ObjectId --------
    if fav_oids:
        for col_name in _COLECCIONES_PRODUCTOS:
            try:
                col = db[col_name]
                # Verificación: ¿existe la colección?
                if col.estimated_document_count() == 0:
                    continue

                for prod in col.find({'_id': {'$in': list(fav_oids)}}):
                    prod['_id'] = str(prod['_id'])
                    favoritos.append(prod)

                if favoritos:
                    current_app.logger.info(
                        f'[perfil] productos cargados desde `{col_name}` '
                        f'por ObjectId: {len(favoritos)}'
                    )
                    break
            except Exception as e:
                current_app.logger.error(f'[perfil] error buscando en {col_name}: {e}')

        # Fallback: por si los _id de productos están como STRINGS
        if not favoritos:
            str_ids = [str(o) for o in fav_oids]
            for col_name in _COLECCIONES_PRODUCTOS:
                try:
                    col = db[col_name]
                    if col.estimated_document_count() == 0:
                        continue
                    for prod in col.find({'_id': {'$in': str_ids}}):
                        prod['_id'] = str(prod['_id'])
                        favoritos.append(prod)
                    if favoritos:
                        current_app.logger.info(
                            f'[perfil] productos cargados desde `{col_name}` '
                            f'por STRING id: {len(favoritos)}'
                        )
                        break
                except Exception:
                    continue

    current_app.logger.info(
        f'[perfil] uid={uid_str} | FAVORITOS FINALES: {len(favoritos)}'
    )

    # ============================================================
    # CATEGORÍAS
    # ============================================================
    categorias = []
    try:
        for c in db.categorias.find({}):
            c['_id'] = str(c['_id'])
            categorias.append(c)
    except Exception:
        pass

    # ============================================================
    # CARRITO
    # ============================================================
    carrito_items = session.get('carrito', []) or []

    return render_template(
        'tienda/perfil.html',
        usuario=usuario,
        pedidos=pedidos,
        favoritos=favoritos,
        categorias=categorias,
        carrito_items=carrito_items,
    )


# ================================================================
# COMUNICACIONES
# ================================================================

def obtener_comunicaciones():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    prefs = usuario.get('preferencias_comunicacion') or {}
    defaults = {
        'email_promo': True, 'email_pedidos': True, 'email_newsletter': True,
        'wa_pedidos': True, 'wa_promo': False,
        'push_pedidos': True, 'push_promo': False,
    }
    resultado = {**defaults, **prefs}
    resultado['email_pedidos'] = True
    resultado.pop('updated_at', None)
    return jsonify({'success': True, 'preferencias': resultado})


def guardar_comunicaciones():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    prefs = {
        'email_promo':      _flag(data, 'email_promo'),
        'email_pedidos':    True,
        'email_newsletter': _flag(data, 'email_newsletter'),
        'wa_pedidos':       _flag(data, 'wa_pedidos'),
        'wa_promo':         _flag(data, 'wa_promo'),
        'push_pedidos':     _flag(data, 'push_pedidos'),
        'push_promo':       _flag(data, 'push_promo'),
        'updated_at':       datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'preferencias_comunicacion': prefs,
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    return jsonify({
        'success': True,
        'message': 'Preferencias de comunicación guardadas',
        'preferencias': prefs,
    })


# ================================================================
# PRIVACIDAD
# ================================================================

def obtener_privacidad():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    prefs = usuario.get('preferencias_privacidad') or {}
    defaults = {'personalizacion': True, 'analiticas': True, 'compartir_socios': False}
    resultado = {**defaults, **prefs}
    resultado.pop('updated_at', None)
    return jsonify({'success': True, 'preferencias': resultado})


def guardar_privacidad():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    prefs = {
        'personalizacion':  _flag(data, 'personalizacion'),
        'analiticas':       _flag(data, 'analiticas'),
        'compartir_socios': _flag(data, 'compartir_socios'),
        'updated_at':       datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'preferencias_privacidad': prefs,
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    return jsonify({
        'success': True,
        'message': 'Preferencias de privacidad guardadas',
        'preferencias': prefs,
    })


# ================================================================
# FACTURACIÓN (datos fiscales)
# ================================================================

def obtener_facturacion():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    datos = usuario.get('datos_fiscales') or {}
    updated = datos.get('updated_at')
    return _json_no_cache({
        'success': True,
        'datos': {
            'rfc':            datos.get('rfc', ''),
            'razon_social':   datos.get('razon_social', ''),
            'regimen_fiscal': datos.get('regimen_fiscal', ''),
            'uso_cfdi':       datos.get('uso_cfdi', ''),
            'updated_at':     updated.isoformat() if hasattr(updated, 'isoformat') else None,
        }
    })


def guardar_facturacion():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    rfc          = (data.get('rfc') or '').strip().upper()
    razon_social = (data.get('razon_social') or '').strip()
    regimen      = (data.get('regimen_fiscal') or '').strip()
    uso_cfdi     = (data.get('uso_cfdi') or '').strip()

    if rfc and len(rfc) not in (12, 13):
        return _error('El RFC debe tener 12 o 13 caracteres')
    if not razon_social:
        return _error('La razón social es obligatoria')

    datos = {
        'rfc': rfc, 'razon_social': razon_social,
        'regimen_fiscal': regimen, 'uso_cfdi': uso_cfdi,
        'updated_at': datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'datos_fiscales': datos,
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    out = dict(datos)
    out['updated_at'] = out['updated_at'].isoformat()
    return jsonify({
        'success': True,
        'message': 'Datos fiscales guardados correctamente',
        'datos': out,
    })


def factura_pdf(pedido_id):
    """GET /mi-cuenta/factura/<pedido_id>  →  render HTML imprimible."""
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    db = current_app.db
    oid = _safe_oid(pedido_id)
    if not oid:
        return _error('ID de pedido inválido', 400)

    pedido = db.pedidos.find_one({
        '_id': oid,
        '$or': [
            {'usuario_id': usuario['_id']},
            {'usuario_id': str(usuario['_id'])},
        ]
    })
    if not pedido:
        return _error('Pedido no encontrado', 404)

    pedido['_id'] = str(pedido['_id'])
    pedido['items_list'] = pedido.get('items') or pedido.get('productos') or []

    return render_template(
        'tienda/factura.html',
        pedido=pedido,
        usuario=usuario,
        fiscal=usuario.get('datos_fiscales') or {},
        generado=datetime.now(timezone.utc),
    )


# ================================================================
# IDIOMA / REGIÓN / MONEDA
# ================================================================

_IDIOMAS_VALIDOS = {'es-MX','es-ES','es-AR','es-CO','en-US','en-GB',
                    'pt-BR','pt-PT','fr-FR','de-DE','it-IT','ja-JP','zh-CN'}
_MONEDAS_VALIDAS = {'MXN','USD','EUR','GBP','BRL','ARS','COP','CLP','JPY','CNY'}
_PAISES_VALIDOS  = {'MX','US','ES','AR','CO','CL','PE','BR','PT','FR','DE','IT','JP','CN'}


def obtener_idioma():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    prefs = usuario.get('preferencias_idioma') or {}
    return jsonify({
        'success': True,
        'preferencias': {
            'idioma': prefs.get('idioma', 'es-MX'),
            'moneda': prefs.get('moneda', 'MXN'),
            'pais':   prefs.get('pais', 'MX'),
        }
    })


def guardar_idioma():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    idioma = (data.get('idioma') or 'es-MX').strip()
    moneda = (data.get('moneda') or 'MXN').strip().upper()
    pais   = (data.get('pais') or 'MX').strip().upper()

    if idioma not in _IDIOMAS_VALIDOS:
        return _error('Idioma no válido')
    if moneda not in _MONEDAS_VALIDAS:
        return _error('Moneda no válida')
    if pais not in _PAISES_VALIDOS:
        return _error('País no válido')

    prefs = {
        'idioma': idioma, 'moneda': moneda, 'pais': pais,
        'updated_at': datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'preferencias_idioma': prefs}}
    )

    return jsonify({
        'success': True,
        'message': 'Preferencias de idioma guardadas',
        'preferencias': {'idioma': idioma, 'moneda': moneda, 'pais': pais},
    })


def vista_previa_idioma():
    """GET /mi-cuenta/idioma/vista-previa?moneda=XXX"""
    if 'user_id' not in session:
        return _error('No autenticado', 401)

    moneda = (request.args.get('moneda') or 'MXN').upper()
    if moneda not in _MONEDAS_VALIDAS:
        moneda = 'MXN'

    tasas = {
        'MXN': 1.0, 'USD': 0.058, 'EUR': 0.053, 'GBP': 0.046,
        'BRL': 0.29, 'ARS': 5.8, 'COP': 230, 'CLP': 55,
        'JPY': 8.6, 'CNY': 0.42,
    }
    simbolos = {
        'MXN': '$', 'USD': '$', 'EUR': '€', 'GBP': '£',
        'BRL': 'R$', 'ARS': '$', 'COP': '$', 'CLP': '$',
        'JPY': '¥', 'CNY': '¥',
    }
    factor = tasas.get(moneda, 1.0)
    simbolo = simbolos.get(moneda, '$')

    db = current_app.db
    productos_out = []
    try:
        for p in db.productos.find({}).limit(3):
            precio_base = float(p.get('precio', 0) or 0)
            if p.get('variantes'):
                precio_base = float(p['variantes'][0].get('precio', precio_base))
            elif p.get('variables'):
                precio_base = float(p['variables'][0].get('precio', precio_base))

            convertido = precio_base * factor
            imagen = ''
            if p.get('fotos'):
                imagen = p['fotos'][0]
            elif p.get('imagenes'):
                imagen = p['imagenes'][0]

            productos_out.append({
                'id': str(p['_id']),
                'nombre': p.get('nombre', ''),
                'imagen': imagen,
                'precio_mostrado': f'{simbolo}{convertido:,.2f} {moneda}',
            })
    except Exception as e:
        current_app.logger.error(f'[vista_previa] {e}')

    return _json_no_cache({
        'success': True,
        'moneda': moneda,
        'productos': productos_out,
    })


# ================================================================
# MÉTODOS DE PAGO
# ================================================================

def _serializar_metodo(m):
    created = m.get('created_at')
    return {
        'id':                        str(m.get('id') or m.get('_id') or ''),
        '_id':                       str(m.get('_id') or ''),
        'tipo':                      m.get('tipo', 'tarjeta'),
        'marca':                     m.get('marca', ''),
        'ultimos4':                  m.get('ultimos4', ''),
        'titular':                   m.get('titular', ''),
        'expira':                    m.get('expira', ''),
        'email':                     m.get('email', ''),
        'referencia':                m.get('referencia'),
        'predeterminado':            bool(m.get('predeterminado', False)),
        'conekta_customer_id':       m.get('conekta_customer_id'),
        'conekta_payment_source_id': m.get('conekta_payment_source_id'),
        'created_at':                created.isoformat() if hasattr(created, 'isoformat') else None,
    }


def listar_metodos_pago():
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        metodos = list(db.metodos_pago.find({
            '$or': [{'usuario_id': uid_str}, {'usuario_id': usuario['_id']}]
        }).sort('created_at', -1))
        lista = [_serializar_metodo(m) for m in metodos]
        return _json_no_cache({'success': True, 'metodos': lista})
    except Exception as e:
        current_app.logger.error(f'[listar_metodos_pago] {e}')
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def agregar_metodo_pago():
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        data = request.get_json(silent=True) or request.form
        tipo = (data.get('tipo') or 'tarjeta').strip().lower()
        predeterminado = bool(data.get('predeterminado', False))
        uid_str = str(usuario['_id'])

        nuevo = {
            'id': secrets.token_urlsafe(16),
            'usuario_id': uid_str,
            'tipo': tipo,
            'predeterminado': predeterminado,
            'created_at': datetime.now(timezone.utc),
        }

        if tipo == 'tarjeta':
            token_id = (data.get('token_id') or '').strip()
            marca    = (data.get('marca') or 'Tarjeta').strip()
            ultimos4 = (data.get('ultimos4') or '').strip()
            titular  = (data.get('titular') or '').strip()
            expira   = (data.get('expira') or '').strip()

            if not ultimos4 or len(ultimos4) != 4 or not ultimos4.isdigit():
                return _json_no_cache({'success': False, 'message': 'Últimos 4 dígitos inválidos'}, 400)
            if not token_id:
                return _json_no_cache({'success': False, 'message': 'Falta el token de Conekta'}, 400)

            from app.services.conekta_service import (
                crear_o_actualizar_customer, crear_payment_source
            )
            cust_res = crear_o_actualizar_customer(
                usuario_id=uid_str,
                nombre=usuario.get('nombre', 'Cliente'),
                email=usuario.get('email', ''),
                telefono=usuario.get('telefono', ''),
                conekta_customer_id=usuario.get('conekta_customer_id'),
            )
            if not cust_res.get('success'):
                return _json_no_cache({
                    'success': False,
                    'message': f'Error customer: {cust_res.get("error")}'
                }, 500)

            customer_id = cust_res['customer_id']
            ps_res = crear_payment_source(customer_id, token_id)
            if not ps_res.get('success'):
                return _json_no_cache({
                    'success': False,
                    'message': f'Error payment source: {ps_res.get("error")}'
                }, 500)

            current_app.db.usuarios.update_one(
                {'_id': usuario['_id']},
                {'$set': {'conekta_customer_id': customer_id}}
            )
            nuevo.update({
                'marca': marca, 'ultimos4': ultimos4,
                'titular': titular, 'expira': expira,
                'conekta_customer_id': customer_id,
                'conekta_payment_source_id': ps_res['payment_source_id'],
            })

        elif tipo == 'paypal':
            email = (data.get('email') or '').strip()
            if not email:
                return _json_no_cache({'success': False, 'message': 'Email requerido'}, 400)
            nuevo['email'] = email

        elif tipo == 'oxxo':
            nuevo['referencia'] = str(uuid.uuid4())[:10].upper()
        else:
            return _json_no_cache({'success': False, 'message': 'Tipo inválido'}, 400)

        db = current_app.db
        if predeterminado:
            db.metodos_pago.update_many(
                {'usuario_id': uid_str}, {'$set': {'predeterminado': False}}
            )
        if db.metodos_pago.count_documents({'usuario_id': uid_str}) == 0:
            nuevo['predeterminado'] = True

        db.metodos_pago.insert_one(nuevo)
        return _json_no_cache({
            'success': True,
            'message': 'Método guardado correctamente',
            'metodo': _serializar_metodo(nuevo),
        })
    except Exception as e:
        current_app.logger.error(f'[agregar_metodo_pago] {e}')
        import traceback; traceback.print_exc()
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def eliminar_metodo_pago(metodo_id):
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        oid = _safe_oid(metodo_id)
        filtro_or = [{'id': metodo_id}]
        if oid:
            filtro_or.append({'_id': oid})

        resultado = db.metodos_pago.delete_one({
            '$or': filtro_or, 'usuario_id': uid_str,
        })
        if resultado.deleted_count == 0:
            return _json_no_cache({'success': False, 'message': 'Método no encontrado'}, 404)

        quedan = list(db.metodos_pago.find({'usuario_id': uid_str}))
        if quedan and not any(m.get('predeterminado') for m in quedan):
            db.metodos_pago.update_one(
                {'_id': quedan[0]['_id']}, {'$set': {'predeterminado': True}}
            )
        return _json_no_cache({'success': True, 'message': 'Método eliminado'})
    except Exception as e:
        current_app.logger.error(f'[eliminar_metodo_pago] {e}')
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


def establecer_metodo_predeterminado(metodo_id):
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'message': 'No autenticado'}, 401)

    try:
        db = current_app.db
        uid_str = str(usuario['_id'])
        oid = _safe_oid(metodo_id)
        filtro_or = [{'id': metodo_id}]
        if oid:
            filtro_or.append({'_id': oid})

        metodo = db.metodos_pago.find_one({
            '$or': filtro_or, 'usuario_id': uid_str,
        })
        if not metodo:
            return _json_no_cache({'success': False, 'message': 'Método no encontrado'}, 404)

        db.metodos_pago.update_many(
            {'usuario_id': uid_str}, {'$set': {'predeterminado': False}}
        )
        db.metodos_pago.update_one(
            {'_id': metodo['_id']}, {'$set': {'predeterminado': True}}
        )
        return _json_no_cache({'success': True, 'message': 'Método predeterminado actualizado'})
    except Exception as e:
        current_app.logger.error(f'[establecer_metodo_predeterminado] {e}')
        return _json_no_cache({'success': False, 'message': str(e)}, 500)


# ================================================================
# ⭐ LEALTAD / CLIENTE CONSENTIDO
# ================================================================

def _calcular_nivel_lealtad(gasto):
    if gasto >= 50000:
        return 'Diamante', '💎', 3.0
    if gasto >= 20000:
        return 'Oro', '🥇', 2.0
    if gasto >= 5000:
        return 'Plata', '🥈', 1.5
    return 'Bronce', '🥉', 1.0


def obtener_lealtad_mi_info():
    usuario = _get_usuario_actual()
    if not usuario:
        return _json_no_cache({'success': False, 'error': 'No autenticado'}, 401)

    db = current_app.db
    uid = usuario['_id']

    try:
        gasto_total = float(usuario.get('gasto_total', 0) or 0)
        compras = int(usuario.get('compras_realizadas', 0) or 0)

        if gasto_total == 0 or compras == 0:
            try:
                pipeline = [
                    {'$match': {
                        '$or': [{'usuario_id': uid}, {'usuario_id': str(uid)}],
                        'estado': {'$nin': ['cancelado', 'Cancelado', 'CANCELADO']},
                    }},
                    {'$group': {
                        '_id': None,
                        'total': {'$sum': '$total'},
                        'cantidad': {'$sum': 1},
                    }},
                ]
                res = list(db.pedidos.aggregate(pipeline))
                if res:
                    gasto_total = float(res[0].get('total', 0) or 0)
                    compras = int(res[0].get('cantidad', 0) or 0)
            except Exception:
                pass

        puntos = int(usuario.get('puntos_disponibles', 0) or 0)
        if puntos == 0 and gasto_total > 0:
            _, _, mult = _calcular_nivel_lealtad(gasto_total)
            puntos = int((gasto_total / 10) * mult)

        nivel, emoji, mult = _calcular_nivel_lealtad(gasto_total)

        niveles = [('Plata', 5000), ('Oro', 20000), ('Diamante', 50000)]
        progreso = {}
        for nombre, umbral in niveles:
            if gasto_total < umbral:
                restante = max(0, umbral - gasto_total)
                pct = min(100, int((gasto_total / umbral) * 100)) if umbral else 0
                progreso = {
                    'siguiente_nivel': nombre,
                    'gasto_restante': restante,
                    'progreso_pct': pct,
                    'gasto_actual': gasto_total,
                    'gasto_para_siguiente': umbral,
                    'nivel_actual': nivel,
                }
                break

        cupones = []
        try:
            for cu in db.cupones_usuarios.find({
                '$or': [{'usuario_id': uid}, {'usuario_id': str(uid)}],
                'usado': {'$ne': True},
            }):
                cupones.append({
                    'codigo':           cu.get('cupon_codigo', ''),
                    'titulo':           cu.get('titulo', 'Cupón ORION'),
                    'descuento':        cu.get('descuento', ''),
                    'descripcion':      cu.get('descripcion', ''),
                    'info':             cu.get('info', ''),
                    'fecha_expiracion': cu.get('fecha_expiracion', ''),
                })
        except Exception:
            pass

        beneficios_map = {
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
        beneficios = beneficios_map.get(nivel, [])

        historial = []
        try:
            for h in db.historial_puntos.find({
                '$or': [{'usuario_id': uid}, {'usuario_id': str(uid)}]
            }).sort('fecha', -1).limit(20):
                fecha = h.get('fecha')
                historial.append({
                    'descripcion': h.get('descripcion', 'Movimiento'),
                    'puntos':      int(h.get('puntos', 0) or 0),
                    'fecha':       fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha or ''),
                })
        except Exception:
            pass

        return _json_no_cache({
            'success': True,
            'nivel':              nivel,
            'emoji_nivel':        emoji,
            'color_nivel':        _COLOR_NIVEL.get(nivel, '#CD7F32'),
            'multiplicador':      mult,
            'puntos_disponibles': puntos,
            'valor_puntos':       round(puntos * 0.01, 2),
            'gasto_total':        gasto_total,
            'compras_realizadas': compras,
            'progreso':           progreso,
            'cupones':            cupones,
            'total_cupones':      len(cupones),
            'beneficios_actuales': beneficios,
            'historial_puntos':   historial,
            'puntos_historicos':  puntos,
        })

    except Exception as e:
        current_app.logger.error(f'[obtener_lealtad_mi_info] {e}')
        import traceback; traceback.print_exc()
        return _json_no_cache({'success': False, 'error': str(e)}, 500)


# ================================================================
# ⭐ 2FA
# ================================================================

def estado_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    tfa = usuario.get('two_factor') or {}
    codigos = tfa.get('codigos_respaldo', []) or []
    usados = [c for c in codigos if c.get('usado')]
    restantes = len(codigos) - len(usados)

    return _json_no_cache({
        'success': True,
        'habilitado': bool(tfa.get('habilitado', False)),
        'codigos_respaldo_restantes': restantes,
    })


def iniciar_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    if not _PYOTP_OK:
        return _error('pyotp no instalado en el servidor', 500)

    secreto = pyotp.random_base32()
    email = usuario.get('email', 'usuario')
    issuer = current_app.config.get('APP_NAME', 'ORION')

    uri = pyotp.TOTP(secreto).provisioning_uri(name=email, issuer_name=issuer)

    qr_base64 = ''
    if _QR_OK:
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode('ascii')

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'two_factor_pendiente': secreto}}
    )
    return _json_no_cache({
        'success': True,
        'secreto': secreto,
        'qr_base64': qr_base64,
    })


def confirmar_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    codigo = (data.get('codigo') or '').strip()

    secreto = usuario.get('two_factor_pendiente')
    if not secreto:
        return _error('No hay configuración 2FA en curso')

    if not pyotp.TOTP(secreto).verify(codigo, valid_window=1):
        return _error('Código incorrecto')

    codigos = [{'codigo': secrets.token_hex(4).upper(), 'usado': False} for _ in range(8)]

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {
            '$set': {
                'two_factor': {
                    'habilitado': True,
                    'secreto': secreto,
                    'codigos_respaldo': codigos,
                    'habilitado_en': datetime.now(timezone.utc),
                }
            },
            '$unset': {'two_factor_pendiente': ''}
        }
    )

    return _json_no_cache({
        'success': True,
        'codigos_respaldo': [c['codigo'] for c in codigos],
    })


def desactivar_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()

    stored = ''
    for campo in ('password', 'password_hash', 'contraseña', 'contrasena', 'hash', 'clave'):
        if usuario.get(campo):
            stored = str(usuario[campo]); break

    if not stored or not _verificar_password(stored, password):
        return _error('Contraseña incorrecta')

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$unset': {'two_factor': ''}}
    )
    return _json_no_cache({'success': True, 'message': '2FA desactivado'})


def regenerar_codigos_2fa():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()

    stored = ''
    for campo in ('password', 'password_hash', 'contraseña', 'contrasena', 'hash', 'clave'):
        if usuario.get(campo):
            stored = str(usuario[campo]); break

    if not stored or not _verificar_password(stored, password):
        return _error('Contraseña incorrecta')

    codigos = [{'codigo': secrets.token_hex(4).upper(), 'usado': False} for _ in range(8)]

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'two_factor.codigos_respaldo': codigos}}
    )
    return _json_no_cache({
        'success': True,
        'codigos_respaldo': [c['codigo'] for c in codigos],
    })


# ================================================================
# ⭐ COMPLEXIÓN
# ================================================================

_OPCIONES_COMPLEXION = {
    'complexion': [
        {'valor': 'delgada',  'etiqueta': 'Delgada'},
        {'valor': 'atletica', 'etiqueta': 'Atlética'},
        {'valor': 'media',    'etiqueta': 'Media'},
        {'valor': 'robusta',  'etiqueta': 'Robusta'},
        {'valor': 'extra',    'etiqueta': 'Extra'},
    ],
    'tallas_camisa':   ['XS','S','M','L','XL','XXL','3XL'],
    'tallas_pantalon': ['24','26','28','30','32','34','36','38','40','42'],
    'tallas_calzado':  ['22','23','24','25','26','27','28','29','30'],
    'tallas_sujetador':['30A','30B','32A','32B','32C','34A','34B','34C','34D',
                        '36B','36C','36D','38B','38C','38D'],
    'estilos': [
        {'valor': 'casual',   'etiqueta': 'Casual'},
        {'valor': 'formal',   'etiqueta': 'Formal'},
        {'valor': 'deportivo','etiqueta': 'Deportivo'},
        {'valor': 'bohemio',  'etiqueta': 'Bohemio'},
        {'valor': 'minimalista','etiqueta': 'Minimalista'},
        {'valor': 'vintage',  'etiqueta': 'Vintage'},
        {'valor': 'elegante', 'etiqueta': 'Elegante'},
        {'valor': 'street',   'etiqueta': 'Street'},
    ],
    'colores': ['negro','blanco','gris','azul','rojo','verde','amarillo',
                'rosa','morado','naranja','beige','café','dorado','plateado'],
}


def obtener_complexion():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    cx = usuario.get('complexion') or {}
    actualizado = cx.get('actualizado')
    if hasattr(actualizado, 'isoformat'):
        cx = dict(cx)
        cx['actualizado'] = actualizado.isoformat()

    return _json_no_cache({
        'success': True,
        'complexion': cx,
        'opciones': _OPCIONES_COMPLEXION,
        'genero': usuario.get('genero') or usuario.get('sexo', ''),
    })


def guardar_complexion():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}

    complexion = {
        'altura_cm':          data.get('altura_cm'),
        'peso_kg':            data.get('peso_kg'),
        'complexion':         data.get('complexion'),
        'talla_camisa':       data.get('talla_camisa'),
        'talla_pantalon':     data.get('talla_pantalon'),
        'talla_calzado':      data.get('talla_calzado'),
        'talla_sujetador':    data.get('talla_sujetador'),
        'medidas':            data.get('medidas') or {},
        'estilos_preferidos': data.get('estilos_preferidos') or [],
        'colores_favoritos':  data.get('colores_favoritos') or [],
        'actualizado':        datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'complexion': complexion}}
    )

    out = dict(complexion)
    out['actualizado'] = out['actualizado'].isoformat()
    return _json_no_cache({'success': True, 'complexion': out})


def borrar_complexion():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$unset': {'complexion': ''}}
    )
    return _json_no_cache({'success': True, 'message': 'Complexión eliminada'})


# ================================================================
# ⭐ INTERESES
# ================================================================

_OPCIONES_INTERESES = {
    'categorias': [
        {'valor': 'ropa',       'etiqueta': 'Ropa',       'icono': 'bag'},
        {'valor': 'calzado',    'etiqueta': 'Calzado',    'icono': 'boot'},
        {'valor': 'accesorios', 'etiqueta': 'Accesorios', 'icono': 'gem'},
        {'valor': 'belleza',    'etiqueta': 'Belleza',    'icono': 'flower1'},
        {'valor': 'tecnologia', 'etiqueta': 'Tecnología', 'icono': 'cpu'},
        {'valor': 'hogar',      'etiqueta': 'Hogar',      'icono': 'house'},
    ],
    'marcas': ['ORION', 'Nike', 'Adidas', 'Zara', 'H&M', 'Levi\'s', 'Puma'],
    'actividades': [
        {'valor': 'fitness',   'etiqueta': 'Fitness',   'icono': 'activity'},
        {'valor': 'yoga',      'etiqueta': 'Yoga',      'icono': 'person-arms-up'},
        {'valor': 'running',   'etiqueta': 'Running',   'icono': 'lightning'},
        {'valor': 'trabajo',   'etiqueta': 'Trabajo',   'icono': 'briefcase'},
        {'valor': 'viajes',    'etiqueta': 'Viajes',    'icono': 'airplane'},
        {'valor': 'fiesta',    'etiqueta': 'Fiesta',    'icono': 'music-note-beamed'},
    ],
    'ocasiones': [
        {'valor': 'mi',        'etiqueta': 'Para mí',       'icono': 'person'},
        {'valor': 'pareja',    'etiqueta': 'Mi pareja',     'icono': 'heart'},
        {'valor': 'hijos',     'etiqueta': 'Mis hijos',     'icono': 'people'},
        {'valor': 'familia',   'etiqueta': 'Familia',       'icono': 'house-heart'},
        {'valor': 'regalos',   'etiqueta': 'Regalos',       'icono': 'gift'},
        {'valor': 'amigos',    'etiqueta': 'Amigos',        'icono': 'people-fill'},
    ],
}


def obtener_intereses():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    intereses = usuario.get('intereses') or {}
    actualizado = intereses.get('actualizado')
    if hasattr(actualizado, 'isoformat'):
        intereses = dict(intereses)
        intereses['actualizado'] = actualizado.isoformat()

    return _json_no_cache({
        'success': True,
        'intereses': intereses,
        'opciones': _OPCIONES_INTERESES,
    })


def guardar_intereses():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}

    intereses = {
        'categorias':  data.get('categorias')  or [],
        'marcas':      data.get('marcas')      or [],
        'actividades': data.get('actividades') or [],
        'ocasiones':   data.get('ocasiones')   or [],
        'frecuencia':  data.get('frecuencia'),
        'actualizado': datetime.now(timezone.utc),
    }

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'intereses': intereses}}
    )

    out = dict(intereses)
    out['actualizado'] = out['actualizado'].isoformat()
    return _json_no_cache({'success': True, 'intereses': out})


def borrar_intereses():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$unset': {'intereses': ''}}
    )
    return _json_no_cache({'success': True, 'message': 'Intereses eliminados'})


# ================================================================
# ⭐ MONEDERO
# ================================================================

def monedero_resumen():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    saldo = float(usuario.get('monedero_saldo', 0) or 0)
    numero = usuario.get('monedero_numero') or ''

    if not numero:
        numero = '**** **** **** ' + f'{secrets.randbelow(10000):04d}'
        current_app.db.usuarios.update_one(
            {'_id': usuario['_id']},
            {'$set': {'monedero_numero': numero}}
        )

    return _json_no_cache({
        'success': True,
        'saldo': saldo,
        'numero_tarjeta': numero,
    })


def monedero_transferir():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    try:
        monto = float(data.get('monto') or 0)
    except (ValueError, TypeError):
        monto = 0

    serie = (data.get('numero_serie') or '').strip()
    cvv = (data.get('cvv') or '').strip()

    if monto <= 0:
        return _error('Monto inválido')
    if len(serie) != 4 or not serie.isdigit():
        return _error('Número de serie debe tener 4 dígitos')
    if len(cvv) != 3 or not cvv.isdigit():
        return _error('CVV debe tener 3 dígitos')

    db = current_app.db
    db.usuarios.update_one(
        {'_id': usuario['_id']},
        {
            '$inc': {'monedero_saldo': monto},
            '$set': {'updated_at': datetime.now(timezone.utc)},
        }
    )

    try:
        db.monedero_movimientos.insert_one({
            'usuario_id': usuario['_id'],
            'tipo': 'transferencia_entrada',
            'monto': monto,
            'fecha': datetime.now(timezone.utc),
        })
    except Exception:
        pass

    return _json_no_cache({
        'success': True,
        'message': f'Transferencia exitosa por ${monto:.2f}',
    })


# ================================================================
# ⭐ CAMBIAR CONTRASEÑA
# ================================================================

def cambiar_password():
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    data = request.form or request.get_json(silent=True) or {}
    actual    = (data.get('password_actual') or '').strip()
    nuevo     = (data.get('password_nuevo') or '').strip()
    confirmar = (data.get('password_confirmar') or '').strip()

    if not actual or not nuevo or not confirmar:
        return _error('Todos los campos son obligatorios')
    if nuevo != confirmar:
        return _error('Las contraseñas no coinciden')
    if len(nuevo) < 8:
        return _error('La contraseña debe tener al menos 8 caracteres')

    stored = ''
    for campo in ('password', 'password_hash', 'contraseña', 'contrasena', 'hash', 'clave'):
        if usuario.get(campo):
            stored = str(usuario[campo]); break

    if not stored or not _verificar_password(stored, actual):
        return _error('Contraseña actual incorrecta')

    from werkzeug.security import generate_password_hash
    nuevo_hash = generate_password_hash(nuevo)

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {
            'password': nuevo_hash,
            'password_hash': nuevo_hash,
            'updated_at': datetime.now(timezone.utc),
        }}
    )
    return _json_no_cache({'success': True, 'message': 'Contraseña actualizada'})


# ================================================================
# ⭐ FAVORITOS — eliminar
# ================================================================

def eliminar_favorito(producto_id):
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    db = current_app.db
    uid = usuario['_id']
    uid_str = str(uid)
    oid = _safe_oid(producto_id)
    if not oid:
        return _error('ID inválido')

    # ---------- Borrar de la colección `favoritos` ----------
    try:
        db[_COLECCION_FAVORITOS].delete_many({
            '$or': [
                {'usuario_id': uid,   'producto_id': oid},
                {'usuario_id': uid_str, 'producto_id': oid},
                {'usuario_id': uid,   'producto_id': producto_id},
                {'usuario_id': uid_str, 'producto_id': producto_id},
            ]
        })
    except Exception as e:
        current_app.logger.error(f'[eliminar_favorito] coleccion: {e}')

    # ---------- Borrar del array `usuario.favoritos` (compatibilidad) ----------
    try:
        db.usuarios.update_one(
            {'_id': uid},
            {'$pull': {'favoritos': {'producto_id': oid}}}
        )
        db.usuarios.update_one(
            {'_id': uid},
            {'$pull': {'favoritos': {'producto_id': str(producto_id)}}}
        )
        db.usuarios.update_one(
            {'_id': uid},
            {'$pull': {'favoritos': str(producto_id)}}
        )
        db.usuarios.update_one(
            {'_id': uid},
            {'$pull': {'favoritos': oid}}
        )
    except Exception as e:
        current_app.logger.error(f'[eliminar_favorito] array: {e}')

    return _json_no_cache({'success': True, 'message': 'Eliminado de favoritos'})


# ================================================================
# ⭐ DIRECCIONES
# ================================================================

def agregar_direccion():
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    form = request.form
    nueva = {
        'nombre':         (form.get('nombre') or '').strip(),
        'calle':          (form.get('calle') or '').strip(),
        'numero':         (form.get('numero') or '').strip(),
        'cp':             (form.get('cp') or '').strip(),
        'colonia':        (form.get('colonia') or '').strip(),
        'ciudad':         (form.get('ciudad') or '').strip(),
        'estado':         (form.get('estado') or '').strip(),
        'referencias':    (form.get('referencias') or '').strip(),
        'predeterminada': bool(form.get('predeterminada')),
    }

    direcciones = usuario.get('direcciones') or []

    if nueva['predeterminada']:
        for d in direcciones:
            d['predeterminada'] = False
    elif not direcciones:
        nueva['predeterminada'] = True

    direcciones.append(nueva)

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'direcciones': direcciones}}
    )
    return redirect(url_for('web.perfil') + '#tab-direcciones')


def editar_direccion(index):
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    try:
        idx = int(index)
    except (ValueError, TypeError):
        return redirect(url_for('web.perfil') + '#tab-direcciones')

    direcciones = usuario.get('direcciones') or []
    if idx < 0 or idx >= len(direcciones):
        return redirect(url_for('web.perfil') + '#tab-direcciones')

    form = request.form
    actualizada = {
        'nombre':         (form.get('nombre') or '').strip(),
        'calle':          (form.get('calle') or '').strip(),
        'numero':         (form.get('numero') or '').strip(),
        'cp':             (form.get('cp') or '').strip(),
        'colonia':        (form.get('colonia') or '').strip(),
        'ciudad':         (form.get('ciudad') or '').strip(),
        'estado':         (form.get('estado') or '').strip(),
        'referencias':    (form.get('referencias') or '').strip(),
        'predeterminada': bool(form.get('predeterminada')),
    }

    if actualizada['predeterminada']:
        for i, d in enumerate(direcciones):
            if i != idx:
                d['predeterminada'] = False

    direcciones[idx] = actualizada

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'direcciones': direcciones}}
    )
    return redirect(url_for('web.perfil') + '#tab-direcciones')


def borrar_direccion(index):
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    try:
        idx = int(index)
    except (ValueError, TypeError):
        return redirect(url_for('web.perfil') + '#tab-direcciones')

    direcciones = usuario.get('direcciones') or []
    if 0 <= idx < len(direcciones):
        era_pred = direcciones[idx].get('predeterminada')
        direcciones.pop(idx)
        if era_pred and direcciones:
            direcciones[0]['predeterminada'] = True

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'direcciones': direcciones}}
    )
    return redirect(url_for('web.perfil') + '#tab-direcciones')


def establecer_predeterminada(index):
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    try:
        idx = int(index)
    except (ValueError, TypeError):
        return redirect(url_for('web.perfil') + '#tab-direcciones')

    direcciones = usuario.get('direcciones') or []
    for i, d in enumerate(direcciones):
        d['predeterminada'] = (i == idx)

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': {'direcciones': direcciones}}
    )
    return redirect(url_for('web.perfil') + '#tab-direcciones')


# ================================================================
# ⭐ ACTUALIZAR PERFIL (formulario)
# ================================================================

def actualizar_perfil():
    usuario = _get_usuario_actual()
    if not usuario:
        return redirect(url_for('web.login'))

    form = request.form
    updates = {
        'nombre':           (form.get('nombre') or '').strip(),
        'apellido_paterno': (form.get('apellido_paterno') or '').strip(),
        'apellido_materno': (form.get('apellido_materno') or '').strip(),
        'telefono':         (form.get('telefono') or '').strip(),
        'fecha_nacimiento': (form.get('fecha_nacimiento') or '').strip(),
        'genero':           (form.get('genero') or '').strip(),
        'updated_at':       datetime.now(timezone.utc),
    }

    try:
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename:
                import os
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                    fname = f'user_{usuario["_id"]}_{secrets.token_hex(6)}{ext}'
                    upload_dir = os.path.join(
                        current_app.root_path, 'static', 'uploads'
                    )
                    os.makedirs(upload_dir, exist_ok=True)
                    file.save(os.path.join(upload_dir, fname))
                    updates['foto'] = fname
                    session['foto'] = fname
    except Exception as e:
        current_app.logger.error(f'[actualizar_perfil] foto: {e}')

    current_app.db.usuarios.update_one(
        {'_id': usuario['_id']},
        {'$set': updates}
    )

    session['nombre'] = updates['nombre']
    return redirect(url_for('web.perfil'))


# ================================================================
# ADMIN: detalle de un cliente
# ================================================================

def admin_obtener_cuenta_cliente(usuario_id):
    if 'user_id' not in session:
        return _error('No autenticado', 401)

    db = current_app.db
    admin = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    rol = str((admin or {}).get('rol', '')).lower()
    if not admin or rol not in ('admin', 'administrador', 'superadmin', 'root'):
        return _error('No autorizado', 403)

    try:
        cliente = db.usuarios.find_one({'_id': ObjectId(usuario_id)})
    except Exception:
        return _error('ID inválido')

    if not cliente:
        return _error('Usuario no encontrado', 404)

    prefs_com = cliente.get('preferencias_comunicacion') or {}
    defaults_com = {
        'email_promo': True, 'email_pedidos': True, 'email_newsletter': True,
        'wa_pedidos': True, 'wa_promo': False,
        'push_pedidos': True, 'push_promo': False,
    }
    comunicacion = {**defaults_com, **prefs_com}
    comunicacion['email_pedidos'] = True
    comunicacion.pop('updated_at', None)

    prefs_priv = cliente.get('preferencias_privacidad') or {}
    defaults_priv = {'personalizacion': True, 'analiticas': True, 'compartir_socios': False}
    privacidad = {**defaults_priv, **prefs_priv}
    privacidad.pop('updated_at', None)

    fiscales_raw = cliente.get('datos_fiscales') or {}
    fiscales = {
        'rfc':            fiscales_raw.get('rfc', ''),
        'razon_social':   fiscales_raw.get('razon_social', ''),
        'regimen_fiscal': fiscales_raw.get('regimen_fiscal', ''),
        'uso_cfdi':       fiscales_raw.get('uso_cfdi', ''),
        'updated_at':     fiscales_raw.get('updated_at').isoformat()
                          if hasattr(fiscales_raw.get('updated_at'), 'isoformat') else None,
    }

    metodos_raw = list(db.metodos_pago.find({
        '$or': [
            {'usuario_id': str(cliente['_id'])},
            {'usuario_id': cliente['_id']},
        ]
    }))
    metodos_out = [_serializar_metodo(m) for m in metodos_raw]

    complexion_raw = cliente.get('complexion') or {}
    complexion_out = dict(complexion_raw)
    if hasattr(complexion_out.get('actualizado'), 'isoformat'):
        complexion_out['actualizado'] = complexion_out['actualizado'].isoformat()

    return jsonify({
        'success': True,
        'cliente': {
            'id':                        str(cliente['_id']),
            'nombre':                    cliente.get('nombre', ''),
            'apellido_paterno':          cliente.get('apellido_paterno', ''),
            'apellido_materno':          cliente.get('apellido_materno', ''),
            'email':                     cliente.get('email', ''),
            'telefono':                  cliente.get('telefono', ''),
            'foto':                      cliente.get('foto', ''),
            'genero':                    cliente.get('genero') or cliente.get('sexo', ''),
            'fecha_nacimiento':          cliente.get('fecha_nacimiento', ''),
            'confirmado':                bool(cliente.get('confirmado', False)),
            'activo':                    bool(cliente.get('activo', True)),
            'rol':                       cliente.get('rol', 'cliente'),
            'created_at':                cliente.get('created_at').isoformat()
                                         if hasattr(cliente.get('created_at'), 'isoformat') else None,
            'preferencias_comunicacion': comunicacion,
            'preferencias_privacidad':   privacidad,
            'datos_fiscales':            fiscales,
            'metodos_pago':              metodos_out,
            'complexion':                complexion_out,
        }
    })


# ================================================================
# ADMIN: listar clientes
# ================================================================

def admin_listar_cuentas_clientes():
    db = current_app.db

    q      = (request.args.get('q') or '').strip()
    estado = (request.args.get('estado') or '').strip().lower()
    pago   = (request.args.get('pago') or '').strip().lower()
    orden  = (request.args.get('orden') or 'recientes').strip()

    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get('per_page', 20))
        if per_page not in (10, 20, 50, 100):
            per_page = 20
    except (ValueError, TypeError):
        per_page = 20

    filtro_base = {'rol': {'$in': ['cliente', 'Cliente', None]}}
    filtro = dict(filtro_base)

    if q:
        regex = re.compile(re.escape(q), re.IGNORECASE)
        filtro['$or'] = [
            {'nombre': regex}, {'apellido_paterno': regex},
            {'apellido_materno': regex}, {'email': regex},
            {'telefono': regex},
        ]

    if estado == 'verificado':
        filtro['confirmado'] = True
    elif estado == 'sin_verificar':
        filtro['confirmado'] = {'$ne': True}

    if pago in ('con', 'sin'):
        usuarios_con_pago = set(
            str(m['usuario_id'])
            for m in db.metodos_pago.find({}, {'usuario_id': 1})
        )
        if pago == 'con':
            filtro['_id'] = {'$in': [ObjectId(u) for u in usuarios_con_pago if _safe_oid(u)]}
        else:
            filtro['_id'] = {'$nin': [ObjectId(u) for u in usuarios_con_pago if _safe_oid(u)]}

    orden_map = {
        'recientes':   [('created_at', -1)],
        'antiguos':    [('created_at', 1)],
        'nombre_asc':  [('nombre', 1), ('apellido_paterno', 1)],
        'nombre_desc': [('nombre', -1), ('apellido_paterno', -1)],
        'email_asc':   [('email', 1)],
    }
    sort = orden_map.get(orden, orden_map['recientes'])

    total_global        = db.usuarios.count_documents(filtro_base)
    total_verificados   = db.usuarios.count_documents({**filtro_base, 'confirmado': True})
    total_sin_verificar = total_global - total_verificados

    total = db.usuarios.count_documents(filtro)
    pages = max(1, math.ceil(total / per_page))
    if page > pages:
        page = pages

    skip = (page - 1) * per_page
    clientes = list(db.usuarios.find(filtro).sort(sort).skip(skip).limit(per_page))

    for c in clientes:
        c['_id'] = str(c['_id'])
        c['confirmado'] = bool(c.get('confirmado', False))
        c['activo'] = bool(c.get('activo', True))
        c['metodos_pago'] = list(db.metodos_pago.find({
            '$or': [
                {'usuario_id': c['_id']},
                {'usuario_id': _safe_oid(c['_id']) or c['_id']},
            ]
        }))
        c['direcciones'] = c.get('direcciones') or []

    paginacion = {
        'page': page, 'per_page': per_page, 'total': total, 'pages': pages,
        'has_prev': page > 1, 'has_next': page < pages,
        'prev_num': page - 1, 'next_num': page + 1,
    }

    filtros = {'q': q, 'estado': estado, 'pago': pago, 'orden': orden}
    stats = {
        'total_global': total_global,
        'total_verificados': total_verificados,
        'total_sin_verificar': total_sin_verificar,
    }

    return clientes, paginacion, filtros, stats


# ================================================================
# HELPER: construye el payload completo del usuario
# ================================================================

def _construir_payload_usuario(usuario, db):
    uid = usuario['_id']
    uid_str = str(uid)

    perfil = {
        'id':               uid_str,
        'nombre':           usuario.get('nombre', ''),
        'apellido_paterno': usuario.get('apellido_paterno', ''),
        'apellido_materno': usuario.get('apellido_materno', ''),
        'email':            usuario.get('email', ''),
        'telefono':         usuario.get('telefono', ''),
        'fecha_nacimiento': usuario.get('fecha_nacimiento', ''),
        'genero':           usuario.get('genero') or usuario.get('sexo', ''),
        'foto':             usuario.get('foto', ''),
        'rol':              usuario.get('rol', 'cliente'),
        'confirmado':       bool(usuario.get('confirmado', False)),
        'activo':           bool(usuario.get('activo', True)),
        'created_at':       usuario.get('created_at').isoformat()
                            if hasattr(usuario.get('created_at'), 'isoformat') else None,
    }

    direcciones = []
    for d in (usuario.get('direcciones') or []):
        direcciones.append({
            'nombre': d.get('nombre', ''),
            'calle': d.get('calle', ''),
            'numero': d.get('numero', ''),
            'colonia': d.get('colonia', ''),
            'cp': d.get('cp', ''),
            'ciudad': d.get('ciudad', ''),
            'estado': d.get('estado', ''),
            'referencias': d.get('referencias', ''),
            'predeterminada': bool(d.get('predeterminada', False)),
        })

    pedidos_raw = list(db.pedidos.find({
        '$or': [{'usuario_id': uid}, {'usuario_id': uid_str}]
    }).sort('created_at', -1))
    pedidos = []
    for p in pedidos_raw:
        pedidos.append({
            'id':        str(p['_id']),
            'estado':    p.get('estado', ''),
            'total':     float(p.get('total', 0) or 0),
            'fecha':     p.get('created_at').isoformat()
                         if hasattr(p.get('created_at'), 'isoformat') else None,
            'fecha_fmt': p.get('created_at').strftime('%d/%m/%Y %H:%M')
                         if hasattr(p.get('created_at'), 'strftime') else '',
            'items':     p.get('items') or p.get('productos') or [],
            'numero_seguimiento': p.get('numero_seguimiento', ''),
        })

    # Favoritos — desde colección `favoritos`
    favoritos = []
    try:
        for f in db[_COLECCION_FAVORITOS].find({
            '$or': [{'usuario_id': uid}, {'usuario_id': uid_str}]
        }):
            pid = f.get('producto_id')
            if pid:
                favoritos.append(str(pid))
    except Exception:
        pass

    metodos_raw = list(db.metodos_pago.find({
        '$or': [{'usuario_id': uid_str}, {'usuario_id': uid}]
    }))
    metodos_pago = [_serializar_metodo(m) for m in metodos_raw]

    prefs_com = usuario.get('preferencias_comunicacion') or {}
    defaults_com = {
        'email_promo': True, 'email_pedidos': True, 'email_newsletter': True,
        'wa_pedidos': True, 'wa_promo': False,
        'push_pedidos': True, 'push_promo': False,
    }
    preferencias_comunicacion = {**defaults_com, **prefs_com}
    preferencias_comunicacion.pop('updated_at', None)

    prefs_priv = usuario.get('preferencias_privacidad') or {}
    defaults_priv = {'personalizacion': True, 'analiticas': True, 'compartir_socios': False}
    preferencias_privacidad = {**defaults_priv, **prefs_priv}
    preferencias_privacidad.pop('updated_at', None)

    fiscales_raw = usuario.get('datos_fiscales') or {}
    datos_fiscales = {
        'rfc':            fiscales_raw.get('rfc', ''),
        'razon_social':   fiscales_raw.get('razon_social', ''),
        'regimen_fiscal': fiscales_raw.get('regimen_fiscal', ''),
        'uso_cfdi':       fiscales_raw.get('uso_cfdi', ''),
        'updated_at':     fiscales_raw.get('updated_at').isoformat()
                          if hasattr(fiscales_raw.get('updated_at'), 'isoformat') else None,
    }

    complexion_raw = usuario.get('complexion') or {}
    complexion = dict(complexion_raw)
    if hasattr(complexion.get('actualizado'), 'isoformat'):
        complexion['actualizado'] = complexion['actualizado'].isoformat()

    intereses_raw = usuario.get('intereses') or {}
    intereses = dict(intereses_raw)
    if hasattr(intereses.get('actualizado'), 'isoformat'):
        intereses['actualizado'] = intereses['actualizado'].isoformat()

    cupones = []
    try:
        for c in db.cupones_usuarios.find({'usuario_id': uid}):
            cupones.append({
                'codigo': c.get('cupon_codigo', ''),
                'fecha_uso': c.get('fecha_uso').isoformat()
                             if hasattr(c.get('fecha_uso'), 'isoformat') else None,
            })
    except Exception:
        pass

    return {
        'perfil':                    perfil,
        'direcciones':               direcciones,
        'pedidos':                   pedidos,
        'favoritos':                 favoritos,
        'metodos_pago':              metodos_pago,
        'preferencias_comunicacion': preferencias_comunicacion,
        'preferencias_privacidad':   preferencias_privacidad,
        'datos_fiscales':            datos_fiscales,
        'complexion':                complexion,
        'intereses':                 intereses,
        'cupones':                   cupones,
    }


# ================================================================
# DESCARGAR MIS DATOS (JSON)
# ================================================================

def descargar_mis_datos():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    payload = _construir_payload_usuario(usuario, current_app.db)
    return jsonify({
        'success': True,
        'generado': datetime.now(timezone.utc).isoformat(),
        'datos':    payload,
        'usuario':  payload,
    })


# ================================================================
# VISTA BONITA PARA IMPRIMIR / GUARDAR COMO PDF
# ================================================================

def ver_mis_datos_pdf():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    payload = _construir_payload_usuario(usuario, current_app.db)
    return render_template(
        'tienda/mis_datos.html',
        datos=payload,
        usuario=usuario,
        generado=datetime.now(timezone.utc),
    )


# ================================================================
# ELIMINAR MI CUENTA
# ================================================================

def eliminar_mi_cuenta():
    usuario = _get_usuario_actual()
    if not usuario:
        return _error('No autenticado', 401)

    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()

    if not password:
        return _error('Debes ingresar tu contraseña para confirmar')

    stored = ''
    for campo in ('password', 'password_hash', 'contraseña', 'contrasena', 'hash', 'clave'):
        if usuario.get(campo):
            stored = str(usuario[campo]); break

    if not stored:
        return _error('No se encontró la contraseña en tu cuenta.')

    if not _verificar_password(stored, password):
        return _error('Contraseña incorrecta')

    db = current_app.db
    uid = usuario['_id']
    uid_str = str(uid)

    try:
        db.usuarios.delete_one({'_id': uid})
        db[_COLECCION_FAVORITOS].delete_many({'usuario_id': uid})
        db[_COLECCION_FAVORITOS].delete_many({'usuario_id': uid_str})
        db.cupones_usuarios.delete_many({'usuario_id': uid})
        db.metodos_pago.delete_many({'usuario_id': uid_str})
        db.metodos_pago.delete_many({'usuario_id': uid})
        db.complexion.delete_many({'usuario_id': uid})

        db.pedidos.update_many(
            {'usuario_id': uid},
            {'$set': {'usuario_eliminado': True}}
        )

        try:
            db.auditoria.insert_one({
                'accion': 'cuenta_eliminada',
                'usuario_id': uid_str,
                'email': usuario.get('email', ''),
                'fecha': datetime.now(timezone.utc),
            })
        except Exception:
            pass
    except Exception as e:
        return _error(f'No se pudo eliminar la cuenta: {e}', 500)

    session.clear()
    return jsonify({'success': True, 'message': 'Cuenta eliminada correctamente'})