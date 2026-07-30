# app/controllers/carrito_controller.py
# Controlador completo del carrito con soporte para cupones y promociones

from flask import session, request, jsonify, current_app, redirect, url_for, render_template, make_response, flash
from datetime import datetime
from bson import ObjectId
from app.models.productos_model import Producto
from app.models.cupon_model import Cupon, CuponUsuario
from app.models.promocion_model import Promocion
import sys


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
    
    # OBTENER STOCK CORRECTAMENTE
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
    
    # Calcular subtotal
    subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 0)) for item in carrito)
    
    # 🔥 OBTENER CUPÓN APLICADO
    cupon_aplicado = session.get('cupon_aplicado', None)
    descuento_cupon = 0
    
    # 🔥 OBTENER PROMOCIÓN APLICADA
    promocion_aplicada = session.get('promocion_aplicada', None)
    descuento_promocion = 0
    
    # Calcular descuento por volumen
    total_unidades = sum(int(item.get('cantidad', 0)) for item in carrito)
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
    
    # Calcular descuento total (volumen + cupón + promoción)
    descuento_total = descuento_volumen
    
    if cupon_aplicado:
        descuento_cupon = cupon_aplicado.get('descuento', 0)
        descuento_total += descuento_cupon
        print(f"💰 Cupón aplicado: {cupon_aplicado.get('codigo')} - Descuento: ${descuento_cupon:.2f}", file=sys.stderr)
    
    if promocion_aplicada:
        descuento_promocion = promocion_aplicada.get('descuento', 0)
        descuento_total += descuento_promocion
        print(f"🎁 Promoción aplicada: {promocion_aplicada.get('nombre')} - Descuento: ${descuento_promocion:.2f}", file=sys.stderr)
    
    # Calcular IVA sobre el subtotal con descuentos
    subtotal_con_descuentos = subtotal - descuento_total
    iva = subtotal_con_descuentos * 0.16
    total_final = subtotal_con_descuentos + iva
    
    db = current_app.db
    categorias = list(db.categorias.find({}))
    
    # Obtener tiendas para el modal
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
    """
    Calcula el descuento por volumen según la cantidad de unidades
    Estilo Liverpool - Descuentos progresivos
    """
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
# ELIMINAR PRODUCTO DEL CARRITO
# ================================================================

def eliminar_del_carrito(id):
    """Eliminar producto del carrito"""
    carrito = session.get('carrito', [])
    session['carrito'] = [item for item in carrito if str(item.get('id')) != str(id)]
    session.modified = True
    return redirect(url_for('web.ver_carrito'))


# ================================================================
# ACTUALIZAR CANTIDAD
# ================================================================

def actualizar_cantidad_carrito(id):
    """Actualizar cantidad de un producto en el carrito"""
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
# QUITAR CUPÓN
# ================================================================

def quitar_cupon_carrito():
    """Quitar cupón del carrito"""
    if 'cupon_aplicado' in session:
        session.pop('cupon_aplicado', None)
        session.pop('descuento_aplicado', None)
        session.pop('total_con_descuento', None)
        session.modified = True
        flash('Cupón eliminado del carrito', 'info')
    return redirect(url_for('web.ver_carrito'))


# ================================================================
# QUITAR PROMOCIÓN
# ================================================================

def quitar_promocion_carrito():
    """Quitar promoción del carrito"""
    if 'promocion_aplicada' in session:
        session.pop('promocion_aplicada', None)
        session.modified = True
        flash('Promoción eliminada del carrito', 'info')
    return redirect(url_for('web.ver_carrito'))


# ================================================================
# DESCARGAR FACTURA (PDF)
# ================================================================

def descargar_factura():
    """Generar factura en PDF y procesar pago con cupón y promoción"""
    carrito = session.get('carrito', [])
    if not carrito:
        return "El carrito ya está vacío.", 400

    subtotal = sum(float(item.get('precio', 0)) * int(item.get('cantidad', 0)) for item in carrito)
    
    # Calcular descuento por volumen
    total_unidades = sum(int(item.get('cantidad', 0)) for item in carrito)
    descuento_volumen, porcentaje_descuento = calcular_descuento_volumen(total_unidades, subtotal)
    
    # 🔥 OBTENER CUPÓN APLICADO
    cupon_aplicado = session.get('cupon_aplicado', None)
    descuento_cupon = 0
    codigo_cupon = None
    if cupon_aplicado:
        descuento_cupon = cupon_aplicado.get('descuento', 0)
        codigo_cupon = cupon_aplicado.get('codigo')
    
    # 🔥 OBTENER PROMOCIÓN APLICADA
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

    # 🔥 REGISTRAR USO DEL CUPÓN
    if codigo_cupon and session.get('user_id'):
        from app.models.cupon_model import CuponUsuario
        CuponUsuario.registrar_uso(
            usuario_id=session['user_id'],
            cupon_codigo=codigo_cupon,
            pedido_id=None,
            descuento_aplicado=descuento_cupon
        )

    # 🔥 REGISTRAR USO DE LA PROMOCIÓN (seguro)
    if promocion_id and session.get('user_id'):
        try:
            # Si el modelo tiene el método, usarlo
            if hasattr(Promocion, 'registrar_uso'):
                Promocion.registrar_uso(promocion_id, session['user_id'], descuento_promocion)
            else:
                # Registrar uso manualmente en la colección de usos
                db.promociones_usos.insert_one({
                    'promocion_id': ObjectId(promocion_id),
                    'usuario_id': ObjectId(session['user_id']),
                    'descuento': descuento_promocion,
                    'fecha': datetime.utcnow()
                })
                # Incrementar usos_actuales en la promoción
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
    
    # 🔥 Actualizar pedido con el ID de la venta para el cupón
    if codigo_cupon and session.get('user_id'):
        from app.models.cupon_model import CuponUsuario
        pedido_id = str(resultado.inserted_id)
        db.cupones_usuarios.update_one(
            {"usuario_id": str(session['user_id']), "cupon_codigo": codigo_cupon},
            {"$set": {"pedido_id": pedido_id}}
        )

    pdf_data = _generar_pdf_factura(
        carrito, total_con_iva, descuento_volumen, porcentaje_descuento,
        descuento_cupon, codigo_cupon, descuento_promocion, promocion_aplicada
    )
    
    # Limpiar carrito, cupón y promoción
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
# PROCESAR PAGO
# ================================================================

def procesar_pago():
    """Procesar pago - redirige a factura"""
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('web.ver_carrito'))
    return redirect(url_for('web.descargar_factura'))


# ================================================================
# VACIAR CARRITO
# ================================================================

def vaciar_carrito():
    """Vaciar carrito (API)"""
    session['carrito'] = []
    session.modified = True
    return jsonify({"success": True, "message": "Carrito vaciado"})


# ================================================================
# APLICAR CUPÓN (DEPRECATED)
# ================================================================

def aplicar_cupon():
    """Aplicar cupón de descuento (API) - DEPRECATED, usar cupon_controller.cliente_aplicar_cupon"""
    return jsonify({"success": False, "message": "Usa /api/cupon/aplicar"})


# ================================================================
# API CARRITO
# ================================================================

def api_carrito():
    """API para carrito"""
    if request.method == 'GET':
        carrito = session.get('carrito', [])
        # Calcular total
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
        return jsonify({"carrito": carrito, "total": total, "items": items})
    
    elif request.method == 'POST':
        return agregar_al_carrito()
    
    elif request.method == 'DELETE':
        return vaciar_carrito()


# ================================================================
# GENERAR PDF FACTURA (FUNCIÓN INTERNA)
# ================================================================

def _generar_pdf_factura(carrito, total_con_iva, descuento_volumen=0, porcentaje=0, descuento_cupon=0, codigo_cupon=None, descuento_promocion=0, promocion_aplicada=None):
    """Generar PDF de factura con descuento por volumen, cupón y promoción"""
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

    stream_lines = [
        "BT",
        "/F1 12 Tf",
        "50 760 Td",
        "14 TL"
    ]
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