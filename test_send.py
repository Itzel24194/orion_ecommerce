import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from pathlib import Path

# 1. Cargar .env desde la raíz del proyecto
base_dir = Path(__file__).parent
load_dotenv(dotenv_path=base_dir / '.env', override=True)

# 2. Obtener credenciales
smtp_server = os.getenv('MAIL_SERVER')
smtp_port = int(os.getenv('MAIL_PORT', 587))
username = os.getenv('MAIL_USERNAME')
password = os.getenv('MAIL_PASSWORD')
sender = os.getenv('MAIL_DEFAULT_SENDER', username)

# 3. IMPORTANTE: Cambia esto por TU correo personal para recibir la prueba
recipient = "recipient@gmail.com"  # <-- ¡CÁMBIALO!
recipient = "recipient"  # <-- ¡CÁMBIALO!

# 4. Verificar credenciales
print(f"🔍 Servidor: {smtp_server}")
print(f"🔍 Puerto: {smtp_port}")
print(f"🔍 Usuario: {username}")
print(f"🔍 Contraseña: {'*' * len(password) if password else 'No cargada'}")
print(f"🔍 Destinatario: {recipient}")

if not username or not password:
    print("❌ Faltan credenciales. Verifica el .env")
    exit(1)

if recipient == "recipient@gmail.com":
    print("⚠️  No olvides cambiar 'recipient' por tu correo personal")
    exit(1)

# 5. Construir mensaje
msg = MIMEMultipart()
msg['From'] = sender
msg['To'] = recipient
msg['Subject'] = "Prueba de correo ORION SYSTEM"
body = """
¡Hola!

Este es un correo de prueba enviado desde ORION SYSTEM.
Si lo recibes, ¡la configuración de correo está funcionando perfectamente!

Saludos,
El equipo de ORION
"""
msg.attach(MIMEText(body, 'plain'))

# 6. Enviar
try:
    print(f"📤 Conectando a {smtp_server}:{smtp_port}...")
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.set_debuglevel(1)          # Muestra logs detallados (opcional)
    server.starttls()
    print("🔑 Iniciando sesión con", username)
    server.login(username, password)
    print("📧 Enviando correo a", recipient)
    server.send_message(msg)
    server.quit()
    print("✅ ¡Correo enviado exitosamente! Revisa tu bandeja.")
except Exception as e:
    print(f"❌ Error: {e}")
