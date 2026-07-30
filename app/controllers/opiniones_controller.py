from flask import request, redirect, url_for, session
from app.models.resenas_model import Resena

def enviar_opinion():
    if request.method == 'POST':
        data = {
            "producto_id": request.form.get('producto_id'),
            "usuario_id": session.get('user_id'),
            "calificacion": int(request.form.get('calificacion')),
            "titulo": request.form.get('titulo'),
            "comentario": request.form.get('comentario'),
            "foto": None,
        }
        Resena.crear(data)
        return redirect(url_for('web.ver_detalle_producto', id=data['producto_id']))
    
    # Si es GET, muestra el formulario o redirige
    return redirect(url_for('web.index'))

def editar_opinion(opinion_id):
    # Lógica para editar opinión
    pass

def eliminar_opinion(opinion_id):
    # Lógica para eliminar opinión
    from flask import session
    Resena.eliminar(opinion_id, session.get('user_id'))
    return redirect(url_for('web.ver_detalle_producto', id=request.args.get('producto_id')))