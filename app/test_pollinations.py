# test_pollinations.py - COLOCAR EN C:\proyectos\proyecto\
import requests
import urllib.parse

print("🧪 Probando Pollinations.ai...")

# Prueba con el prompt más simple posible
prompt = "fashion model studio lighting"
prompt_codificado = urllib.parse.quote(prompt)
url = f"https://image.pollinations.ai/prompt/{prompt_codificado}?model=turbo&nologo=true"

print(f"📡 URL: {url[:80]}...")
print("⏳ Esperando respuesta...")

try:
    response = requests.get(url, timeout=30)
    print(f"✅ Status code: {response.status_code}")
    
    if response.status_code == 200:
        with open("test_pollinations.jpg", "wb") as f:
            f.write(response.content)
        print("✅ ¡Imagen guardada como 'test_pollinations.jpg'!")
        print("📸 Abre el archivo para verificar que funciona.")
    else:
        print(f"❌ Error: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Excepción: {str(e)}")