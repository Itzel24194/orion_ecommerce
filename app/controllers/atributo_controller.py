# ================================================================
# app/controllers/atributo_controller.py - CONTROLADOR DE ATRIBUTOS COMPLETO
# ================================================================

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from app.models.atributos_model import Atributo as AtributoModel
from app.models.categorias_model import Categoria as CategoriaModel
from bson import ObjectId
from datetime import datetime


def listar_atributos():
    atributos = AtributoModel.obtener_todos()
    return render_template('admin/atributos.html', atributos=atributos)


def agregar():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        valores = request.form.get('valores', '')
        
        if not nombre:
            flash('El nombre del atributo es requerido', 'danger')
            return redirect(url_for('web.lista_atributos'))
        
        # Convertir valores a lista si vienen separados por comas
        lista_valores = []
        if valores:
            lista_valores = [v.strip() for v in valores.split(',') if v.strip()]
        
        data = {
            "nombre": nombre.strip(),
            "valores": lista_valores,
            "activo": True,
            "created_at": datetime.utcnow()
        }
        
        AtributoModel.crear(data)
        flash('Atributo agregado exitosamente', 'success')
    
    return redirect(url_for('web.lista_atributos'))


def editar(id):
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        valores = request.form.get('valores', '')
        
        if not nombre:
            flash('El nombre del atributo es requerido', 'danger')
            return redirect(url_for('web.lista_atributos'))
        
        # Convertir valores a lista si vienen separados por comas
        lista_valores = []
        if valores:
            lista_valores = [v.strip() for v in valores.split(',') if v.strip()]
        
        data = {
            "nombre": nombre.strip(),
            "valores": lista_valores,
            "updated_at": datetime.utcnow()
        }
        
        AtributoModel.actualizar(id, data)
        flash('Atributo actualizado exitosamente', 'success')
    
    return redirect(url_for('web.lista_atributos'))


def borrar(id):
    try:
        # Verificar si el atributo está siendo usado por alguna categoría
        db = current_app.db
        usado = db.categorias_atributos.find_one({'atributo_id': ObjectId(id)})
        
        if usado:
            flash('No se puede eliminar el atributo porque está asignado a una categoría', 'danger')
            return redirect(url_for('web.lista_atributos'))
        
        AtributoModel.borrar(id)
        flash('Atributo eliminado exitosamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')
    
    return redirect(url_for('web.lista_atributos'))


# ================================================================
# ====== FUNCIONES NUEVAS AGREGADAS ======
# ================================================================

def asignar_atributos_categoria(categoria_id):
    """Asignar atributos a una categoría (admin)"""
    db = current_app.db
    
    if request.method == 'POST':
        # Obtener atributos seleccionados
        atributos_seleccionados = request.form.getlist('atributos[]')
        
        # Eliminar asignaciones existentes
        db.categorias_atributos.delete_many({'categoria_id': ObjectId(categoria_id)})
        
        # Crear nuevas asignaciones
        for atributo_id in atributos_seleccionados:
            if atributo_id:
                db.categorias_atributos.insert_one({
                    'categoria_id': ObjectId(categoria_id),
                    'atributo_id': ObjectId(atributo_id),
                    'created_at': datetime.utcnow()
                })
        
        flash('Atributos asignados correctamente', 'success')
        return redirect(url_for('web.lista_categorias'))
    
    # GET - Mostrar formulario
    categoria = CategoriaModel.obtener_por_id(categoria_id)
    if not categoria:
        flash('Categoría no encontrada', 'danger')
        return redirect(url_for('web.lista_categorias'))
    
    # Obtener todos los atributos
    atributos = list(AtributoModel.obtener_todos())
    
    # Obtener atributos ya asignados a esta categoría
    asignados = list(db.categorias_atributos.find({'categoria_id': ObjectId(categoria_id)}))
    ids_asignados = [str(a.get('atributo_id')) for a in asignados]
    
    # Marcar atributos como seleccionados
    for attr in atributos:
        attr['seleccionado'] = str(attr['_id']) in ids_asignados
    
    return render_template('admin/asignar_atributos.html', 
                         categoria=categoria,
                         atributos=atributos,
                         ids_asignados=ids_asignados)


def obtener_atributos_por_categoria(categoria_id):
    """Obtener atributos de una categoría (API)"""
    db = current_app.db
    
    # Obtener asignaciones
    asignaciones = list(db.categorias_atributos.find({'categoria_id': ObjectId(categoria_id)}))
    ids_atributos = [a.get('atributo_id') for a in asignaciones]
    
    # Obtener atributos
    atributos = []
    for attr_id in ids_atributos:
        atributo = AtributoModel.obtener_por_id(str(attr_id))
        if atributo:
            atributo['_id'] = str(atributo['_id'])
            atributos.append(atributo)
    
    return jsonify({'success': True, 'atributos': atributos})


def ver_atributo(id):
    """Ver detalle de un atributo específico"""
    atributos = list(AtributoModel.obtener_todos())
    atributo_seleccionado = AtributoModel.obtener_por_id(id)
    
    if not atributo_seleccionado:
        flash('Atributo no encontrado', 'danger')
        return redirect(url_for('web.lista_atributos'))
    
    return render_template('admin/atributos.html', 
                         atributos=atributos,
                         atributo_seleccionado=atributo_seleccionado)


def toggle_atributo(id):
    """Activar/Desactivar atributo (admin)"""
    if request.method == 'POST':
        db = current_app.db
        atributo = db.atributos.find_one({'_id': ObjectId(id)})
        if atributo:
            nuevo_estado = not atributo.get('activo', True)
            db.atributos.update_one(
                {'_id': ObjectId(id)},
                {'$set': {'activo': nuevo_estado, 'updated_at': datetime.utcnow()}}
            )
            flash(f'Atributo {"activado" if nuevo_estado else "desactivado"} correctamente', 'success')
        else:
            flash('Atributo no encontrado', 'danger')
    
    return redirect(url_for('web.lista_atributos'))


def api_atributos():
    """API para listar atributos"""
    db = current_app.db
    atributos = list(db.atributos.find({'activo': True}))
    
    for a in atributos:
        a['_id'] = str(a['_id'])
    
    return jsonify({'success': True, 'atributos': atributos})


def api_atributo(id):
    """API para obtener un atributo específico"""
    db = current_app.db
    atributo = db.atributos.find_one({'_id': ObjectId(id)})
    
    if not atributo:
        return jsonify({'success': False, 'message': 'Atributo no encontrado'}), 404
    
    atributo['_id'] = str(atributo['_id'])
    return jsonify({'success': True, 'atributo': atributo})


def desasignar_atributo_categoria(categoria_id, atributo_id):
    """Desasignar un atributo de una categoría (admin)"""
    if request.method == 'POST':
        db = current_app.db
        db.categorias_atributos.delete_one({
            'categoria_id': ObjectId(categoria_id),
            'atributo_id': ObjectId(atributo_id)
        })
        flash('Atributo desasignado correctamente', 'success')
    
    return redirect(url_for('web.asignar_atributos_categoria', categoria_id=categoria_id))


def obtener_atributos_disponibles(categoria_id):
    """Obtener atributos disponibles para asignar a una categoría (API)"""
    db = current_app.db
    
    # Obtener atributos ya asignados
    asignados = list(db.categorias_atributos.find({'categoria_id': ObjectId(categoria_id)}))
    ids_asignados = [a.get('atributo_id') for a in asignados]
    
    # Obtener atributos no asignados
    atributos = list(db.atributos.find({
        '_id': {'$nin': ids_asignados},
        'activo': True
    }))
    
    for a in atributos:
        a['_id'] = str(a['_id'])
    
    return jsonify({'success': True, 'atributos': atributos})


def verificar_atributo_en_uso(id):
    """Verificar si un atributo está siendo usado (API)"""
    db = current_app.db
    usado = db.categorias_atributos.find_one({'atributo_id': ObjectId(id)})
    
    return jsonify({
        'success': True,
        'en_uso': usado is not None,
        'categoria_id': str(usado.get('categoria_id')) if usado else None
    })