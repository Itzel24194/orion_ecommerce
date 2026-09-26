# ================================================================
# app/controllers/pedido_controller.py
# COMPLETO — con MSI: soporta tarjeta guardada (MIT) y tarjeta nueva (token)
# ================================================================

from flask import (
    current_app, session, request, jsonify, render_template,
    flash, redirect, url_for, send_file
)
from datetime import datetime, timedelta
from bson import ObjectId
from io import BytesIO
import random
import string
import sys
import re
from app.models.pedidos_model import Pedido
from app.models.productos_model import Producto

# ⭐ MARKETPLACE (opcional, con try/except para no romper si no está)
try:
    from app.models.marketplace_model import Vendedor
    MARKETPLACE_OK = True
except ImportError:
    Vendedor = None
    MARKETPLACE_OK = False
    print("ℹ️ Módulo Marketplace no disponible (opcional)")


# ================================================================
# ROLES
# ================================================================

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


# ================================================================
# HELPERS GENERALES
# ================================================================

def _safe_items_list(pedido):
    if not pedido:
        return []
    raw = pedido.get('items')
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return list(raw.values())
    if raw is None or callable(raw):
        return []
    try:
        if hasattr(raw, '__iter__') and not isinstance(raw, str):
            return list(raw)
    except Exception:
        pass
    return []


def _enriquecer_items(items):
    if not items:
        return []
    for item in items:
        if not item.get('imagen'):
            item['imagen'] = 'default.jpg'
        if not item.get('foto'):
            item['foto'] = item['imagen']
    return items


def generar_codigo_recogida():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def calcular_descuento_volumen(total_unidades, subtotal):
    porcentaje = 0
    if total_unidades >= 200: porcentaje = 25
    elif total_unidades >= 150: porcentaje = 20
    elif total_unidades >= 100: porcentaje = 15
    elif total_unidades >= 50: porcentaje = 10
    elif total_unidades >= 25: porcentaje = 7
    elif total_unidades >= 10: porcentaje = 5
    descuento = subtotal * (porcentaje / 100) if porcentaje > 0 else 0
    return descuento, porcentaje


# ================================================================
# ⭐ MARKETPLACE — COMISIONES AUTOMÁTICAS
# ================================================================

def _procesar_comisiones_marketplace(items, pedido_id=None, numero_pedido=None):
    """
    Recorre los items del pedido, agrupa por vendedor_id y actualiza
    las métricas del vendedor (ventas, ingresos, comisiones).

    ⭐ Debe llamarse DESPUÉS de insertar el pedido en Mongo.

    Args:
        items: lista de dicts (normalizada) con campo 'vendedor_id' opcional
        pedido_id: str o ObjectId del pedido (para auditoría)
        numero_pedido: str del número de pedido (para auditoría)

    Returns:
        dict con resumen: {
            'procesados': int,
            'vendedores': {vid: {ventas, subtotal, comision}},
            'errores': [str]
        }
    """
    if not MARKETPLACE_OK or Vendedor is None:
        return {'procesados': 0, 'vendedores': {}, 'errores': ['Marketplace no disponible']}

    if not items:
        return {'procesados': 0, 'vendedores': {}, 'errores': []}

    db = current_app.db
    resumen = {'procesados': 0, 'vendedores': {}, 'errores': []}

    # 1. Agrupar items por vendedor_id
    agrupado = {}
    for item in items:
        vid = item.get('vendedor_id')
        if not vid:
            continue

        try:
            cantidad = int(item.get('cantidad', 1) or 1)
            precio = float(item.get('precio', 0) or 0)
        except (ValueError, TypeError):
            continue

        subtotal_item = precio * cantidad

        if vid not in agrupado:
            agrupado[vid] = {
                'ventas': 0,
                'subtotal': 0.0,
                'items': [],
            }

        agrupado[vid]['ventas']    += cantidad
        agrupado[vid]['subtotal']  += subtotal_item
        agrupado[vid]['items'].append({
            'nombre':   item.get('nombre', ''),
            'cantidad': cantidad,
            'precio':   precio,
        })

    if not agrupado:
        print(f"ℹ️ [Marketplace] No hay items con vendedor_id en este pedido",
              file=sys.stderr)
        return resumen

    ahora = datetime.utcnow()

    # 2. Procesar cada vendedor
    for vid, data in agrupado.items():
        try:
            # Buscar vendedor
            vendedor = None
            try:
                vendedor = Vendedor.obtener_por_id(db, vid)
            except Exception:
                pass

            if not vendedor:
                msg = f'Vendedor {vid} no encontrado'
                resumen['errores'].append(msg)
                print(f"⚠️ [Marketplace] {msg}", file=sys.stderr)
                continue

            if vendedor.get('estado') != 'aprobado':
                msg = f'Vendedor {vendedor.get("nombre_tienda")} no está aprobado'
                resumen['errores'].append(msg)
                print(f"⚠️ [Marketplace] {msg}", file=sys.stderr)
                continue

            # Calcular comisión
            comision_pct = float(vendedor.get('comision_pct', 15.0))
            comision     = round(data['subtotal'] * (comision_pct / 100.0), 2)
            subtotal     = round(data['subtotal'], 2)

            # Actualizar métricas en el vendedor
            db[Vendedor.COLLECTION].update_one(
                {'_id': vendedor['_id']},
                {
                    '$inc': {
                        'metricas.ventas':     1,
                        'metricas.ingresos':   subtotal,
                        'metricas.comisiones': comision,
                    },
                    '$set': {'updated_at': ahora},
                }
            )

            # Registrar transacción de comisión (opcional, para auditoría)
            try:
                db['comisiones_marketplace'].insert_one({
                    'vendedor_id':   str(vendedor['_id']),
                    'vendedor_nombre': vendedor.get('nombre_tienda', ''),
                    'pedido_id':     str(pedido_id) if pedido_id else None,
                    'numero_pedido': numero_pedido,
                    'items':         data['items'],
                    'ventas':        data['ventas'],
                    'subtotal':      subtotal,
                    'comision_pct':  comision_pct,
                    'comision':      comision,
                    'neto_vendedor': round(subtotal - comision, 2),
                    'estado':        'pendiente_pago',
                    'created_at':    ahora,
                })
            except Exception as e:
                # La colección es opcional — no bloqueamos si falla
                print(f"ℹ️ [Marketplace] No se pudo registrar auditoría: {e}",
                      file=sys.stderr)

            resumen['procesados'] += 1
            resumen['vendedores'][str(vendedor['_id'])] = {
                'nombre':    vendedor.get('nombre_tienda', ''),
                'ventas':    data['ventas'],
                'subtotal':  subtotal,
                'comision':  comision,
                'neto':      round(subtotal - comision, 2),
            }

            print(
                f"💰 [Marketplace] {vendedor.get('nombre_tienda')} — "
                f"subtotal=${subtotal} comisión={comision_pct}% (${comision}) "
                f"neto=${round(subtotal - comision, 2)}",
                file=sys.stderr
            )

        except Exception as e:
            msg = f'Error procesando vendedor {vid}: {e}'
            resumen['errores'].append(msg)
            print(f"❌ [Marketplace] {msg}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    return resumen


# ================================================================
# LEALTAD
# ================================================================

def _obtener_beneficios_lealtad(usuario_id, subtotal, tipo_envio='domicilio'):
    try:
        from app.services.lealtad_service import LealtadService
        beneficios = LealtadService.calcular_beneficios_checkout(usuario_id, subtotal)
        envio_gratis = beneficios.get('envio_gratis', False) and tipo_envio == 'domicilio'
        return {
            'descuento_lealtad': beneficios.get('descuento_lealtad', 0),
            'envio_gratis': envio_gratis,
            'puntos_a_ganar': beneficios.get('puntos_a_ganar', 0),
            'multiplicador': beneficios.get('multiplicador', 1.0),
            'nivel': beneficios.get('nivel', 'Bronce'),
            'emoji_nivel': beneficios.get('emoji_nivel', '🥉'),
            'color_nivel': beneficios.get('color_nivel', '#CD7F32')
        }
    except Exception as e:
        print(f"[Lealtad] Error: {e}", file=sys.stderr)
        return {
            'descuento_lealtad': 0, 'envio_gratis': False, 'puntos_a_ganar': 0,
            'multiplicador': 1.0, 'nivel': 'Bronce',
            'emoji_nivel': '🥉', 'color_nivel': '#CD7F32'
        }


def _procesar_lealtad_compra(usuario_id, total, numero_pedido):
    try:
        from app.services.lealtad_service import LealtadService
        return LealtadService.procesar_compra(
            usuario_id=usuario_id, monto=total, numero_pedido=numero_pedido
        )
    except Exception as e:
        print(f"[Lealtad] Error: {e}", file=sys.stderr)
        return None


def _revertir_lealtad_pedido(usuario_id, puntos_a_revertir, motivo="Pedido cancelado"):
    try:
        from app.models.lealtad_model import Lealtad
        if puntos_a_revertir and puntos_a_revertir > 0:
            Lealtad.ajustar_puntos(usuario_id=usuario_id, puntos=-puntos_a_revertir, motivo=motivo)
            return True
    except Exception as e:
        print(f"[Lealtad] Error: {e}", file=sys.stderr)
    return False


# ================================================================
# MONEDERO
# ================================================================

def _procesar_cashback_monedero(usuario_id, total, nivel_cliente, pedido_id):
    try:
        from app.models.monedero_model import Monedero
        nivel_valido = nivel_cliente if nivel_cliente in Monedero.CASHBACK_POR_NIVEL else 'Bronce'
        return Monedero.aplicar_cashback(
            usuario_id=usuario_id, monto_compra=float(total or 0),
            nivel_cliente=nivel_valido, pedido_id=str(pedido_id)
        ) or 0
    except Exception as e:
        print(f"[Monedero] Error: {e}", file=sys.stderr)
        return 0


def _revertir_cashback_pedido(usuario_id, monto_cashback, motivo="Pedido cancelado"):
    try:
        from app.models.monedero_model import Monedero
        if not monto_cashback or monto_cashback <= 0:
            return False
        if not Monedero.obtener_por_usuario(usuario_id):
            return False
        Monedero.collection.update_one(
            {'usuario_id': str(usuario_id)},
            {'$inc': {'saldo': -float(monto_cashback),
                      'cashback_historico': -float(monto_cashback)},
             '$set': {'updated_at': datetime.utcnow()}}
        )
        Monedero._registrar_movimiento(usuario_id, 'cashback_revertido',
                                        -float(monto_cashback), motivo)
        return True
    except Exception as e:
        print(f"[Monedero] Error: {e}", file=sys.stderr)
        return False


# ================================================================
# CARRITO HELPERS
# ================================================================

def _obtener_carrito_usuario(usuario_id):
    db = current_app.db
    carrito_sesion = session.get('carrito', [])
    if carrito_sesion:
        print(f"🛒 Carrito desde SESIÓN ({len(carrito_sesion)} items)", file=sys.stderr)
        return list(carrito_sesion)
    try:
        usuario_oid = usuario_id if isinstance(usuario_id, ObjectId) else ObjectId(str(usuario_id))
        carrito_db = list(db.carrito.find({'usuario_id': usuario_oid}))
        if carrito_db:
            return carrito_db
    except Exception:
        pass
    try:
        carrito_db_str = list(db.carrito.find({'usuario_id': str(usuario_id)}))
        if carrito_db_str:
            return carrito_db_str
    except Exception:
        pass
    return []


def _vaciar_carrito_usuario(usuario_id):
    db = current_app.db
    session['carrito'] = []
    session['carrito_para_guardar'] = []
    session.modified = True
    try:
        usuario_oid = usuario_id if isinstance(usuario_id, ObjectId) else ObjectId(str(usuario_id))
        db.carrito.delete_many({'usuario_id': usuario_oid})
    except Exception:
        pass
    try:
        db.carrito.delete_many({'usuario_id': str(usuario_id)})
    except Exception:
        pass


def _normalizar_items_para_guardar(carrito_items):
    items = []
    for item in carrito_items:
        producto = None
        try:
            producto = Producto.obtener_por_id(item.get('id'))
        except Exception:
            pass
        imagen = 'default.jpg'
        if producto:
            fotos = producto.get('fotos', [])
            if fotos:
                imagen = fotos[0]
        atributos = item.get('atributos', {}) or {}
        for k, v in list(atributos.items()):
            if isinstance(v, str):
                atributos[k] = ' '.join(v.split())

        # ⭐ MARKETPLACE: preservar vendedor_id desde el producto o el item
        vendedor_id = None
        vendedor_nombre = ''
        if item.get('vendedor_id'):
            vendedor_id = item.get('vendedor_id')
            vendedor_nombre = item.get('vendedor_nombre', '')
        elif producto and producto.get('vendedor_id'):
            vendedor_id = producto.get('vendedor_id')
            vendedor_nombre = producto.get('vendedor_nombre', '')

        item_normalizado = {
            'id': str(item.get('id', '')),
            'nombre': str(item.get('nombre', 'Producto')),
            'precio': float(item.get('precio', 0)),
            'cantidad': int(item.get('cantidad', 1)),
            'atributos': atributos,
            'imagen': item.get('imagen') or item.get('foto') or imagen,
            'foto': item.get('foto') or item.get('imagen') or imagen,
            'sku': str(item.get('sku', ''))
        }

        # ⭐ Agregar vendedor solo si existe
        if vendedor_id:
            item_normalizado['vendedor_id']     = str(vendedor_id)
            item_normalizado['vendedor_nombre'] = vendedor_nombre

        items.append(item_normalizado)
    return items


# ================================================================
# ⭐ BÚSQUEDA ROBUSTA DE TARJETA GUARDADA
# ================================================================

def _es_oid_valido(s):
    try:
        ObjectId(str(s))
        return True
    except Exception:
        return False


def _buscar_tarjeta_guardada(usuario_id, tarjeta_id):
    """
    Busca una tarjeta guardada del usuario soportando:
      1. Match exacto por 'id'
      2. Match exacto por '_id' (ObjectId)
      3. Match parcial (prefijo/sufijo/substring)
      4. Regex laxo
      5. FALLBACK: si el usuario tiene UNA sola tarjeta, la devuelve.
    """
    db = current_app.db
    usuario_id_str = str(usuario_id)
    tarjeta_id = (tarjeta_id or '').strip()

    if not tarjeta_id:
        return None

    print(f"🔍 [Tarjeta] Buscando '{tarjeta_id}' para usuario='{usuario_id_str}'", file=sys.stderr)

    filtro_usuario = [{'usuario_id': usuario_id_str}]
    if _es_oid_valido(usuario_id_str):
        filtro_usuario.append({'usuario_id': ObjectId(usuario_id_str)})

    todas = list(db.metodos_pago.find({'$or': filtro_usuario}))

    print(f"🔍 [Tarjeta] Total tarjetas del usuario: {len(todas)}", file=sys.stderr)
    for t in todas:
        print(f"   → id='{t.get('id')}' | _id='{t.get('_id')}' | ultimos4='{t.get('ultimos4')}'",
              file=sys.stderr)

    # 1. Exacto por 'id'
    for t in todas:
        if str(t.get('id') or '') == tarjeta_id:
            print(f"✅ [Tarjeta] Match exacto por 'id'", file=sys.stderr)
            return t

    # 2. Exacto por '_id'
    for t in todas:
        if str(t.get('_id') or '') == tarjeta_id:
            print(f"✅ [Tarjeta] Match exacto por '_id'", file=sys.stderr)
            return t

    # 3. Match parcial
    if len(tarjeta_id) >= 6:
        for t in todas:
            stored_id = str(t.get('id') or '')
            stored_oid = str(t.get('_id') or '')

            if stored_id and (
                tarjeta_id in stored_id
                or stored_id.startswith(tarjeta_id)
                or stored_id.endswith(tarjeta_id)
            ):
                print(f"✅ [Tarjeta] Match parcial 'id': '{tarjeta_id}' ⊆ '{stored_id}'",
                      file=sys.stderr)
                return t

            if stored_oid and (
                tarjeta_id in stored_oid
                or stored_oid.startswith(tarjeta_id)
                or stored_oid.endswith(tarjeta_id)
            ):
                print(f"✅ [Tarjeta] Match parcial '_id': '{tarjeta_id}' ⊆ '{stored_oid}'",
                      file=sys.stderr)
                return t

    # 4. Regex laxo
    try:
        patron = re.compile(re.escape(tarjeta_id), re.IGNORECASE)
        for t in todas:
            stored_id = str(t.get('id') or '')
            stored_oid = str(t.get('_id') or '')
            if patron.search(stored_id) or patron.search(stored_oid):
                print(f"✅ [Tarjeta] Match regex", file=sys.stderr)
                return t
    except Exception:
        pass

    # 5. FALLBACK: única tarjeta del usuario
    if len(todas) == 1:
        unica = todas[0]
        print(
            f"⚠️  [Tarjeta] ID '{tarjeta_id}' no coincide con ninguna, "
            f"usando ÚNICA tarjeta del usuario "
            f"(id='{unica.get('id')}', ultimos4='{unica.get('ultimos4')}')",
            file=sys.stderr
        )
        return unica

    # 6. Último intento: sin filtro de usuario
    try:
        t = db.metodos_pago.find_one({'id': tarjeta_id})
        if t and str(t.get('usuario_id')) == usuario_id_str:
            print(f"✅ [Tarjeta] Match sin filtro usuario", file=sys.stderr)
            return t
    except Exception:
        pass

    print(f"❌ [Tarjeta] No se encontró '{tarjeta_id}'", file=sys.stderr)
    return None


# ================================================================
# CARRITO Y CHECKOUT
# ================================================================

def carrito_checkout():
    if 'user_id' not in session:
        flash('Inicia sesión para realizar tu pedido', 'warning')
        return redirect(url_for('web.login'))

    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))

    carrito_items = session.get('carrito', [])
    if not carrito_items:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('web.catalogo'))

    items_enriquecidos = []
    for item in carrito_items:
        producto = Producto.obtener_por_id(item.get('id'))
        if producto:
            fotos = producto.get('fotos', [])
            imagen = fotos[0] if fotos else 'default.jpg'
            atributos = item.get('atributos', {})
            for k, v in list(atributos.items()):
                if isinstance(v, str):
                    atributos[k] = ' '.join(v.split())

            # ⭐ MARKETPLACE: preservar vendedor
            vend_id = item.get('vendedor_id') or producto.get('vendedor_id')
            vend_nombre = item.get('vendedor_nombre') or producto.get('vendedor_nombre', '')

            item_enr = {
                'id': item.get('id'), 'nombre': item.get('nombre', 'Producto'),
                'precio': float(item.get('precio', 0)),
                'cantidad': int(item.get('cantidad', 1)),
                'atributos': atributos, 'imagen': imagen, 'foto': imagen,
                'sku': item.get('sku', '')
            }
            if vend_id:
                item_enr['vendedor_id'] = str(vend_id)
                item_enr['vendedor_nombre'] = vend_nombre

            items_enriquecidos.append(item_enr)
        else:
            items_enriquecidos.append(item)

    session['carrito_para_guardar'] = items_enriquecidos
    session.modified = True

    subtotal = sum(float(i.get('precio', 0)) * int(i.get('cantidad', 1)) for i in items_enriquecidos)
    iva = subtotal * 0.16
    total_unidades = sum(int(i.get('cantidad', 0)) for i in items_enriquecidos)

    cupon_aplicado = session.get('cupon_aplicado')
    promocion_aplicada = session.get('promocion_aplicada')
    descuento_cupon = cupon_aplicado.get('descuento', 0) if cupon_aplicado else 0
    descuento_promocion = promocion_aplicada.get('descuento', 0) if promocion_aplicada else 0

    beneficios_lealtad = _obtener_beneficios_lealtad(session['user_id'], subtotal, 'domicilio')
    descuento_lealtad = beneficios_lealtad.get('descuento_lealtad', 0)
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
    descuento_total = descuento_volumen + descuento_lealtad + descuento_cupon + descuento_promocion

    subtotal_con_descuentos = subtotal - descuento_total
    envio = 199.00 if total_unidades >= 50 else 99.00
    if beneficios_lealtad.get('envio_gratis'):
        envio = 0
    total_carrito = subtotal_con_descuentos + iva + envio

    if request.method == 'POST':
        return procesar_checkout()

    tiendas = []
    config = db.configuracion.find_one({'_id': 'tiendas'})
    if config:
        tiendas = config.get('tiendas', [])
    categorias = list(db.categorias.find({}))

    conekta_public_key = current_app.config.get('CONEKTA_PUBLIC_KEY', '')
    conekta_private_key = current_app.config.get('CONEKTA_PRIVATE_KEY', '')
    conekta_configured = bool(
        conekta_public_key and conekta_public_key.startswith('key_') and len(conekta_public_key) >= 25
    )

    return render_template('tienda/carrito.html',
                         usuario=usuario,
                         carrito_items=items_enriquecidos,
                         tiendas=tiendas, categorias=categorias,
                         subtotal=subtotal, iva=iva, total_carrito=total_carrito,
                         envio=envio, total_unidades=total_unidades,
                         descuento_volumen=descuento_volumen,
                         porcentaje_descuento=porcentaje_descuento,
                         cupon_aplicado=cupon_aplicado, descuento_cupon=descuento_cupon,
                         promocion_aplicada=promocion_aplicada, descuento_promocion=descuento_promocion,
                         descuento_total=descuento_total,
                         subtotal_con_descuentos=subtotal_con_descuentos,
                         beneficios_lealtad=beneficios_lealtad,
                         descuento_lealtad=descuento_lealtad,
                         CONEKTA_PUBLIC_KEY=conekta_public_key,
                         CONEKTA_PRIVATE_KEY=conekta_private_key,
                         CONEKTA_PUBLIC_KEY_CONFIGURED=conekta_configured)


def procesar_checkout():
    if 'user_id' not in session:
        flash('Inicia sesión para procesar tu pedido', 'warning')
        return redirect(url_for('web.login'))

    db = current_app.db
    try:
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('web.carrito_checkout'))

        carrito_items = session.get('carrito', [])
        if not carrito_items:
            flash('Tu carrito está vacío', 'warning')
            return redirect(url_for('web.catalogo'))

        items_para_guardar = _normalizar_items_para_guardar(carrito_items)
        tipo_envio = request.form.get('tipo_envio', 'domicilio')
        metodo_pago = request.form.get('metodo_pago', 'tarjeta')
        notas = request.form.get('notas', '')

        subtotal = sum(float(i.get('precio', 0)) * int(i.get('cantidad', 1)) for i in items_para_guardar)
        iva = subtotal * 0.16
        total_unidades = sum(int(i.get('cantidad', 0)) for i in items_para_guardar)

        cupon_aplicado = session.get('cupon_aplicado')
        descuento_cupon = 0
        codigo_cupon = None
        if cupon_aplicado:
            descuento_cupon = cupon_aplicado.get('descuento', 0)
            codigo_cupon = cupon_aplicado.get('codigo')

        promocion_aplicada = session.get('promocion_aplicada')
        descuento_promocion = 0
        promocion_id = None
        if promocion_aplicada:
            descuento_promocion = promocion_aplicada.get('descuento', 0)
            promocion_id = promocion_aplicada.get('id')

        beneficios_lealtad = _obtener_beneficios_lealtad(session['user_id'], subtotal, tipo_envio)
        descuento_lealtad = beneficios_lealtad.get('descuento_lealtad', 0)
        nivel_cliente = beneficios_lealtad.get('nivel', 'Bronce')

        descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
        descuento_total = descuento_volumen + descuento_cupon + descuento_promocion + descuento_lealtad
        subtotal_con_descuentos = subtotal - descuento_total

        if tipo_envio == 'click_collect':
            envio = 0
        else:
            envio = 199.00 if total_unidades >= 50 else 99.00
        if beneficios_lealtad.get('envio_gratis') and tipo_envio == 'domicilio':
            envio = 0

        total = subtotal_con_descuentos + iva + envio

        year = datetime.utcnow().year
        count = db.pedidos.count_documents({}) + 1
        numero_pedido = f"ORION-{year}-{str(count).zfill(4)}"
        fecha_entrega = datetime.utcnow() + timedelta(days=1 if total_unidades >= 50 else 5)

        pedido = {
            'usuario_id': session['user_id'],
            'usuario_nombre': usuario.get('nombre', ''),
            'usuario_email': usuario.get('email', ''),
            'usuario_telefono': usuario.get('telefono', ''),
            'numero_pedido': numero_pedido,
            'items': items_para_guardar,
            'subtotal': round(subtotal, 2), 'iva': round(iva, 2), 'envio': round(envio, 2),
            'descuento_volumen': round(descuento_volumen, 2),
            'porcentaje_descuento': porcentaje_descuento,
            'descuento_cupon': round(descuento_cupon, 2), 'codigo_cupon': codigo_cupon,
            'descuento_promocion': round(descuento_promocion, 2), 'promocion_id': promocion_id,
            'descuento_lealtad': round(descuento_lealtad, 2), 'nivel_lealtad': nivel_cliente,
            'descuento_total': round(descuento_total, 2), 'total': round(total, 2),
            'metodo_pago': metodo_pago, 'tipo_envio': tipo_envio,
            'estado': 'pendiente', 'pago_estado': 'pendiente',
            'notas': notas, 'total_unidades': total_unidades,
            'es_mayorista': total_unidades >= 50,
            'fecha_entrega_estimada': fecha_entrega,
            'created_at': datetime.utcnow(), 'updated_at': datetime.utcnow()
        }

        if tipo_envio == 'domicilio':
            pedido['direccion'] = {
                'calle': request.form.get('calle'),
                'numero': request.form.get('numero'),
                'colonia': request.form.get('colonia'),
                'ciudad': request.form.get('ciudad'),
                'estado': request.form.get('estado'),
                'cp': request.form.get('cp'),
                'pais': request.form.get('pais', 'México'),
                'referencias': request.form.get('referencias')
            }
        else:
            pedido['tienda_recogida'] = request.form.get('tienda_recogida')
            pedido['codigo_recogida'] = generar_codigo_recogida()

        if codigo_cupon:
            from app.models.cupon_model import CuponUsuario
            r = db.pedidos.insert_one(pedido)
            pedido_id = str(r.inserted_id)
            CuponUsuario.registrar_uso(
                usuario_id=session['user_id'], cupon_codigo=codigo_cupon,
                pedido_id=pedido_id, descuento_aplicado=descuento_cupon
            )
            session.pop('cupon_aplicado', None)
        else:
            r = db.pedidos.insert_one(pedido)
            pedido_id = str(r.inserted_id)

        # ⭐ MARKETPLACE: procesar comisiones de vendedores
        try:
            comisiones_resumen = _procesar_comisiones_marketplace(
                items=items_para_guardar,
                pedido_id=pedido_id,
                numero_pedido=numero_pedido,
            )
            if comisiones_resumen['procesados'] > 0:
                print(
                    f"🏪 [Marketplace] {comisiones_resumen['procesados']} vendedor(es) "
                    f"acreditados en pedido {numero_pedido}",
                    file=sys.stderr
                )
            if comisiones_resumen['errores']:
                for err in comisiones_resumen['errores']:
                    print(f"   ⚠️ {err}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ [Marketplace] Error procesando comisiones: {e}", file=sys.stderr)

        if promocion_id:
            try:
                from app.models.promocion_model import Promocion
                Promocion.registrar_uso(promocion_id, session['user_id'], descuento_promocion)
            except Exception as e:
                print(f"⚠️ Promo: {e}", file=sys.stderr)

        resultado_lealtad = _procesar_lealtad_compra(session['user_id'], total, numero_pedido)
        if resultado_lealtad:
            db.pedidos.update_one(
                {'_id': ObjectId(pedido_id)},
                {'$set': {
                    'puntos_ganados': resultado_lealtad.get('puntos_ganados', 0),
                    'puntos_multiplicador': resultado_lealtad.get('multiplicador', 1.0),
                    'cupones_generados': resultado_lealtad.get('cupones_generados', 0)
                }}
            )

        cashback_ganado = _procesar_cashback_monedero(session['user_id'], total, nivel_cliente, pedido_id)
        if cashback_ganado > 0:
            db.pedidos.update_one(
                {'_id': ObjectId(pedido_id)},
                {'$set': {'cashback_ganado': round(cashback_ganado, 2)}}
            )

        session['carrito'] = []
        session['carrito_para_guardar'] = []
        session.pop('promocion_aplicada', None)
        session.modified = True

        mensaje = '¡Pedido realizado con éxito!'
        if resultado_lealtad and resultado_lealtad.get('puntos_ganados', 0) > 0:
            mensaje += f" Ganaste {resultado_lealtad['puntos_ganados']} puntos 👑"
        if cashback_ganado > 0:
            mensaje += f" y ${cashback_ganado:.2f} de cashback 💸"

        flash(mensaje, 'success')
        return redirect(url_for('web.ver_pedido', id=pedido_id))

    except Exception as e:
        print(f"❌ procesar_checkout: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('web.ver_carrito'))


# ================================================================
# PEDIDOS CLIENTE
# ================================================================

def mis_pedidos_clientes():
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus pedidos', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    pedidos = list(db.pedidos.find({'usuario_id': session['user_id']}).sort('created_at', -1))
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']
        pedido.setdefault('total', 0)
        pedido['puede_cancelar'] = pedido.get('estado') in ['pendiente', 'confirmado']
    categorias = list(db.categorias.find({}))
    return render_template('tienda/mis_pedidos_clientes.html', pedidos=pedidos, categorias=categorias)


def ver_pedido(id):
    if 'user_id' not in session:
        flash('Inicia sesión para ver tus pedidos', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    try:
        pedido = None
        try:
            pedido = db.pedidos.find_one({'_id': ObjectId(id), 'usuario_id': session['user_id']})
        except Exception:
            pass
        if not pedido:
            pedido = db.pedidos.find_one({'numero_pedido': id, 'usuario_id': session['user_id']})
        if not pedido:
            pedido = db.pedidos.find_one({'_id': id, 'usuario_id': session['user_id']})
        if not pedido:
            flash('Pedido no encontrado', 'danger')
            return redirect(url_for('web.mis_pedidos_clientes'))
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']
        pedido.setdefault('total', 0)
        categorias = list(db.categorias.find({}))
        return render_template('tienda/detalle_pedido.html', pedido=pedido, categorias=categorias)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('web.mis_pedidos_clientes'))


def cancelar_pedido(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id), 'usuario_id': session['user_id']})
        if not pedido:
            return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404
        if pedido.get('estado') not in ['pendiente', 'confirmado']:
            return jsonify({'success': False, 'message': 'No se puede cancelar'}), 400
        puntos = pedido.get('puntos_ganados', 0)
        cashback = pedido.get('cashback_ganado', 0)
        if puntos > 0:
            _revertir_lealtad_pedido(session['user_id'], puntos,
                f"Cancelación {pedido.get('numero_pedido')}")
        if cashback > 0:
            _revertir_cashback_pedido(session['user_id'], cashback,
                f"Cancelación {pedido.get('numero_pedido')}")
        db.pedidos.update_one({'_id': ObjectId(id)},
            {'$set': {'estado': 'cancelado', 'fecha_cancelacion': datetime.utcnow(),
                      'puntos_revertidos': puntos, 'cashback_revertido': cashback}})
        return jsonify({'success': True, 'message': 'Pedido cancelado'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def generar_codigo_recogida_api(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id), 'usuario_id': session['user_id']})
        if not pedido:
            return jsonify({'success': False, 'message': 'No encontrado'}), 404
        if pedido.get('tipo_envio') != 'click_collect':
            return jsonify({'success': False, 'message': 'No es Click & Collect'}), 400
        if pedido.get('estado') != 'confirmado':
            return jsonify({'success': False, 'message': 'Aún no está listo'}), 400
        codigo = generar_codigo_recogida()
        db.pedidos.update_one({'_id': ObjectId(id)},
            {'$set': {'codigo_recogida': codigo, 'estado': 'preparando',
                      'fecha_preparacion': datetime.utcnow()}})
        return jsonify({'success': True, 'codigo': codigo, 'tienda': pedido.get('tienda_recogida')})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def confirmar_pedido(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id), 'usuario_id': session['user_id']})
        if not pedido:
            return jsonify({'success': False, 'message': 'No encontrado'}), 404
        if pedido.get('estado') != 'enviado':
            return jsonify({'success': False, 'message': 'No enviado'}), 400
        db.pedidos.update_one({'_id': ObjectId(id)},
            {'$set': {'estado': 'entregado', 'fecha_entrega_real': datetime.utcnow()}})
        return jsonify({'success': True, 'message': 'Confirmado'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def rastrear_pedido():
    db = current_app.db
    if request.method == 'POST':
        numero = request.form.get('numero_pedido')
        email = request.form.get('email')
        pedido = db.pedidos.find_one({'numero_pedido': numero, 'usuario_email': email})
        if pedido:
            pedido['_id'] = str(pedido['_id'])
            pedido['items'] = _safe_items_list(pedido)
            _enriquecer_items(pedido['items'])
            categorias = list(db.categorias.find({}))
            return render_template('tienda/rastrear_pedido.html', pedido=pedido, categorias=categorias)
        flash('Pedido no encontrado', 'danger')
    categorias = list(db.categorias.find({}))
    return render_template('tienda/rastrear_pedido.html', categorias=categorias)


# ================================================================
# APIs
# ================================================================

def api_pedidos():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    pedidos = list(db.pedidos.find({'usuario_id': session['user_id']}).sort('created_at', -1))
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['usuario_id'] = str(pedido['usuario_id'])
        pedido['items'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items'])
    return jsonify({'pedidos': pedidos})


def api_pedido(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id), 'usuario_id': session['user_id']})
        if not pedido:
            return jsonify({'error': 'No encontrado'}), 404
        pedido['_id'] = str(pedido['_id'])
        pedido['usuario_id'] = str(pedido['usuario_id'])
        pedido['items'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items'])
        return jsonify(pedido)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ================================================================
# ADMIN
# ================================================================

def admin_listar_pedidos():
    if 'user_id' not in session:
        flash('Inicia sesión', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario:
        session.clear()
        return redirect(url_for('web.login'))
    if normalizar_rol(usuario.get('rol')) != 'admin':
        flash('Sin permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    pedidos = list(db.pedidos.find().sort('created_at', -1))
    for pedido in pedidos:
        pedido['_id'] = str(pedido['_id'])
        pedido['items_list'] = _safe_items_list(pedido)
        _enriquecer_items(pedido['items_list'])
        pedido['items'] = pedido['items_list']
    return render_template('admin/pedidos.html', pedidos=pedidos)


def admin_ver_pedido(id):
    if 'user_id' not in session:
        flash('Inicia sesión', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        flash('Sin permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    pedido = db.pedidos.find_one({'_id': ObjectId(id)})
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('web.admin_listar_pedidos'))
    pedido['_id'] = str(pedido['_id'])
    pedido['items_list'] = _safe_items_list(pedido)
    _enriquecer_items(pedido['items_list'])
    pedido['items'] = pedido['items_list']
    return render_template('admin/detalle_pedido_admin.html', pedido=pedido)


def admin_actualizar_estado_pedido(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    data = request.get_json() or {}
    nuevo_estado = data.get('estado')
    estados_validos = ['pendiente', 'confirmado', 'preparando', 'enviado', 'entregado', 'cancelado']
    if nuevo_estado not in estados_validos:
        return jsonify({'error': 'Estado inválido'}), 400
    try:
        if nuevo_estado == 'cancelado':
            pedido = db.pedidos.find_one({'_id': ObjectId(id)})
            if pedido:
                if pedido.get('puntos_ganados', 0) > 0:
                    _revertir_lealtad_pedido(pedido.get('usuario_id'),
                        pedido.get('puntos_ganados', 0),
                        f"Cancelación admin {pedido.get('numero_pedido')}")
                if pedido.get('cashback_ganado', 0) > 0:
                    _revertir_cashback_pedido(pedido.get('usuario_id'),
                        pedido.get('cashback_ganado', 0),
                        f"Cancelación admin {pedido.get('numero_pedido')}")
        db.pedidos.update_one({'_id': ObjectId(id)},
            {'$set': {'estado': nuevo_estado, 'updated_at': datetime.utcnow()}})
        return jsonify({'success': True, 'message': f'Actualizado a {nuevo_estado}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def admin_eliminar_pedido(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    try:
        db.pedidos.delete_one({'_id': ObjectId(id)})
        return jsonify({'success': True, 'message': 'Eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ================================================================
# PDF MASIVO
# ================================================================

def exportar_pedidos_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether)
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    db = current_app.db
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    filtro = (request.args.get('filtro') or 'todos').strip().lower()
    query = {}
    if filtro and filtro not in ['todos', '']:
        query['estado'] = filtro
    pedidos = list(db.pedidos.find(query).sort('created_at', -1))

    PINK = HexColor('#e10098')
    DARK = HexColor('#1a1a2e')
    GRAY = HexColor('#888888')
    LIGHT = HexColor('#f8fafc')
    LINE = HexColor('#e8e8e8')

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('T', parent=styles['Heading1'], fontSize=22,
        textColor=PINK, alignment=TA_CENTER, fontName='Helvetica-Bold')
    style_sub = ParagraphStyle('S', parent=styles['Normal'], fontSize=11,
        textColor=DARK, alignment=TA_CENTER, fontName='Helvetica-Bold')
    style_info = ParagraphStyle('I', parent=styles['Normal'], fontSize=8,
        textColor=GRAY, alignment=TA_CENTER)
    style_ph = ParagraphStyle('PH', parent=styles['Normal'], fontSize=10,
        textColor=DARK, fontName='Helvetica-Bold')
    style_pi = ParagraphStyle('PI', parent=styles['Normal'], fontSize=8, textColor=GRAY)
    style_n = ParagraphStyle('N', parent=styles['Normal'], fontSize=8, textColor=DARK)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm, title='Pedidos ORION')
    story = [Paragraph('ORION.', style_title),
             Paragraph('Reporte de Pedidos', style_sub),
             Paragraph(f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")}', style_info),
             Paragraph(f'Filtro: {filtro.capitalize()}', style_info),
             Spacer(1, 8*mm)]

    total_pedidos = len(pedidos)
    total_monto = sum(float(p.get('total', 0)) for p in pedidos)
    resumen = Table([['PEDIDOS', 'MONTO TOTAL'], [str(total_pedidos), f'${total_monto:,.2f}']],
                    colWidths=[90*mm, 90*mm])
    resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
        ('TEXTCOLOR', (0, 0), (-1, 0), GRAY),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 1), (-1, 1), PINK),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 16),
        ('GRID', (0, 0), (-1, -1), 0.5, LINE),
    ]))
    story.append(resumen)
    story.append(Spacer(1, 10*mm))

    for pedido in pedidos:
        elementos = []
        numero = pedido.get('numero_pedido') or str(pedido.get('_id', ''))[:8]
        fecha = pedido.get('created_at')
        fecha_str = fecha.strftime('%d/%m/%Y %H:%M') if hasattr(fecha, 'strftime') else str(fecha or 'N/A')
        items = _safe_items_list(pedido)
        header = Table([[
            Paragraph(f'<b>#{numero}</b>', style_ph),
            Paragraph(f'<b>{(pedido.get("estado") or "pendiente").capitalize()}</b>', style_ph)
        ],[
            Paragraph(fecha_str, style_pi),
            Paragraph(f'Total: <font color="#e10098"><b>${float(pedido.get("total", 0)):,.2f}</b></font>', style_pi)
        ]], colWidths=[90*mm, 90*mm])
        header.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1),'TOP'),
            ('ALIGN', (1,0),(1,-1),'RIGHT'),
            ('LEFTPADDING', (0,0),(-1,-1),0),
            ('RIGHTPADDING', (0,0),(-1,-1),0),
        ]))
        elementos.append(header)
        elementos.append(Spacer(1, 3*mm))
        if items:
            prod_data = [['Producto', 'Cant.', 'Precio', 'Subtotal']]
            for item in items:
                prod_data.append([
                    Paragraph(str(item.get('nombre', ''))[:60], style_n),
                    str(item.get('cantidad', 1)),
                    f'${float(item.get("precio", 0)):,.2f}',
                    f'${float(item.get("precio", 0))*int(item.get("cantidad", 1)):,.2f}'
                ])
            prod_table = Table(prod_data, colWidths=[95*mm, 20*mm, 27*mm, 28*mm])
            prod_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0),(-1,0), DARK),
                ('TEXTCOLOR', (0,0),(-1,0), white),
                ('FONTNAME', (0,0),(-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0),(-1,-1), 0.3, LINE),
                ('ALIGN', (1,0),(-1,-1), 'RIGHT'),
                ('ROWBACKGROUNDS', (0,1),(-1,-1), [white, LIGHT]),
            ]))
            elementos.append(prod_table)
        box = Table([[elementos]], colWidths=[180*mm])
        box.setStyle(TableStyle([
            ('BOX', (0,0),(-1,-1), 1, PINK),
            ('LEFTPADDING', (0,0),(-1,-1), 6),
            ('RIGHTPADDING', (0,0),(-1,-1), 6),
            ('TOPPADDING', (0,0),(-1,-1), 6),
            ('BOTTOMPADDING', (0,0),(-1,-1), 6),
        ]))
        story.append(KeepTogether(box))
        story.append(Spacer(1, 5*mm))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'orion-pedidos-{datetime.now().strftime("%Y-%m-%d")}.pdf')


# ================================================================
# FACTURA INDIVIDUAL
# ================================================================

def _numero_a_letras(n):
    U = ['', 'UN', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE',
         'DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE',
         'DIECIOCHO', 'DIECINUEVE', 'VEINTE']
    D = ['', '', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
    C = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS',
         'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS']

    def td(num):
        if num == 0: return ''
        if num == 100: return 'CIEN'
        c, d, u = num // 100, (num % 100) // 10, num % 10
        p = []
        if c: p.append(C[c])
        if d < 2:
            if num % 100: p.append(U[num % 100])
        else:
            dec = D[d]
            if u: dec += ' Y ' + U[u]
            p.append(dec)
        return ' '.join(x for x in p if x)

    entero = int(n)
    cent = int(round((n - entero) * 100))
    if entero == 0:
        letras = 'CERO'
    else:
        mill = entero // 1_000_000
        miles = (entero % 1_000_000) // 1000
        resto = entero % 1000
        parts = []
        if mill == 1: parts.append('UN MILLÓN')
        elif mill > 1: parts.append(td(mill) + ' MILLONES')
        if miles == 1: parts.append('MIL')
        elif miles > 1: parts.append(td(miles) + ' MIL')
        if resto: parts.append(td(resto))
        letras = ' '.join(parts)
    return f"{letras} PESOS {cent:02d}/100 M.N."


def _buscar_pedido_por_id(id):
    db = current_app.db
    pedido = None
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id)})
    except Exception:
        pass
    if not pedido:
        pedido = db.pedidos.find_one({'numero_pedido': id})
    if not pedido:
        pedido = db.pedidos.find_one({'_id': id})
    return pedido


def _obtener_usuario_de_pedido(pedido):
    db = current_app.db
    try:
        uid = pedido.get('usuario_id')
        if isinstance(uid, str):
            try:
                return db.usuarios.find_one({'_id': ObjectId(uid)})
            except Exception:
                return None
        elif isinstance(uid, ObjectId):
            return db.usuarios.find_one({'_id': uid})
    except Exception:
        return None
    return None


def _generar_factura_pdf_interno(pedido, usuario):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    df = (usuario or {}).get('datos_fiscales', {}) or {}
    PINK = HexColor('#e10098')
    DARK = HexColor('#1a1a2e')
    GRAY = HexColor('#64748b')
    LIGHT = HexColor('#f8fafc')
    LINE = HexColor('#e8e8e8')
    styles = getSampleStyleSheet()

    def ps(name, **kw): return ParagraphStyle(name, parent=styles['Normal'], **kw)

    numero = pedido.get('numero_pedido') or str(pedido.get('_id', ''))[:8]
    fecha = pedido.get('created_at')
    fecha_str = fecha.strftime('%d/%m/%Y %H:%M') if hasattr(fecha, 'strftime') else str(fecha or 'N/A')

    cliente_nombre = pedido.get('usuario_nombre') or (usuario or {}).get('nombre', 'Cliente')
    cliente_email = pedido.get('usuario_email') or (usuario or {}).get('email', '')
    cliente_tel = pedido.get('usuario_telefono') or (usuario or {}).get('telefono', '')

    rfc = df.get('rfc', 'XAXX010101000')
    razon = df.get('razon_social', cliente_nombre)
    regimen = df.get('regimen_fiscal', '616')
    uso = df.get('uso_cfdi', 'G03')

    metodo = (pedido.get('metodo_pago') or 'N/A').title()
    items = _safe_items_list(pedido)
    subtotal = float(pedido.get('subtotal', 0) or 0)
    iva = float(pedido.get('iva', 0) or 0)
    envio = float(pedido.get('envio', 0) or 0)
    desc = float(pedido.get('descuento_total', 0) or 0)
    total = float(pedido.get('total', 0) or 0)
    letras = _numero_a_letras(total)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm, title=f'Factura {numero}')
    story = []

    left = [Paragraph('ORION.', ps('E', fontSize=20, textColor=PINK, fontName='Helvetica-Bold')),
            Paragraph('Tecnología y Estilo S.A. de C.V.', ps('ES', fontSize=8, textColor=GRAY)),
            Paragraph('RFC: ORN240101ABC', ps('ES2', fontSize=8, textColor=GRAY))]
    right = [Paragraph('FACTURA', ps('F', fontSize=14, textColor=DARK,
                                     fontName='Helvetica-Bold', alignment=TA_RIGHT)),
             Paragraph(f'Folio: <b>{numero}</b>', ps('FS', fontSize=8, textColor=GRAY, alignment=TA_RIGHT)),
             Paragraph(f'Fecha: {fecha_str}', ps('FS2', fontSize=8, textColor=GRAY, alignment=TA_RIGHT))]
    h = Table([[left, right]], colWidths=[110*mm, 70*mm])
    h.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                           ('RIGHTPADDING',(0,0),(-1,-1),0)]))
    story += [h, Spacer(1, 5*mm)]
    story.append(Table([['']], colWidths=[180*mm], rowHeights=[1.2],
                        style=TableStyle([('BACKGROUND',(0,0),(-1,-1),PINK)])))
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph('DATOS DEL RECEPTOR', ps('S', fontSize=9, textColor=DARK, fontName='Helvetica-Bold')))
    rec = [
        [Paragraph('<b>Razón social:</b>', ps('N', fontSize=8.5)), Paragraph(str(razon), ps('N2', fontSize=8.5))],
        [Paragraph('<b>RFC:</b>', ps('N3', fontSize=8.5)), Paragraph(str(rfc), ps('N4', fontSize=8.5))],
        [Paragraph('<b>Email:</b>', ps('N5', fontSize=8.5)), Paragraph(cliente_email or '—', ps('N6', fontSize=8.5))],
        [Paragraph('<b>Uso CFDI:</b>', ps('N7', fontSize=8.5)), Paragraph(str(uso), ps('N8', fontSize=8.5))],
    ]
    rt = Table(rec, colWidths=[35*mm, 145*mm])
    rt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),0.5,LINE),
                            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story += [rt, Spacer(1, 5*mm)]

    story.append(Paragraph('CONCEPTOS', ps('S2', fontSize=9, textColor=DARK, fontName='Helvetica-Bold')))
    rows = [[Paragraph('Descripción', ps('TH', fontSize=8, textColor=white, fontName='Helvetica-Bold', alignment=TA_LEFT)),
             Paragraph('Cant.', ps('TH2', fontSize=8, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER)),
             Paragraph('P.Unit', ps('TH3', fontSize=8, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER)),
             Paragraph('Importe', ps('TH4', fontSize=8, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER))]]
    for it in items:
        c = int(it.get('cantidad', 1) or 1)
        p = float(it.get('precio', 0) or 0)
        rows.append([Paragraph(str(it.get('nombre', ''))[:80], ps('I', fontSize=8.5)),
                     Paragraph(str(c), ps('I2', fontSize=8.5)),
                     Paragraph(f'${p:,.2f}', ps('I3', fontSize=8.5)),
                     Paragraph(f'${p*c:,.2f}', ps('I4', fontSize=8.5))])
    it_t = Table(rows, colWidths=[100*mm, 15*mm, 32.5*mm, 32.5*mm])
    it_t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),DARK),('GRID',(0,0),(-1,-1),0.3,LINE),
                              ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                              ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                              ('ROWBACKGROUNDS',(0,1),(-1,-1),[white, LIGHT])]))
    story += [it_t, Spacer(1, 5*mm)]

    tot = [[Paragraph('Subtotal', ps('T1', fontSize=8.5)), Paragraph(f'${subtotal:,.2f}', ps('T2', fontSize=8.5))]]
    if desc > 0:
        tot.append([Paragraph('Descuentos', ps('T3', fontSize=8.5)), Paragraph(f'-${desc:,.2f}', ps('T4', fontSize=8.5))])
    tot.append([Paragraph('IVA (16%)', ps('T5', fontSize=8.5)), Paragraph(f'${iva:,.2f}', ps('T6', fontSize=8.5))])
    tot.append([Paragraph('Envío', ps('T7', fontSize=8.5)), Paragraph(f'${envio:,.2f}', ps('T8', fontSize=8.5))])
    tt = Table(tot, colWidths=[40*mm, 40*mm], hAlign='RIGHT')
    tt.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'RIGHT'),('TOPPADDING',(0,0),(-1,-1),3),
                            ('BOTTOMPADDING',(0,0),(-1,-1),3),('LINEBELOW',(0,0),(-1,-2),0.3,LINE)]))
    story += [tt, Spacer(1, 3*mm)]

    tb = Table([[Paragraph('<b>TOTAL</b>', ps('TL', fontSize=11, textColor=white, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
                 Paragraph(f'<b>${total:,.2f} MXN</b>', ps('TV', fontSize=14, textColor=white, fontName='Helvetica-Bold', alignment=TA_RIGHT))]],
               colWidths=[40*mm, 40*mm], hAlign='RIGHT')
    tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PINK),('TOPPADDING',(0,0),(-1,-1),6),
                            ('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),8),
                            ('RIGHTPADDING',(0,0),(-1,-1),8)]))
    story += [tb, Spacer(1, 3*mm)]
    story.append(Paragraph(f'<b>Importe con letra:</b> {letras}',
                            ps('L', fontSize=8, textColor=GRAY, alignment=TA_RIGHT)))
    story.append(Spacer(1, 5*mm))

    pago = Table([[Paragraph(
        f'<b>Método de pago:</b> {metodo}<br/>'
        f'<b>Moneda:</b> MXN<br/>'
        f'<b>Estado:</b> {(pedido.get("estado") or "pendiente").capitalize()}',
        ps('P', fontSize=8.5))]], colWidths=[180*mm])
    pago.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),0.5,LINE),
                              ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                              ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story += [pago, Spacer(1, 6*mm)]

    story.append(Paragraph('Este documento es una representación impresa de un CFDI.',
                            ps('LG', fontSize=7, textColor=GRAY, alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=False,
                     download_name=f'factura-{numero}.pdf')


def admin_generar_factura_pdf(id):
    if 'user_id' not in session:
        flash('Inicia sesión', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario_admin = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario_admin or normalizar_rol(usuario_admin.get('rol')) != 'admin':
        flash('Sin permisos', 'danger')
        return redirect(url_for('web.raiz_tienda'))
    pedido = _buscar_pedido_por_id(id)
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('web.admin_listar_pedidos'))
    usuario = _obtener_usuario_de_pedido(pedido)
    return _generar_factura_pdf_interno(pedido, usuario)


def cliente_generar_factura_pdf(id):
    if 'user_id' not in session:
        flash('Inicia sesión', 'warning')
        return redirect(url_for('web.login'))
    db = current_app.db
    usuario_actual = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario_actual:
        session.clear()
        return redirect(url_for('web.login'))
    pedido = _buscar_pedido_por_id(id)
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('web.mis_pedidos_clientes'))
    es_admin = normalizar_rol(usuario_actual.get('rol')) == 'admin'
    es_mio = str(pedido.get('usuario_id')) == str(session['user_id'])
    if not (es_admin or es_mio):
        flash('No autorizado', 'danger')
        return redirect(url_for('web.mis_pedidos_clientes'))
    usuario_factura = usuario_actual if es_mio else _obtener_usuario_de_pedido(pedido)
    return _generar_factura_pdf_interno(pedido, usuario_factura)


# ================================================================
# DEBUG
# ================================================================

def debug_pedido(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    db = current_app.db
    try:
        pedido = db.pedidos.find_one({'_id': ObjectId(id)})
        if not pedido:
            return jsonify({'error': 'No encontrado'}), 404
        raw = pedido.get('items')
        return jsonify({
            'numero_pedido': pedido.get('numero_pedido'),
            'total': pedido.get('total'),
            'items_type': str(type(raw)),
            'items_is_list': isinstance(raw, list),
            'items_value': raw if isinstance(raw, (list, dict)) else str(raw)[:200],
            'all_keys': list(pedido.keys()),
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def test_admin_pedidos():
    return "OK"


# ================================================================
# 💳 CHECKOUT MSI — soporta tarjeta guardada (MIT) y tarjeta nueva (token)
# ================================================================

def procesar_checkout_msi():
    """
    Flujo MSI con DOS rutas:

      A) TARJETA GUARDADA (MIT — Merchant Initiated Transaction)
         Frontend → solo `tarjeta_guardada_id`
         Backend  → resuelve customer_id + payment_source_id
                  → crea orden CON customer_id asociado
                  → cobra con payment_source_id (SIN cvc)
         ✅ No requiere re-tokenización ni CVC.

      B) TARJETA NUEVA
         Frontend → `token_id` (Conekta.Token.create)
         Backend  → crea orden + cobra con `token_id`
    """
    from app.services.conekta_service import (
        crear_orden_con_msi,
        crear_cargo_con_token,
        cobrar_orden_con_payment_source,
    )
    from app.config.payment_config import CONEKTA_MSI_PLAZOS
    from datetime import timezone

    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Debes iniciar sesión'}), 401

    try:
        data = request.get_json() or {}
        token_id            = (data.get('token_id') or '').strip()
        tarjeta_guardada_id = (data.get('tarjeta_guardada_id') or '').strip()
        meses_msi           = int(data.get('meses_msi', 0))

        print(f"📥 [MSI] token_id={bool(token_id)} | "
              f"tarjeta_guardada_id='{tarjeta_guardada_id}' | "
              f"msi={meses_msi}", file=sys.stderr)

        if meses_msi not in CONEKTA_MSI_PLAZOS and meses_msi != 0:
            return jsonify({
                'success': False,
                'error': f'Plazo MSI inválido. Válidos: {CONEKTA_MSI_PLAZOS}'
            }), 400

        # Debe haber AL MENOS uno de los dos
        if not token_id and not tarjeta_guardada_id:
            return jsonify({
                'success': False,
                'error': 'Falta el token de la tarjeta o el ID de tarjeta guardada'
            }), 400

        db = current_app.db
        carrito = _obtener_carrito_usuario(session['user_id'])
        if not carrito:
            return jsonify({'success': False, 'error': 'El carrito está vacío'}), 400

        items_normalizados = _normalizar_items_para_guardar(carrito)

        subtotal = sum(float(i.get('precio', 0)) * int(i.get('cantidad', 1))
                       for i in items_normalizados)
        iva = subtotal * 0.16
        total = subtotal + iva

        print(f"💰 [MSI] Total: ${total:.2f}", file=sys.stderr)

        # ---------------------------------------------------------
        # Resolver tarjeta guardada (si aplica)
        # ---------------------------------------------------------
        tarjeta = None
        customer_id_orden = None
        payment_source_id_orden = None

        if tarjeta_guardada_id and not token_id:
            print(f"🔍 [MSI] Resolviendo tarjeta guardada (flujo MIT)...",
                  file=sys.stderr)

            tarjeta = _buscar_tarjeta_guardada(session['user_id'], tarjeta_guardada_id)
            if not tarjeta:
                return jsonify({
                    'success': False,
                    'error': f'No encontramos la tarjeta (ID: {tarjeta_guardada_id}). '
                             f'Recarga la página e intenta de nuevo.'
                }), 404

            customer_id_orden       = tarjeta.get('conekta_customer_id')
            payment_source_id_orden = tarjeta.get('conekta_payment_source_id')

            print(f"💳 [MSI] Tarjeta: ••••{tarjeta.get('ultimos4')} | "
                  f"customer={customer_id_orden} | "
                  f"payment_source={payment_source_id_orden}", file=sys.stderr)

            if not customer_id_orden or not payment_source_id_orden:
                return jsonify({
                    'success': False,
                    'error': 'Esta tarjeta no está vinculada a Conekta. '
                             'Elimínala desde Mi Cuenta → Métodos de Pago y vuelve a guardarla.'
                }), 400

        # ---------------------------------------------------------
        # line_items
        # ---------------------------------------------------------
        line_items = []
        for item in items_normalizados:
            line_items.append({
                'name':       item.get('nombre', 'Producto'),
                'unit_price': float(item.get('precio', 0)),
                'quantity':   int(item.get('cantidad', 1)),
            })
        if iva > 0:
            line_items.append({
                'name':       'IVA (16%)',
                'unit_price': round(iva, 2),
                'quantity':   1
            })

        # ---------------------------------------------------------
        # customer_info — incluir customer_id si hay tarjeta guardada
        # ---------------------------------------------------------
        customer_info = {
            'nombre':   data.get('nombre', session.get('nombre', 'Cliente')),
            'email':    data.get('email', session.get('email', '')),
            'telefono': data.get('telefono', '+525555555555'),
        }
        if customer_id_orden:
            customer_info['customer_id'] = customer_id_orden
            print(f"👤 [MSI] customer_info.customer_id = {customer_id_orden}",
                  file=sys.stderr)

        # ---------------------------------------------------------
        # Crear orden en Conekta
        # ---------------------------------------------------------
        resultado_orden = crear_orden_con_msi(
            monto_total=total,
            descripcion=f'Compra ORION ({len(items_normalizados)} productos)',
            customer_info=customer_info,
            line_items=line_items,
            meses_sin_intereses=meses_msi,
        )
        if not resultado_orden.get('success'):
            return jsonify({
                'success': False,
                'error': f'Error al crear orden: {resultado_orden.get("error")}'
            }), 500

        order_id = resultado_orden['order_id']
        print(f"✅ [MSI] Orden Conekta: {order_id}", file=sys.stderr)

        # ---------------------------------------------------------
        # Cobrar — rama según el flujo
        # ---------------------------------------------------------
        if tarjeta:
            # ⭐ TARJETA GUARDADA → MIT sin CVC
            resultado_cargo = cobrar_orden_con_payment_source(
                order_id=order_id,
                customer_id=customer_id_orden,
                payment_source_id=payment_source_id_orden,
                cvc=None,                      # ⭐ SIN CVC
                meses_sin_intereses=meses_msi,
            )
            if not resultado_cargo.get('success'):
                return jsonify({
                    'success': False,
                    'error': f'Pago rechazado: {resultado_cargo.get("error")}'
                }), 400

            print(f"💳 [MSI] Aprobado (guardada, MIT, sin cvc) {order_id}",
                  file=sys.stderr)
        else:
            # ⭐ TARJETA NUEVA → cobrar con token
            resultado_cargo = crear_cargo_con_token(
                order_id=order_id,
                token_id=token_id,
                monto_total=total,
                meses_sin_intereses=meses_msi,
            )
            if not resultado_cargo.get('success'):
                return jsonify({
                    'success': False,
                    'error': f'Pago rechazado: {resultado_cargo.get("error")}'
                }), 400

            print(f"💳 [MSI] Aprobado (token) {order_id}", file=sys.stderr)

        # ---------------------------------------------------------
        # Guardar pedido
        # ---------------------------------------------------------
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
        year = datetime.now(timezone.utc).year
        count = db.pedidos.count_documents({}) + 1
        numero_pedido = f"ORION-{year}-{str(count).zfill(4)}"

        # ⭐ Calcular envío, fecha de entrega y unidades
        total_unidades = sum(int(i.get('cantidad', 0)) for i in items_normalizados)

        tipo_envio_final = data.get('tipo_envio', 'domicilio')

        if tipo_envio_final == 'click_collect':
            envio = 0
        else:
            envio = 199.00 if total_unidades >= 50 else 99.00

        dias_entrega = 1 if total_unidades >= 50 else 5
        fecha_entrega_estimada = datetime.now(timezone.utc) + timedelta(days=dias_entrega)

        pedido = {
            'usuario_id':        session['user_id'],
            'usuario_nombre':    usuario.get('nombre', '') if usuario else '',
            'usuario_email':     usuario.get('email', '') if usuario else '',
            'usuario_telefono':  usuario.get('telefono', '') if usuario else '',
            'numero_pedido':     numero_pedido,
            'items':             items_normalizados,
            'subtotal':          round(subtotal, 2),
            'iva':               round(iva, 2),
            'envio':             round(envio, 2),
            'descuento':         0.0,
            'descuento_total':   0.0,
            'porcentaje_descuento': 0,
            'total':             round(total, 2),
            'msi_meses':         meses_msi,
            'metodo_pago':       'tarjeta_credito',
            'tipo_envio':        tipo_envio_final,
            'conekta_order_id':  order_id,
            'conekta_status':    resultado_cargo.get('raw', {}).get('status'),
            'estado':            'pendiente',
            'pago_estado':       'pagado',
            'notas':             data.get('notas', ''),
            'direccion':         data.get('direccion', {}) or {},
            'tienda_recogida':   data.get('tienda_recogida') or None,
            'total_unidades':    total_unidades,
            'fecha_entrega_estimada': fecha_entrega_estimada,
            'created_at':        datetime.now(timezone.utc),
            'updated_at':        datetime.now(timezone.utc),
        }

        # Generar código de recogida si es click_collect
        if tipo_envio_final == 'click_collect':
            pedido['codigo_recogida'] = generar_codigo_recogida()

        r = db.pedidos.insert_one(pedido)
        pedido_id = str(r.inserted_id)
        print(f"✅ [MSI] Pedido: {numero_pedido} (id: {pedido_id})", file=sys.stderr)

        # ⭐ MARKETPLACE: procesar comisiones de vendedores
        try:
            comisiones_resumen = _procesar_comisiones_marketplace(
                items=items_normalizados,
                pedido_id=pedido_id,
                numero_pedido=numero_pedido,
            )
            if comisiones_resumen['procesados'] > 0:
                print(
                    f"🏪 [MSI] [Marketplace] {comisiones_resumen['procesados']} vendedor(es) "
                    f"acreditados en pedido {numero_pedido}",
                    file=sys.stderr
                )
            if comisiones_resumen['errores']:
                for err in comisiones_resumen['errores']:
                    print(f"   ⚠️ {err}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ [MSI] [Marketplace] Error procesando comisiones: {e}",
                  file=sys.stderr)

        # ---------------------------------------------------------
        # Guardar tarjeta NUEVA si el usuario lo pidió
        # ---------------------------------------------------------
        try:
            guardar_tarjeta = bool(data.get('guardar_tarjeta', False))
            tarjeta_info = data.get('tarjeta_info') or {}

            if guardar_tarjeta and tarjeta_info.get('ultimos4') and token_id:
                from app.services.conekta_service import (
                    crear_o_actualizar_customer, crear_payment_source
                )
                usuario_id_str = str(session['user_id'])

                cust_res = crear_o_actualizar_customer(
                    usuario_id=usuario_id_str,
                    nombre=customer_info['nombre'],
                    email=customer_info['email'],
                    telefono=customer_info['telefono'],
                    conekta_customer_id=(usuario or {}).get('conekta_customer_id'),
                )
                if not cust_res.get('success'):
                    raise Exception(cust_res.get('error'))

                customer_id = cust_res['customer_id']
                db.usuarios.update_one(
                    {'_id': ObjectId(session['user_id'])},
                    {'$set': {'conekta_customer_id': customer_id}}
                )

                ps_res = crear_payment_source(customer_id, token_id)
                if not ps_res.get('success'):
                    raise Exception(ps_res.get('error'))

                nuevo_metodo = {
                    'id': str(ObjectId()),
                    'usuario_id': usuario_id_str,
                    'tipo': 'tarjeta',
                    'marca': tarjeta_info.get('marca', 'Tarjeta'),
                    'ultimos4': tarjeta_info.get('ultimos4', ''),
                    'titular': tarjeta_info.get('titular', ''),
                    'expira': tarjeta_info.get('expira', ''),
                    'conekta_customer_id': customer_id,
                    'conekta_payment_source_id': ps_res['payment_source_id'],
                    'predeterminado': False,
                    'created_at': datetime.now(timezone.utc),
                }
                if db.metodos_pago.count_documents({'usuario_id': usuario_id_str}) == 0:
                    nuevo_metodo['predeterminado'] = True

                db.metodos_pago.insert_one(nuevo_metodo)
                print(f"💾 [MSI] Tarjeta guardada: "
                      f"{nuevo_metodo['marca']} •••• {nuevo_metodo['ultimos4']}",
                      file=sys.stderr)
        except Exception as e:
            print(f"⚠️ No se pudo guardar tarjeta: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()

        _vaciar_carrito_usuario(session['user_id'])

        return jsonify({
            'success': True,
            'message': 'Pago exitoso',
            'pedido_id': pedido_id,
            'numero_pedido': numero_pedido,
            'redirect': url_for('web.ver_pedido', id=pedido_id),
            'msi_meses': meses_msi,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500