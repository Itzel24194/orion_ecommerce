# app/controllers/carrito_controller.py
# Controlador completo del carrito con soporte para cupones y promociones

from flask import session, request, jsonify, current_app, redirect, url_for, render_template, make_response, flash
from datetime import datetime, timezone
from bson import ObjectId
from app.models.productos_model import Producto
from app.models.cupon_model import Cupon, CuponUsuario
from app.models.promocion_model import Promocion
import sys


# ================================================================
# HELPERS CUPONES
# ================================================================

def _normalizar_codigo(s):
    """Mayúsculas, sin espacios internos, sin invisibles."""
    if not s:
        return ''
    return ''.join(str(s).split()).upper()


def _cupon_vigente(cupon):
    """Devuelve True si el cupón no está vencido.
    Acepta valido_hasta, fecha_expiracion o fecha_fin, en datetime o str."""
    vence = (
        cupon.get('valido_hasta')
        or cupon.get('fecha_expiracion')
        or cupon.get('fecha_fin')
    )
    if not vence:
        return True
    try:
        if isinstance(vence, str):
            vence_dt = datetime.fromisoformat(vence.replace('Z', '+00:00'))
        else:
            vence_dt = vence
        if vence_dt.tzinfo is None:
            vence_dt = vence_dt.replace(tzinfo=timezone.utc)
        return vence_dt > datetime.now(timezone.utc)
    except Exception:
        return True


def _calcular_descuento(tipo, valor, subtotal):
    """Calcula el descuento en MXN a partir del tipo y valor del cupón."""
    try:
        tipo = (tipo or 'porcentaje').lower()
        valor = float(valor or 0)
        if tipo == 'porcentaje':
            return round(subtotal * (valor / 100.0), 2)
        return round(min(valor, subtotal), 2)
    except Exception:
        return 0.0


def _buscar_registro_lealtad(usuario_id_session):
    """
    Busca el registro de lealtad probando todas las variantes posibles
    del usuario_id (str, ObjectId, valor crudo).
    Devuelve el documento de Mongo o None.
    """
    try:
        db = current_app.db
    except Exception:
        return None

    uid_str = str(usuario_id_session)

    filtros = [
        {'usuario_id': uid_str},
        {'usuario_id': usuario_id_session},
    ]
    try:
        filtros.append({'usuario_id': ObjectId(uid_str)})
    except Exception:
        pass

    for filtro in filtros:
        try:
            reg = db.lealtad.find_one(filtro)
            if reg:
                return reg
        except Exception:
            continue
    return None


# ================================================================
# AGREGAR AL CARRITO
# ================================================================

def agregar_al_carrito():
    """Agregar producto al carrito (session) con soporte para grandes cantidades"""
    data = request.get_json(silent=True) or {}
    p_id = str(data.get('producto_id'))
    cantidad = int(data.get('cantidad', 1))
    atributos = data.get('atributos', {})

    if cantidad < 1:
        return jsonify({"success": False, "message": "Cantidad inválida"})

    producto = Producto.obtener_por_id(p_id)
    if not producto:
        return jsonify({"success": False, "message": "Producto no encontrado"})

    variantes = producto.get('variables') or producto.get('variantes') or []
    stock_disponible = 0

    if variantes:
        if atributos and (atributos.get('color') or atributos.get('tamano')):
            for v in variantes:
                v_color = str(v.get('color', '')).strip().lower()
                v_tamano = str(v.get('tamano', '')).strip().lower()
                attr_color = str(atributos.get('color', '')).strip().lower()
                attr_tamano = str(atributos.get('tamano', '')).strip().lower()

                match_color = not attr_color or v_color == attr_color
                match_tamano = not attr_tamano or v_tamano == attr_tamano

                if match_color and match_tamano:
                    try:
                        stock_disponible = int(v.get('stock', 0))
                    except (ValueError, TypeError):
                        stock_disponible = 0
                    break

        if stock_disponible == 0 and variantes:
            try:
                stock_disponible = int(variantes[0].get('stock', 0))
            except (ValueError, TypeError):
                stock_disponible = 0
    else:
        try:
            stock_disponible = int(producto.get('stock', 0))
        except (ValueError, TypeError):
            stock_disponible = 0

    if stock_disponible <= 0:
        return jsonify({
            "success": False,
            "message": "Producto sin stock disponible",
            "stock_disponible": 0
        })

    if cantidad > stock_disponible:
        return jsonify({
            "success": False,
            "message": f"Stock insuficiente. Disponible: {stock_disponible} unidades",
            "stock_disponible": stock_disponible
        })

    carrito = session.get('carrito', [])

    existe = None
    for item in carrito:
        if item['id'] == p_id:
            item_atributos = item.get('atributos', {})
            if item_atributos.get('color') == atributos.get('color') and \
               item_atributos.get('tamano') == atributos.get('tamano'):
                existe = item
                break

    if existe:
        nueva_cantidad = existe['cantidad'] + cantidad
        if nueva_cantidad > stock_disponible:
            return jsonify({
                "success": False,
                "message": f"La cantidad total ({nueva_cantidad}) supera el stock disponible ({stock_disponible})",
                "stock_disponible": stock_disponible
            })
        existe['cantidad'] = nueva_cantidad
    else:
        precio = 0.0
        if variantes:
            for v in variantes:
                v_color = str(v.get('color', '')).strip().lower()
                v_tamano = str(v.get('tamano', '')).strip().lower()
                attr_color = str(atributos.get('color', '')).strip().lower()
                attr_tamano = str(atributos.get('tamano', '')).strip().lower()

                match_color = not attr_color or v_color == attr_color
                match_tamano = not attr_tamano or v_tamano == attr_tamano

                if match_color and match_tamano:
                    try:
                        precio = float(v.get('precio', 0))
                    except (ValueError, TypeError):
                        precio = 0.0
                    break

            if precio == 0 and variantes:
                try:
                    precio = float(variantes[0].get('precio', 0))
                except (ValueError, TypeError):
                    precio = 0.0

        imagen = producto['fotos'][0] if producto.get('fotos') else 'default.jpg'

        carrito.append({
            'id': p_id,
            'nombre': producto.get('nombre', 'Producto'),
            'precio': precio,
            'imagen': imagen,
            'cantidad': cantidad,
            'atributos': atributos,
            'stock_disponible': stock_disponible
        })

    session['carrito'] = carrito
    session.modified = True

    return jsonify({
        "success": True,
        "message": f"Producto agregado. Cantidad: {cantidad}",
        "stock_restante": stock_disponible - cantidad
    })


# ================================================================
# VER CARRITO
# ================================================================

def ver_carrito():
    """Ver carrito de compras con soporte para cupones y promociones"""
    carrito = session.get('carrito', [])

    # Revalidar cupón aplicado
    cupon_sesion = session.get('cupon_aplicado')
    if cupon_sesion and session.get('user_id'):
        codigo_actual = _normalizar_codigo(cupon_sesion.get('codigo'))
        registro = _buscar_registro_lealtad(session['user_id'])

        sigue_vigente = False
        if registro:
            for c in (registro.get('cupones_personalizados') or []):
                if not isinstance(c, dict) or c.get('usado'):
                    continue
                cid = _normalizar_codigo(c.get('id') or c.get('codigo'))
                if cid != codigo_actual:
                    continue
                sigue_vigente = _cupon_vigente(c)
                break

        if not sigue_vigente and cupon_sesion.get('origen') == 'lealtad':
            session.pop('cupon_aplicado', None)
            session.modified = True
            flash('El cupón aplicado ya no es válido', 'warning')

    subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 0)) for item in carrito)

    cupon_aplicado = session.get('cupon_aplicado', None)
    descuento_cupon = float(cupon_aplicado.get('descuento', 0)) if cupon_aplicado else 0.0

    promocion_aplicada = session.get('promocion_aplicada', None)
    descuento_promocion = float(promocion_aplicada.get('descuento', 0)) if promocion_aplicada else 0.0

    total_unidades = sum(int(item.get('cantidad', 0)) for item in carrito)
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)

    descuento_total = descuento_volumen + descuento_cupon + descuento_promocion

    if cupon_aplicado:
        print(f"💰 Cupón aplicado: {cupon_aplicado.get('codigo')} - Descuento: ${descuento_cupon:.2f}", file=sys.stderr)
    if promocion_aplicada:
        print(f"🎁 Promoción aplicada: {promocion_aplicada.get('nombre')} - Descuento: ${descuento_promocion:.2f}", file=sys.stderr)

    subtotal_con_descuentos = subtotal - descuento_total
    iva = subtotal_con_descuentos * 0.16
    total_final = subtotal_con_descuentos + iva

    db = current_app.db
    categorias = list(db.categorias.find({}))

    tiendas = []
    config_tiendas = db.configuracion.find_one({'_id': 'tiendas'})
    if config_tiendas:
        tiendas = config_tiendas.get('tiendas', [])

    return render_template(
        'tienda/carrito.html',
        carrito=carrito,
        carrito_items=carrito,
        subtotal=subtotal,
        iva=iva,
        total_carrito=total_final,
        categorias=categorias,
        tiendas=tiendas,
        total_unidades=total_unidades,
        descuento_volumen=descuento_volumen,
        porcentaje_descuento=porcentaje_descuento,
        cupon_aplicado=cupon_aplicado,
        descuento_cupon=descuento_cupon,
        promocion_aplicada=promocion_aplicada,
        descuento_promocion=descuento_promocion,
        descuento_total=descuento_total,
        subtotal_con_descuentos=subtotal_con_descuentos
    )


# ================================================================
# CALCULAR DESCUENTO POR VOLUMEN
# ================================================================

def calcular_descuento_volumen(total_unidades, subtotal):
    porcentaje = 0
    descuento = 0

    if total_unidades >= 200:
        porcentaje = 25
    elif total_unidades >= 150:
        porcentaje = 20
    elif total_unidades >= 100:
        porcentaje = 15
    elif total_unidades >= 50:
        porcentaje = 10
    elif total_unidades >= 25:
        porcentaje = 7
    elif total_unidades >= 10:
        porcentaje = 5

    if porcentaje > 0:
        descuento = subtotal * (porcentaje / 100)

    return descuento, porcentaje


# ================================================================
# ELIMINAR / ACTUALIZAR
# ================================================================

def eliminar_del_carrito(id):
    carrito = session.get('carrito', [])
    session['carrito'] = [item for item in carrito if str(item.get('id')) != str(id)]
    session.modified = True
    return redirect(url_for('web.ver_carrito'))


def actualizar_cantidad_carrito(id):
    cantidad = int(request.form.get('cantidad', 1))
    carrito = session.get('carrito', [])

    for item in carrito:
        if str(item['id']) == str(id):
            stock_disponible = item.get('stock_disponible', 999999)
            if cantidad > stock_disponible:
                flash(f"No hay suficiente stock. Disponible: {stock_disponible}", "danger")
                return redirect(url_for('web.ver_carrito'))
            item['cantidad'] = max(1, cantidad)

    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('web.ver_carrito'))


# ================================================================
# ⭐ APLICAR CUPÓN (lealtad + generales) — versión robusta
# ================================================================

def aplicar_cupon():
    """
    Aplica un cupón al carrito.
    - Normaliza el código (espacios, mayúsculas).
    - Busca registro de lealtad probando str / ObjectId / raw.
    - Si no está en lealtad, busca en cupones generales.
    - Si YA hay un cupón aplicado, lo rechaza (solo 1 a la vez).
    - Devuelve debug detallado si falla.
    """
    if not session.get('user_id'):
        return jsonify({"success": False, "message": "Inicia sesión para usar cupones"}), 401

    data = request.get_json(silent=True) or {}
    codigo_raw = data.get('codigo') or ''
    codigo = _normalizar_codigo(codigo_raw)

    if not codigo:
        return jsonify({
            "success": False,
            "message": "Ingresa un código",
            "debug": "codigo_vacio",
        }), 400

    # ⭐ SOLO 1 CUPÓN A LA VEZ
    cupon_previo = session.get('cupon_aplicado')
    if cupon_previo and _normalizar_codigo(cupon_previo.get('codigo')) != codigo:
        return jsonify({
            "success": False,
            "message": f"Ya tienes el cupón '{cupon_previo.get('codigo')}' aplicado. Quítalo primero.",
            "debug": "cupon_previo_aplicado",
            "codigo_previo": cupon_previo.get('codigo'),
        }), 400

    carrito = session.get('carrito', [])
    if not carrito:
        return jsonify({"success": False, "message": "Tu carrito está vacío"}), 400

    subtotal = sum(
        float(item.get('precio', 0)) * int(item.get('cantidad', 0))
        for item in carrito
    )

    db = current_app.db

    # ---------- 1) Buscar en cupones de LEALTAD ----------
    cupon_lealtad = None
    registro = _buscar_registro_lealtad(session['user_id'])

    if not registro:
        return jsonify({
            "success": False,
            "message": "No encontramos tu registro de lealtad. Visita /mi-lealtad primero.",
            "debug": "registro_lealtad_no_encontrado",
            "session_user_id": str(session['user_id']),
        }), 404

    for c in (registro.get('cupones_personalizados') or []):
        if not isinstance(c, dict):
            continue
        cid = _normalizar_codigo(c.get('id') or c.get('codigo') or '')
        if cid != codigo:
            continue

        if c.get('usado'):
            return jsonify({
                "success": False,
                "message": "Este cupón ya fue utilizado",
                "debug": "cupon_usado",
                "codigo": cid,
            }), 400

        if not _cupon_vigente(c):
            return jsonify({
                "success": False,
                "message": "Este cupón ya expiró",
                "debug": "cupon_vencido",
                "codigo": cid,
                "valido_hasta": str(c.get('valido_hasta', '')),
            }), 400

        min_compra = float(c.get('min_compra', 0) or 0)
        if subtotal < min_compra:
            return jsonify({
                "success": False,
                "message": f"Compra mínima requerida: ${min_compra:.2f} (tu subtotal: ${subtotal:.2f})",
                "debug": "min_compra_no_alcanzado",
                "codigo": cid,
                "min_compra": min_compra,
                "subtotal": subtotal,
            }), 400

        cupon_lealtad = c
        break

    if cupon_lealtad:
        tipo = cupon_lealtad.get('tipo') or 'porcentaje'
        valor = float(cupon_lealtad.get('valor', 0) or 0)
        descuento = _calcular_descuento(tipo, valor, subtotal)

        session['cupon_aplicado'] = {
            'codigo':       codigo,
            'titulo':       cupon_lealtad.get('titulo', 'Cupón'),
            'descripcion':  cupon_lealtad.get('descripcion', ''),
            'tipo':         tipo,
            'valor':        valor,
            'descuento':    descuento,
            'envio_gratis': bool(cupon_lealtado.get('envio_gratis', False)) if False else bool(cupon_lealtad.get('envio_gratis', False)),
            'min_compra':   float(cupon_lealtad.get('min_compra', 0) or 0),
            'origen':       'lealtad',
        }
        session.modified = True

        print(f'💰 Cupón lealtad aplicado: {codigo} - ${descuento:.2f}', file=sys.stderr)

        return jsonify({
            "success":     True,
            "codigo":      codigo,
            "titulo":      cupon_lealtad.get('titulo', 'Cupón aplicado'),
            "descuento":   descuento,
            "envio_gratis": bool(cupon_lealtad.get('envio_gratis', False)),
            "message":     f"Cupón aplicado: -${descuento:.2f}",
        })

    # ---------- 2) Buscar en cupones GENERALES ----------
    cupon_general = None
    try:
        for cg in db.cupones.find({'activo': True}):
            cg_code = _normalizar_codigo(cg.get('codigo'))
            if cg_code == codigo:
                cupon_general = cg
                break
    except Exception:
        pass

    if not cupon_general:
        # Listar cupones disponibles para debug
        disponibles = []
        for c in (registro.get('cupones_personalizados') or []):
            if not isinstance(c, dict) or c.get('usado'):
                continue
            disponibles.append({
                "id": c.get('id') or c.get('codigo'),
                "titulo": c.get('titulo'),
                "min_compra": c.get('min_compra', 0),
            })

        return jsonify({
            "success": False,
            "message": "Cupón no válido o no existe",
            "debug": "no_encontrado",
            "codigo_buscado": codigo,
            "codigo_raw": codigo_raw,
            "subtotal": subtotal,
            "cupones_disponibles": disponibles,
            "session_user_id": str(session['user_id']),
        }), 404

    if not _cupon_vigente(cupon_general):
        return jsonify({
            "success": False,
            "message": "Este cupón expiró",
            "debug": "cupon_general_vencido",
        }), 400

    min_compra = float(cupon_general.get('min_compra', 0) or 0)
    if subtotal < min_compra:
        return jsonify({
            "success": False,
            "message": f"Compra mínima requerida: ${min_compra:.2f}"
        }), 400

    tipo = cupon_general.get('tipo') or 'porcentaje'
    valor = float(cupon_general.get('valor', 0) or 0)
    descuento = _calcular_descuento(tipo, valor, subtotal)

    session['cupon_aplicado'] = {
        'codigo':       codigo,
        'titulo':       cupon_general.get('titulo', 'Cupón'),
        'descripcion':  cupon_general.get('descripcion', ''),
        'tipo':         tipo,
        'valor':        valor,
        'descuento':    descuento,
        'envio_gratis': bool(cupon_general.get('envio_gratis', False)),
        'min_compra':   min_compra,
        'origen':       'general',
    }
    session.modified = True

    return jsonify({
        "success":     True,
        "codigo":      codigo,
        "titulo":      cupon_general.get('titulo', 'Cupón aplicado'),
        "descuento":   descuento,
        "envio_gratis": bool(cupon_general.get('envio_gratis', False)),
        "message":     f"Cupón aplicado: -${descuento:.2f}",
    })


# ================================================================
# ⭐ LISTAR MIS CUPONES
# ================================================================

def api_mis_cupones():
    """Devuelve los cupones disponibles del usuario para el carrito."""
    if not session.get('user_id'):
        return jsonify({"success": False, "cupones": []}), 401

    registro = _buscar_registro_lealtad(session['user_id'])
    cupones = []
    if registro:
        for c in (registro.get('cupones_personalizados') or []):
            if not isinstance(c, dict) or c.get('usado'):
                continue
            if not _cupon_vigente(c):
                continue

            cupones.append({
                'codigo':       c.get('id') or c.get('codigo') or '',
                'titulo':       c.get('titulo') or 'Cupón',
                'descripcion':  c.get('descripcion') or '',
                'tipo':         c.get('tipo') or 'porcentaje',
                'valor':        c.get('valor') or 0,
                'min_compra':   float(c.get('min_compra', 0) or 0),
                'valido_hasta': str(c.get('valido_hasta', ''))[:10],
                'envio_gratis': bool(c.get('envio_gratis', False)),
                'tipo_regla':   c.get('tipo_regla') or 'manual',
            })

    return jsonify({"success": True, "cupones": cupones})


# ================================================================
# ⭐ DIAGNÓSTICO DE CUPONES
# ================================================================

def api_diagnostico_cupones():
    """
    Devuelve toda la info para depurar por qué un cupón no aplica:
    - session_user_id y su tipo
    - registros encontrados por cada variante de búsqueda
    - cupones del cliente
    - estado del carrito
    """
    if not session.get('user_id'):
        return jsonify({"success": False, "error": "No autenticado"}), 401

    try:
        db = current_app.db
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    uid_raw = session['user_id']
    uid_str = str(uid_raw)

    variantes = [
        {'usuario_id': uid_str},
        {'usuario_id': uid_raw},
    ]
    try:
        variantes.append({'usuario_id': ObjectId(uid_str)})
    except Exception:
        pass

    hallazgos = []
    registro_ok = None
    for filtro in variantes:
        try:
            r = db.lealtad.find_one(filtro)
            if r:
                hallazgos.append({
                    "filtro": str(filtro),
                    "match": True,
                    "_id": str(r.get('_id')),
                    "usuario_id": str(r.get('usuario_id')),
                    "tipo_usuario_id_mongo": type(r.get('usuario_id')).__name__,
                    "nivel": r.get('nivel'),
                    "gasto_total": r.get('gasto_total'),
                    "compras_realizadas": r.get('compras_realizadas'),
                    "cupones_total": len(r.get('cupones_personalizados') or []),
                })
                if registro_ok is None:
                    registro_ok = r
        except Exception as e:
            hallazgos.append({"filtro": str(filtro), "error": str(e)})

    cupones = []
    if registro_ok:
        for c in (registro_ok.get('cupones_personalizados') or []):
            if not isinstance(c, dict):
                continue
            cupones.append({
                "id": c.get('id'),
                "codigo": c.get('codigo'),
                "usado": c.get('usado', False),
                "titulo": c.get('titulo'),
                "tipo": c.get('tipo'),
                "valor": c.get('valor'),
                "min_compra": c.get('min_compra', 0),
                "valido_hasta": str(c.get('valido_hasta', '')),
                "vigente": _cupon_vigente(c),
                "tipo_regla": c.get('tipo_regla'),
            })

    carrito = session.get('carrito', [])
    subtotal = sum(float(i.get('precio', 0)) * int(i.get('cantidad', 0)) for i in carrito)

    return jsonify({
        "success": True,
        "session_user_id": uid_str,
        "session_user_id_type": type(uid_raw).__name__,
        "carrito_items": len(carrito),
        "subtotal": subtotal,
        "hallazgos": hallazgos,
        "registro_encontrado": registro_ok is not None,
        "cupones": cupones,
        "cupon_aplicado": session.get('cupon_aplicado'),  # ⭐ ahora el diagnóstico lo expone
        "sugerencia": (
            "Si 'registro_encontrado' es false → session['user_id'] no coincide "
            "con db.lealtad.usuario_id. Revisa que ambos sean del mismo tipo (str vs ObjectId)."
            if registro_ok is None else
            "Revisa 'cupones': los que tengan usado=true o vigente=false no se pueden aplicar."
        ),
    })


# ================================================================
# QUITAR CUPÓN / PROMOCIÓN
# ================================================================

def quitar_cupon_carrito():
    """Quita el cupón. Responde JSON si lo llaman por fetch, redirect si es un link."""
    session.pop('cupon_aplicado', None)
    session.pop('descuento_aplicado', None)
    session.pop('total_con_descuento', None)
    session.modified = True

    # Si la petición viene de fetch/JS, devolvemos JSON
    acepta_json = (
        request.headers.get('Accept') == 'application/json'
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.is_json
    )
    if acepta_json:
        return jsonify({"success": True, "message": "Cupón eliminado"})

    flash('Cupón eliminado del carrito', 'info')
    return redirect(url_for('web.ver_carrito'))


def quitar_promocion_carrito():
    if 'promocion_aplicada' in session:
        session.pop('promocion_aplicada', None)
        session.modified = True
        flash('Promoción eliminada del carrito', 'info')

    acepta_json = (
        request.headers.get('Accept') == 'application/json'
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.is_json
    )
    if acepta_json:
        return jsonify({"success": True, "message": "Promoción eliminada"})

    return redirect(url_for('web.ver_carrito'))


# ================================================================
# DESCARGAR FACTURA (PDF) + MARCAR CUPÓN USADO
# ================================================================

def descargar_factura():
    carrito = session.get('carrito', [])
    if not carrito:
        return "El carrito ya está vacío.", 400

    subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 0)) for item in carrito)

    total_unidades = sum(int(item.get('cantidad', 0)) for item in carrito)
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)

    cupon_aplicado = session.get('cupon_aplicado', None)
    descuento_cupon = 0
    codigo_cupon = None
    if cupon_aplicado:
        descuento_cupon = cupon_aplicado.get('descuento', 0)
        codigo_cupon = cupon_aplicado.get('codigo')

    promocion_aplicada = session.get('promocion_aplicada', None)
    descuento_promocion = 0
    promocion_id = None
    if promocion_aplicada:
        descuento_promocion = promocion_aplicada.get('descuento', 0)
        promocion_id = promocion_aplicada.get('id')

    descuento_total = descuento_volumen + descuento_cupon + descuento_promocion
    subtotal_con_descuento = subtotal - descuento_total
    iva = subtotal_con_descuento * 0.16
    total_con_iva = round(subtotal_con_descuento + iva, 2)

    db = current_app.db

    # Actualizar stock
    for item in carrito:
        producto_id = item.get('id')
        cantidad_vendida = int(item.get('cantidad', 0))
        atributos = item.get('atributos', {})

        producto = Producto.obtener_por_id(producto_id)
        if producto:
            variantes = producto.get('variables') or producto.get('variantes') or []
            for v in variantes:
                v_color = str(v.get('color', '')).strip().lower()
                v_tamano = str(v.get('tamano', '')).strip().lower()
                attr_color = str(atributos.get('color', '')).strip().lower()
                attr_tamano = str(atributos.get('tamano', '')).strip().lower()

                match_color = not attr_color or v_color == attr_color
                match_tamano = not attr_tamano or v_tamano == attr_tamano

                if match_color and match_tamano:
                    try:
                        stock_actual = int(v.get('stock', 0))
                    except (ValueError, TypeError):
                        stock_actual = 0

                    if stock_actual < cantidad_vendida:
                        return f"Stock insuficiente para {producto['nombre']}", 400

                    v['stock'] = stock_actual - cantidad_vendida
                    break

            if 'variables' in producto:
                Producto.actualizar(producto_id, {"variables": variantes})
            else:
                Producto.actualizar(producto_id, {"variantes": variantes})

    # Registrar uso en cupones_usuarios (legacy)
    if codigo_cupon and session.get('user_id'):
        try:
            CuponUsuario.registrar_uso(
                usuario_id=session['user_id'],
                cupon_codigo=codigo_cupon,
                pedido_id=None,
                descuento_aplicado=descuento_cupon
            )
        except Exception as e:
            print(f'[factura] No se pudo registrar uso en CuponUsuario: {e}', flush=True)

    # Registrar uso de la promoción
    if promocion_id and session.get('user_id'):
        try:
            if hasattr(Promocion, 'registrar_uso'):
                Promocion.registrar_uso(promocion_id, session['user_id'], descuento_promocion)
            else:
                db.promociones_usos.insert_one({
                    'promocion_id': ObjectId(promocion_id),
                    'usuario_id': ObjectId(session['user_id']),
                    'descuento': descuento_promocion,
                    'fecha': datetime.utcnow()
                })
                db.promociones.update_one(
                    {'_id': ObjectId(promocion_id)},
                    {'$inc': {'usos_actuales': 1}}
                )
        except Exception as e:
            print(f"Error registrando uso de promoción: {e}")

    # Guardar venta
    venta = {
        "usuario_id": session.get("user_id"),
        "fecha": datetime.now(),
        "subtotal": subtotal,
        "descuento_volumen": descuento_volumen,
        "porcentaje_descuento": porcentaje_descuento,
        "descuento_cupon": descuento_cupon,
        "codigo_cupon": codigo_cupon,
        "descuento_promocion": descuento_promocion,
        "promocion_id": promocion_id,
        "iva": iva,
        "total": total_con_iva,
        "estado": "Pagada",
        "productos": carrito,
        "total_unidades": total_unidades,
        "es_mayorista": total_unidades >= 50
    }
    resultado = db.ventas.insert_one(venta)
    pedido_id_str = str(resultado.inserted_id)

    # Marcar cupón de lealtad como usado (probando todas las variantes)
    if cupon_aplicado and codigo_cupon and session.get('user_id'):
        try:
            registro = _buscar_registro_lealtad(session['user_id'])
            if registro:
                cupones = registro.get('cupones_personalizados') or []
                modificado = False
                codigo_norm = _normalizar_codigo(codigo_cupon)
                for i, c in enumerate(cupones):
                    if not isinstance(c, dict):
                        continue
                    cid = _normalizar_codigo(c.get('id') or c.get('codigo') or '')
                    if cid == codigo_norm and not c.get('usado'):
                        cupones[i]['usado'] = True
                        cupones[i]['usado_en'] = datetime.utcnow()
                        cupones[i]['pedido_id'] = pedido_id_str
                        modificado = True
                        break

                if modificado:
                    db.lealtad.update_one(
                        {'_id': registro['_id']},
                        {'$set': {'cupones_personalizados': cupones}}
                    )
                    print(f'✅ Cupón {codigo_cupon} marcado como USADO (lealtad)', file=sys.stderr)
        except Exception as e:
            print(f'⚠️ No se pudo marcar cupón lealtad como usado: {e}', file=sys.stderr)

    # Actualizar pedido_id en cupones_usuarios
    if codigo_cupon and session.get('user_id'):
        try:
            db.cupones_usuarios.update_one(
                {"usuario_id": str(session['user_id']), "cupon_codigo": codigo_cupon},
                {"$set": {"pedido_id": pedido_id_str}}
            )
        except Exception:
            pass

    pdf_data = _generar_pdf_factura(
        carrito, total_con_iva, descuento_volumen, porcentaje_descuento,
        descuento_cupon, codigo_cupon, descuento_promocion, promocion_aplicada
    )

    session.pop('carrito', None)
    session.pop('cupon_aplicado', None)
    session.pop('descuento_aplicado', None)
    session.pop('total_con_descuento', None)
    session.pop('promocion_aplicada', None)
    session.modified = True

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=factura_orion.pdf'
    return response


# ================================================================
# PROCESAR PAGO / VACIAR
# ================================================================

def procesar_pago():
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('web.ver_carrito'))
    return redirect(url_for('web.descargar_factura'))


def vaciar_carrito():
    session['carrito'] = []
    session.pop('cupon_aplicado', None)
    session.pop('promocion_aplicada', None)
    session.modified = True
    return jsonify({"success": True, "message": "Carrito vaciado"})


# ================================================================
# ⭐ API CARRITO  (incluye cupón y promoción aplicados)
# ================================================================

def api_carrito():
    if request.method == 'GET':
        carrito = session.get('carrito', [])
        total = 0
        items = []
        for item in carrito:
            precio = item.get('precio', 0)
            cantidad = item.get('cantidad', 1)
            subtotal = precio * cantidad
            total += subtotal
            items.append({
                'id': item.get('id'),
                'nombre': item.get('nombre'),
                'precio': precio,
                'cantidad': cantidad,
                'subtotal': subtotal,
                'imagen': item.get('imagen', ''),
                'atributos': item.get('atributos', {})
            })

        # ⭐ CRÍTICO: incluir cupón y promoción aplicados para que el frontend
        # (carrito.html y mis_cupones.html) sepa que ya hay uno activo.
        cupon_aplicado = session.get('cupon_aplicado')
        promocion_aplicada = session.get('promocion_aplicada')

        return jsonify({
            "carrito": carrito,
            "total": total,
            "items": items,
            "cupon_aplicado": cupon_aplicado,
            "promocion_aplicada": promocion_aplicada,
        })

    elif request.method == 'POST':
        return agregar_al_carrito()

    elif request.method == 'DELETE':
        return vaciar_carrito()


# ================================================================
# GENERAR PDF FACTURA
# ================================================================

def _generar_pdf_factura(carrito, total_con_iva, descuento_volumen=0, porcentaje=0, descuento_cupon=0, codigo_cupon=None, descuento_promocion=0, promocion_aplicada=None):
    lineas = [
        "=" * 50,
        "              FACTURA ORION",
        "=" * 50,
        f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"Cliente: {session.get('nombre', 'Cliente')}",
        "-" * 50,
        "PRODUCTOS:",
        ""
    ]

    subtotal = 0.0
    for item in carrito:
        cantidad = int(item.get('cantidad', 0))
        precio = float(item.get('precio', 0))
        total_item = cantidad * precio
        subtotal += total_item
        nombre = item.get('nombre', 'Producto')
        atributos = item.get('atributos')
        descripcion = f"  {nombre} x{cantidad} = ${total_item:.2f}"
        if atributos:
            if atributos.get('color'):
                descripcion += f" (Color: {atributos.get('color')})"
            if atributos.get('tamano'):
                descripcion += f" (Talla: {atributos.get('tamano')})"
        lineas.append(descripcion)

    lineas.append("")
    lineas.append("-" * 50)
    lineas.append(f"SUBTOTAL: ${subtotal:.2f}")

    if descuento_volumen > 0:
        lineas.append(f"DESCUENTO VOLUMEN ({porcentaje}%): -${descuento_volumen:.2f}")

    if descuento_cupon > 0 and codigo_cupon:
        lineas.append(f"DESCUENTO CUPÓN ({codigo_cupon}): -${descuento_cupon:.2f}")

    if descuento_promocion > 0 and promocion_aplicada:
        nombre_promo = promocion_aplicada.get('nombre', 'Promoción')
        lineas.append(f"DESCUENTO PROMOCIÓN ({nombre_promo}): -${descuento_promocion:.2f}")

    iva_calculado = (subtotal - descuento_volumen - descuento_cupon - descuento_promocion) * 0.16
    lineas.append(f"IVA (16%): ${iva_calculado:.2f}")
    lineas.append("=" * 50)
    lineas.append(f"TOTAL: ${total_con_iva:.2f}")
    lineas.append("=" * 50)
    lineas.append("")
    lineas.append("¡Gracias por tu compra!")

    def _pdf_escape(text):
        return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    stream_lines = ["BT", "/F1 12 Tf", "50 760 Td", "14 TL"]
    for i, linea in enumerate(lineas):
        stream_lines.append(f"({_pdf_escape(linea)}) Tj")
        if i < len(lineas) - 1:
            stream_lines.append("T*")
    stream_lines.append("ET")

    stream = "\n".join(stream_lines).encode('latin-1')

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode('latin-1') + stream + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    position = len(pdf[0])
    for obj in objects:
        offsets.append(position)
        pdf.append(obj)
        position += len(obj)

    xref_lines = [b"xref\n0 6\n0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010} 00000 n \n".encode('latin-1'))

    startxref = position
    pdf.extend(xref_lines)
    pdf.append(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode('latin-1')
    )

    return b"".join(pdf)