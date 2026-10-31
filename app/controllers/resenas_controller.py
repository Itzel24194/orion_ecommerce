# app/controllers/resenas_controller.py
import os
import uuid
from flask import (
    request, jsonify, render_template, session, flash,
    redirect, url_for, current_app
)
from app.models.resenas_model import Resena
from app.models.productos_model import Producto
from app.models.usuarios_model import Usuario
from bson import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename

# ❌ NO importar el blueprint aquí. Las rutas se registran en app/routes/web.py


def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


def convertir_objectid(doc):
    if isinstance(doc, list):
        return [convertir_objectid(item) for item in doc]
    if isinstance(doc, dict):
        nuevo = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                nuevo[k] = str(v)
            elif isinstance(v, (list, dict)):
                nuevo[k] = convertir_objectid(v)
            else:
                nuevo[k] = v
        return nuevo
    return doc


def _es_admin():
    return normalizar_rol(session.get('rol')) == 'admin'


def _get_resena_folder():
    folder = os.path.join(current_app.root_path, 'static', 'uploads', 'resenas')
    os.makedirs(folder, exist_ok=True)
    return folder


def _guardar_fotos(archivos):
    folder = _get_resena_folder()
    nombres = []
    for archivo in archivos or []:
        if archivo and archivo.filename:
            nombre = f"resena_{uuid.uuid4().hex[:8]}_{secure_filename(archivo.filename)}"
            archivo.save(os.path.join(folder, nombre))
            nombres.append(nombre)
    return nombres


def _borrar_fotos(lista):
    folder = _get_resena_folder()
    for fname in lista or []:
        ruta = os.path.join(folder, fname)
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
            except Exception:
                pass


# ================================================================
# ADMIN
# ================================================================

def admin_resenas():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    if normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))
    return render_template('admin/resenas.html', usuario=usuario)


def api_resenas_listar():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    estado = request.args.get('estado')
    resenas = Resena.obtener_todas()
    if estado and estado != 'todos':
        resenas = [r for r in resenas if r.get('estado') == estado]
    for resena in resenas:
        resena['_id'] = str(resena['_id'])
        if 'producto_id' in resena:
            producto = Producto.obtener_por_id(resena['producto_id'])
            resena['producto_nombre'] = producto.get('nombre', 'Producto eliminado') if producto else 'Producto eliminado'
        if 'usuario_id' in resena:
            usuario = Usuario.obtener_por_id(resena['usuario_id'])
            resena['usuario_nombre'] = usuario.get('nombre', 'Usuario eliminado') if usuario else 'Usuario eliminado'
            resena['usuario_email'] = usuario.get('email', '') if usuario else ''
    resenas_convertidas = convertir_objectid(resenas)
    stats = Resena.contar_por_estado()
    return jsonify({'success': True, 'resenas': resenas_convertidas, 'stats': stats})


def api_resena_aprobar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    if not _es_admin():
        return jsonify({'error': 'No autorizado'}), 403
    try:
        resultado = Resena.actualizar_estado(id, 'aprobado')
        if resultado:
            return jsonify({'success': True, 'message': 'Reseña aprobada correctamente'})
        return jsonify({'error': 'No se pudo aprobar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_rechazar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    if not _es_admin():
        return jsonify({'error': 'No autorizado'}), 403
    try:
        resultado = Resena.actualizar_estado(id, 'rechazado')
        if resultado:
            return jsonify({'success': True, 'message': 'Reseña rechazada correctamente'})
        return jsonify({'error': 'No se pudo rechazar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_responder(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    if not _es_admin():
        return jsonify({'error': 'No autorizado'}), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Datos inválidos'}), 400
    respuesta = (data.get('respuesta') or '').strip()
    if not respuesta:
        return jsonify({'error': 'La respuesta es obligatoria'}), 400
    try:
        resultado = Resena.responder_admin(id, respuesta)
        if resultado:
            return jsonify({'success': True, 'message': 'Respuesta enviada correctamente'})
        return jsonify({'error': 'No se pudo enviar la respuesta'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_eliminar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    if not _es_admin():
        return jsonify({'error': 'No autorizado'}), 403
    try:
        resultado = Resena.eliminar(id, None)
        if resultado and getattr(resultado, 'deleted_count', 0) > 0:
            return jsonify({'success': True, 'message': 'Reseña eliminada correctamente'})
        return jsonify({'error': 'No se pudo eliminar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_obtener(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    resena = Resena.obtener_por_id(id)
    if not resena:
        return jsonify({'error': 'Reseña no encontrada'}), 404
    resena['_id'] = str(resena['_id'])
    if 'producto_id' in resena:
        producto = Producto.obtener_por_id(resena['producto_id'])
        resena['producto_nombre'] = producto.get('nombre', 'Producto eliminado') if producto else 'Producto eliminado'
    if 'usuario_id' in resena:
        usuario = Usuario.obtener_por_id(resena['usuario_id'])
        resena['usuario_nombre'] = usuario.get('nombre', 'Usuario eliminado') if usuario else 'Usuario eliminado'
        resena['usuario_email'] = usuario.get('email', '') if usuario else ''
    resena_convertida = convertir_objectid(resena)
    return jsonify({'success': True, 'resena': resena_convertida})


# ================================================================
# ⭐ PÚBLICOS
# ================================================================

def agregar_opinion():
    if 'user_id' not in session:
        flash("Debes iniciar sesión para opinar.", "warning")
        return redirect(url_for('web.login'))

    producto_id = request.form.get('producto_id')
    try:
        calificacion = int(request.form.get('calificacion', 0))
    except (ValueError, TypeError):
        calificacion = 0

    titulo     = (request.form.get('titulo') or '').strip()
    comentario = (request.form.get('comentario') or '').strip()

    if not producto_id or calificacion < 1 or calificacion > 5 or not titulo or not comentario:
        flash("Todos los campos son obligatorios y la calificación debe ser de 1 a 5.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    lista_archivos = _guardar_fotos(request.files.getlist('fotos'))

    compra_verificada = False
    try:
        db = current_app.db
        compra_verificada = db.ventas.find_one({
            'usuario_id': session.get('user_id'),
            'productos.id': producto_id
        }) is not None
    except Exception:
        pass

    data = {
        "producto_id":       producto_id,
        "usuario_id":        str(session.get('user_id')),
        "usuario_nombre":    session.get('nombre', 'Usuario'),
        "calificacion":      calificacion,
        "titulo":            titulo,
        "comentario":        comentario,
        "foto_path":         lista_archivos,
        "fecha":             datetime.now().strftime("%d/%m/%Y"),
        "compra_verificada": compra_verificada,
        "votos_utiles":      [],
        "reportes":          0,
        "estado":            "aprobado",
        "created_at":        datetime.utcnow(),
        "updated_at":        datetime.utcnow(),
    }

    try:
        Resena.crear(data)
        flash("¡Opinión publicada!", "success")
    except Exception as e:
        print(f"❌ Error creando opinión: {e}")
        flash("Error al publicar la opinión.", "danger")

    return redirect(url_for('web.ver_detalle_producto', id=producto_id) + '#opiniones')


def editar_opinion():
    """Edita una reseña. Solo el DUEÑO o un ADMIN pueden hacerlo."""
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for('web.login'))

    opinion_id  = request.form.get('opinion_id')
    producto_id = request.form.get('producto_id')

    print("\n" + "=" * 60)
    print(f"📝 EDITAR OPINIÓN")
    print(f"   opinion_id: {opinion_id}")
    print(f"   producto_id: {producto_id}")
    print(f"   user_id sesión: {session.get('user_id')}")
    print(f"   form: {dict(request.form)}")

    if not opinion_id:
        flash("Opinión no válida.", "danger")
        return redirect(url_for('web.catalogo'))

    db = current_app.db

    try:
        oid = ObjectId(opinion_id)
    except Exception as e:
        print(f"   ❌ opinion_id inválido: {e}")
        flash("Opinión no válida.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    try:
        opinion = db.resenas.find_one({'_id': oid})
    except Exception as e:
        print(f"   ❌ Error buscando opinión: {e}")
        opinion = None

    if not opinion:
        print(f"   ❌ Opinión NO encontrada en DB")
        flash("Opinión no encontrada.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    print(f"   ✅ Opinión encontrada")
    print(f"   usuario_id opinión: {opinion.get('usuario_id')!r} ({type(opinion.get('usuario_id')).__name__})")
    print(f"   calificación actual: {opinion.get('calificacion')}")
    print(f"   título actual: {opinion.get('titulo')!r}")

    # 🔒 VALIDACIÓN DE PROPIEDAD
    es_dueño = str(opinion.get('usuario_id')) == str(session['user_id'])
    es_admin = _es_admin()
    print(f"   ¿es dueño?: {es_dueño} | ¿es admin?: {es_admin}")

    if not (es_dueño or es_admin):
        flash("No tienes permiso para editar esta opinión.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    # 📥 VALORES DEL FORMULARIO
    try:
        calificacion = int(request.form.get('calificacion', 0))
    except (ValueError, TypeError):
        calificacion = int(opinion.get('calificacion', 5))

    titulo     = (request.form.get('titulo') or '').strip()
    comentario = (request.form.get('comentario') or '').strip()

    print(f"   📥 nuevos → calif: {calificacion}, título: {titulo!r}, comentario: {comentario[:60]!r}...")

    if calificacion < 1 or calificacion > 5 or not titulo or not comentario:
        print(f"   ❌ Validación falló")
        flash("Completa todos los campos correctamente.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id) + '#opiniones')

    # 📸 FOTOS
    fotos_actuales = list(opinion.get('foto_path') or [])
    fotos_a_eliminar = request.form.getlist('eliminar_foto')
    print(f"   📸 fotos actuales: {fotos_actuales}")
    print(f"   📸 fotos a eliminar: {fotos_a_eliminar}")

    for fname in fotos_a_eliminar:
        if fname in fotos_actuales:
            fotos_actuales.remove(fname)
            _borrar_fotos([fname])

    nuevas_fotos = _guardar_fotos(request.files.getlist('fotos'))
    print(f"   📸 fotos nuevas: {nuevas_fotos}")
    fotos_actuales.extend(nuevas_fotos)

    update_data = {
        "calificacion": calificacion,
        "titulo":       titulo,
        "comentario":   comentario,
        "foto_path":    fotos_actuales,
        "updated_at":   datetime.utcnow(),
    }

    print(f"   💾 update_data: {update_data}")

    # 💾 ACTUALIZAR DIRECTAMENTE EN MONGO
    try:
        resultado = db.resenas.update_one(
            {'_id': oid},
            {'$set': update_data}
        )
        print(f"   ✅ update_one → matched: {resultado.matched_count}, modified: {resultado.modified_count}")

        # Verificar
        verificacion = db.resenas.find_one({'_id': oid})
        print(f"   🔎 verificación:")
        print(f"      calificación: {verificacion.get('calificacion')}")
        print(f"      título: {verificacion.get('titulo')!r}")
        print(f"      comentario: {verificacion.get('comentario')[:60]!r}...")

        if resultado.modified_count > 0:
            flash("Opinión actualizada correctamente.", "success")
        else:
            print(f"   ⚠️ modified_count = 0 (posiblemente los datos son iguales)")
            flash("No se detectaron cambios.", "info")

    except Exception as e:
        print(f"   ❌ Error en update_one: {e}")
        import traceback
        traceback.print_exc()
        flash("No se pudo actualizar la opinión.", "danger")

    print("=" * 60 + "\n")
    return redirect(url_for('web.ver_detalle_producto', id=producto_id) + '#opiniones')


def eliminar_opinion():
    if 'user_id' not in session:
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for('web.login'))

    opinion_id  = request.form.get('opinion_id')
    producto_id = request.form.get('producto_id')

    db = current_app.db
    try:
        opinion = db.resenas.find_one({'_id': ObjectId(opinion_id)})
    except Exception:
        opinion = None

    if not opinion:
        flash("Opinión no encontrada.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    es_dueño = str(opinion.get('usuario_id')) == str(session['user_id'])
    es_admin = _es_admin()
    if not (es_dueño or es_admin):
        flash("No tienes permiso para eliminar esta opinión.", "danger")
        return redirect(url_for('web.ver_detalle_producto', id=producto_id))

    _borrar_fotos(opinion.get('foto_path'))

    try:
        db.resenas.delete_one({'_id': ObjectId(opinion_id)})
        flash("Opinión eliminada.", "success")
    except Exception as e:
        print(f"❌ Error eliminando opinión: {e}")
        flash("No se pudo eliminar la opinión.", "danger")

    return redirect(url_for('web.ver_detalle_producto', id=producto_id) + '#opiniones')


def marcar_util():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}
    opinion_id = data.get('opinion_id')
    if not opinion_id:
        return jsonify({'success': False, 'message': 'ID requerido'}), 400

    db = current_app.db
    try:
        opinion = db.resenas.find_one({'_id': ObjectId(opinion_id)})
    except Exception:
        opinion = None

    if not opinion:
        return jsonify({'success': False, 'message': 'Opinión no encontrada'}), 404

    usuario_id = str(session['user_id'])
    votos = [str(v) for v in (opinion.get('votos_utiles') or [])]

    if usuario_id in votos:
        votos.remove(usuario_id)
        voto = False
    else:
        votos.append(usuario_id)
        voto = True

    db.resenas.update_one(
        {'_id': ObjectId(opinion_id)},
        {'$set': {'votos_utiles': votos, 'updated_at': datetime.utcnow()}}
    )
    return jsonify({'success': True, 'voted': voto, 'total': len(votos)})


def reportar_opinion():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401

    data = request.get_json(silent=True) or {}
    opinion_id = data.get('opinion_id')
    if not opinion_id:
        return jsonify({'success': False, 'message': 'ID requerido'}), 400

    db = current_app.db
    try:
        db.resenas.update_one(
            {'_id': ObjectId(opinion_id)},
            {'$inc': {'reportes': 1}, '$set': {'updated_at': datetime.utcnow()}}
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500