from pymongo import MongoClient
import re

c = MongoClient("mongodb://localhost:27017")
db = c["orioon"]

# Buscar cualquier rol que NO sea cliente ni vendedor exacto
print("=== ROLES ÚNICOS EN LA BD ===")
roles = db.usuarios.distinct("rol")
print(roles)

print("\n=== USUARIOS CON ROL QUE NO ES 'cliente' NI 'vendedor' ===")
for u in db.usuarios.find(
    {"rol": {"$nin": ["cliente", "vendedor"]}},
    {"email": 1, "rol": 1, "confirmado": 1, "activo": 1}
):
    print(u)

print("\n=== BUSQUEDA CASE-INSENSITIVE DE 'admin' ===")
for u in db.usuarios.find(
    {"rol": {"$regex": "admin", "$options": "i"}},
    {"email": 1, "rol": 1, "confirmado": 1, "activo": 1}
):
    print(u)