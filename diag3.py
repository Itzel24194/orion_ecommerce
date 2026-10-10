# diag3.py — identifica la referencia exacta del cupon
print(">>> INICIO", flush=True)

from app.config.database_config import db
from bson import ObjectId

dups = list(db.pedidos.aggregate([
    {'$group': {
        '_id': '$numero_pedido',
        'count': {'$sum': 1},
        'ids': {'$push': '$_id'}
    }},
    {'$match': {'count': {'$gt': 1}}},
    {'$sort': {'_id': 1}}
]))

all_oids = [i for d in dups for i in d['ids']]
all_str  = [str(i) for i in all_oids]
nums     = [d['_id'] for d in dups]

print(">>> Documento de cupones_usuarios con la referencia:", flush=True)
ref = list(db.cupones_usuarios.find({
    '$or': [
        {'pedido_id': {'$in': all_oids}},
        {'pedido_id': {'$in': all_str}},
        {'pedido_id': {'$in': nums}},
    ]
}))
for r in ref:
    print("    _id:", r.get('_id'), flush=True)
    print("    pedido_id:", r.get('pedido_id'), flush=True)
    print("    usuario_id:", r.get('usuario_id'), flush=True)
    print("    cupon_codigo:", r.get('cupon_codigo'), flush=True)
    print("    fecha_uso:", r.get('fecha_uso'), flush=True)

# Y ademas: para cada grupo duplicado, listar todos los pedidos con detalle
print("\n>>> Detalle completo de cada grupo:", flush=True)
for d in dups:
    print(f"\n=== {d['_id']} ===", flush=True)
    for pid in d['ids']:
        p = db.pedidos.find_one({'_id': pid}, {
            'numero_pedido': 1, 'usuario_id': 1, 'usuario_email': 1,
            'total': 1, 'estado': 1, 'created_at': 1, 'metodo_pago': 1
        })
        if p:
            print(f"  _id={pid}  user={p.get('usuario_id')}  email={p.get('usuario_email')}  "
                  f"total={p.get('total')}  estado={p.get('estado')}  fecha={p.get('created_at')}", flush=True)

print("\n>>> FIN", flush=True)