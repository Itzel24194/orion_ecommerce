import os
import threading

from flask import (
    render_template,
    request,
    jsonify,
    current_app,
    session
)

from bson import ObjectId

from app.models.productos_model import (
    Producto as ProductoModel
)

from app.models.probador_model import (
    ProbadorVirtual
)

from app.services.probador_service import (
    ProbadorService
)

from app.services.ia_service import (
    generar_outfit_completo
)


# ==========================================================
# PÁGINA PRINCIPAL DEL PROBADOR
# ==========================================================

def mostrar_probador():

    db = current_app.db

    productos = ProductoModel.obtener_activos()

    productos_preparados = []

    for producto in productos:

        try:

            preparado = (
                ProbadorService.preparar_producto(
                    producto
                )
            )

            productos_preparados.append(
                preparado
            )

        except Exception as e:

            print(
                f"Error preparando producto: {e}"
            )

    return render_template(
        "tienda/probador_virtual.html",
        productos=productos_preparados
    )


# ==========================================================
# SUBIR FOTOGRAFÍA
# ==========================================================

def subir_fotografia():

    if "foto" not in request.files:

        return jsonify({
            "success": False,
            "message": "No se recibió ninguna fotografía."
        }), 400

    archivo = request.files["foto"]

    valido, mensaje = (
        ProbadorService.validar_fotografia(
            archivo
        )
    )

    if not valido:

        return jsonify({
            "success": False,
            "message": mensaje
        }), 400

    try:

        nombre_archivo = (
            ProbadorService.guardar_fotografia(
                current_app,
                archivo
            )
        )

        usuario_id = session.get(
            "user_id"
        )

        data = {
            "usuario_id": usuario_id,
            "foto_usuario": nombre_archivo,
            "productos_seleccionados": [],
            "resultado": None,
            "estado": "foto_subida"
        }

        probador_id = (
            ProbadorVirtual.crear_sesion(
                current_app.db,
                data
            )
        )

        return jsonify({
            "success": True,
            "message": "Fotografía subida correctamente.",
            "probador_id": probador_id,
            "foto": nombre_archivo,
            "url": (
                "/static/uploads/probador/"
                + nombre_archivo
            )
        })

    except Exception as e:

        print(
            f"ERROR subir fotografía: {e}"
        )

        return jsonify({
            "success": False,
            "message": "No fue posible guardar la fotografía."
        }), 500


# ==========================================================
# OBTENER PRODUCTOS PARA EL PROBADOR
# ==========================================================

def obtener_productos_probador():

    productos = ProductoModel.obtener_activos()

    resultado = []

    for producto in productos:

        try:

            resultado.append(
                ProbadorService.preparar_producto(
                    producto
                )
            )

        except Exception:
            continue

    return jsonify({
        "success": True,
        "productos": resultado
    })


# ==========================================================
# GUARDAR OUTFIT
# ==========================================================

def guardar_outfit():

    datos = request.get_json()

    if not datos:

        return jsonify({
            "success": False,
            "message": "No se recibieron datos."
        }), 400

    probador_id = datos.get(
        "probador_id"
    )

    productos = datos.get(
        "productos",
        []
    )

    if not probador_id:

        return jsonify({
            "success": False,
            "message": "Falta el identificador del probador."
        }), 400

    if not isinstance(productos, list):

        return jsonify({
            "success": False,
            "message": "Los productos deben ser una lista."
        }), 400

    try:

        actualizado = ProbadorVirtual.actualizar(
            current_app.db,
            probador_id,
            {
                "productos_seleccionados": productos,
                "estado": "outfit_seleccionado"
            }
        )

        if not actualizado:

            return jsonify({
                "success": False,
                "message": "No se pudo guardar el outfit."
            }), 404

        return jsonify({
            "success": True,
            "message": "Outfit guardado correctamente."
        })

    except Exception as e:

        print(
            f"ERROR guardar outfit: {e}"
        )

        return jsonify({
            "success": False,
            "message": "Error al guardar el outfit."
        }), 500


# ==========================================================
# HILO DE FONDO: EJECUTA LA IA SIN BLOQUEAR LA PETICIÓN HTTP
# ==========================================================

def _ejecutar_generacion_en_hilo(app, probador_id, foto_usuario, productos):
    """
    La generación con IDM-VTON puede tardar entre ~10 y ~40 segundos
    por prenda. Si lo corriéramos directo dentro de generar_simulacion(),
    el navegador se quedaría esperando ese tiempo en la misma petición
    (y muchos proxies/timeouts la cortarían). Por eso corremos la
    generación en un hilo aparte: la petición HTTP responde de
    inmediato con estado "generando", y el frontend consulta
    /probador/estado/<id> cada par de segundos hasta que termine.
    """

    with app.app_context():

        db = app.db

        try:

            nombre_resultado = generar_outfit_completo(
                app,
                foto_usuario,
                productos
            )

            ProbadorVirtual.actualizar(
                db,
                probador_id,
                {
                    "estado": "completado",
                    "resultado": nombre_resultado
                }
            )

        except Exception as e:

            print(f"ERROR generando outfit con IA: {e}")

            ProbadorVirtual.actualizar(
                db,
                probador_id,
                {
                    "estado": "error",
                    "error_mensaje": str(e)
                }
            )


# ==========================================================
# GENERAR SIMULACIÓN (ahora sí llama al motor de IA real)
# ==========================================================

def generar_simulacion():

    datos = request.get_json()

    if not datos:

        return jsonify({
            "success": False,
            "message": "No se recibieron datos."
        }), 400

    probador_id = datos.get(
        "probador_id"
    )

    productos_ids = datos.get(
        "productos",
        []
    )

    if not probador_id:

        return jsonify({
            "success": False,
            "message": "Falta el probador_id."
        }), 400

    if not productos_ids:

        return jsonify({
            "success": False,
            "message": (
                "Selecciona al menos una prenda."
            )
        }), 400

    try:

        probador = (
            ProbadorVirtual.obtener_por_id(
                current_app.db,
                probador_id
            )
        )

        if not probador:

            return jsonify({
                "success": False,
                "message": "Sesión de probador no encontrada."
            }), 404

        if not probador.get("foto_usuario"):

            return jsonify({
                "success": False,
                "message": "Primero sube tu fotografía."
            }), 400

        productos = []

        for producto_id in productos_ids:

            try:

                producto = (
                    ProductoModel.obtener_por_id(
                        producto_id
                    )
                )

                if producto:

                    productos.append(
                        ProbadorService.preparar_producto(
                            producto
                        )
                    )

            except Exception:
                continue

        if not productos:

            return jsonify({
                "success": False,
                "message": "No se encontraron los productos."
            }), 404

        ProbadorVirtual.actualizar(
            current_app.db,
            probador_id,
            {
                "productos_seleccionados": productos,
                "estado": "generando",
                "resultado": None,
                "error_mensaje": None
            }
        )

        # Objeto real de la app (no el proxy current_app) para
        # poder usarlo dentro del hilo de fondo.
        app_real = current_app._get_current_object()

        hilo = threading.Thread(
            target=_ejecutar_generacion_en_hilo,
            args=(
                app_real,
                probador_id,
                probador["foto_usuario"],
                productos
            ),
            daemon=True
        )

        hilo.start()

        return jsonify({
            "success": True,
            "message": "Generando tu simulación con IA...",
            "probador_id": probador_id,
            "estado": "generando"
        })

    except Exception as e:

        print(
            f"ERROR generar simulación: {e}"
        )

        return jsonify({
            "success": False,
            "message": "Error al generar la simulación."
        }), 500


# ==========================================================
# CONSULTAR ESTADO DE LA SIMULACIÓN (usado por polling del frontend)
# ==========================================================

def obtener_estado_simulacion(probador_id):

    try:

        probador = ProbadorVirtual.obtener_por_id(
            current_app.db,
            probador_id
        )

        if not probador:

            return jsonify({
                "success": False,
                "message": "Sesión de probador no encontrada."
            }), 404

        estado = probador.get("estado", "desconocido")

        respuesta = {
            "success": True,
            "estado": estado
        }

        if estado == "completado" and probador.get("resultado"):

            respuesta["resultado_url"] = (
                "/static/uploads/probador/resultados/"
                + probador["resultado"]
            )

        if estado == "error":

            respuesta["message"] = probador.get(
                "error_mensaje",
                "Ocurrió un error al generar la simulación."
            )

        return jsonify(respuesta)

    except Exception as e:

        print(f"ERROR obtener estado: {e}")

        return jsonify({
            "success": False,
            "message": "Error al consultar el estado."
        }), 500