import os
import re
import time
import unicodedata
import uuid

from flask import current_app
from PIL import Image, ImageOps

EXT_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}
MAX_BYTES = 10 * 1024 * 1024      # 10 MB
LADO_MIN = 400                    # px
LADO_MAX = 1600                   # px (se reduce si es más grande)


# ==========================================================
# CLASIFICACIÓN DE PRODUCTOS (qué se puede probar y en qué capa)
# ==========================================================

def _norm(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _patron(palabras):
    return re.compile(r"\b(?:" + "|".join(palabras) + r")(?:s|es)?\b")


# (clave, patrón, categoria_probador, grupo/filtro, orden de capa)
_REGLAS = [
    ("vestido", _patron(["vestido", "dress", "enterizo", "jumpsuit", "overol", "mameluco"]),
     "one-pieces", "vestidos", 0),
    ("calzado", _patron(["tenis", "zapato", "zapatilla", "bota", "botin", "sandalia",
                         "calzado", "mocasin", "huarache", "sneaker", "shoe"]),
     "shoes", "tenis", 4),
    ("exterior", _patron(["chaqueta", "chamarra", "abrigo", "blazer", "gabardina", "sudadera",
                          "sueter", "cardigan", "saco", "poncho", "jacket", "hoodie", "coat"]),
     "tops", "chaquetas", 3),
    ("superior", _patron(["camisa", "playera", "blusa", "camiseta", "polo", "jersey", "top",
                          "shirt", "tank", "crop"]),
     "tops", "camisas", 2),
    ("inferior", _patron(["pantalon", "jean", "falda", "short", "bermuda", "legging",
                          "leggin", "jogger", "skirt", "pants"]),
     "bottoms", "pantalones", 1),
    ("accesorio", _patron(["gorra", "sombrero", "lente", "gafas", "reloj", "collar", "arete",
                           "pulsera", "bolsa", "bolso", "mochila", "cinturon", "bufanda",
                           "guante", "anillo", "accesorio", "cartera"]),
     "accessory", "accesorios", 5),
]


def _clasificar(texto):
    t = _norm(texto)
    for _, patron, cat, grupo, capa in _REGLAS:
        if patron.search(t):
            return cat, grupo, capa
    return None


_CACHE_CATS = {"ts": 0.0, "data": {}}


def _categorias(db):
    """Categorías en memoria durante 60 s para no consultar Mongo por cada producto."""
    if time.time() - _CACHE_CATS["ts"] > 60:
        _CACHE_CATS["data"] = {
            str(c["_id"]): c
            for c in db.categorias.find({}, {"nombre": 1, "padre_id": 1})
        }
        _CACHE_CATS["ts"] = time.time()
    return _CACHE_CATS["data"]


def _primera_imagen(p):
    cand = p.get("imagen") or p.get("foto") or p.get("imagen_principal")

    if not cand:
        imgs = p.get("imagenes") or p.get("fotos") or []
        if isinstance(imgs, (list, tuple)) and imgs:
            cand = imgs[0]
        elif isinstance(imgs, str):
            cand = imgs

    if isinstance(cand, dict):
        cand = (cand.get("url") or cand.get("archivo")
                or cand.get("nombre") or cand.get("filename"))

    return str(cand).strip() if cand else None


class ProbadorService:

    # ------------------------------------------------------
    # Prepara un producto para el probador (o lanza ValueError
    # si no se puede probar: electrónica, sin imagen, etc.)
    # ------------------------------------------------------
    @staticmethod
    def preparar_producto(producto):

        nombre = producto.get("nombre") or ""

        cats = _categorias(current_app.db)
        cat_doc = cats.get(str(producto.get("categoria_id") or producto.get("categoria")))
        padre_doc = cats.get(str(cat_doc.get("padre_id"))) if cat_doc else None

        texto_cats = " ".join(filter(None, [
            cat_doc.get("nombre") if cat_doc else None,
            padre_doc.get("nombre") if padre_doc else None,
            producto.get("categoria") if isinstance(producto.get("categoria"), str) else None,
            producto.get("tipo"),
        ]))

        clasif = _clasificar(nombre) or _clasificar(texto_cats)

        if not clasif:
            raise ValueError("Este producto no se puede probar virtualmente.")

        cat_probador, grupo, capa = clasif

        imagen = _primera_imagen(producto)

        if not imagen:
            raise ValueError("El producto no tiene imagen.")

        if imagen.lower().startswith(("http://", "https://")):
            archivo = None
            url = imagen
        else:
            archivo = os.path.basename(imagen)
            url = f"/static/uploads/productos/{archivo}"

        try:
            precio = float(producto.get("precio") or producto.get("precio_venta") or 0)
        except (TypeError, ValueError):
            precio = 0.0

        etiqueta = ("Tenis" if cat_probador == "shoes"
                    else "Accesorio" if cat_probador == "accessory"
                    else "Prenda")

        pid = str(producto["_id"])

        return {
            "id": pid,
            "_id": pid,
            "nombre": nombre,
            "descripcion": producto.get("descripcion") or "",
            "precio": precio,
            "imagen": url,
            "imagen_url": url,
            "imagen_archivo": archivo,
            "categoria": cat_doc.get("nombre") if cat_doc else "",
            "tipo": etiqueta,
            "grupo": grupo,                       # vestidos | camisas | pantalones | tenis | chaquetas | accesorios
            "categoria_probador": cat_probador,   # one-pieces | tops | bottoms | shoes | accessory
            "orden_capa": capa,
        }

    # ------------------------------------------------------
    # Valida la fotografía subida
    # ------------------------------------------------------
    @staticmethod
    def validar_fotografia(archivo):

        if not archivo or not archivo.filename:
            return False, "No se seleccionó ninguna fotografía."

        ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else ""

        if ext not in EXT_PERMITIDAS:
            return False, "Formato no permitido. Usa JPG, PNG o WEBP."

        archivo.stream.seek(0, os.SEEK_END)
        tam = archivo.stream.tell()
        archivo.stream.seek(0)

        if tam == 0:
            return False, "El archivo está vacío."

        if tam > MAX_BYTES:
            return False, "La fotografía pesa más de 10 MB."

        try:
            img = Image.open(archivo.stream)
            img = ImageOps.exif_transpose(img)
            img.load()
            ancho, alto = img.size
        except Exception:
            return False, "El archivo no es una imagen válida."
        finally:
            archivo.stream.seek(0)

        if min(ancho, alto) < LADO_MIN:
            return False, f"La fotografía es muy pequeña (mínimo {LADO_MIN} px por lado)."

        if ancho > alto * 1.15:
            return False, "Sube una fotografía vertical, de cuerpo completo y de frente."

        return True, "OK"

    # ------------------------------------------------------
    # Guarda la foto (corrige rotación, quita metadatos/GPS,
    # reduce tamaño y usa un nombre imposible de adivinar)
    # ------------------------------------------------------
    @staticmethod
    def guardar_fotografia(app, archivo):

        carpeta = os.path.join(app.config["UPLOAD_FOLDER"], "probador")
        os.makedirs(carpeta, exist_ok=True)

        img = Image.open(archivo.stream)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((LADO_MAX, LADO_MAX))

        nombre = f"foto_{uuid.uuid4().hex}.jpg"
        img.save(os.path.join(carpeta, nombre), "JPEG", quality=92)

        return nombre