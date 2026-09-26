from flask import Blueprint, render_template, current_app, session, redirect, url_for, flash, request, jsonify
import app.controllers.user_controller as uc 
import app.controllers.auth_controller as ac
import app.controllers.categoria_controller as cc
import app.controllers.atributo_controller as atrc
import app.controllers.producto_controller as pc
import app.controllers.marca_controller as marca_c
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
from app.controllers import probador_controller
import app.controllers.monedero_controller as monedero_c4
import app.controllers.vendedor_controller as vendedor_c
import app.controllers.cuenta_controller as cuenta_c
from app.controllers import mesa_regalos_controller as mesa_ctrl
from app.controllers import marketplace_controller as mkt_ctrl



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

@web.route('/api/productos/autocompletar')
def api_autocompletar_productos():
    return pc.autocompletar_productos()


@web.route('/api/favoritos/agregar/<producto_id>', methods=['POST'])
@cliente_required
def agregar_favorito(producto_id):
    return uc.agregar_favorito(producto_id)

@web.route('/api/favoritos/eliminar/<producto_id>', methods=['DELETE'])
@cliente_required
def eliminar_favorito(producto_id):
    return uc.eliminar_favorito(producto_id)

@web.route('/api/favoritos/toggle', methods=['POST'])
@cliente_required
def toggle_favorito():
    return uc.toggle_favorito()

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

@web.route('/reenviar-confirmacion', methods=['POST'])
def reenviar_confirmacion():
    return ac.reenviar_confirmacion()

@web.route('/resetear-password/<token>', methods=['GET', 'POST'])
def resetear_password(token):
    return ac.resetear_password(token)

@web.route('/logout', methods=['GET'])
@login_required
def logout():
    return ac.logout()

@web.route('/perfil', methods=['GET'])
@web.route('/mi-cuenta', methods=['GET'])
@cliente_required
def perfil():
    return cuenta_c.vista_perfil() 

@web.route('/perfil/actualizar', methods=['POST'])
@cliente_required
def actualizar():
    return uc.actualizar_perfil()

@web.route('/perfil/cambiar-password', methods=['POST'])
@cliente_required
def cambiar_password():
    return ac.cambiar_password()


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

# ================================================================
# VERIFICACIÓN EN DOS PASOS (2FA)
# ================================================================
@web.route('/mi-cuenta/2fa/estado', methods=['GET'])
@cliente_required
def estado_2fa():
    return uc.estado_2fa()

@web.route('/mi-cuenta/2fa/iniciar', methods=['POST'])
@cliente_required
def iniciar_configuracion_2fa():
    return uc.iniciar_configuracion_2fa()

@web.route('/mi-cuenta/2fa/confirmar', methods=['POST'])
@cliente_required
def confirmar_2fa():
    return uc.confirmar_2fa()

@web.route('/mi-cuenta/2fa/desactivar', methods=['POST'])
@cliente_required
def desactivar_2fa():
    return uc.desactivar_2fa()

@web.route('/mi-cuenta/2fa/regenerar-codigos', methods=['POST'])
@cliente_required
def regenerar_codigos_respaldo():
    return uc.regenerar_codigos_respaldo()

@web.route('/mi-cuenta/2fa/usar-codigo-respaldo', methods=['POST'])
@cliente_required
def usar_codigo_respaldo():
    return uc.usar_codigo_respaldo()


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


@web.route('/mi-cuenta/direcciones/agregar', methods=['POST'])
@cliente_required
def cliente_agregar_direccion():
    return uc.cliente_agregar_direccion()

@web.route('/mi-cuenta/direcciones/editar/<int:direccion_id>', methods=['POST'])
@cliente_required
def cliente_editar_direccion(direccion_id):
    return uc.cliente_editar_direccion(direccion_id)

@web.route('/mi-cuenta/direcciones/predeterminada/<int:direccion_id>', methods=['POST'])
@cliente_required
def cliente_establecer_predeterminada(direccion_id):
    return uc.cliente_establecer_predeterminada(direccion_id)

@web.route('/mi-cuenta/direcciones/borrar/<int:direccion_id>', methods=['POST'])
@cliente_required
def cliente_borrar_direccion(direccion_id):
    return uc.cliente_borrar_direccion(direccion_id)


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
# ADMIN: Guardar intereses de un usuario desde el panel
# ================================================================
@web.route('/admin/usuarios/<usuario_id>/intereses', methods=['POST'])
@admin_required
def admin_guardar_intereses(usuario_id):
    return uc.admin_guardar_intereses(usuario_id)

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


@web.route('/admin/reporte-ventas/detalle/<fecha>', methods=['GET'])
@admin_required
def admin_detalle_ventas_dia(fecha):
    from app.controllers.ventas_controller import admin_detalle_ventas_dia
    return admin_detalle_ventas_dia(fecha)


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
# CHATBOT - CLIENTE
# ================================================================
@web.route('/api/chat/iniciar', methods=['POST'])
def api_chat_iniciar():
    from app.controllers.chat_controller import iniciar_conversacion
    return iniciar_conversacion()

@web.route('/api/chat/obtener', methods=['GET'])
def api_chat_obtener():
    from app.controllers.chat_controller import obtener_conversacion
    return obtener_conversacion()

@web.route('/api/chat/enviar', methods=['POST'])
def api_chat_enviar():
    from app.controllers.chat_controller import enviar_mensaje_widget
    return enviar_mensaje_widget()

@web.route('/api/chat/crear-sesion', methods=['POST'])
def api_chat_crear_sesion():
    from app.controllers.chat_controller import crear_sesion
    return crear_sesion()


# ================================================================
# CHATBOT - ADMIN
# ================================================================
@web.route('/admin/chat', methods=['GET'])
@admin_required
def admin_chat_panel():
    from app.controllers.chat_controller import admin_chat_panel
    return admin_chat_panel()

@web.route('/api/admin/chat/sesiones', methods=['GET'])
@admin_required
def admin_chat_sesiones():
    from app.controllers.chat_controller import admin_obtener_sesiones
    return admin_obtener_sesiones()

@web.route('/api/admin/chat/sesiones-archivadas', methods=['GET'])
@admin_required
def admin_chat_sesiones_archivadas():
    from app.controllers.chat_controller import admin_obtener_sesiones_archivadas
    return admin_obtener_sesiones_archivadas()

@web.route('/api/admin/chat/mensajes', methods=['GET'])
@admin_required
def admin_chat_mensajes_sesion():
    from app.controllers.chat_controller import admin_obtener_mensajes_sesion
    return admin_obtener_mensajes_sesion()

@web.route('/api/admin/chat/enviar', methods=['POST'])
@admin_required
def admin_chat_enviar():
    from app.controllers.chat_controller import admin_enviar_mensaje
    return admin_enviar_mensaje()

@web.route('/api/admin/chat/generar-ia', methods=['POST'])
@admin_required
def admin_generar_respuesta_ia():
    from app.controllers.chat_controller import admin_generar_respuesta_ia
    return admin_generar_respuesta_ia()

@web.route('/api/admin/chat/archivar', methods=['POST'])
@admin_required
def admin_chat_archivar():
    from app.controllers.chat_controller import admin_archivar_sesion
    return admin_archivar_sesion()

@web.route('/api/admin/chat/cerrar', methods=['POST'])
@admin_required
def admin_chat_cerrar():
    from app.controllers.chat_controller import admin_cerrar_sesion
    return admin_cerrar_sesion()

@web.route('/api/admin/chat/reactivar', methods=['POST'])
@admin_required
def admin_chat_reactivar():
    from app.controllers.chat_controller import admin_reactivar_sesion
    return admin_reactivar_sesion()


# ================================================================
# NLP - ADMIN
# ================================================================
@web.route('/api/admin/nlp/entrenar', methods=['POST'])
@admin_required
def admin_nlp_entrenar():
    from app.controllers.chat_controller import admin_entrenar_nlp
    return admin_entrenar_nlp()

@web.route('/api/admin/nlp/info', methods=['GET'])
@admin_required
def admin_nlp_info():
    from app.controllers.chat_controller import admin_info_nlp
    return admin_info_nlp()

@web.route('/api/admin/nlp/probar', methods=['POST'])
@admin_required
def admin_nlp_probar():
    from app.controllers.chat_controller import admin_probar_nlp
    return admin_probar_nlp()

@web.route('/api/admin/scheduler/info', methods=['GET'])
@admin_required
def admin_scheduler_info():
    from app.controllers.chat_controller import admin_info_scheduler
    return admin_info_scheduler()

# ================================================================
# CHATBOT - RETENCIÓN
# ================================================================
@web.route('/api/admin/chat/retencion/previsualizar', methods=['GET'])
@admin_required
def admin_chat_retencion_previsualizar():
    from app.controllers.chat_controller import admin_previsualizar_retencion
    return admin_previsualizar_retencion()

@web.route('/api/admin/chat/retencion/ejecutar', methods=['POST'])
@admin_required
def admin_chat_retencion_ejecutar():
    from app.controllers.chat_controller import admin_ejecutar_retencion
    return admin_ejecutar_retencion()

# ================================================================
# CHATBOT - AUDITORÍA
# ================================================================
@web.route('/api/admin/chat/auditoria', methods=['GET'])
@admin_required
def admin_chat_auditoria():
    from app.controllers.chat_controller import admin_listar_auditoria
    return admin_listar_auditoria()

@web.route('/api/admin/chat/auditoria/stats', methods=['GET'])
@admin_required
def admin_chat_auditoria_stats():
    from app.controllers.chat_controller import admin_estadisticas_auditoria
    return admin_estadisticas_auditoria()


# ================================================================
# CHATBOT - EXPORTAR PDF
# ================================================================
@web.route('/api/admin/chat/exportar-pdf', methods=['GET'])
@admin_required
def admin_chat_exportar_pdf():
    from app.controllers.chat_controller import admin_exportar_historial_pdf
    return admin_exportar_historial_pdf()


# ================================================================
# CHATBOT - ANONIMIZAR
# ================================================================
@web.route('/api/admin/chat/anonimizar', methods=['POST'])
@admin_required
def admin_chat_anonimizar():
    from app.controllers.chat_controller import admin_anonimizar_sesion
    return admin_anonimizar_sesion()

# ================================================================
# DASHBOARD DE AUDITORÍA
# ================================================================
@web.route('/admin/auditoria', methods=['GET'])
@admin_required
def admin_dashboard_auditoria():
    from app.controllers.chat_controller import admin_dashboard_auditoria
    return admin_dashboard_auditoria()

@web.route('/api/admin/auditoria/dashboard', methods=['GET'])
@admin_required
def admin_datos_dashboard_auditoria():
    from app.controllers.chat_controller import admin_datos_dashboard_auditoria
    return admin_datos_dashboard_auditoria()


from app.controllers.temporada_controller import (
    listar_temporadas as listar_temporadas_ctrl,
    crear_temporada as crear_temporada_ctrl,
    editar_temporada as editar_temporada_ctrl,
    eliminar_temporada as eliminar_temporada_ctrl
)

@web.route('/admin/temporadas', methods=['GET'])
@admin_required
def listar_temporadas():
    return listar_temporadas_ctrl()

@web.route('/admin/temporadas/crear', methods=['POST'])
@admin_required
def crear_temporada():
    return crear_temporada_ctrl()

@web.route('/admin/temporadas/editar/<id>', methods=['POST'])
@admin_required
def editar_temporada(id):
    return editar_temporada_ctrl(id)

@web.route('/admin/temporadas/eliminar/<id>', methods=['POST'])
@admin_required
def eliminar_temporada(id):
    return eliminar_temporada_ctrl(id)


# ================================================================
# IDIOMA Y REGIÓN
# ================================================================

@web.route('/mi-cuenta/idioma', methods=['GET'])
@cliente_required
def obtener_preferencias_idioma():
    return uc.obtener_preferencias_idioma()

@web.route('/mi-cuenta/idioma', methods=['POST'])
@cliente_required
def actualizar_preferencias_idioma():
    return uc.actualizar_preferencias_idioma()

@web.route('/mi-cuenta/idioma/vista-previa', methods=['GET'])
@cliente_required
def vista_previa_idioma():
    return uc.vista_previa_idioma()


# ================================================================
# 20. ERRORES
# ================================================================
@web.route('/404')
def error_404():
    return render_template('errores/404.html'), 404

@web.route('/500')
def error_500():
    return render_template('errores/500.html'), 500


# ==========================================================
# PROBADOR VIRTUAL ORION
# ==========================================================

@web.route("/probador-virtual", methods=["GET"])
def probador_virtual():
    return probador_controller.mostrar_probador()

@web.route("/probador-virtual/subir", methods=["POST"])
def probador_virtual_subir():
    return probador_controller.subir_fotografia()

@web.route("/api/probador/productos", methods=["GET"])
def probador_productos():
    return probador_controller.obtener_productos_probador()

@web.route("/api/probador/outfit", methods=["POST"])
def probador_outfit():
    return probador_controller.guardar_outfit()

@web.route("/api/probador/generar", methods=["POST"])
def probador_generar():
    return probador_controller.generar_simulacion()

@web.route("/probador/estado/<probador_id>", methods=["GET"])
def probador_estado(probador_id):
    return probador_controller.obtener_estado_simulacion(probador_id)


# ================================================================
# CLIENTE CONSENTIDO - LEALTAD
# ================================================================

# ---- CLIENTE ----
@web.route('/mi-lealtad', methods=['GET'])
@cliente_required
def mi_lealtad():
    from app.controllers.lealtad_controller import mi_lealtad
    return mi_lealtad()

@web.route('/api/lealtad/mi-info', methods=['GET'])
@cliente_required
def api_mi_lealtad():
    from app.controllers.lealtad_controller import api_mi_lealtad
    return api_mi_lealtad()

@web.route('/api/lealtad/canjear', methods=['POST'])
@cliente_required
def api_canjear_puntos():
    from app.controllers.lealtad_controller import canjear_puntos_cliente
    return canjear_puntos_cliente()


# ---- ADMIN ----
@web.route('/admin/lealtad', methods=['GET'])
@admin_required
def admin_lealtad_panel():
    from app.controllers.lealtad_controller import admin_lealtad_panel
    return admin_lealtad_panel()

@web.route('/api/admin/lealtad/stats', methods=['GET'])
@admin_required
def api_admin_lealtad_stats():
    from app.controllers.lealtad_controller import api_admin_stats
    return api_admin_stats()

@web.route('/api/admin/lealtad/clientes', methods=['GET'])
@admin_required
def api_admin_lealtad_clientes():
    from app.controllers.lealtad_controller import api_admin_listar_clientes
    return api_admin_listar_clientes()

@web.route('/api/admin/lealtad/ajustar-puntos', methods=['POST'])
@admin_required
def api_admin_ajustar_puntos():
    from app.controllers.lealtad_controller import admin_ajustar_puntos
    return admin_ajustar_puntos()

@web.route('/api/admin/lealtad/generar-cupones', methods=['POST'])
@admin_required
def api_admin_generar_cupones():
    from app.controllers.lealtad_controller import admin_generar_cupones_masivos
    return admin_generar_cupones_masivos()

@web.route('/api/admin/lealtad/otorgar-puntos', methods=['POST'])
@admin_required
def api_admin_otorgar_puntos():
    from app.controllers.lealtad_controller import admin_otorgar_puntos_masivos
    return admin_otorgar_puntos_masivos()

@web.route('/verificar-2fa', methods=['GET', 'POST'])
def verificar_2fa_login():
    return ac.verificar_2fa_login()

import app.controllers.monedero_controller as monedero_c

# ================================================================
# MONEDERO DIGITAL ORION - Estilo Liverpool
# ================================================================
@web.route('/mi-monedero', methods=['GET'])
@cliente_required
def mi_monedero():
    return monedero_c.mi_monedero()


@web.route('/api/monedero/resumen', methods=['GET'])
@cliente_required
def api_monedero_resumen():
    return monedero_c.api_resumen()


@web.route('/api/monedero/transferir', methods=['POST'])
@cliente_required
def api_monedero_transferir():
    return monedero_c.api_transferir()


@web.route('/api/monedero/recargar', methods=['POST'])
@cliente_required
def api_monedero_recargar():
    return monedero_c.api_recargar()


@web.route('/api/monedero/movimientos', methods=['GET'])
@cliente_required
def api_monedero_movimientos():
    return monedero_c.api_movimientos()


import app.controllers.marca_controller as marca_c

# ================================================================
# MARCAS - Estilo MARCANET
# ================================================================

# ---- VISTAS ----
@web.route('/admin/marcas', methods=['GET'])
@admin_required
def lista_marcas():
    return marca_c.listar_marcas()

@web.route('/admin/marcas/ver/<id>', methods=['GET'])
@admin_required
def ver_marca(id):
    return marca_c.ver_marca(id)

# ---- CRUD ----
@web.route('/admin/marcas/agregar', methods=['POST'])
@admin_required
def agregar_marca():
    return marca_c.agregar_marca()

@web.route('/admin/marcas/editar/<id>', methods=['POST'])
@admin_required
def editar_marca(id):
    return marca_c.editar_marca(id)

@web.route('/admin/marcas/aprobar/<id>', methods=['GET'])
@admin_required
def aprobar_marca(id):
    return marca_c.aprobar_marca(id)

@web.route('/admin/marcas/negar/<id>', methods=['POST'])
@admin_required
def negar_marca(id):
    return marca_c.negar_marca(id)

@web.route('/admin/marcas/eliminar/<id>', methods=['GET', 'POST'])
@admin_required
def eliminar_marca(id):
    return marca_c.eliminar_marca(id)

@web.route('/admin/marcas/toggle/<id>', methods=['POST'])
@admin_required
def toggle_marca(id):
    return marca_c.toggle_marca(id)

# ---- SCRAPING IMPI ----
@web.route('/admin/marcas/validar/<id>', methods=['GET'])
@admin_required
def validar_impi(id):
    return marca_c.buscar_y_guardar_impi(id)

# ---- PDFs ----
@web.route('/admin/marcas/pdf/<id>', methods=['GET'])
@admin_required
def descargar_pdf_marca(id):
    return marca_c.descargar_pdf_marca(id)

@web.route('/admin/marcas/pdf/todas', methods=['GET'])
@admin_required
def descargar_pdf_todas_marcas():
    return marca_c.descargar_pdf_todas_marcas()

# ---- EXPORTAR CSV ----
@web.route('/admin/marcas/exportar-csv', methods=['GET'])
@admin_required
def exportar_marcas_csv():
    return marca_c.exportar_marcas_csv()

# ---- APIs JSON ----
@web.route('/api/marcas', methods=['GET'])
def api_marcas():
    return marca_c.api_marcas()

@web.route('/api/marcas/<id>', methods=['GET'])
def api_marca(id):
    return marca_c.api_marca(id)

@web.route('/api/marcas/buscar', methods=['GET'])
def buscar_marcas():
    return marca_c.buscar_marcas()

@web.route('/api/marcas/activas', methods=['GET'])
def obtener_marcas_activas():
    return marca_c.obtener_marcas_activas()

@web.route('/api/marcas/por-rfc', methods=['GET'])
def obtener_marca_por_rfc():
    return marca_c.obtener_marca_por_rfc()

@web.route('/api/marcas/estadisticas', methods=['GET'])
def estadisticas_marcas():
    return marca_c.estadisticas_marcas()

@web.route('/api/marcas/buscar-fonetica', methods=['GET'])
def buscar_marcas_fonetica():
    return marca_c.buscar_marcas_fonetica()

@web.route('/admin/marcas/pdf/<marca_id>/resultado/<int:index>', methods=['GET'])
@admin_required
def descargar_pdf_resultado_impi(marca_id, index):
    return marca_c.descargar_pdf_resultado_impi(marca_id, index)


from app.decorators import vendedor_required

# ================================================================
# VENDEDOR
# ================================================================

# Dashboard
@web.route('/vendedor/dashboard', methods=['GET'])
@vendedor_required
def vendedor_dashboard():
    return vendedor_c.dashboard()

# Productos
@web.route('/vendedor/productos', methods=['GET'])
@vendedor_required
def vendedor_productos():
    return vendedor_c.lista_productos()

@web.route('/vendedor/productos/crear', methods=['POST'])
@vendedor_required
def vendedor_crear_producto():
    return vendedor_c.crear_producto()

@web.route('/vendedor/productos/editar/<producto_id>', methods=['POST'])
@vendedor_required
def vendedor_editar_producto(producto_id):
    return vendedor_c.editar_producto(producto_id)

@web.route('/vendedor/productos/eliminar/<producto_id>', methods=['POST'])
@vendedor_required
def vendedor_eliminar_producto(producto_id):
    return vendedor_c.eliminar_producto(producto_id)

@web.route('/vendedor/productos/toggle/<producto_id>', methods=['POST'])
@vendedor_required
def vendedor_toggle_producto(producto_id):
    return vendedor_c.toggle_producto(producto_id)

# Pedidos
@web.route('/vendedor/pedidos', methods=['GET'])
@vendedor_required
def vendedor_pedidos():
    return vendedor_c.lista_pedidos()

@web.route('/vendedor/pedidos/<pedido_id>', methods=['GET'])
@vendedor_required
def vendedor_ver_pedido(pedido_id):
    return vendedor_c.ver_pedido(pedido_id)

@web.route('/vendedor/pedidos/<pedido_id>/estado', methods=['POST'])
@vendedor_required
def vendedor_actualizar_pedido(pedido_id):
    return vendedor_c.actualizar_estado_pedido(pedido_id)

# Reseñas
@web.route('/vendedor/resenas', methods=['GET'])
@vendedor_required
def vendedor_resenas():
    return vendedor_c.lista_resenas()

@web.route('/vendedor/resenas/responder/<resena_id>', methods=['POST'])
@vendedor_required
def vendedor_responder_resena(resena_id):
    return vendedor_c.responder_resena(resena_id)

# API
@web.route('/api/vendedor/stats', methods=['GET'])
@vendedor_required
def api_vendedor_stats():
    return vendedor_c.api_stats()

# ============================================================
# RUTAS DE COMPLEXIÓN (API)
# ============================================================
from app.controllers import complexion_controller as complexion_c

@web.route('/api/complexion/obtener', methods=['GET'])
@cliente_required
def api_obtener_medidas():
    return complexion_c.api_obtener_medidas()

@web.route('/api/complexion/guardar', methods=['POST'])
@cliente_required
def api_guardar_medidas():
    return complexion_c.api_guardar_medidas()

@web.route('/api/complexion/recomendar-talla', methods=['GET'])
@cliente_required
def api_recomendar_talla():
    return complexion_c.api_recomendar_talla()

@web.route('/api/complexion', methods=['GET'])
@cliente_required
def api_obtener_complexion():
    return complexion_c.api_obtener_complexion()

@web.route('/api/complexion', methods=['POST'])
@cliente_required
def api_guardar_complexion():
    return complexion_c.api_guardar_complexion()

@web.route('/api/complexion/limpiar', methods=['POST'])
@cliente_required
def api_limpiar_complexion():
    return complexion_c.api_limpiar_complexion()


# ================================================================
# API v1 - AUTENTICACIÓN JWT (React Native / SPA)
# ================================================================

@web.route('/api/v1/auth/login', methods=['POST'])
def api_v1_login():
    from app.controllers.auth_controller import api_login_jwt
    return api_login_jwt()

@web.route('/api/v1/auth/register', methods=['POST'])
def api_v1_register():
    from app.controllers.auth_controller import api_register_jwt
    return api_register_jwt()

@web.route('/api/v1/auth/me', methods=['GET'])
def api_v1_me():
    from app.controllers.auth_controller import api_me_jwt
    return api_me_jwt()

@web.route('/api/v1/auth/logout', methods=['POST'])
def api_v1_logout():
    return {"message": "Sesión cerrada en el cliente"}, 200

@web.route('/api/v1/usuarios', methods=['GET'])
def api_v1_usuarios():
    from app.controllers.auth_controller import api_listar_usuarios_jwt
    return api_listar_usuarios_jwt()

# ================================================================
# PREFERENCIAS DE COMUNICACIÓN
# ================================================================
@web.route('/mi-cuenta/preferencias', methods=['GET'])
@cliente_required
def obtener_preferencias_comunicacion():
    return cuenta_c.obtener_comunicaciones()

@web.route('/mi-cuenta/preferencias', methods=['POST'])
@cliente_required
def actualizar_preferencias():
    return cuenta_c.guardar_comunicaciones()


# ================================================================
# PRIVACIDAD
# ================================================================
@web.route('/mi-cuenta/privacidad', methods=['GET'])
@cliente_required
def obtener_privacidad():
    return cuenta_c.obtener_privacidad()

@web.route('/mi-cuenta/privacidad', methods=['POST'])
@cliente_required
def guardar_privacidad():
    return cuenta_c.guardar_privacidad()


# ================================================================
# FACTURACIÓN
# ================================================================
@web.route('/mi-cuenta/facturacion', methods=['GET'])
@cliente_required
def obtener_facturacion():
    return cuenta_c.obtener_facturacion()

@web.route('/mi-cuenta/facturacion', methods=['POST'])
@cliente_required
def guardar_facturacion():
    return cuenta_c.guardar_facturacion()


# ================================================================
# MÉTODOS DE PAGO
# ================================================================
@web.route('/mi-cuenta/metodos-pago', methods=['GET'])
@cliente_required
def listar_metodos_pago():
    return cuenta_c.listar_metodos_pago()

@web.route('/mi-cuenta/metodos-pago', methods=['POST'])
@cliente_required
def agregar_metodo_pago():
    return cuenta_c.agregar_metodo_pago()

@web.route('/mi-cuenta/metodos-pago/<metodo_id>', methods=['DELETE'])
@cliente_required
def eliminar_metodo_pago(metodo_id):
    return cuenta_c.eliminar_metodo_pago(metodo_id)

@web.route('/mi-cuenta/metodos-pago/<metodo_id>/predeterminado', methods=['POST'])
@cliente_required
def metodo_predeterminado(metodo_id):
    return cuenta_c.establecer_metodo_predeterminado(metodo_id)


# ================================================================
# ADMIN — Cuentas de Clientes
# ================================================================
@web.route('/admin/cuentas-clientes', methods=['GET'])
@admin_required
def admin_cuentas_clientes():
    from flask import render_template, current_app
    db = current_app.db
    clientes = list(db.usuarios.find({'rol': 'cliente'}).sort('nombre', 1))
    for c in clientes:
        c['_id'] = str(c['_id'])
    return render_template('admin/cuentas_clientes.html', clientes=clientes)


@web.route('/admin/clientes/<usuario_id>/cuenta', methods=['GET'])
@admin_required
def admin_ver_cuenta(usuario_id):
    from flask import render_template
    return render_template('admin/cliente_cuenta.html', usuario_id=usuario_id)


@web.route('/api/admin/clientes/<usuario_id>/cuenta', methods=['GET'])
@admin_required
def admin_ver_cuenta_cliente(usuario_id):
    return cuenta_c.admin_obtener_cuenta_cliente(usuario_id)


# ================================================================
# MIS DATOS (PDF) — Vista imprimible del cliente
# ================================================================
@web.route('/mi-cuenta/mis-datos', methods=['GET'])
@cliente_required
def ver_mis_datos_pdf():
    from app.controllers import cuenta_controller
    return cuenta_controller.ver_mis_datos_pdf()


# ================================================================
# ELIMINAR CUENTA (Cliente)
# ================================================================
@web.route('/mi-cuenta/eliminar-cuenta', methods=['POST'])
@cliente_required
def eliminar_cuenta():
    from app.controllers import cuenta_controller
    return cuenta_controller.eliminar_mi_cuenta()


# ================================================================
# DESCARGAR DATOS (JSON)
# ================================================================
@web.route('/mi-cuenta/descargar-datos', methods=['GET'])
@cliente_required
def descargar_mis_datos():
    return cuenta_c.descargar_mis_datos()


# ================================================================
# API INTERESES (Pestaña "Intereses" del perfil)
# ================================================================
@web.route('/api/intereses', methods=['GET'])
@cliente_required
def api_intereses_get():
    return uc.api_intereses_get()


@web.route('/api/intereses', methods=['POST'])
@cliente_required
def api_intereses_post():
    return uc.api_intereses_post()


@web.route('/api/intereses', methods=['DELETE'])
@cliente_required
def api_intereses_delete():
    return uc.api_intereses_delete()

# ================================================================
# PRODUCTOS - EXCEL + MSI
# ================================================================
@web.route('/admin/productos/importar-excel', methods=['POST'])
@admin_required
def importar_productos_excel():
    return pc.importar_productos_excel()

@web.route('/admin/pedidos/exportar-pdf', methods=['GET'])
@admin_required
def exportar_pedidos_pdf():
    return pedido_c.exportar_pedidos_pdf()

@web.route('/api/msi/calcular')
def api_calcular_msi():
    return pc.api_calcular_msi()

@web.route('/api/checkout/msi', methods=['POST'])
@cliente_required
def checkout_msi():
    return pedido_c.procesar_checkout_msi()

@web.route('/admin/pedidos/factura/<id>')
@admin_required
def admin_generar_factura_pdf(id):
    return pedido_c.admin_generar_factura_pdf(id)


@web.route('/mi-cuenta/factura/<id>')
@cliente_required
def mi_factura_pdf(id):
    return pedido_c.cliente_generar_factura_pdf(id)


# ================================================================
# MESA DE REGALOS
# ================================================================

@web.route('/mesa-regalos/crear', methods=['GET'])
def crear_mesa_regalos():
    return mesa_ctrl.crear_mesa()


@web.route('/api/mesa-regalos/crear', methods=['POST'])
def api_crear_mesa_regalos():
    return mesa_ctrl.guardar_mesa()


@web.route('/mesa/<slug>', methods=['GET'])
def ver_mesa_regalos(slug):
    return mesa_ctrl.ver_mesa(slug)


@web.route('/mis-mesas-regalos', methods=['GET'])
def mis_mesas_regalos():
    return mesa_ctrl.mis_mesas()


@web.route('/api/mesa-regalos/<mesa_id>/reservar', methods=['POST'])
def api_reservar_regalo(mesa_id):
    return mesa_ctrl.reservar_regalo(mesa_id)


@web.route('/api/mesa-regalos/<mesa_id>/contribuir', methods=['POST'])
def api_contribuir_fondo(mesa_id):
    return mesa_ctrl.contribuir_fondo(mesa_id)


@web.route('/api/mesa-regalos/<mesa_id>/eliminar', methods=['DELETE'])
def api_eliminar_mesa(mesa_id):
    return mesa_ctrl.eliminar_mesa(mesa_id)


# ================================================================
# MARKETPLACE
# ================================================================

# ---- Público ----
@web.route('/marketplace', methods=['GET'])
def marketplace():
    return mkt_ctrl.index()


@web.route('/marketplace/registro', methods=['GET', 'POST'])
def marketplace_registro():
    return mkt_ctrl.registro()


@web.route('/marketplace/estado', methods=['GET'])
def marketplace_estado():
    return mkt_ctrl.estado_solicitud()


@web.route('/marketplace/dashboard', methods=['GET'])
def marketplace_dashboard():
    return mkt_ctrl.dashboard()


# ⭐ NUEVO: Tienda pública de un vendedor
@web.route('/marketplace/tienda/<slug>', methods=['GET'])
def marketplace_ver_tienda(slug):
    """
    Vista pública de la tienda de un vendedor.
    URL amigable: /marketplace/tienda/mi-tienda-fitness-abc123
    """
    return mkt_ctrl.ver_tienda_publica(slug)


# ⭐ NUEVO: APIs públicas de vendedores
@web.route('/api/marketplace/vendedores', methods=['GET'])
def api_marketplace_vendedores():
    """
    Lista de vendedores aprobados (JSON).
    Params opcionales: ?limite=24&categoria=moda&destacados=1
    """
    return mkt_ctrl.api_vendedores()


@web.route('/api/marketplace/vendedor/<vid>', methods=['GET'])
def api_marketplace_vendedor(vid):
    """
    Detalle público de un vendedor (JSON).
    """
    return mkt_ctrl.api_vendedor(vid)


# ---- Admin ----
@web.route('/admin/marketplace/vendedores', methods=['GET'])
@admin_required
def admin_marketplace_vendedores():
    return mkt_ctrl.admin_lista()


@web.route('/admin/marketplace/vendedores/<vid>', methods=['GET'])
@admin_required
def admin_marketplace_vendedor_detalle(vid):
    return mkt_ctrl.admin_detalle(vid)


@web.route('/api/admin/marketplace/vendedores/<vid>/estado', methods=['POST'])
@admin_required
def api_admin_mkt_estado(vid):
    return mkt_ctrl.admin_cambiar_estado(vid)


@web.route('/api/admin/marketplace/vendedores/<vid>/comision', methods=['POST'])
@admin_required
def api_admin_mkt_comision(vid):
    return mkt_ctrl.admin_actualizar_comision(vid)


@web.route('/api/admin/marketplace/vendedores/<vid>/eliminar', methods=['DELETE'])
@admin_required
def api_admin_mkt_eliminar(vid):
    return mkt_ctrl.admin_eliminar(vid)

# ================================================================
# MARKETPLACE — Panel del vendedor de marketplace
# Nombres con prefijo "marketplace_" para no chocar con /vendedor/*
# ================================================================

@web.route('/marketplace/mis-productos', methods=['GET'])
@vendedor_required
def marketplace_mis_productos():
    return vendedor_c.vendedor_mis_productos()


@web.route('/marketplace/mis-productos/nuevo', methods=['GET', 'POST'])
@vendedor_required
def marketplace_nuevo_producto():
    return vendedor_c.vendedor_nuevo_producto()


@web.route('/marketplace/mis-productos/editar/<producto_id>', methods=['GET', 'POST'])
@vendedor_required
def marketplace_editar_producto(producto_id):
    return vendedor_c.vendedor_editar_producto(producto_id)


@web.route('/marketplace/mis-productos/eliminar/<producto_id>', methods=['POST'])
@vendedor_required
def marketplace_eliminar_producto(producto_id):
    return vendedor_c.vendedor_eliminar_producto(producto_id)


@web.route('/marketplace/mis-pedidos', methods=['GET'])
@vendedor_required
def marketplace_mis_pedidos():
    return vendedor_c.vendedor_mis_pedidos()


@web.route('/marketplace/mis-pedidos/<pedido_id>', methods=['GET'])
@vendedor_required
def marketplace_ver_pedido(pedido_id):
    return vendedor_c.vendedor_ver_pedido(pedido_id)

# ================================================================
# ADMIN — MONEDERO (AGREGAR AL FINAL)
# ================================================================
import app.controllers.monedero_admin_controller as monedero_admin_c

@web.route('/admin/monedero', methods=['GET'])
@admin_required
def admin_monedero_panel():
    return monedero_admin_c.admin_monedero_panel()

@web.route('/admin/monedero/clientes', methods=['GET'])
@admin_required
def admin_monedero_clientes():
    return monedero_admin_c.admin_monedero_clientes()

@web.route('/admin/monedero/cliente/<usuario_id>', methods=['GET'])
@admin_required
def admin_monedero_cliente(usuario_id):
    return monedero_admin_c.admin_monedero_cliente(usuario_id)

@web.route('/admin/monedero/<usuario_id>/ajustar', methods=['POST'])
@admin_required
def admin_monedero_ajustar(usuario_id):
    return monedero_admin_c.admin_monedero_ajustar(usuario_id)

@web.route('/admin/monedero/cliente/<usuario_id>/toggle', methods=['POST'])
@admin_required
def admin_monedero_toggle(usuario_id):
    return monedero_admin_c.admin_monedero_toggle(usuario_id)

@web.route('/admin/monedero/configuracion', methods=['GET', 'POST'])
@admin_required
def admin_monedero_config():
    return monedero_admin_c.admin_monedero_config()

@web.route('/api/admin/monedero/stats', methods=['GET'])
@admin_required
def api_admin_monedero_stats():
    return monedero_admin_c.api_admin_monedero_stats()

@web.route('/api/admin/monedero/top', methods=['GET'])
@admin_required
def api_admin_monedero_top():
    return monedero_admin_c.api_admin_monedero_top()

# ⭐ NUEVAS RUTAS
@web.route('/api/admin/monedero/grafico', methods=['GET'])
@admin_required
def api_admin_monedero_grafico():
    return monedero_admin_c.api_admin_monedero_grafico()

@web.route('/admin/monedero/exportar-csv', methods=['GET'])
@admin_required
def admin_monedero_exportar_csv():
    return monedero_admin_c.admin_monedero_exportar_csv()

