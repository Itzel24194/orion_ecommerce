import os
import uuid
from werkzeug.utils import secure_filename


EXTENSIONES_PERMITIDAS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
}


class ProbadorService:

    @staticmethod
    def obtener_carpeta_upload(current_app):

        carpeta = os.path.join(
            current_app.root_path,
            "static",
            "uploads",
            "probador"
        )

        os.makedirs(carpeta, exist_ok=True)

        return carpeta

    @staticmethod
    def guardar_fotografia(current_app, archivo):

        if not archivo:
            raise ValueError("No se recibió ninguna fotografía.")

        if not archivo.filename:
            raise ValueError("El archivo no tiene nombre.")

        nombre_original = secure_filename(archivo.filename)

        extension = os.path.splitext(
            nombre_original
        )[1].lower()

        if extension not in EXTENSIONES_PERMITIDAS:
            raise ValueError(
                "Formato no permitido. "
                "Usa JPG, JPEG, PNG o WEBP."
            )

        nombre = (
            f"probador_"
            f"{uuid.uuid4().hex}"
            f"{extension}"
        )

        carpeta = ProbadorService.obtener_carpeta_upload(
            current_app
        )

        ruta = os.path.join(
            carpeta,
            nombre
        )

        archivo.save(ruta)

        return nombre

    @staticmethod
    def validar_fotografia(archivo):

        if not archivo:
            return False, "Debes seleccionar una fotografía."

        if not archivo.filename:
            return False, "No se seleccionó ninguna fotografía."

        extension = os.path.splitext(
            archivo.filename
        )[1].lower()

        if extension not in EXTENSIONES_PERMITIDAS:
            return False, (
                "Formato no válido. "
                "Usa JPG, JPEG, PNG o WEBP."
            )

        return True, None

    @staticmethod
    def preparar_producto(producto):

        foto = ""

        if producto.get("fotos"):
            foto = producto["fotos"][0]

        precio = 0

        if producto.get("variables"):
            if len(producto["variables"]) > 0:
                precio = producto["variables"][0].get(
                    "precio",
                    0
                )

        if not precio:
            precio = producto.get(
                "precio",
                0
            )

        return {
            "id": str(producto["_id"]),
            "nombre": producto.get(
                "nombre",
                ""
            ),
            "descripcion": producto.get(
                "descripcion",
                ""
            ),
            "categoria_id": str(
                producto.get(
                    "categoria_id",
                    ""
                )
            ),
            "marca_id": str(
                producto.get(
                    "marca_id",
                    ""
                )
            ),
            "genero": producto.get(
                "genero",
                ""
            ),
            "marca": producto.get(
                "marca",
                ""
            ),
            "color": producto.get(
                "color",
                ""
            ),
            "material": producto.get(
                "material",
                ""
            ),
            "precio": precio,
            "foto": foto
        }

    @staticmethod
    def construir_recomendaciones(productos, producto_base=None):

        resultado = []

        for producto in productos:

            if producto_base:

                if str(producto.get("_id")) == str(
                    producto_base.get("_id")
                ):
                    continue

            resultado.append(
                ProbadorService.preparar_producto(
                    producto
                )
            )

        return resultado[:12]