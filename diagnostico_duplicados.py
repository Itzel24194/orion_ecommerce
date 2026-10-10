# diagnostico_duplicados.py
# Solo diagnostica. NO modifica nada.

from app.config.database_config import db
from bson import ObjectId

# 1. Encontrar TODOS los grupos con numero_pedido duplicado
dups = list(db.pedidos.aggregate([
    {'$group': {
        '_id': '$numero_pedido',
        'count': {'$sum': 1},
        'ids': {'$push': '$_id'}
    }},
    {'$match': {'count': {'$gt': 1}}},
    {'$sort': {'_id': 1}}
]))

if not dups:
    print("✅ No hay numeros_pedido duplicados. Nada que hacer.")
    raise SystemExit

print(f"Grupos duplicados: {len(dups)}")
for d in dups:
    print(f"  - {d['_id']}  ({d['count']} pedidos)")

# 2. Recolectar todos los IDs afectados
all_oids = [i for d in dups for i in d['ids']]
all_str = [str(i) for i in all_oids]
nums    = [d['_id'] for d in dups]

print(f"\nPedidos afectados: {len(all_oids)}")

# 3. Buscar referencias en TODAS las demas colecciones
cols_a_ignorar = {'pedidos', 'contadores'}
colecciones = [c for c in db.list_collection_names() if c not in cols_a_ignorar]

campos = ['pedido_id', 'numero_pedido', 'pedido', 'id_pedido', 'pedido_origen', 'pedido_ref']

print("\nREFERENCIAS ENCONTRADAS EN OTRAS COLECCIONES:")
encontradas = 0
for c in colecciones:
    for campo in campos:
        n = (db[c].count_documents({campo: {'$in': all_oids}})
             + db[c].count_documents({campo: {'$in': all_str}})
             + db[c].count_documents({campo: {'$in': nums}}))
        if n > 0:
            print(f"  {c}.{campo}: {n}")
            encontradas += 1

if encontradas == 0:
    print("  (ninguna)")

print("\nFIN DEL DIAGNOSTICO")