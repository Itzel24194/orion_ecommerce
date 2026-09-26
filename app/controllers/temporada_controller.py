from flask import render_template, request, redirect, url_for, flash
from app.models.temporada_model import Temporada
from datetime import datetime

def listar_temporadas():
    temporadas = Temporada.obtener_todas()
    from app.models.productos_model import Producto
    productos_por_temporada = {}
    for temp in temporadas:
        count = len(Producto.obtener_por_temporada(str(temp['_id'])))
        productos_por_temporada[str(temp['_id'])] = count
    return render_template('admin/temporadas.html', 
                         temporadas=temporadas,
                         productos_por_temporada=productos_por_temporada)

def crear_temporada():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        activa = request.form.get('activa') == 'on'

        if not nombre or not fecha_inicio or not fecha_fin:
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        except ValueError:
            flash('Formato de fecha inválido', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        if fecha_inicio_dt > fecha_fin_dt:
            flash('La fecha de inicio no puede ser mayor que la fecha de fin', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        data = {
            'nombre': nombre,
            'fecha_inicio': fecha_inicio_dt,
            'fecha_fin': fecha_fin_dt,
            'activa': activa
        }
        Temporada.crear(data)
        flash('Temporada creada exitosamente', 'success')
        return redirect(url_for('web.listar_temporadas'))
    
    return redirect(url_for('web.listar_temporadas'))

def editar_temporada(id):
    if request.method == 'POST':
        temporada = Temporada.obtener_por_id(id)
        if not temporada:
            flash('Temporada no encontrada', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        nombre = request.form.get('nombre', '').strip()
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        activa = request.form.get('activa') == 'on'

        if not nombre or not fecha_inicio or not fecha_fin:
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        except ValueError:
            flash('Formato de fecha inválido', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        if fecha_inicio_dt > fecha_fin_dt:
            flash('La fecha de inicio no puede ser mayor que la fecha de fin', 'danger')
            return redirect(url_for('web.listar_temporadas'))

        data = {
            'nombre': nombre,
            'fecha_inicio': fecha_inicio_dt,
            'fecha_fin': fecha_fin_dt,
            'activa': activa
        }
        Temporada.actualizar(id, data)
        flash('Temporada actualizada exitosamente', 'success')
        return redirect(url_for('web.listar_temporadas'))
    
    return redirect(url_for('web.listar_temporadas'))

def eliminar_temporada(id):
    from app.models.productos_model import Producto
    productos = Producto.obtener_por_temporada(id)
    if productos and len(productos) > 0:
        flash(f'No se puede eliminar la temporada porque tiene {len(productos)} productos asociados.', 'danger')
        return redirect(url_for('web.listar_temporadas'))

    if Temporada.eliminar(id):
        flash('Temporada eliminada correctamente', 'success')
    else:
        flash('Error al eliminar la temporada', 'danger')
    return redirect(url_for('web.listar_temporadas'))