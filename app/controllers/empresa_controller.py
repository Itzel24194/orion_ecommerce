# ================================================================
# app/controllers/empresa_controller.py - CONTROLADOR DE EMPRESAS COMPLETO
# ================================================================

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from playwright.sync_api import sync_playwright
from app.models.empresas_model import Empresa
from bson import ObjectId
from datetime import datetime


def listar_empresas():
    empresas = Empresa.obtener_todas()
    return render_template('admin/empresas.html', empresas=empresas)


def ver_empresa(id):
    """Ver detalle de una empresa específica"""
    empresa = Empresa.obtener_por_id(id)
    if not empresa:
        flash("Empresa no encontrada", "danger")
        return redirect(url_for('web.lista_empresas'))
    
    return render_template('admin/empresas.html', 
                         empresas=Empresa.obtener_todas(),
                         empresa_seleccionada=empresa)


def agregar_empresa():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        rfc = request.form.get('rfc', '').upper().strip()
        correo = request.form.get('correo', '')
        telefono = request.form.get('telefono', '')
        direccion = request.form.get('direccion', '')
        
        if not nombre:
            flash("El nombre comercial es requerido", "danger")
            return redirect(url_for('web.lista_empresas'))
        
        # Verificar si ya existe
        existente = Empresa.buscar_por_nombre(nombre)
        if existente:
            flash("Ya existe una empresa con ese nombre", "danger")
            return redirect(url_for('web.lista_empresas'))
        
        data = {
            "nombre_comercial": nombre,
            "rfc": rfc,
            "correo": correo,
            "telefono": telefono,
            "direccion": direccion,
            "status": "pendiente",
            "datos_impi": [],
            "activa": True,
            "created_at": datetime.utcnow()
        }
        
        Empresa.crear(data)
        flash("Empresa registrada exitosamente.", "success")
    
    return redirect(url_for('web.lista_empresas'))


def editar_empresa(id):
    if request.method == 'POST':
        data = {
            "nombre_comercial": request.form.get('nombre'),
            "rfc": request.form.get('rfc', '').upper().strip(),
            "correo": request.form.get('correo', ''),
            "telefono": request.form.get('telefono', ''),
            "direccion": request.form.get('direccion', ''),
            "updated_at": datetime.utcnow()
        }
        
        Empresa.actualizar_datos(id, data)
        flash("Datos actualizados correctamente.", "success")
    
    return redirect(url_for('web.lista_empresas'))


def aprobar_empresa(id):
    Empresa.actualizar_con_notas(id, "activo", "Aprobada por administrador")
    flash("Empresa aprobada exitosamente.", "success")
    return redirect(url_for('web.lista_empresas'))


def negar_empresa(id):
    motivo = request.form.get('motivo', 'No especificado')
    Empresa.actualizar_con_notas(id, "negado", f"Negada: {motivo}")
    flash("Empresa denegada.", "info")
    return redirect(url_for('web.lista_empresas'))


def eliminar_empresa(id):
    try:
        Empresa.borrar(id)
        flash("Empresa eliminada exitosamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar: {e}", "danger")
    return redirect(url_for('web.lista_empresas'))


def buscar_y_guardar_impi(id):
    empresa = Empresa.obtener_por_id(id)
    if not empresa:
        flash("Empresa no encontrada", "danger")
        return redirect(url_for('web.lista_empresas'))
        
    nombre = empresa.get('nombre_comercial')
    
    try:
        with sync_playwright() as p:
            # Iniciamos el navegador
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            page = context.new_page()
            
            # Navegar al sitio esperando que cargue todo el contenido dinámico
            page.goto("https://acervomarcas.impi.gob.mx:8181/", wait_until="networkidle", timeout=60000)
            
            # Localizar el campo de texto (buscamos cualquier input de tipo texto)
            page.wait_for_selector('input[type="text"]', timeout=20000)
            page.fill('input[type="text"]', nombre)
            
            # Hacer clic en el botón buscar
            page.click('button:has-text("Buscar")')
            
            # Esperar a que la tabla aparezca
            page.wait_for_selector('table', timeout=30000)
            
            # Extraer filas de la tabla
            filas = page.query_selector_all('tbody tr')
            datos = []
            for f in filas:
                c = f.query_selector_all('td')
                if len(c) >= 7:
                    datos.append({
                        "solicitud": c[1].inner_text(),
                        "tipo": c[2].inner_text(),
                        "expediente": c[3].inner_text(),
                        "registro": c[4].inner_text(),
                        "denominacion": c[5].inner_text(),
                        "clase": c[6].inner_text()
                    })
            
            browser.close()
            # Guardamos resultados
            Empresa.actualizar_resultados_impi(id, datos)
            flash(f"Se extrajeron {len(datos)} registros de la marca '{nombre}'.", "success")
            
    except Exception as e:
        flash(f"Error técnico durante la extracción: {str(e)}", "danger")
    
    return redirect(url_for('web.lista_empresas'))


# ================================================================
# ====== FUNCIONES NUEVAS AGREGADAS ======
# ================================================================

def toggle_empresa(id):
    """Activar/Desactivar empresa (admin)"""
    if request.method == 'POST':
        db = current_app.db
        empresa = db.empresas.find_one({'_id': ObjectId(id)})
        if empresa:
            nuevo_estado = not empresa.get('activa', True)
            db.empresas.update_one(
                {'_id': ObjectId(id)},
                {'$set': {'activa': nuevo_estado, 'updated_at': datetime.utcnow()}}
            )
            flash(f'Empresa {"activada" if nuevo_estado else "desactivada"} correctamente', 'success')
        else:
            flash('Empresa no encontrada', 'danger')
    
    return redirect(url_for('web.lista_empresas'))


def obtener_empresas_activas():
    """Obtener empresas activas (API)"""
    db = current_app.db
    empresas = list(db.empresas.find({
        'activa': True,
        'status': 'activo'
    }).sort('nombre_comercial', 1))
    
    for e in empresas:
        e['_id'] = str(e['_id'])
    
    return jsonify({'success': True, 'empresas': empresas})


def api_empresas():
    """API para listar todas las empresas"""
    db = current_app.db
    empresas = list(db.empresas.find({}).sort('nombre_comercial', 1))
    
    for e in empresas:
        e['_id'] = str(e['_id'])
    
    return jsonify({'success': True, 'empresas': empresas})


def api_empresa(id):
    """API para obtener una empresa específica"""
    db = current_app.db
    empresa = db.empresas.find_one({'_id': ObjectId(id)})
    
    if not empresa:
        return jsonify({'success': False, 'message': 'Empresa no encontrada'}), 404
    
    empresa['_id'] = str(empresa['_id'])
    return jsonify({'success': True, 'empresa': empresa})


def buscar_empresas():
    """Buscar empresas por nombre (API)"""
    db = current_app.db
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'success': True, 'empresas': []})
    
    empresas = list(db.empresas.find({
        'nombre_comercial': {'$regex': query, '$options': 'i'},
        'activa': True,
        'status': 'activo'
    }).limit(10))
    
    for e in empresas:
        e['_id'] = str(e['_id'])
    
    return jsonify({'success': True, 'empresas': empresas})


def obtener_empresa_por_rfc():
    """Obtener empresa por RFC (API)"""
    db = current_app.db
    rfc = request.args.get('rfc', '').upper().strip()
    
    if not rfc:
        return jsonify({'success': False, 'message': 'RFC requerido'}), 400
    
    empresa = db.empresas.find_one({'rfc': rfc})
    
    if not empresa:
        return jsonify({'success': False, 'message': 'Empresa no encontrada'}), 404
    
    empresa['_id'] = str(empresa['_id'])
    return jsonify({'success': True, 'empresa': empresa})


def actualizar_datos_impi(id):
    """Actualizar manualmente los datos IMPI de una empresa (admin)"""
    if request.method == 'POST':
        db = current_app.db
        datos_impi = request.get_json() or {}
        
        if not datos_impi:
            flash('No se enviaron datos', 'danger')
            return redirect(url_for('web.lista_empresas'))
        
        db.empresas.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'datos_impi': datos_impi,
                'updated_at': datetime.utcnow()
            }}
        )
        flash('Datos IMPI actualizados correctamente', 'success')
    
    return redirect(url_for('web.lista_empresas'))


def limpiar_datos_impi(id):
    """Limpiar los datos IMPI de una empresa (admin)"""
    if request.method == 'POST':
        db = current_app.db
        db.empresas.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'datos_impi': [],
                'updated_at': datetime.utcnow()
            }}
        )
        flash('Datos IMPI limpiados correctamente', 'success')
    
    return redirect(url_for('web.lista_empresas'))


def estadisticas_empresas():
    """Obtener estadísticas de empresas (API)"""
    db = current_app.db
    
    total = db.empresas.count_documents({})
    activas = db.empresas.count_documents({'status': 'activo'})
    pendientes = db.empresas.count_documents({'status': 'pendiente'})
    negadas = db.empresas.count_documents({'status': 'negado'})
    
    return jsonify({
        'success': True,
        'estadisticas': {
            'total': total,
            'activas': activas,
            'pendientes': pendientes,
            'negadas': negadas
        }
    })