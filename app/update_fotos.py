from pymongo import MongoClient
import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar .env (igual que tu app)
BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / '.env', override=True)

# Conexión
client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
db = client["orioon"]

print("🔄 Actualizando nombres de fotos y videos (.avif → .jpg)...\n")

total = 0
for p in db.productos.find({}):
    cambios = False

    if isinstance(p.get('fotos'), list) and p['fotos']:
        nuevas = [f.replace('.avif', '.jpg') if isinstance(f, str) else f for f in p['fotos']]
        if nuevas != p['fotos']:
            p['fotos'] = nuevas
            cambios = True

    if isinstance(p.get('videos'), list) and p['videos']:
        nuevos = [v.replace('.avif', '.jpg') if isinstance(v, str) else v for v in p['videos']]
        if nuevos != p['videos']:
            p['videos'] = nuevos
            cambios = True

    if cambios:
        db.productos.update_one(
            {'_id': p['_id']},
            {'$set': {'fotos': p['fotos'], 'videos': p.get('videos', [])}}
        )
        total += 1
        print(f"✅ {p.get('nombre', 'sin nombre')}")

print(f"\n🎉 Total actualizados: {total}")

# Verificación
print("\n📋 Verificación (primeros 3 productos):")
for p in db.productos.find({}, {'nombre': 1, 'fotos': 1}).limit(3):
    print(f"  • {p.get('nombre')}: {p.get('fotos')}")