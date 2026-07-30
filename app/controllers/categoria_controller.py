# ================================================================
# app/controllers/categoria_controller.py - CONTROLADOR DE CATEGORÍAS COMPLETO
# ================================================================

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from app.models.categorias_model import Categoria as CategoriaModel
from bson import ObjectId
from datetime import datetime


def listar_categorias():
    """Lista todas las categorías con su nivel y jerarquía"""
    todas = list(CategoriaModel.obtener_todas())
    mapa = {str(c['_id']): c for c in todas}
    
    for c in todas:
        padre_id = c.get('padre_id')
        
        # Si padre_id es None, vacío o 'None' -> es raíz
        if not padre_id or str(padre_id) in ['None', 'null', '']:
            c['nivel'] = 1
            c['padre_nombre'] = "Raíz"
            c['padre_id_str'] = None
        else:
            padre_id_str = str(padre_id)
            padre = mapa.get(padre_id_str)
            if padre:
                abuelo_id = padre.get('padre_id')
                # Si el padre tiene un padre, es nivel 3, si no es nivel 2
                if abuelo_id and str(abuelo_id) not in ['None', 'null', '']:
                    c['nivel'] = 3
                else:
                    c['nivel'] = 2
                c['padre_nombre'] = padre.get('nombre', 'Desconocido')
                c['padre_id_str'] = padre_id_str
            else:
                # Caso de seguridad: si el padre ya no existe
                c['nivel'] = 1
                c['padre_nombre'] = "Raíz (Corregido)"
                c['padre_id_str'] = None
                
    return render_template('admin/categorias.html', categorias=todas)


def agregar():
    """Agrega una nueva categoría"""
    if request.method == 'POST':
        data = request.form.to_dict()
        data['activo'] = 'activo' in data
        
        # Normalización de ID de padre
        padre_id = data.get('padre_id')
        if not padre_id or str(padre_id) in ['', 'None', 'null']:
            data['padre_id'] = None
        else:
            try:
                data['padre_id'] = ObjectId(padre_id)
            except:
                data['padre_id'] = None
            
        # Validación: Evitar duplicados por nombre
        if CategoriaModel.buscar_por_nombre(data['nombre']):
            flash("Error: Ya existe una categoría con ese nombre.", "danger")
            return redirect(url_for('web.lista_categorias'))
            
        CategoriaModel.crear(data)
        flash("Categoría agregada exitosamente.", "success")
    return redirect(url_for('web.lista_categorias'))


def editar(id):
    """Edita una categoría existente"""
    if request.method == 'POST':
        data = request.form.to_dict()
        data['activo'] = 'activo' in data
        
        # Normalización
        padre_id = data.get('padre_id')
        if not padre_id or str(padre_id) in ['', 'None', 'null']:
            data['padre_id'] = None
        else:
            try:
                data['padre_id'] = ObjectId(padre_id)
            except:
                data['padre_id'] = None
            
        # Protección: Una categoría no puede ser padre de sí misma
        if str(id) == str(data.get('padre_id')):
            data['padre_id'] = None
            
        CategoriaModel.actualizar(id, data)
        flash("Categoría actualizada exitosamente.", "success")
    return redirect(url_for('web.lista_categorias'))


def borrar(id):
    """Borra una categoría"""
    try:
        # Verificar si tiene subcategorías
        subcategorias = CategoriaModel.obtener_hijos(id)
        if subcategorias and len(subcategorias) > 0:
            flash("No se puede eliminar la categoría porque tiene subcategorías.", "danger")
            return redirect(url_for('web.lista_categorias'))
        
        CategoriaModel.borrar(id)
        flash("Categoría eliminada exitosamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar: {e}", "danger")
    return redirect(url_for('web.lista_categorias'))


# ================================================================
# ====== FUNCIONES NUEVAS AGREGADAS ======
# ================================================================

def reordenar_categorias():
    """Reordenar categorías (admin)"""
    if request.method == 'POST':
        db = current_app.db
        orden = request.get_json() or {}
        
        for categoria_id, nuevo_orden in orden.items():
            if categoria_id and nuevo_orden is not None:
                db.categorias.update_one(
                    {'_id': ObjectId(categoria_id)},
                    {'$set': {'orden': int(nuevo_orden)}}
                )
        
        return jsonify({'success': True, 'message': 'Orden actualizado correctamente'})
    
    return jsonify({'success': False, 'message': 'Método no permitido'}), 405


def obtener_categorias():
    """Obtener todas las categorías (API)"""
    db = current_app.db
    categorias = list(db.categorias.find({}).sort('orden', 1))
    
    for c in categorias:
        c['_id'] = str(c['_id'])
        if c.get('padre_id'):
            c['padre_id'] = str(c['padre_id'])
    
    return jsonify({'success': True, 'categorias': categorias})


def obtener_categorias_raices():
    """Obtener categorías raíz (API)"""
    db = current_app.db
    categorias = list(db.categorias.find({
        'padre_id': None,
        'activa': True
    }).sort('orden', 1))
    
    for c in categorias:
        c['_id'] = str(c['_id'])
    
    return jsonify({'success': True, 'categorias': categorias})


def obtener_subcategorias(id):
    """Obtener subcategorías de una categoría (API)"""
    db = current_app.db
    categorias = list(db.categorias.find({
        'padre_id': ObjectId(id),
        'activa': True
    }).sort('orden', 1))
    
    for c in categorias:
        c['_id'] = str(c['_id'])
        c['padre_id'] = str(c['padre_id'])
    
    return jsonify({'success': True, 'categorias': categorias})


def activar_categoria(id):
    """Activar una categoría (admin)"""
    if request.method == 'POST':
        db = current_app.db
        db.categorias.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'activa': True, 'updated_at': datetime.utcnow()}}
        )
        flash('Categoría activada correctamente', 'success')
    
    return redirect(url_for('web.lista_categorias'))


def desactivar_categoria(id):
    """Desactivar una categoría (admin)"""
    if request.method == 'POST':
        db = current_app.db
        db.categorias.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'activa': False, 'updated_at': datetime.utcnow()}}
        )
        flash('Categoría desactivada correctamente', 'success')
    
    return redirect(url_for('web.lista_categorias'))


def api_categorias():
    """API para listar categorías"""
    db = current_app.db
    categorias = list(db.categorias.find({
        'activa': True
    }).sort('orden', 1))
    
    for c in categorias:
        c['_id'] = str(c['_id'])
        if c.get('padre_id'):
            c['padre_id'] = str(c['padre_id'])
    
    return jsonify({'success': True, 'categorias': categorias})


def obtener_jerarquia_categorias():
    """Obtener jerarquía completa de categorías (API)"""
    db = current_app.db
    categorias = list(db.categorias.find({'activa': True}).sort('orden', 1))
    
    # Construir árbol
    mapa = {str(c['_id']): c for c in categorias}
    arbol = []
    
    for c in categorias:
        c['_id'] = str(c['_id'])
        if c.get('padre_id'):
            c['padre_id'] = str(c['padre_id'])
            padre = mapa.get(c['padre_id'])
            if padre:
                if 'hijos' not in padre:
                    padre['hijos'] = []
                padre['hijos'].append(c)
            else:
                arbol.append(c)
        else:
            arbol.append(c)
    
    return jsonify({'success': True, 'categorias': arbol})


def ver_categoria(id):
    """Ver detalle de una categoría específica"""
    categorias = list(CategoriaModel.obtener_todas())
    categoria_seleccionada = CategoriaModel.obtener_por_id(id)
    
    if not categoria_seleccionada:
        flash('Categoría no encontrada', 'danger')
        return redirect(url_for('web.lista_categorias'))
    
    return render_template('admin/categorias.html', 
                         categorias=categorias, 
                         categoria_seleccionada=categoria_seleccionada)


def toggle_categoria(id):
    """Activar/Desactivar categoría (toggle)"""
    if request.method == 'POST':
        db = current_app.db
        categoria = db.categorias.find_one({'_id': ObjectId(id)})
        if categoria:
            nuevo_estado = not categoria.get('activa', True)
            db.categorias.update_one(
                {'_id': ObjectId(id)},
                {'$set': {'activa': nuevo_estado, 'updated_at': datetime.utcnow()}}
            )
            flash(f'Categoría {"activada" if nuevo_estado else "desactivada"} correctamente', 'success')
        else:
            flash('Categoría no encontrada', 'danger')
    
    return redirect(url_for('web.lista_categorias'))