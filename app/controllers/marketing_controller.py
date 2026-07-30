# ================================================================
# app/controllers/marketing_controller.py - CONTROLADOR DE MARKETING COMPLETO
# ================================================================

from flask import render_template, request, redirect, jsonify, flash, current_app
from app.models.marketing_model import Marketing
from datetime import datetime
from bson import ObjectId


class MarketingController:
    
    # ================================================================
    # MÉTODOS PARA LA TIENDA (PÚBLICOS)
    # ================================================================
    
    def obtener_banners_publicos(self):
        """Retorna solo los banners activos para mostrar en la web principal."""
        todos = Marketing.obtener_todo('banners')
        # Filtramos los que tengan el campo 'activo' en True
        return [b for b in todos if b.get('activo') == True]

    def obtener_cupones_publicos(self):
        """Retorna solo los cupones activos para mostrar en la web principal."""
        todos = Marketing.obtener_todo('cupones')
        return [c for c in todos if c.get('activo') == True]


    # ================================================================
    # MÉTODOS PARA BANNERS (ADMIN)
    # ================================================================
    
    def listar_banners(self):
        """Lista todos los banners y cupones"""
        return render_template('admin/marketing.html', 
                               banners=Marketing.obtener_todo('banners'), 
                               cupones=Marketing.obtener_todo('cupones'))

    def agregar_banner(self):
        """Agrega un nuevo banner"""
        if request.method == 'POST':
            data = request.form.to_dict()
            data['activo'] = True
            data['tipo_plantilla'] = data.get('tipo_plantilla', 'full-width')
            data['created_at'] = datetime.utcnow()
            Marketing.guardar('banners', data)
            flash('Banner agregado exitosamente', 'success')
        return redirect('/admin/marketing/banners')

    def editar_banner(self, id):
        """Edita un banner existente"""
        if request.method == 'POST':
            data = request.form.to_dict()
            data['updated_at'] = datetime.utcnow()
            Marketing.actualizar('banners', id, data)
            flash('Banner actualizado exitosamente', 'success')
        return redirect('/admin/marketing/banners')

    def eliminar_banner(self, id):
        """Elimina un banner"""
        Marketing.borrar('banners', id)
        flash('Banner eliminado exitosamente', 'success')
        return redirect('/admin/marketing/banners')

    def activar_banner(self, id):
        """Activa un banner"""
        Marketing.actualizar('banners', id, {"activo": True, "updated_at": datetime.utcnow()})
        flash('Banner activado', 'success')
        return redirect('/admin/marketing/banners')

    def toggle_banner(self, id):
        """Activa/Desactiva un banner (toggle)"""
        if request.method == 'POST':
            db = current_app.db
            banner = db.banners.find_one({'_id': ObjectId(id)})
            if banner:
                nuevo_estado = not banner.get('activo', True)
                db.banners.update_one(
                    {'_id': ObjectId(id)},
                    {'$set': {'activo': nuevo_estado, 'updated_at': datetime.utcnow()}}
                )
                flash(f'Banner {"activado" if nuevo_estado else "desactivado"} correctamente', 'success')
            else:
                flash('Banner no encontrado', 'danger')
        return redirect('/admin/marketing/banners')


    # ================================================================
    # MÉTODOS PARA CUPONES (ADMIN)
    # ================================================================
    
    def listar_cupones(self):
        """Lista todos los cupones y banners"""
        return render_template('admin/marketing.html', 
                               banners=Marketing.obtener_todo('banners'), 
                               cupones=Marketing.obtener_todo('cupones'))

    def agregar_cupon(self):
        """Agrega un nuevo cupón"""
        if request.method == 'POST':
            data = request.form.to_dict()
            try:
                data['descuento'] = float(data.get('descuento', 0))
                data['limite_usos'] = int(data.get('limite_usos', 100))
                data['prioridad'] = int(data.get('prioridad', 1))
            except (ValueError, TypeError):
                data['descuento'] = 0
            
            data['usos_actuales'] = 0
            data['activo'] = True
            data['created_at'] = datetime.utcnow()
            Marketing.guardar('cupones', data)
            flash('Cupón agregado exitosamente', 'success')
        return redirect('/admin/marketing/cupones')

    def editar_cupon(self, id):
        """Edita un cupón existente"""
        if request.method == 'POST':
            data = request.form.to_dict()
            try:
                data['descuento'] = float(data.get('descuento', 0))
                data['limite_usos'] = int(data.get('limite_usos', 100))
                data['prioridad'] = int(data.get('prioridad', 1))
            except (ValueError, TypeError):
                data['descuento'] = 0
            data['updated_at'] = datetime.utcnow()
            Marketing.actualizar('cupones', id, data)
            flash('Cupón actualizado exitosamente', 'success')
        return redirect('/admin/marketing/cupones')

    def toggle_cupon(self, id):
        """Activa/Desactiva un cupón (toggle)"""
        if request.method == 'POST':
            db = current_app.db
            cupon = db.cupones.find_one({'_id': ObjectId(id)})
            if cupon:
                nuevo_estado = not cupon.get('activo', True)
                db.cupones.update_one(
                    {'_id': ObjectId(id)},
                    {'$set': {'activo': nuevo_estado, 'updated_at': datetime.utcnow()}}
                )
                flash(f'Cupón {"activado" if nuevo_estado else "desactivado"} correctamente', 'success')
            else:
                flash('Cupón no encontrado', 'danger')
        return redirect('/admin/marketing/cupones')

    def validar_cupon(self):
        """Valida un cupón (API)"""
        codigo = request.form.get('codigo')
        cupom = Marketing.buscar_por_codigo(codigo)
        
        if not cupom:
            return jsonify({'valido': False, 'mensaje': 'Código inválido'})
        
        hoy = datetime.now().strftime('%Y-%m-%d')
        
        if cupom.get('fecha_inicio') and hoy < cupom.get('fecha_inicio'):
            return jsonify({'valido': False, 'mensaje': 'El cupón aún no está activo'})
        
        if cupom.get('fecha_fin') and hoy > cupom.get('fecha_fin'):
            return jsonify({'valido': False, 'mensaje': 'Cupón expirado'})
        
        if cupom.get('usos_actuales', 0) >= cupom.get('limite_usos', 100):
            return jsonify({'valido': False, 'mensaje': 'Cupón agotado'})

        return jsonify({'valido': True, 'descuento': cupom.get('descuento', 0)})

    def eliminar_cupon(self, id):
        """Elimina un cupón"""
        Marketing.borrar('cupones', id)
        flash('Cupón eliminado exitosamente', 'success')
        return redirect('/admin/marketing/cupones')


    # ================================================================
    # MÉTODOS PARA CAMPAÑAS DE EMAIL MARKETING
    # ================================================================
    
    def listar_campanas(self):
        """Lista todas las campañas de email"""
        db = current_app.db
        campanas = list(db.campanas_email.find({}).sort('created_at', -1))
        return render_template('admin/campanas.html', campanas=campanas)

    def agregar_campana(self):
        """Agrega una nueva campaña de email"""
        if request.method == 'POST':
            db = current_app.db
            data = {
                'nombre': request.form.get('nombre'),
                'asunto': request.form.get('asunto'),
                'contenido': request.form.get('contenido'),
                'estado': 'borrador',
                'created_at': datetime.utcnow()
            }
            db.campanas_email.insert_one(data)
            flash('Campaña creada exitosamente', 'success')
        return redirect('/admin/marketing/campanas')

    def editar_campana(self, id):
        """Edita una campaña de email existente"""
        if request.method == 'POST':
            db = current_app.db
            data = {
                'nombre': request.form.get('nombre'),
                'asunto': request.form.get('asunto'),
                'contenido': request.form.get('contenido'),
                'updated_at': datetime.utcnow()
            }
            db.campanas_email.update_one(
                {'_id': ObjectId(id)},
                {'$set': data}
            )
            flash('Campaña actualizada exitosamente', 'success')
        return redirect('/admin/marketing/campanas')

    def eliminar_campana(self, id):
        """Elimina una campaña de email"""
        db = current_app.db
        db.campanas_email.delete_one({'_id': ObjectId(id)})
        flash('Campaña eliminada exitosamente', 'success')
        return redirect('/admin/marketing/campanas')

    def enviar_campana(self, id):
        """Envía una campaña de email a todos los suscriptores"""
        if request.method == 'POST':
            db = current_app.db
            campana = db.campanas_email.find_one({'_id': ObjectId(id)})
            
            if not campana:
                flash('Campaña no encontrada', 'danger')
                return redirect('/admin/marketing/campanas')
            
            # Obtener suscriptores
            suscriptores = list(db.suscriptores.find({'activo': True}))
            
            # Aquí iría la lógica de envío de emails
            # Por ahora solo marcamos como enviada
            
            db.campanas_email.update_one(
                {'_id': ObjectId(id)},
                {'$set': {
                    'estado': 'enviada',
                    'fecha_envio': datetime.utcnow(),
                    'total_enviados': len(suscriptores)
                }}
            )
            flash(f'Campaña enviada a {len(suscriptores)} suscriptores', 'success')
        return redirect('/admin/marketing/campanas')


    # ================================================================
    # MÉTODOS PARA SUSCRIPTORES NEWSLETTER
    # ================================================================
    
    def listar_suscriptores(self):
        """Lista todos los suscriptores"""
        db = current_app.db
        suscriptores = list(db.suscriptores.find({}).sort('created_at', -1))
        return render_template('admin/suscriptores.html', suscriptores=suscriptores)

    def suscribir_newsletter(self):
        """Suscribe un email al newsletter (API)"""
        data = request.get_json() or {}
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email requerido'}), 400
        
        db = current_app.db
        existente = db.suscriptores.find_one({'email': email})
        
        if existente:
            if not existente.get('activo', True):
                db.suscriptores.update_one(
                    {'email': email},
                    {'$set': {'activo': True, 'updated_at': datetime.utcnow()}}
                )
                return jsonify({'success': True, 'message': 'Suscripción reactivada'})
            return jsonify({'success': False, 'message': 'Ya estás suscrito'}), 400
        
        db.suscriptores.insert_one({
            'email': email,
            'activo': True,
            'created_at': datetime.utcnow()
        })
        
        return jsonify({'success': True, 'message': 'Suscrito exitosamente'})

    def cancelar_newsletter(self):
        """Cancela la suscripción al newsletter (API)"""
        data = request.get_json() or {}
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email requerido'}), 400
        
        db = current_app.db
        db.suscriptores.update_one(
            {'email': email},
            {'$set': {'activo': False, 'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({'success': True, 'message': 'Suscripción cancelada'})

    def eliminar_suscriptor(self, id):
        """Elimina un suscriptor (admin)"""
        db = current_app.db
        db.suscriptores.delete_one({'_id': ObjectId(id)})
        flash('Suscriptor eliminado', 'success')
        return redirect('/admin/marketing/suscriptores')

    def exportar_suscriptores(self):
        """Exporta suscriptores a CSV (admin)"""
        db = current_app.db
        suscriptores = list(db.suscriptores.find({'activo': True}))
        
        import csv
        from io import StringIO
        from flask import Response
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Email', 'Fecha de suscripción'])
        
        for s in suscriptores:
            writer.writerow([
                s.get('email'),
                s.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M') if s.get('created_at') else ''
            ])
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=suscriptores.csv'
        return response