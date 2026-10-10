"""
app/routes/tryon_outfit.py  ->  app.include_router(tryon_outfit.router)

"Probar outfit": el usuario sube una foto de cuerpo completo, elige 1..N productos
(vestido, camisa, pantalón, chaqueta, tenis, accesorios) y la API devuelve la foto
con esas prendas puestas.

Usa el API de FASHN (modelo "tryon-max", que soporta ropa, zapatos, sombreros, joyería y bolsas).
Cada producto es una generación; se aplican en cadena: la salida de una es la entrada de la siguiente.
La generación tarda segundos, así que es asíncrona: POST crea un job y el cliente consulta su estado.

Variables de entorno:  FASHN_API_KEY
requirements.txt:      httpx, python-multipart
Productos (colección `products`): image_url, name, category y, opcional, tryon_category
                       ("one-pieces" | "bottoms" | "tops" | "shoes" | "accessory") para no depender de adivinar.
"""
import asyncio
import base64
import os
import uuid
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.database import db  # AJUSTAR: tu conexión a MongoDB (motor)

router = APIRouter(prefix="/api/tryon", tags=["tryon"])

FASHN = "https://api.fashn.ai/v1"
KEY = os.getenv("FASHN_API_KEY", "")
ORDER = ["one-pieces", "bottoms", "tops", "shoes", "accessory"]  # orden de aplicación
MAX_PRODUCTS = 5
MAX_BYTES = 10_000_000


async def init_tryon_indexes():
    """Llamar al arrancar la app: borra los jobs (y sus imágenes) a las 24 h."""
    await db.tryon_jobs.create_index("created_at", expireAfterSeconds=86400)


def classify(p: dict) -> str:
    if p.get("tryon_category") in ORDER:
        return p["tryon_category"]
    t = f"{p.get('category', '')} {p.get('name', '')}".lower()
    if any(k in t for k in ("vestido", "dress", "enterizo", "jumpsuit")):
        return "one-pieces"
    if any(k in t for k in ("pantal", "jean", "falda", "short")):
        return "bottoms"
    if any(k in t for k in ("tenis", "zapat", "bota", "sandal", "calzado")):
        return "shoes"
    if any(k in t for k in ("camisa", "playera", "blusa", "chaqueta", "suéter", "sueter", "sudadera", "abrigo")):
        return "tops"
    return "accessory"


def _data_uri(img: bytes) -> str:
    mime = "image/png" if img[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(img).decode()


async def _step(http: httpx.AsyncClient, person: bytes, product_url: str, cat: str) -> bytes:
    h = {"Authorization": f"Bearer {KEY}"}
    body = {
        "model_name": "tryon-max",
        "inputs": {
            "model_image": _data_uri(person),
            "product_image": product_url,
            "prompt": f"The person is wearing this product ({cat}). Keep face, body, pose and the rest of the outfit unchanged.",
        },
    }
    r = await http.post(f"{FASHN}/run", json=body, headers=h)
    r.raise_for_status()
    pid = r.json()["id"]
    for _ in range(90):  # hasta ~3 min por producto
        await asyncio.sleep(2)
        s = (await http.get(f"{FASHN}/status/{pid}", headers=h)).json()
        if s["status"] == "completed":
            return (await http.get(s["output"][0])).content
        if s["status"] == "failed":
            raise RuntimeError(str(s.get("error"))[:200])
    raise TimeoutError("El proveedor tardó demasiado")


async def _run_job(job_id: str, photo: bytes, items: list[tuple[str, str]]):
    try:
        img = photo
        async with httpx.AsyncClient(timeout=60) as http:
            for i, (cat, url) in enumerate(items, 1):
                img = await _step(http, img, url, cat)
                await db.tryon_jobs.update_one({"_id": job_id}, {"$set": {"done": i}})
        await db.tryon_jobs.update_one({"_id": job_id}, {"$set": {"status": "done", "image": img}})
    except Exception as e:  # noqa: BLE001
        await db.tryon_jobs.update_one({"_id": job_id}, {"$set": {"status": "error", "error": str(e)[:300]}})


@router.post("/outfit")
async def create_outfit(
    background: BackgroundTasks,
    photo: UploadFile = File(..., description="Foto de cuerpo completo"),
    product_ids: list[str] = Form(...),
):
    if not KEY:
        raise HTTPException(503, "Falta configurar FASHN_API_KEY")
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen")
    data = await photo.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Imagen demasiado grande (máx. 10 MB)")
    if not 1 <= len(product_ids) <= MAX_PRODUCTS:
        raise HTTPException(400, f"Elige entre 1 y {MAX_PRODUCTS} productos")

    try:
        oids = [ObjectId(i) for i in product_ids]  # AJUSTAR si tus ids no son ObjectId
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "product_ids inválidos")
    prods = await db.products.find({"_id": {"$in": oids}}).to_list(MAX_PRODUCTS)
    if len(prods) != len(set(product_ids)):
        raise HTTPException(404, "Algún producto no existe")

    items = sorted(
        ((classify(p), p["image_url"]) for p in prods if p.get("image_url")),
        key=lambda x: ORDER.index(x[0]),
    )
    if not items:
        raise HTTPException(400, "Los productos no tienen imagen")

    job_id = uuid.uuid4().hex  # TODO: guarda también el user_id y valida que el GET sea del mismo usuario
    await db.tryon_jobs.insert_one({
        "_id": job_id, "status": "processing", "done": 0, "total": len(items),
        "created_at": datetime.now(timezone.utc),
    })
    background.add_task(_run_job, job_id, data, items)
    return {"job_id": job_id, "total": len(items)}


@router.get("/outfit/{job_id}")
async def outfit_status(job_id: str):
    job = await db.tryon_jobs.find_one({"_id": job_id}, {"image": 0})
    if not job:
        raise HTTPException(404, "Job no encontrado o expirado")
    return {k: job.get(k) for k in ("status", "done", "total", "error")}


@router.get("/outfit/{job_id}/image")
async def outfit_image(job_id: str):
    job = await db.tryon_jobs.find_one({"_id": job_id})
    if not job or job.get("status") != "done":
        raise HTTPException(404, "Imagen no disponible")
    return Response(bytes(job["image"]), media_type="image/png")