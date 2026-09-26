"""
ia_service.py - Versión con Pollinations.ai (GRATIS) - FUNCIONAL
==========================================================
"""
import os
import uuid
import urllib.parse
import requests
from flask import current_app


# ==========================================================
# CONFIGURACIÓN DE POLLINATIONS
# ==========================================================

POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"
MODELO_POLLINATIONS = "turbo"  # Más estable que flux
ANCHO = 768
ALTO = 768


# ==========================================================
# UTILIDADES
# ==========================================================

def inferir_categoria_prenda(producto):
    """Infiere si la prenda es superior, inferior o vestido"""
    texto = (
        (producto.get("nombre", "") or "") + " " +
        (producto.get("descripcion", "") or "")
    ).lower()

    palabras_lower = ["pantalon", "pantalón", "short", "bermuda", "falda", "jean", "jeans", "leggin"]
    palabras_dress = ["vestido", "enterizo", "jumpsuit", "overol"]

    for palabra in palabras_dress:
        if palabra in texto:
            return "vestido"

    for palabra in palabras_lower:
        if palabra in texto:
            return "pantalón"

    return "camisa"


def _carpeta_resultados(current_app):
    carpeta = os.path.join(
        current_app.root_path,
        "static", "uploads", "probador", "resultados"
    )
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


# ==========================================================
# FUNCIÓN PRINCIPAL - GENERAR OUTFIT CON POLLINATIONS
# ==========================================================

def generar_outfit_completo(current_app, foto_usuario_nombre, productos):
    """
    Genera una imagen usando Pollinations.ai con el outfit seleccionado.
    """
    
    if not productos:
        raise ValueError("No hay productos para generar el outfit")
    
    # --- PROMPT EN INGLÉS, CORTO Y SIN CARACTERES ESPECIALES ---
    
    # Tomar solo nombres limpios (máximo 2 productos)
    nombres = []
    for producto in productos[:2]:
        nombre = producto.get("nombre", "clothing")
        # Limpiar nombre: eliminar apóstrofes, acentos, etc.
        nombre = nombre.replace("'", "").replace('"', "").replace("á", "a").replace("é", "e")
        nombre = nombre.replace("í", "i").replace("ó", "o").replace("ú", "u")
        # Traducción básica al inglés
        nombre = nombre.replace("vestido", "dress")
        nombre = nombre.replace("pantalón", "pants")
        nombre = nombre.replace("camisa", "shirt")
        nombre = nombre.replace("zapatilla", "shoes")
        nombre = nombre.replace("casual", "")
        nombres.append(nombre.strip())
    
    # Prompt en inglés, simple y corto
    if len(nombres) == 1:
        prompt = f"a person wearing {nombres[0]}, fashion photography, studio lighting"
    else:
        prompt = f"a person wearing {', '.join(nombres)}, fashion photography, studio lighting"
    
    # Limpiar espacios dobles
    prompt = " ".join(prompt.split())
    
    # Codificar para URL
    prompt_codificado = urllib.parse.quote(prompt)
    
    # URLs de respaldo con diferentes modelos
    urls = [
        f"https://image.pollinations.ai/prompt/{prompt_codificado}?width={ANCHO}&height={ALTO}&model=turbo&nologo=true",
        f"https://image.pollinations.ai/prompt/{prompt_codificado}?width={ANCHO}&height={ALTO}&model=openjourney&nologo=true",
        f"https://image.pollinations.ai/prompt/{prompt_codificado}?width={ANCHO}&height={ALTO}&model=flux&nologo=true",
        f"https://image.pollinations.ai/prompt/{prompt_codificado}?width={ANCHO}&height={ALTO}&model=sdxl&nologo=true",
    ]
    
    print(f"🎨 Generando imagen con Pollinations...")
    print(f"📝 Prompt: {prompt}")
    
    ultimo_error = None
    
    for i, url in enumerate(urls):
        try:
            print(f"🔄 Intento {i+1} de {len(urls)}...")
            response = requests.get(url, timeout=45)
            
            if response.status_code == 200:
                # Guardar imagen
                carpeta_resultados = _carpeta_resultados(current_app)
                nombre_archivo = f"outfit_{uuid.uuid4().hex}.jpg"
                ruta_archivo = os.path.join(carpeta_resultados, nombre_archivo)
                
                with open(ruta_archivo, "wb") as f:
                    f.write(response.content)
                
                print(f"✅ Imagen generada: {nombre_archivo}")
                return nombre_archivo
            else:
                print(f"⚠️ Código {response.status_code} en intento {i+1}")
                ultimo_error = f"Error {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"⏰ Timeout en intento {i+1}")
            ultimo_error = "Timeout"
        except Exception as e:
            print(f"❌ Error en intento {i+1}: {str(e)}")
            ultimo_error = str(e)
    
    # Si todo falló, intentar con un prompt ultra simple
    print("🔄 Último intento con prompt ultra simple...")
    try:
        prompt_simple = "fashion model, studio lighting"
        prompt_codificado = urllib.parse.quote(prompt_simple)
        url = f"https://image.pollinations.ai/prompt/{prompt_codificado}?model=turbo&nologo=true"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            carpeta_resultados = _carpeta_resultados(current_app)
            nombre_archivo = f"outfit_{uuid.uuid4().hex}.jpg"
            ruta_archivo = os.path.join(carpeta_resultados, nombre_archivo)
            
            with open(ruta_archivo, "wb") as f:
                f.write(response.content)
            
            print(f"✅ Imagen generada (ultra simple): {nombre_archivo}")
            return nombre_archivo
    except Exception as e:
        print(f"❌ Último intento falló: {str(e)}")
    
    raise RuntimeError(f"No se pudo generar la imagen. Último error: {ultimo_error}")