# ================================================================
# app/controllers/producto_controller.py - CONTROLADOR COMPLETO (SIN CARRITO)
# ================================================================

import os
import uuid
from flask import render_template, request, redirect, url_for, current_app, session, jsonify, make_response, flash
from datetime import datetime
from app.models.empresas_model import Empresa
from app.models.resenas_model import Resena
from app.models.categorias_model import Categoria
from app.models.productos_model import Producto as ProductoModel
from bson import ObjectId
from werkzeug.utils import secure_filename

# --- UTILIDADES ---

def _get_upload_folder():
    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'productos')
    os.makedirs(folder, exist_ok=True)
    return folder

def _save_photos(files, nombre_producto, fotos_existentes=None):
    upload_path = _get_upload_folder()
    prefijo = "".join([c if c.isalnum() else "_" for c in nombre_producto.lower()])
    fotos_guardadas = list(fotos_existentes) if fotos_existentes else []
    for file in [f for f in files if f and f.filename]:
        if len(fotos_guardadas) >= 6: break
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            continue
        nombre_archivo = f"{prefijo}_{len(fotos_guardadas)}_{os.urandom(2).hex()}{ext}"
        file.save(os.path.join(upload_path, nombre_archivo))
        fotos_guardadas.append(nombre_archivo)
    return fotos_guardadas

def _extraer_variantes(form):
    skus = form.getlist('sku[]')
    colores = form.getlist('color[]')
    tamanos = form.getlist('tamano[]')
    precios = form.getlist('precio[]')
    stocks = form.getlist('stock[]')
    variantes = []
    for i in range(len(skus)):
        if skus[i].strip():
            variantes.append({
                "sku": skus[i].strip(),
                "color": colores[i].strip() if i < len(colores) else "",
                "tamano": tamanos[i].strip() if i < len(tamanos) else "",
                "precio": float(precios[i]) if i < len(precios) and precios[i] not in (None, "") else 0.0,
                "stock": int(stocks[i]) if i < len(stocks) and stocks[i] not in (None, "") else 0
            })
    return variantes

# ====================================================================
# FUNCIÓN CLAVE: Calcular jerarquía de categorías
# ====================================================================
def _calcular_jerarquia_categorias(categorias_crudas):
    todas = list(categorias_crudas)
    mapa = {str(c['_id']): c for c in todas}
    
    for c in todas:
        padre_id = c.get('padre_id')
        if not padre_id or str(padre_id) in ['None', 'null', '']:
            c['nivel'] = 1
            c['padre_nombre'] = "Raíz"
            c['padre_id_str'] = None
        else:
            padre_id_str = str(padre_id)
            padre = mapa.get(padre_id_str)
            if padre:
                abuelo_id = padre.get('padre_id')
                if abuelo_id and str(abuelo_id) not in ['None', 'null', '']:
                    c['nivel'] = 3
                else:
                    c['nivel'] = 2
                c['padre_nombre'] = padre.get('nombre', 'Desconocido')
                c['padre_id_str'] = padre_id_str
            else:
                c['nivel'] = 1
                c['padre_nombre'] = "Raíz (Corregido)"
                c['padre_id_str'] = None
    
    return todas

# --- CONTROLADORES ---

def listar_productos():
    productos = ProductoModel.obtener_todos()
    categorias_crudas = Categoria.obtener_todas()
    categorias = _calcular_jerarquia_categorias(categorias_crudas)
    empresas = Empresa.obtener_todas()
    
    for p in productos:
        p['empresa_nombre'] = ''
        for emp in empresas:
            if str(emp.get('_id')) == str(p.get('empresa_id')):
                p['empresa_nombre'] = emp.get('nombre_comercial', '')
                break
    
    return render_template('admin/productos.html', 
                           productos=productos, 
                           categorias=categorias,
                           empresas=empresas,
                           producto_seleccionado=None)

def ver_producto(id):
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        flash('Producto no encontrado', 'danger')
        return redirect(url_for('web.lista_productos'))
    
    productos = ProductoModel.obtener_todos()
    categorias_crudas = Categoria.obtener_todas()
    categorias = _calcular_jerarquia_categorias(categorias_crudas)
    empresas = Empresa.obtener_todas()
    
    for p in productos:
        p['empresa_nombre'] = ''
        for emp in empresas:
            if str(emp.get('_id')) == str(p.get('empresa_id')):
                p['empresa_nombre'] = emp.get('nombre_comercial', '')
                break
    
    for emp in empresas:
        if str(emp.get('_id')) == str(producto.get('empresa_id')):
            producto['empresa_nombre'] = emp.get('nombre_comercial', '')
            break
    
    return render_template('admin/productos.html', 
                           productos=productos, 
                           categorias=categorias,
                           empresas=empresas,
                           producto_seleccionado=producto)

def agregar():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        if not nombre:
            flash('El nombre del producto es requerido', 'danger')
            return redirect(url_for('web.lista_productos'))
        
        variantes = _extraer_variantes(request.form)
        fotos = _save_photos(request.files.getlist('fotos[]'), nombre)
        
        data = {
            "nombre": nombre.strip(),
            "descripcion": request.form.get('descripcion', '').strip(),
            "categoria_id": request.form.get('categoria_id', '').strip() or None,
            "empresa_id": request.form.get('empresa_id', '').strip() or None,
            "estado": request.form.get('estado', 'activo').strip(),
            "variables": variantes,
            "fotos": fotos,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        ProductoModel.crear(data)
        flash('Producto agregado exitosamente', 'success')
        return redirect(url_for('web.lista_productos'))
    
    return redirect(url_for('web.lista_productos'))

def editar(id):
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        flash('Producto no encontrado', 'danger')
        return redirect(url_for('web.lista_productos'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        if not nombre:
            flash('El nombre del producto es requerido', 'danger')
            return redirect(url_for('web.ver_producto', id=id))
        
        variantes = _extraer_variantes(request.form)
        fotos_existentes = request.form.getlist('fotos_existentes[]')
        fotos = _save_photos(request.files.getlist('fotos[]'), nombre, fotos_existentes)
        
        data = {
            "nombre": nombre.strip(),
            "descripcion": request.form.get('descripcion', '').strip(),
            "categoria_id": request.form.get('categoria_id', '').strip() or None,
            "empresa_id": request.form.get('empresa_id', '').strip() or None,
            "estado": request.form.get('estado', 'activo').strip(),
            "variables": variantes,
            "fotos": fotos,
            "updated_at": datetime.utcnow()
        }
        
        ProductoModel.actualizar(id, data)
        flash('Producto actualizado exitosamente', 'success')
        return redirect(url_for('web.lista_productos'))
    
    return redirect(url_for('web.ver_producto', id=id))

def dar_de_baja(id):
    producto = ProductoModel.obtener_por_id(id)
    if producto:
        ProductoModel.actualizar(id, {"estado": "inactivo", "updated_at": datetime.utcnow()})
        flash('Producto dado de baja exitosamente', 'success')
    else:
        flash('Producto no encontrado', 'danger')
    return redirect(url_for('web.lista_productos'))

def borrar(id):
    if ProductoModel.eliminar(id):
        flash('Producto eliminado exitosamente', 'success')
    else:
        flash('Producto no encontrado', 'danger')
    return redirect(url_for('web.lista_productos'))

# --- CATÁLOGO Y TIENDA ---

def catalogo():
    cat_id = request.args.get('categoria')
    empresa_id = request.args.get('empresa')
    genero = request.args.get('genero')
    query = request.args.get('q', '')

    categorias_crudas = Categoria.obtener_todas()
    todas = _calcular_jerarquia_categorias(categorias_crudas)
    
    if cat_id:
        productos = ProductoModel.filtrar_por_categoria_y_descendientes(cat_id)
    else:
        productos = ProductoModel.obtener_todos()

    if empresa_id:
        productos = [p for p in productos if str(p.get('empresa_id')) == str(empresa_id)]

    if genero:
        productos = [p for p in productos if (p.get('genero') or '').strip().lower() == genero.strip().lower()]

    if query:
        query_lower = query.lower()
        productos = [p for p in productos if query_lower in p.get('nombre', '').lower() or query_lower in p.get('descripcion', '').lower()]

    cat_actual = next((c for c in todas if str(c['_id']) == str(cat_id)), None)
    empresas = Empresa.obtener_todas()
    empresa_actual = next((e for e in empresas if str(e['_id']) == str(empresa_id)), None) if empresa_id else None

    ids_visibles = []
    if cat_actual:
        ids_visibles.append(str(cat_actual['_id']))
        if cat_actual.get('padre_id'):
            ids_visibles.append(str(cat_actual['padre_id']))
            padre = next((c for c in todas if str(c['_id']) == str(cat_actual['padre_id'])), None)
            if padre and padre.get('padre_id'):
                ids_visibles.append(str(padre['padre_id']))
    
    return render_template('tienda/catalogo.html', 
                           categorias=todas, 
                           productos=productos, 
                           categoria_seleccionada=cat_id, 
                           cat_actual=cat_actual,
                           ids_visibles=ids_visibles,
                           empresa_seleccionada=empresa_id,
                           empresa_actual=empresa_actual,
                           genero_seleccionado=genero,
                           query=query)

def ver_detalle_producto(id):
    """Ver detalle de un producto en la tienda"""
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        return "Producto no encontrado", 404
    
    if 'variables' in producto and producto['variables']:
        producto['variantes_para_template'] = producto['variables']
    elif 'variantes' in producto and producto['variantes']:
        producto['variantes_para_template'] = producto['variantes']
    else:
        producto['variantes_para_template'] = []

    # Obtener opiniones del producto
    opiniones = Resena.obtener_por_producto(id)
    producto['opiniones'] = opiniones

    # Obtener empresas
    empresas = Empresa.obtener_todas()
    
    # Obtener la empresa del producto actual
    empresa_actual = next((e for e in empresas if str(e['_id']) == str(producto.get('empresa_id'))), None)
    
    if empresa_actual:
        producto['empresa_nombre'] = empresa_actual.get('nombre_comercial')
        producto['marca'] = empresa_actual.get('nombre_comercial')
    else:
        producto['empresa_nombre'] = 'Marca no especificada'
        producto['marca'] = 'Marca no especificada'

    categorias_crudas = Categoria.obtener_todas()
    categorias = _calcular_jerarquia_categorias(categorias_crudas)
    categoria_actual = next((c for c in categorias if str(c['_id']) == str(producto.get('categoria_id'))), None)
    producto['categoria'] = categoria_actual.get('nombre') if categoria_actual else producto.get('categoria', '')
    producto['genero'] = producto.get('genero') or (categoria_actual.get('genero') if categoria_actual else '')

    db = current_app.db

    productos_relacionados = []
    if producto.get('categoria_id'):
        productos_relacionados = [
            p for p in ProductoModel.obtener_todos()
            if str(p.get('categoria_id')) == str(producto.get('categoria_id'))
            and str(p['_id']) != str(producto['_id'])
            and p.get('estado', 'activo') == 'activo'
        ][:8]

    ids_relacionados = {str(p['_id']) for p in productos_relacionados}
    productos_complementa = [
        p for p in ProductoModel.obtener_todos()
        if str(p['_id']) != str(producto['_id'])
        and str(p['_id']) not in ids_relacionados
        and p.get('estado', 'activo') == 'activo'
    ][:8]

    # OBTENER PRODUCTOS DE LA MISMA MARCA (EMPRESA)
    productos_de_marca = []
    if producto.get('empresa_id'):
        productos_de_marca = [
            p for p in ProductoModel.obtener_todos()
            if str(p.get('empresa_id')) == str(producto.get('empresa_id'))
            and str(p['_id']) != str(producto['_id'])
            and p.get('estado', 'activo') == 'activo'
        ][:12]

    productos_mas_vendidos = []
    try:
        pipeline = [
            {"$unwind": "$productos"},
            {"$group": {"_id": "$productos.id", "total_vendido": {"$sum": "$productos.cantidad"}}},
            {"$sort": {"total_vendido": -1}},
            {"$limit": 8}
        ]
        top_ids = [r['_id'] for r in db.ventas.aggregate(pipeline)]
        for pid in top_ids:
            if str(pid) == str(producto['_id']):
                continue
            p = ProductoModel.obtener_por_id(pid)
            if p:
                productos_mas_vendidos.append(p)
    except Exception:
        productos_mas_vendidos = []

    return render_template(
        'tienda/detalle_producto.html',
        producto=producto,
        empresas=empresas,
        productos_relacionados=productos_relacionados,
        productos_complementa=productos_complementa,
        productos_de_marca=productos_de_marca,
        productos_mas_vendidos=productos_mas_vendidos
    )

def enviar_opinion():
    """Enviar una nueva opinión/reseña de un producto"""
    if request.method == 'POST':
        if 'user_id' not in session:
            flash("Debes iniciar sesión para opinar.", "warning")
            return redirect(url_for('web.login'))
        
        producto_id = request.form.get('producto_id')
        calificacion = request.form.get('calificacion')
        titulo = request.form.get('titulo')
        comentario = request.form.get('comentario')
        
        # Validaciones
        if not producto_id or not calificacion or not titulo or not comentario:
            flash("Todos los campos son obligatorios.", "danger")
            return redirect(url_for('web.ver_detalle_producto', id=producto_id))
        
        # Procesar fotos
        archivos = request.files.getlist('fotos')
        lista_archivos = []
        folder = os.path.join(current_app.root_path, 'static', 'uploads', 'resenas')
        os.makedirs(folder, exist_ok=True)
        
        for archivo in archivos:
            if archivo and archivo.filename:
                nombre_archivo = f"resena_{uuid.uuid4().hex[:8]}_{secure_filename(archivo.filename)}"
                archivo.save(os.path.join(folder, nombre_archivo))
                lista_archivos.append(nombre_archivo)
        
        # Verificar si el usuario ha comprado el producto (para compra_verificada)
        compra_verificada = False
        try:
            db = current_app.db
            compras = db.ventas.find_one({
                'usuario_id': session.get('user_id'),
                'productos.id': producto_id
            })
            if compras:
                compra_verificada = True
        except Exception:
            compra_verificada = False
        
        # Crear la reseña
        data = {
            "producto_id": producto_id,
            "usuario_id": session.get('user_id'),
            "usuario_nombre": session.get('nombre', 'Usuario'),
            "calificacion": int(calificacion),
            "titulo": titulo,
            "comentario": comentario,
            "foto_path": lista_archivos,
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "compra_verificada": compra_verificada,
            "votos_utiles": [],
            "reportes": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        try:
            Resena.crear(data)
            flash("¡Opinión enviada correctamente!", "success")
        except Exception as e:
            print(f"❌ Error al crear opinión: {e}")
            flash("Error al enviar la opinión.", "danger")
        
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))
    
    return redirect(url_for('web.catalogo'))

def listar_por_marca(marca):
    db = current_app.db
    productos = list(db.productos.find({"empresa_id": marca}))

    if not productos:
        empresas = Empresa.obtener_todas()
        empresa = next((e for e in empresas if e.get('nombre_comercial', '').strip().lower() == marca.strip().lower()), None)
        if empresa:
            productos = list(db.productos.find({"empresa_id": str(empresa['_id'])}))

    categorias_crudas = Categoria.obtener_todas()
    categorias = _calcular_jerarquia_categorias(categorias_crudas)
    return render_template('tienda/catalogo.html', productos=productos, categorias=categorias, ids_visibles=[])

# ================================================================
# ====== FUNCIONES NUEVAS AGREGADAS (EXCEPTO LAS DEL CARRITO) ======
# ================================================================

def productos_relacionados(id):
    """Obtiene productos relacionados (API)"""
    db = current_app.db
    
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
    
    categoria = producto.get('categoria_id')
    relacionados = list(db.productos.find({
        '_id': {'$ne': ObjectId(id)},
        'categoria_id': categoria,
        'estado': 'activo'
    }).limit(8))
    
    for p in relacionados:
        p['_id'] = str(p['_id'])
    
    return jsonify({'success': True, 'productos': relacionados})

def productos_mas_vendidos():
    """Obtiene los productos más vendidos (API)"""
    db = current_app.db
    
    try:
        pipeline = [
            {"$unwind": "$productos"},
            {"$group": {"_id": "$productos.id", "total_vendido": {"$sum": "$productos.cantidad"}}},
            {"$sort": {"total_vendido": -1}},
            {"$limit": 8}
        ]
        top_ids = [r['_id'] for r in db.ventas.aggregate(pipeline)]
        productos = []
        for pid in top_ids:
            p = ProductoModel.obtener_por_id(pid)
            if p:
                p['_id'] = str(p['_id'])
                productos.append(p)
        return jsonify({'success': True, 'productos': productos})
    except Exception as e:
        return jsonify({'success': True, 'productos': [], 'message': str(e)})

def productos_por_categoria_api(categoria_id):
    """Obtiene productos por categoría (API)"""
    db = current_app.db
    
    productos = list(db.productos.find({
        'categoria_id': ObjectId(categoria_id),
        'estado': 'activo'
    }).limit(20))
    
    for p in productos:
        p['_id'] = str(p['_id'])
    
    return jsonify({'success': True, 'productos': productos})

def buscar_productos():
    """Buscar productos (API)"""
    db = current_app.db
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'success': True, 'productos': []})
    
    productos = list(db.productos.find({
        '$or': [
            {'nombre': {'$regex': query, '$options': 'i'}},
            {'descripcion': {'$regex': query, '$options': 'i'}}
        ],
        'estado': 'activo'
    }).limit(20))
    
    for p in productos:
        p['_id'] = str(p['_id'])
    
    return jsonify({'success': True, 'productos': productos})

def api_productos():
    """API para listar productos"""
    db = current_app.db
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    skip = (page - 1) * per_page
    
    productos = list(db.productos.find({'estado': 'activo'}).skip(skip).limit(per_page))
    total = db.productos.count_documents({'estado': 'activo'})
    
    for p in productos:
        p['_id'] = str(p['_id'])
    
    return jsonify({
        'success': True,
        'productos': productos,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

def api_producto(id):
    """API para obtener un producto específico"""
    db = current_app.db
    
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
    
    producto['_id'] = str(producto['_id'])
    return jsonify({'success': True, 'producto': producto})

def subir_imagen_producto(id):
    """Subir imagen de producto (admin)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or usuario.get('rol') != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    if 'imagen' not in request.files:
        return jsonify({'success': False, 'message': 'No se envió ninguna imagen'}), 400
    
    imagen = request.files['imagen']
    if imagen.filename == '':
        return jsonify({'success': False, 'message': 'No se seleccionó ninguna imagen'}), 400
    
    filename = secure_filename(imagen.filename)
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'productos')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)
    
    filepath = os.path.join(upload_folder, filename)
    imagen.save(filepath)
    
    db.productos.update_one(
        {'_id': ObjectId(id)},
        {'$push': {'fotos': filename}, '$set': {'updated_at': datetime.utcnow()}}
    )
    
    return jsonify({'success': True, 'message': 'Imagen subida correctamente', 'filename': filename})

def eliminar_imagen_producto(id, index):
    """Eliminar imagen de producto (admin)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401
    
    db = current_app.db
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or usuario.get('rol') != 'admin':
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    producto = ProductoModel.obtener_por_id(id)
    if not producto:
        return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
    
    fotos = producto.get('fotos', [])
    if index < len(fotos):
        filename = fotos[index]
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'productos', filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        fotos.pop(index)
        ProductoModel.actualizar(id, {'fotos': fotos, 'updated_at': datetime.utcnow()})
        
        return jsonify({'success': True, 'message': 'Imagen eliminada correctamente'})
    
    return jsonify({'success': False, 'message': 'Imagen no encontrada'}), 404

def exportar_productos():
    """Exportar productos a CSV (admin)"""
    if 'user_id' not in session:
        flash('Inicia sesión para exportar', 'warning')
        return redirect(url_for('web.login'))
    
    db = current_app.db
    
    usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    if not usuario or usuario.get('rol') != 'admin':
        flash('No autorizado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    productos = list(db.productos.find({'estado': 'activo'}))
    
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID', 'Nombre', 'Descripción', 'Precio', 'Categoría', 'Stock', 'Creado'])
    
    for p in productos:
        stock = 0
        if p.get('variables'):
            stock = sum(v.get('stock', 0) for v in p.get('variables', []))
        
        writer.writerow([
            str(p['_id']),
            p.get('nombre', ''),
            p.get('descripcion', ''),
            p.get('precio', 0),
            p.get('categoria', ''),
            stock,
            p.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M') if p.get('created_at') else ''
        ])
    
    from flask import Response
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=productos.csv'
    return response