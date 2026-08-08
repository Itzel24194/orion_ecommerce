from flask import Blueprint, render_template, current_app, session, redirect, url_for, flash
import app.controllers.user_controller as uc 
import app.controllers.auth_controller as ac
import app.controllers.categoria_controller as cc
import app.controllers.atributo_controller as atrc
import app.controllers.producto_controller as pc
import app.controllers.empresa_controller as ec
import app.controllers.ventas_controller as vc
from app.controllers.marketing_controller import MarketingController
import app.controllers.carrito_controller as carrito_c
import app.controllers.pedido_controller as pedido_c
from app.decorators import login_required, admin_required, cliente_required
import app.controllers.cupon_controller as cupon_controller
import app.controllers.ml_controller as ml_controller  
import app.controllers.promociones_controller as promo_c 
import app.controllers.clasificacion_controller as clasificacion_c
import app.controllers.combo_controller as combo_c

mc = MarketingController()
web = Blueprint('web', __name__)

# ================================================================
# 1. RUTA PRINCIPAL (PÚBLICA - CON REDIRECCIÓN PARA ADMIN)
# ================================================================
@web.route('/')
def raiz_tienda():
    if session.get('rol') == 'admin':
        flash('Los administradores no pueden acceder a la tienda.', 'warning')
        return redirect(url_for('web.dashboard'))

    db = current_app.db
    categorias = list(db.categorias.find({}))
    productos = list(db.productos.find({}).limit(8))

    sugerencias = []
    promociones_home = []

    if session.get('user_id') and session.get('rol') != 'admin':
        sugerencias = list(db.productos.find({}).limit(4))
        promociones_home = promo_c.obtener_promociones_destacadas(session.get('user_id'))

    return render_template('tienda/pagina.html',
                         categorias=categorias,
                         productos=productos,
                         sugerencias=sugerencias,
                         promociones_home=promociones_home)
                    
@web.route('/servicios')
def servicios():
    """Página de servicios exclusivos de ORION"""
    db = current_app.db
    categorias = list(db.categorias.find({}))
    return render_template('tienda/servicios.html', categorias=categorias)

# ================================================================
# 2. CATÁLOGO Y PRODUCTOS (PÚBLICOS)
# ================================================================
@web.route('/catalogo')
def catalogo():
    return pc.catalogo()

@web.route('/producto/<id>')
def ver_detalle_producto(id):
    return pc.ver_detalle_producto(id)

@web.route('/productos/marca/<marca>')
def productos_por_marca(marca):
    return pc.listar_por_marca(marca)

@web.route('/api/productos/relacionados/<id>')
def productos_relacionados(id):
    return pc.productos_relacionados(id)

@web.route('/api/productos/mas-vendidos')
def productos_mas_vendidos():
    return pc.productos_mas_vendidos()

@web.route('/api/productos/categoria/<categoria_id>')
def productos_por_categoria_api(categoria_id):
    return pc.productos_por_categoria_api(categoria_id)

@web.route('/api/productos/buscar')
def buscar_productos():
    return pc.buscar_productos()

# ================================================================
# 3. CARRITO (SOLO CLIENTES)
# ================================================================
@web.route('/carrito', methods=['GET', 'POST'])
@cliente_required
def ver_carrito():
    return pedido_c.carrito_checkout()

@web.route('/carrito/agregar', methods=['POST'])
@cliente_required
def agregar_al_carrito():
    return carrito_c.agregar_al_carrito()

@web.route('/carrito/eliminar/<id>', methods=['GET', 'DELETE'])
@cliente_required
def eliminar_del_carrito(id):
    return carrito_c.eliminar_del_carrito(id)

@web.route('/carrito/actualizar/<id>', methods=['POST', 'PUT'])
@cliente_required
def actualizar_carrito(id):
    return carrito_c.actualizar_cantidad_carrito(id)

@web.route('/carrito/vaciar', methods=['DELETE'])
@cliente_required
def vaciar_carrito():
    return carrito_c.vaciar_carrito()

@web.route('/carrito/procesar_pago', methods=['GET'])
@cliente_required
def procesar_pago():
    return carrito_c.procesar_pago()

@web.route('/carrito/factura', methods=['GET'])
@cliente_required
def descargar_factura():
    return carrito_c.descargar_factura()

# ================================================================
# 4. PEDIDOS
# ================================================================
@web.route('/procesar-checkout', methods=['POST'])
@cliente_required
def procesar_checkout():
    return pedido_c.procesar_checkout()

@web.route('/mis-pedidos')
@cliente_required
def mis_pedidos_clientes():
    return pedido_c.mis_pedidos_clientes()

@web.route('/pedido/<id>')
@cliente_required
def ver_pedido(id):
    return pedido_c.ver_pedido(id)

@web.route('/api/pedido/cancelar/<id>', methods=['POST'])
@cliente_required
def cancelar_pedido(id):
    return pedido_c.cancelar_pedido(id)

@web.route('/api/pedido/recoger/<id>', methods=['POST'])
@cliente_required
def generar_codigo_recogida(id):
    return pedido_c.generar_codigo_recogida_api(id)

@web.route('/api/pedido/confirmar/<id>', methods=['POST'])
@cliente_required
def confirmar_pedido(id):
    return pedido_c.confirmar_pedido(id)

@web.route('/rastrear-pedido', methods=['GET', 'POST'])
def rastrear_pedido():
    return pedido_c.rastrear_pedido()

@web.route('/admin/pedidos')
@admin_required
def admin_listar_pedidos():
    return pedido_c.admin_listar_pedidos()

@web.route('/admin/pedidos/ver/<id>')
@admin_required
def admin_ver_pedido(id):
    return pedido_c.admin_ver_pedido(id)

@web.route('/api/admin/pedidos/estado/<id>', methods=['POST'])
@admin_required
def admin_actualizar_estado_pedido(id):
    return pedido_c.admin_actualizar_estado_pedido(id)

@web.route('/api/admin/pedidos/eliminar/<id>', methods=['DELETE'])
@admin_required
def admin_eliminar_pedido(id):
    return pedido_c.admin_eliminar_pedido(id)

# ================================================================
# 5. AUTENTICACIÓN Y USUARIO
# ================================================================
@web.route('/login', methods=['GET', 'POST'])
def login():
    return ac.login()

@web.route('/register', methods=['GET', 'POST'])
def register():
    return ac.register()

@web.route('/register-profile', methods=['GET', 'POST'])
def register_profile():
    return ac.register_profile()

@web.route('/recuperar-password', methods=['GET', 'POST'])
def recuperar_password():
    return ac.recuperar_password()

@web.route('/confirmar/<token>')
def confirmar_email(token):
    return ac.confirmar_email(token)

# ===== ✅ RUTA CORREGIDA: ahora apunta a `ac.reenviar_confirmacion` =====
@web.route('/reenviar-confirmacion', methods=['POST'])
def reenviar_confirmacion():
    return ac.reenviar_confirmacion()  # ← Cambiado de uc a ac

@web.route('/resetear-password/<token>', methods=['GET', 'POST'])
def resetear_password(token):
    return ac.resetear_password(token)

@web.route('/logout', methods=['GET'])
@login_required
def logout():
    return ac.logout()

@web.route('/perfil', methods=['GET'])
@cliente_required
def perfil():
    return ac.ver_perfil()

@web.route('/perfil/actualizar', methods=['POST'])
@cliente_required
def actualizar():
    return uc.actualizar_perfil()

@web.route('/perfil/cambiar-password', methods=['POST'])
@cliente_required
def cambiar_password():
    return ac.cambiar_password()

# ---- FAVORITOS ----
@web.route('/favoritos', methods=['GET'])
@cliente_required
def lista_favoritos():
    return uc.lista_favoritos()

@web.route('/api/favoritos/agregar/<producto_id>', methods=['POST'])
@cliente_required
def agregar_favorito(producto_id):
    return uc.agregar_favorito(producto_id)

@web.route('/api/favoritos/eliminar/<producto_id>', methods=['DELETE'])
@cliente_required
def eliminar_favorito(producto_id):
    return uc.eliminar_favorito(producto_id)

# ---- OPINIONES ----
@web.route('/opinion/agregar', methods=['POST'])
@cliente_required
def agregar_opinion():
    return pc.enviar_opinion()

@web.route('/opinion/editar', methods=['POST'])
@cliente_required
def editar_opinion():
    return uc.editar_opinion()

@web.route('/opinion/eliminar', methods=['POST'])
@cliente_required
def eliminar_opinion():
    return uc.eliminar_opinion()

@web.route('/opinion/util', methods=['POST'])
@cliente_required
def marcar_util():
    return uc.marcar_util()

@web.route('/opinion/reportar', methods=['POST'])
@cliente_required
def reportar_opinion():
    return uc.reportar_opinion()

# ================================================================
# 6. ADMIN - USUARIOS
# ================================================================
@web.route('/admin/usuarios', methods=['GET'])
@admin_required
def lista_usuarios():
    return uc.lista_usuarios()

@web.route('/admin/usuarios/ver/<id>', methods=['GET'])
@admin_required
def ver_usuario(id):
    return uc.ver_usuario(id)

@web.route('/admin/usuarios/agregar', methods=['POST'])
@admin_required
def agregar_usuario():
    return uc.agregar_usuario()

@web.route('/admin/usuarios/editar/<id>', methods=['POST'])
@admin_required
def editar_usuario(id):
    return uc.editar_usuario(id)

@web.route('/admin/usuarios/borrar/<id>', methods=['GET', 'POST'])
@admin_required
def borrar_usuario(id):
    return uc.borrar_usuario(id)

# ---- DIRECCIONES ----
@web.route('/admin/usuarios/direccion/agregar/<usuario_id>', methods=['POST'])
@admin_required
def agregar_direccion(usuario_id):
    return uc.agregar_direccion(usuario_id)

@web.route('/admin/usuarios/direccion/editar/<usuario_id>/<direccion_id>', methods=['POST'])
@admin_required
def editar_direccion(usuario_id, direccion_id):
    return uc.editar_direccion(usuario_id, direccion_id)

@web.route('/admin/usuarios/direccion/predeterminada/<usuario_id>/<direccion_id>', methods=['POST'])
@admin_required
def establecer_predeterminada(usuario_id, direccion_id):
    return uc.establecer_predeterminada(usuario_id, direccion_id)

@web.route('/admin/usuarios/direccion/borrar/<usuario_id>/<direccion_id>', methods=['GET', 'POST'])
@admin_required
def borrar_direccion(usuario_id, direccion_id):
    return uc.borrar_direccion(usuario_id, direccion_id)

@web.route('/api/admin/usuarios/<usuario_id>/direcciones', methods=['GET'])
@admin_required
def obtener_direcciones_usuario(usuario_id):
    return uc.obtener_direcciones_usuario(usuario_id)

@web.route('/api/admin/usuarios/<usuario_id>/direccion/predeterminada', methods=['GET'])
@admin_required
def obtener_direccion_predeterminada(usuario_id):
    return uc.obtener_direccion_predeterminada(usuario_id)

# ---- API ADMIN USUARIOS ----
@web.route('/api/admin/usuarios/editar/<id>', methods=['POST', 'PUT'])
@admin_required
def editar_usuario_admin(id):
    return uc.editar_usuario_admin(id)

@web.route('/api/admin/usuarios/eliminar/<id>', methods=['DELETE'])
@admin_required
def eliminar_usuario_admin(id):
    return uc.eliminar_usuario_admin(id)

@web.route('/api/admin/usuarios/toggle/<id>', methods=['POST'])
@admin_required
def toggle_usuario(id):
    return uc.toggle_usuario(id)

@web.route('/api/admin/usuarios/rol/<id>', methods=['POST'])
@admin_required
def asignar_rol(id):
    return uc.asignar_rol(id)

# ================================================================
# 7. ADMIN - PRODUCTOS
# ================================================================
@web.route('/admin/productos', methods=['GET'])
@admin_required
def lista_productos():
    return pc.listar_productos()

@web.route('/admin/productos/ver/<id>', methods=['GET'])
@admin_required
def ver_producto(id):
    return pc.ver_producto(id)

@web.route('/admin/productos/agregar', methods=['GET', 'POST'])
@admin_required
def agregar_producto():
    return pc.agregar()

@web.route('/admin/productos/editar/<id>', methods=['GET', 'POST'])
@admin_required
def editar_producto(id):
    return pc.editar(id)

@web.route('/admin/productos/baja/<id>', methods=['POST'])
@admin_required
def baja_producto(id):
    return pc.dar_de_baja(id)

@web.route('/admin/productos/borrar/<id>', methods=['POST'])
@admin_required
def borrar_producto(id):
    return pc.borrar(id)

@web.route('/admin/productos/subir-imagen/<id>', methods=['POST'])
@admin_required
def subir_imagen_producto(id):
    return pc.subir_imagen_producto(id)

@web.route('/admin/productos/eliminar-imagen/<id>/<int:index>', methods=['DELETE'])
@admin_required
def eliminar_imagen_producto(id, index):
    return pc.eliminar_imagen_producto(id, index)

@web.route('/admin/productos/exportar', methods=['GET'])
@admin_required
def exportar_productos():
    return pc.exportar_productos()

# ================================================================
# 8. ADMIN - CATEGORÍAS
# ================================================================
@web.route('/admin/categorias', methods=['GET'])
@admin_required
def lista_categorias():
    return cc.listar_categorias()

@web.route('/admin/categorias/agregar', methods=['POST'])
@admin_required
def agregar_categoria():
    return cc.agregar()

@web.route('/admin/categorias/editar/<id>', methods=['POST'])
@admin_required
def editar_categoria(id):
    return cc.editar(id)

@web.route('/admin/categorias/borrar/<id>', methods=['POST'])
@admin_required
def borrar_categoria(id):
    return cc.borrar(id)

@web.route('/admin/categorias/reordenar', methods=['POST'])
@admin_required
def reordenar_categorias():
    return cc.reordenar_categorias()

# ================================================================
# 9. ADMIN - ATRIBUTOS
# ================================================================
@web.route('/admin/atributos', methods=['GET'])
@admin_required
def lista_atributos():
    return atrc.listar_atributos()

@web.route('/admin/atributos/agregar', methods=['POST'])
@admin_required
def agregar_atributo():
    return atrc.agregar()

@web.route('/admin/atributos/editar/<id>', methods=['POST'])
@admin_required
def editar_atributo(id):
    return atrc.editar(id)

@web.route('/admin/atributos/borrar/<id>', methods=['GET', 'POST'])
@admin_required
def borrar_atributo(id):
    return atrc.borrar(id)

@web.route('/admin/categorias/atributos/<categoria_id>', methods=['GET', 'POST'])
@admin_required
def asignar_atributos_categoria(categoria_id):
    return atrc.asignar_atributos_categoria(categoria_id)

# ================================================================
# 10. ADMIN - EMPRESAS
# ================================================================
@web.route('/admin/empresas', methods=['GET'])
@admin_required
def lista_empresas():
    return ec.listar_empresas()

@web.route('/admin/empresas/agregar', methods=['POST'])
@admin_required
def agregar_empresa():
    return ec.agregar_empresa()

@web.route('/admin/empresas/editar/<id>', methods=['POST'])
@admin_required
def editar_empresa(id):
    return ec.editar_empresa(id)

@web.route('/admin/empresas/aprobar/<id>', methods=['POST'])
@admin_required
def aprobar_empresa(id):
    return ec.aprobar_empresa(id)

@web.route('/admin/empresas/negar/<id>', methods=['POST'])
@admin_required
def negar_empresa(id):
    return ec.negar_empresa(id)

@web.route('/admin/empresas/eliminar/<id>', methods=['POST'])
@admin_required
def eliminar_empresa(id):
    return ec.eliminar_empresa(id)

@web.route('/admin/empresas/validar/<id>', methods=['GET', 'POST'])
@admin_required
def validar_impi(id):
    return ec.buscar_y_guardar_impi(id)

@web.route('/admin/empresas/ver/<id>', methods=['GET'])
@admin_required
def ver_empresa(id):
    return ec.ver_empresa(id)

@web.route('/admin/empresas/toggle/<id>', methods=['POST'])
@admin_required
def toggle_empresa(id):
    return ec.toggle_empresa(id)

# ================================================================
# 12. ADMIN - DASHBOARD Y ANALÍTICA
# ================================================================
@web.route('/admin/dashboard', methods=['GET'])
@admin_required
def dashboard():
    return uc.dashboard()

@web.route('/admin/analisis', methods=['GET'])
@admin_required
def analisis():
    return uc.analisis()

@web.route('/admin/inteligencia', methods=['GET'])
@admin_required
def inteligencia():
    return uc.inteligencia()

@web.route('/admin/segmentacion', methods=['GET'])
@admin_required
def segmentacion_clientes():
    return uc.segmentacion_clientes()

@web.route('/admin/prediccion_abandono', methods=['GET'])
@admin_required
def prediccion_abandono():
    return uc.prediccion_abandono()

@web.route('/admin/prediccion_ventas', methods=['GET'])
@admin_required
def prediccion_ventas():
    return uc.prediccion_ventas()

@web.route('/admin/deteccion_fraude', methods=['GET'])
@admin_required
def deteccion_fraude():
    return uc.deteccion_fraude()

@web.route('/admin/reportes', methods=['GET'])
@admin_required
def reportes():
    return uc.reportes()

@web.route('/admin/reportes/ventas', methods=['GET'])
@admin_required
def reporte_ventas():
    return uc.reporte_ventas()

@web.route('/admin/reportes/usuarios', methods=['GET'])
@admin_required
def reporte_usuarios():
    return uc.reporte_usuarios()

@web.route('/admin/reportes/productos', methods=['GET'])
@admin_required
def reporte_productos():
    return uc.reporte_productos()

# ================================================================
# RUTAS PARA CUPONES
# ================================================================
@web.route('/admin/cupones', methods=['GET'])
@admin_required
def admin_listar_cupones():
    return cupon_controller.admin_listar_cupones()

@web.route('/admin/cupones/crear', methods=['GET', 'POST'])
@admin_required
def admin_crear_cupon():
    return cupon_controller.admin_crear_cupon()

@web.route('/admin/cupones/editar/<id>', methods=['GET', 'POST'])
@admin_required
def admin_editar_cupon(id):
    return cupon_controller.admin_editar_cupon(id)

@web.route('/admin/cupones/eliminar/<id>', methods=['POST'])
@admin_required
def admin_eliminar_cupon(id):
    return cupon_controller.admin_eliminar_cupon(id)

@web.route('/admin/cupones/estadisticas/<id>', methods=['GET'])
@admin_required
def admin_cupon_estadisticas(id):
    return cupon_controller.admin_cupon_estadisticas(id)

@web.route('/mis-cupones', methods=['GET'])
@cliente_required
def mis_cupones():
    return cupon_controller.clientes_mis_cupones()

@web.route('/api/cupon/aplicar', methods=['POST'])
@cliente_required
def aplicar_cupon():
    return cupon_controller.cliente_aplicar_cupon()

@web.route('/api/cupon/quitar', methods=['POST'])
@cliente_required
def quitar_cupon():
    return cupon_controller.cliente_quitar_cupon()

@web.route('/api/cupon/validar', methods=['GET'])
@cliente_required
def validar_cupon():
    return cupon_controller.cliente_validar_cupon()

@web.route('/api/cupon/info', methods=['GET'])
@cliente_required
def cupon_info():
    return cupon_controller.cliente_cupon_info()

# ================================================================
# 16. PROMOCIONES - ADMIN
# ================================================================
@web.route('/admin/promociones')
@admin_required
def admin_listar_promociones():
    return promo_c.admin_listar_promociones()

@web.route('/admin/promociones/crear', methods=['GET', 'POST'])
@admin_required
def admin_crear_promocion():
    return promo_c.admin_crear_promocion()

@web.route('/admin/promociones/editar/<promocion_id>', methods=['GET', 'POST'])
@admin_required
def admin_editar_promocion(promocion_id):
    return promo_c.admin_editar_promocion(promocion_id)

@web.route('/admin/promociones/eliminar/<promocion_id>', methods=['POST'])
@admin_required
def admin_eliminar_promocion(promocion_id):
    return promo_c.admin_eliminar_promocion(promocion_id)

@web.route('/admin/promociones/estadisticas/<promocion_id>')
@admin_required
def admin_promocion_estadisticas(promocion_id):
    return promo_c.admin_promocion_estadisticas(promocion_id)

@web.route('/admin/promociones/toggle/<promocion_id>', methods=['POST'])
@admin_required
def admin_toggle_promocion(promocion_id):
    return promo_c.admin_toggle_promocion(promocion_id)

@web.route('/admin/promociones/accion-masiva', methods=['POST'])
@admin_required
def admin_promocion_accion_masiva():
    return promo_c.admin_promocion_accion_masiva()

@web.route('/admin/promociones/exportar-csv')
@admin_required
def admin_promociones_exportar_csv():
    return promo_c.admin_promociones_exportar_csv()

@web.route('/admin/promociones/exportar-pdf')
@admin_required
def admin_promociones_exportar_pdf():
    return promo_c.admin_promociones_exportar_pdf()

@web.route('/api/admin/promociones', methods=['GET'])
@admin_required
def admin_promociones_api():
    return promo_c.admin_promociones_api()

# ================================================================
# 17. PROMOCIONES - CLIENTE
# ================================================================
@web.route('/promociones')
@login_required
def listar_promociones_cliente():
    return promo_c.listar_promociones_cliente()

@web.route('/api/promociones/aplicar', methods=['POST'])
@login_required
def aplicar_promocion():
    return promo_c.aplicar_promocion()

@web.route('/api/promociones/quitar', methods=['POST'])
@login_required
def quitar_promocion():
    return promo_c.quitar_promocion()

@web.route('/api/promociones/validar_codigo', methods=['POST'])
@login_required
def validar_codigo_promocion():
    return promo_c.validar_codigo_promocion()

@web.route('/api/promociones/carrito')
@login_required
def promociones_carrito():
    return promo_c.promociones_carrito()

@web.route('/api/promociones/disponibles')
@login_required
def promociones_disponibles_api():
    return promo_c.promociones_disponibles_api()

# ================================================================
# 13. ADMIN - REPORTE DE VENTAS
# ================================================================
@web.route('/admin/reporte-ventas', methods=['GET'])
@admin_required
def admin_reporte_ventas():
    return vc.admin_reporte_ventas()

@web.route('/admin/reporte-ventas/exportar-csv', methods=['GET'])
@admin_required
def admin_exportar_ventas_csv():
    return vc.admin_exportar_ventas_csv()

@web.route('/admin/reporte-ventas/exportar-pdf', methods=['GET'])
@admin_required
def admin_exportar_ventas_pdf():
    return vc.admin_exportar_ventas_pdf()

@web.route('/api/admin/ventas', methods=['GET'])
@admin_required
def admin_ventas_api():
    return vc.admin_ventas_api()

@web.route('/api/admin/ventas/resumen', methods=['GET'])
@admin_required
def admin_ventas_resumen_api():
    return vc.admin_ventas_resumen_api()

# ================================================================
# 15. ADMIN - ANÁLISIS SUPERVISADO (ML)
# ================================================================
@web.route('/admin/analisis-supervisado', methods=['GET'])
@admin_required
def admin_analisis_supervisado():
    from app.controllers.ml_controller import admin_analisis_supervisado
    return admin_analisis_supervisado()

@web.route('/api/ml/entrenar/ventas', methods=['POST'])
@admin_required
def api_ml_entrenar_ventas():
    from app.controllers.ml_controller import admin_entrenar_modelo_ventas
    return admin_entrenar_modelo_ventas()

@web.route('/api/ml/entrenar/abandono', methods=['POST'])
@admin_required
def api_ml_entrenar_abandono():
    from app.controllers.ml_controller import admin_entrenar_modelo_abandono
    return admin_entrenar_modelo_abandono()

@web.route('/api/ml/predecir/ventas', methods=['GET'])
@admin_required
def api_ml_predecir_ventas():
    from app.controllers.ml_controller import admin_predecir_ventas
    return admin_predecir_ventas()

@web.route('/api/ml/predecir/abandono', methods=['GET'])
@admin_required
def api_ml_predecir_abandono():
    from app.controllers.ml_controller import admin_predecir_abandono
    return admin_predecir_abandono()

@web.route('/api/ml/metricas', methods=['GET'])
@admin_required
def api_ml_metricas():
    from app.controllers.ml_controller import admin_metricas_modelos
    return admin_metricas_modelos()

@web.route('/api/ml/matriz-confusion', methods=['GET'])
@admin_required
def api_ml_matriz_confusion():
    from app.controllers.ml_controller import admin_matriz_confusion
    return admin_matriz_confusion()

@web.route('/api/ml/reporte-clasificacion', methods=['GET'])
@admin_required
def api_ml_reporte_clasificacion():
    from app.controllers.ml_controller import admin_reporte_clasificacion
    return admin_reporte_clasificacion()

@web.route('/api/ml/diagnosticar-abandono', methods=['GET'])
@admin_required
def api_ml_diagnosticar_abandono():
    from app.controllers.ml_controller import admin_diagnosticar_abandono
    return admin_diagnosticar_abandono()

@web.route('/api/ml/limpiar-modelos', methods=['POST'])
@admin_required
def api_ml_limpiar_modelos():
    from app.controllers.ml_controller import admin_limpiar_modelos
    return admin_limpiar_modelos()

@web.route('/api/ml/verificar-modelos', methods=['GET'])
@admin_required
def api_ml_verificar_modelos():
    from app.controllers.ml_controller import admin_verificar_modelos
    return admin_verificar_modelos()

@web.route('/api/ml/umbrales', methods=['GET'])
@admin_required
def api_ml_get_umbrales():
    from app.controllers.ml_controller import admin_get_umbrales
    return admin_get_umbrales()

@web.route('/api/ml/ajustar-umbral', methods=['POST'])
@admin_required
def api_ml_ajustar_umbral():
    from app.controllers.ml_controller import admin_ajustar_umbral
    return admin_ajustar_umbral()

@web.route('/api/ml/dashboard', methods=['GET'])
@admin_required
def api_ml_dashboard():
    from app.controllers.ml_controller import admin_dashboard_ml
    return admin_dashboard_ml()

@web.route('/api/ml/importancia', methods=['GET'])
@admin_required
def api_ml_importancia():
    from app.controllers.ml_controller import admin_importancia_caracteristicas
    return admin_importancia_caracteristicas()

# ===== SEGMENTACIÓN K-MEANS =====
@web.route('/api/ml/entrenar/segmentacion', methods=['POST'])
@admin_required
def api_ml_entrenar_segmentacion():
    from app.controllers.ml_controller import admin_entrenar_modelo_segmentacion
    return admin_entrenar_modelo_segmentacion()

@web.route('/api/ml/segmentacion/metricas', methods=['GET'])
@admin_required
def api_ml_segmentacion_metricas():
    from app.controllers.ml_controller import admin_obtener_metricas_segmentacion
    return admin_obtener_metricas_segmentacion()

@web.route('/api/ml/segmentacion/cluster-stats', methods=['GET'])
@admin_required
def api_ml_segmentacion_cluster_stats():
    from app.controllers.ml_controller import admin_obtener_cluster_stats
    return admin_obtener_cluster_stats()

# ===== REGRESIÓN LOGÍSTICA =====
@web.route('/api/ml/entrenar/logistico', methods=['POST'])
@admin_required
def api_ml_entrenar_logistico():
    from app.controllers.ml_controller import admin_entrenar_modelo_logistico
    return admin_entrenar_modelo_logistico()

@web.route('/api/ml/predecir/logistico', methods=['GET'])
@admin_required
def api_ml_predecir_logistico():
    from app.controllers.ml_controller import admin_predecir_logistico
    return admin_predecir_logistico()

@web.route('/api/ml/metricas/logistico', methods=['GET'])
@admin_required
def api_ml_metricas_logistico():
    from app.controllers.ml_controller import admin_metricas_logistico
    return admin_metricas_logistico()

@web.route('/api/ml/matriz-confusion/logistico', methods=['GET'])
@admin_required
def api_ml_matriz_confusion_logistico():
    from app.controllers.ml_controller import admin_matriz_confusion_logistico
    return admin_matriz_confusion_logistico()

@web.route('/api/ml/reporte/logistico', methods=['GET'])
@admin_required
def api_ml_reporte_logistico():
    from app.controllers.ml_controller import admin_reporte_logistico
    return admin_reporte_logistico()

@web.route('/api/ml/importancia/logistico', methods=['GET'])
@admin_required
def api_ml_importancia_logistico():
    from app.controllers.ml_controller import admin_importancia_logistico
    return admin_importancia_logistico()

@web.route('/api/ml/logistico/curva-roc', methods=['GET'])
@admin_required
def api_logistico_curva_roc():
    from app.controllers.ml_controller import admin_curva_roc_logistico
    return admin_curva_roc_logistico()

@web.route('/api/ml/segmentacion/codo-silueta', methods=['GET'])
@admin_required
def api_segmentacion_codo_silueta():
    from app.controllers.ml_controller import admin_segmentacion_codo_silueta
    return admin_segmentacion_codo_silueta()

@web.route('/api/ml/segmentacion/pca', methods=['GET'])
@admin_required
def api_segmentacion_pca():
    from app.controllers.ml_controller import admin_segmentacion_pca
    return admin_segmentacion_pca()

@web.route('/api/ml/segmentacion/datos', methods=['GET'])
@admin_required
def api_ml_segmentacion_datos():
    from app.controllers.ml_controller import admin_obtener_datos_segmentacion
    return admin_obtener_datos_segmentacion()

# ================================================================
# CLASIFICACIÓN BINARIA (ABANDONO)
# ================================================================
@web.route('/admin/clasificacion-binaria', methods=['GET'])
@admin_required
def clasificacion_binaria():
    from app.controllers.clasificacion_controller import clasificacion_binaria_view
    return clasificacion_binaria_view()

@web.route('/api/clasificacion/entrenar', methods=['POST'])
@admin_required
def api_clasificacion_entrenar():
    from app.controllers.clasificacion_controller import api_entrenar
    return api_entrenar()

@web.route('/api/clasificacion/predecir', methods=['GET'])
@admin_required
def api_clasificacion_predecir():
    from app.controllers.clasificacion_controller import api_predecir
    return api_predecir()

@web.route('/api/clasificacion/metricas', methods=['GET'])
@admin_required
def api_clasificacion_metricas():
    from app.controllers.clasificacion_controller import api_metricas
    return api_metricas()

@web.route('/api/clasificacion/exportar', methods=['GET'])
@admin_required
def api_clasificacion_exportar():
    from app.controllers.clasificacion_controller import api_exportar
    return api_exportar()

@web.route('/api/clasificacion/limpiar', methods=['POST'])
@admin_required
def api_clasificacion_limpiar():
    from app.controllers.clasificacion_controller import api_limpiar
    return api_limpiar()

# ================================================================
# 14. ADMIN - CONFIGURACIÓN
# ================================================================
@web.route('/admin/configuracion', methods=['GET', 'POST'])
@admin_required
def configuracion():
    return uc.configuracion()

@web.route('/admin/configuracion/envios', methods=['GET', 'POST'])
@admin_required
def configuracion_envios():
    return uc.configuracion_envios()

@web.route('/admin/configuracion/pagos', methods=['GET', 'POST'])
@admin_required
def configuracion_pagos():
    return uc.configuracion_pagos()

@web.route('/admin/configuracion/impuestos', methods=['GET', 'POST'])
@admin_required
def configuracion_impuestos():
    return uc.configuracion_impuestos()

@web.route('/admin/configuracion/tiendas', methods=['GET', 'POST'])
@admin_required
def configuracion_tiendas():
    return uc.configuracion_tiendas()

# ================================================================
# 15. WEBHOOKS Y NOTIFICACIONES
# ================================================================
@web.route('/webhook/pago', methods=['POST'])
def webhook_pago():
    return vc.webhook_pago()

@web.route('/webhook/envio', methods=['POST'])
def webhook_envio():
    return vc.webhook_envio()

@web.route('/webhook/seguimiento', methods=['POST'])
def webhook_seguimiento():
    return vc.webhook_seguimiento()

# ================================================================
# 16. PÁGINAS ESTÁTICAS
# ================================================================
@web.route('/contacto', methods=['GET', 'POST'])
def contacto():
    return uc.contacto()

@web.route('/terminos', methods=['GET'])
def terminos():
    return uc.terminos()

@web.route('/privacidad', methods=['GET'])
def privacidad():
    return uc.privacidad()

@web.route('/faq', methods=['GET'])
def faq():
    return uc.faq()

@web.route('/devoluciones', methods=['GET'])
def devoluciones():
    return uc.devoluciones()

@web.route('/nosotros', methods=['GET'])
def nosotros():
    return uc.nosotros()

# ================================================================
# 17. API PARA MÓVIL Y FRONTEND
# ================================================================
@web.route('/api/v1/productos', methods=['GET'])
def api_productos():
    return pc.api_productos()

@web.route('/api/v1/productos/<id>', methods=['GET'])
def api_producto(id):
    return pc.api_producto(id)

@web.route('/api/v1/categorias', methods=['GET'])
def api_categorias():
    return cc.api_categorias()

@web.route('/api/auth/verificar', methods=['GET'])
def verificar_autenticacion():
    return uc.verificar_autenticacion()

@web.route('/api/v1/usuario/actual', methods=['GET'])
@login_required
def obtener_usuario_actual():
    return uc.obtener_usuario_actual()

@web.route('/api/v1/usuario', methods=['GET'])
@login_required
def api_usuario():
    return uc.api_usuario()

@web.route('/api/v1/carrito', methods=['GET', 'POST', 'PUT', 'DELETE'])
@cliente_required
def api_carrito():
    return carrito_c.api_carrito()

@web.route('/api/v1/pedidos', methods=['GET'])
@cliente_required
def api_pedidos():
    return pedido_c.api_pedidos()

@web.route('/api/v1/pedidos/<id>', methods=['GET'])
@cliente_required
def api_pedido(id):
    return pedido_c.api_pedido(id)

@web.route('/api/newsletter/suscribir', methods=['POST'])
def suscribir_newsletter():
    return mc.suscribir_newsletter()

@web.route('/api/newsletter/cancelar', methods=['POST'])
def cancelar_newsletter():
    return mc.cancelar_newsletter()

# ================================================================
# 18. MANTENIMIENTO Y PRUEBAS
# ================================================================
@web.route('/health', methods=['GET'])
def health_check():
    return uc.health_check()

@web.route('/admin/cache/limpiar', methods=['POST'])
@admin_required
def limpiar_cache():
    return uc.limpiar_cache()

@web.route('/admin/migraciones', methods=['GET', 'POST'])
@admin_required
def migraciones():
    return uc.migraciones()

@web.route('/admin/registrar', methods=['GET', 'POST'])
@admin_required
def registrar_admin():
    return uc.registrar_admin()

@web.route('/admin/notificacion/enviar', methods=['POST'])
@admin_required
def enviar_notificacion():
    return uc.enviar_notificacion()

# ================================================================
# COMBOS
# ================================================================
@web.route('/admin/combos', methods=['GET'])
@admin_required
def admin_combos():
    from app.controllers.combo_controller import admin_combos
    return admin_combos()

@web.route('/api/combos', methods=['GET'])
@admin_required
def api_combos_listar():
    from app.controllers.combo_controller import api_combos_listar
    return api_combos_listar()

@web.route('/api/combos', methods=['POST'])
@admin_required
def api_combo_crear():
    from app.controllers.combo_controller import api_combo_crear
    return api_combo_crear()

@web.route('/api/combos/<id>', methods=['GET'])
@admin_required
def api_combo_obtener(id):
    from app.controllers.combo_controller import api_combo_obtener
    return api_combo_obtener(id)

@web.route('/api/combos/<id>', methods=['PUT'])
@admin_required
def api_combo_actualizar(id):
    from app.controllers.combo_controller import api_combo_actualizar
    return api_combo_actualizar(id)

@web.route('/api/combos/<id>', methods=['DELETE'])
@admin_required
def api_combo_eliminar(id):
    from app.controllers.combo_controller import api_combo_eliminar
    return api_combo_eliminar(id)

# ================================================================
# RESEÑAS
# ================================================================
@web.route('/admin/resenas', methods=['GET'])
@admin_required
def admin_resenas():
    from app.controllers.resenas_controller import admin_resenas
    return admin_resenas()

@web.route('/api/resenas', methods=['GET'])
@admin_required
def api_resenas_listar():
    from app.controllers.resenas_controller import api_resenas_listar
    return api_resenas_listar()

@web.route('/api/resenas/<id>/aprobar', methods=['POST'])
@admin_required
def api_resena_aprobar(id):
    from app.controllers.resenas_controller import api_resena_aprobar
    return api_resena_aprobar(id)

@web.route('/api/resenas/<id>/rechazar', methods=['POST'])
@admin_required
def api_resena_rechazar(id):
    from app.controllers.resenas_controller import api_resena_rechazar
    return api_resena_rechazar(id)

@web.route('/api/resenas/<id>/responder', methods=['POST'])
@admin_required
def api_resena_responder(id):
    from app.controllers.resenas_controller import api_resena_responder
    return api_resena_responder(id)

@web.route('/api/resenas/<id>', methods=['DELETE'])
@admin_required
def api_resena_eliminar(id):
    from app.controllers.resenas_controller import api_resena_eliminar
    return api_resena_eliminar(id)

@web.route('/api/resenas/<id>', methods=['GET'])
@admin_required
def api_resena_obtener(id):
    from app.controllers.resenas_controller import api_resena_obtener
    return api_resena_obtener(id)

# ================================================================
# CHAT EN VIVO - WIDGET Y ADMIN
# ================================================================
from app.controllers import chat_controller as chat_c

# --- Rutas para el widget del cliente ---
@web.route('/api/chat/iniciar', methods=['POST'])
def chat_iniciar():
    return chat_c.iniciar_conversacion()

@web.route('/api/chat/obtener', methods=['GET'])
def chat_obtener():
    return chat_c.obtener_conversacion()

@web.route('/api/chat/enviar', methods=['POST'])
def chat_enviar_widget():
    return chat_c.enviar_mensaje_widget()

# --- Rutas para el panel de administración ---
@web.route('/admin/chat')
@admin_required
def admin_chat_panel():
    return chat_c.admin_chat_panel()

@web.route('/api/admin/chat/enviar', methods=['POST'])
@admin_required
def admin_chat_enviar():
    return chat_c.admin_enviar_mensaje()

@web.route('/api/admin/chat/sesiones', methods=['GET'])
@admin_required
def admin_chat_sesiones():
    return chat_c.admin_obtener_sesiones()

@web.route('/api/admin/chat/mensajes', methods=['GET'])
@admin_required
def admin_chat_mensajes_sesion():
    return chat_c.admin_obtener_mensajes_sesion()

@web.route('/api/admin/chat/cerrar', methods=['POST'])
@admin_required
def admin_chat_cerrar():
    return chat_c.admin_cerrar_sesion()

# (Opcional) Ruta para el widget HTML embebido (si usas include)
@web.route('/widget_chat')
def widget_chat():
    return chat_c.widget_chat()

# ================================================================
# 20. ERRORES
# ================================================================
@web.route('/404')
def error_404():
    return render_template('errores/404.html'), 404

@web.route('/500')
def error_500():
    return render_template('errores/500.html'), 500