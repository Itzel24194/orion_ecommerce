import os
from pathlib import Path
from dotenv import load_dotenv

# Ruta absoluta al .env
base_dir = Path(__file__).parent  # C:\proyectos\proyecto
env_path = base_dir / '.env'
print(f"📁 Buscando .env en: {env_path}")
print(f"✅ ¿Existe? {env_path.exists()}")

# Cargar con ruta explícita
load_dotenv(dotenv_path=env_path, override=True)

# Verificar que se cargaron
print("\n📧 Variables cargadas:")
print(f"MAIL_SERVER: {os.getenv('MAIL_SERVER')}")
print(f"MAIL_PORT: {os.getenv('MAIL_PORT')}")
print(f"MAIL_USERNAME: {os.getenv('MAIL_USERNAME')}")
print(f"MAIL_PASSWORD: {'*' * len(os.getenv('MAIL_PASSWORD', '')) if os.getenv('MAIL_PASSWORD') else 'No cargada'}")
print(f"MAIL_DEFAULT_SENDER: {os.getenv('MAIL_DEFAULT_SENDER')}")