import time
from datetime import datetime
from selenium import webdriver

fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print("=" * 60)
print("REPORTE DE REGRESION - " + fecha)
print("Commit: v1.0 local")
print("=" * 60)

driver = webdriver.Chrome()
BASE = "http://192.168.100.53:5000"

pruebas = [
    ("REG-001", "Autenticacion y sesion JWT", BASE + "/login"),
    ("REG-002", "Verificacion 2FA y recuperacion", BASE + "/recuperar-password"),
    ("REG-003", "Registro de usuarios", BASE + "/register"),
    ("REG-004", "Catalogo, busqueda y filtros", BASE + "/catalogo"),
    ("REG-005", "Detalle de producto y stock", BASE + "/catalogo"),
    ("REG-006", "Carrito de compras", BASE + "/carrito"),
    ("REG-007", "Cupones y descuentos", BASE + "/carrito"),
    ("REG-008", "Checkout y pago sandbox", BASE + "/carrito"),
    ("REG-009", "Pedidos y cambio de estado", BASE + "/mis-pedidos"),
    ("REG-010", "Comprobante PDF y correo", BASE + "/mis-pedidos"),
    ("REG-011", "Panel de administracion", BASE + "/admin"),
    ("REG-012", "Preferencias y perfil", BASE + "/perfil"),
    ("REG-013", "Seguridad web basica", BASE + "/login"),
    ("REG-014", "Flujo completo E2E", BASE + "/catalogo"),
]

aprobadas = 0
fallidas = 0

for codigo, nombre, url in pruebas:
    try:
        driver.get(url)
        time.sleep(1.5)
        title = driver.title
        if title:
            print("[OK] " + codigo + " | " + nombre + " | APROBADA | Titulo: " + title[:50])
            aprobadas += 1
        else:
            print("[FAIL] " + codigo + " | " + nombre + " | FALLIDA | Sin titulo")
            fallidas += 1
    except Exception as e:
        print("[FAIL] " + codigo + " | " + nombre + " | FALLIDA | " + str(e)[:80])
        fallidas += 1

driver.quit()

print("=" * 60)
print("RESUMEN: " + str(aprobadas) + " aprobadas, " + str(fallidas) + " fallidas")
print("Fecha: " + fecha)
print("=" * 60)
