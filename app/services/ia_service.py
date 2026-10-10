"""
app/services/ia_service.py

Motor de prueba virtual (Virtual Try-On) usando el Space gratuito
IDM-VTON de Hugging Face a través de gradio_client.
Reemplaza por completo la integración anterior con pollinations.ai.

Instalar:
    pip install gradio_client pillow

Variable de entorno recomendada (gratis, da más cuota):
    HF_TOKEN=hf_xxxxxxxxxxxxxxxxx     (https://huggingface.co/settings/tokens)

Contrato (el que ya usa tu controlador):
    generar_outfit_completo(app, foto_usuario, productos) -> nombre_archivo_resultado
      - app:          instancia real de Flask
      - foto_usuario: nombre del archivo en static/uploads/probador/
      - productos:    lista de dicts de ProbadorService.preparar_producto()
                      (usa las claves: nombre, descripcion, foto)
    El resultado se guarda en static/uploads/probador/resultados/
"""
import os
import time
import uuid
import shutil
import tempfile
import threading

from PIL import Image
from gradio_client import Client, handle_file

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------
SPACE_IDM = "yisol/IDM-VTON"
HF_TOKEN = os.environ.get("HF_TOKEN")

MAX_LADO_PX = 1024      # se reduce la foto para acelerar la generación
REINTENTOS = 2          # el Space gratuito a veces falla / está en cola
ESPERA_REINTENTO_S = 5
DENOISE_STEPS = 30
SEED = 42

# Prendas que los modelos VTON no soportan
PALABRAS_NO_SOPORTADAS = ("tenis", "zapato", "zapatilla", "bota", "sandalia", "calzado")

# Orden de aplicación: primero lo de abajo / vestidos, al final lo de arriba
ORDEN_CATEGORIAS = {"pantalon": 0, "vestido": 1, "camisa": 2, "chaqueta": 3, "otro": 2}

_client = None
_client_lock = threading.Lock()
# El Space gratuito procesa una petición a la vez; evitamos saturarlo
_generacion_lock = threading.Lock()


# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------
def _get_client():
    """Conexión reutilizable al Space (compatible con versiones nuevas y viejas de gradio_client)."""
    global _client
    with _client_lock:
        if _client is None:
            if HF_TOKEN:
                try:
                    _client = Client(SPACE_IDM, token=HF_TOKEN)
                except TypeError:
                    _client = Client(SPACE_IDM, hf_token=HF_TOKEN)
            else:
                _client = Client(SPACE_IDM)
        return _client


def _reset_client():
    global _client
    with _client_lock:
        _client = None


def _categoria(producto):
    texto = f"{producto.get('nombre', '')} {producto.get('descripcion', '')}".lower()
    if any(p in texto for p in PALABRAS_NO_SOPORTADAS):
        return "no_soportada"
    if "vestido" in texto:
        return "vestido"
    if "pantalon" in texto or "pantalón" in texto or "jeans" in texto or "short" in texto or "falda" in texto:
        return "pantalon"
    if "chaqueta" in texto or "blazer" in texto or "abrigo" in texto:
        return "chaqueta"
    if "camisa" in texto or "playera" in texto or "blusa" in texto or "sudadera" in texto:
        return "camisa"
    return "otro"


def _preparar_imagen(origen, destino_dir, nombre):
    """Convierte a RGB y limita el tamaño. Devuelve la ruta nueva."""
    img = Image.open(origen).convert("RGB")
    img.thumbnail((MAX_LADO_PX, MAX_LADO_PX))
    ruta = os.path.join(destino_dir, nombre)
    img.save(ruta, "JPEG", quality=92)
    return ruta


def _llamar_idm(persona_path, prenda_path, descripcion):
    """Una llamada a IDM-VTON con reintentos. Devuelve ruta local del resultado."""
    ultimo_error = None

    for intento in range(1, REINTENTOS + 1):
        try:
            client = _get_client()
            resultado = client.predict(
                dict={
                    "background": handle_file(persona_path),
                    "layers": [],
                    "composite": None,
                },
                garm_img=handle_file(prenda_path),
                garment_des=descripcion or "clothing",
                is_checked=True,         # máscara automática
                is_checked_crop=False,   # no recortar
                denoise_steps=DENOISE_STEPS,
                seed=SEED,
                api_name="/tryon",
            )
            # IDM-VTON devuelve (imagen_resultado, imagen_mascara)
            salida = resultado[0] if isinstance(resultado, (list, tuple)) else resultado
            if salida and os.path.exists(salida):
                return salida
            raise RuntimeError("El Space no devolvió una imagen válida.")

        except Exception as e:
            ultimo_error = e
            print(f"[VTON] intento {intento}/{REINTENTOS} falló: {e}")
            _reset_client()
            if intento < REINTENTOS:
                time.sleep(ESPERA_REINTENTO_S)

    raise RuntimeError(
        "El servicio de prueba virtual está ocupado o no disponible. "
        f"Intenta de nuevo en un momento. ({ultimo_error})"
    )


# ----------------------------------------------------------------------
# FUNCIÓN PÚBLICA
# ----------------------------------------------------------------------
def generar_outfit_completo(app, foto_usuario, productos):
    """
    Aplica cada prenda en cadena: el resultado de una prenda se usa
    como "persona" para la siguiente. Devuelve el nombre del archivo final.
    """
    carpeta_probador = os.path.join(app.static_folder, "uploads", "probador")
    carpeta_productos = os.path.join(app.static_folder, "uploads", "productos")
    carpeta_resultados = os.path.join(carpeta_probador, "resultados")
    os.makedirs(carpeta_resultados, exist_ok=True)

    foto_origen = os.path.join(carpeta_probador, foto_usuario)
    if not os.path.exists(foto_origen):
        raise FileNotFoundError("No se encontró la fotografía del usuario.")

    # Filtrar prendas no soportadas y ordenar
    soportadas = []
    omitidas = []
    for p in productos:
        cat = _categoria(p)
        if cat == "no_soportada":
            omitidas.append(p.get("nombre", "prenda"))
        else:
            soportadas.append((cat, p))

    if not soportadas:
        raise RuntimeError(
            "Las prendas seleccionadas (calzado) no se pueden probar virtualmente. "
            "Elige ropa: camisas, vestidos, pantalones o chaquetas."
        )

    soportadas.sort(key=lambda x: ORDEN_CATEGORIAS.get(x[0], 2))

    tmp_dir = tempfile.mkdtemp(prefix="vton_")

    try:
        actual = _preparar_imagen(foto_origen, tmp_dir, "persona_0.jpg")

        # Un solo trabajo a la vez contra el Space gratuito
        with _generacion_lock:
            for i, (cat, prod) in enumerate(soportadas, start=1):
                nombre_foto = prod.get("foto")
                if not nombre_foto:
                    print(f"[VTON] '{prod.get('nombre')}' no tiene foto, se omite.")
                    continue

                prenda_src = os.path.join(carpeta_productos, nombre_foto)
                if not os.path.exists(prenda_src):
                    print(f"[VTON] no existe el archivo {prenda_src}, se omite.")
                    continue

                prenda_path = _preparar_imagen(prenda_src, tmp_dir, f"prenda_{i}.jpg")
                descripcion = (prod.get("nombre") or "clothing")[:80]

                salida = _llamar_idm(actual, prenda_path, descripcion)

                # El resultado pasa a ser la "persona" de la siguiente prenda
                siguiente = os.path.join(tmp_dir, f"persona_{i}.jpg")
                Image.open(salida).convert("RGB").save(siguiente, "JPEG", quality=92)
                actual = siguiente

        # Si nunca se generó nada, actual sigue siendo persona_0
        if os.path.basename(actual) == "persona_0.jpg":
            raise RuntimeError("No se pudo aplicar ninguna prenda (faltan fotos de producto).")

        nombre_final = f"outfit_{uuid.uuid4().hex}.jpg"
        shutil.copyfile(actual, os.path.join(carpeta_resultados, nombre_final))

        if omitidas:
            print(f"[VTON] prendas omitidas (no soportadas): {', '.join(omitidas)}")

        return nombre_final

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)