# ================================================================
# limpiar_duplicados.py
# Renombra numero_pedido de pedidos duplicados. NO borra nada.
#
# Uso:
#   py limpiar_duplicados.py            -> DRY RUN (no modifica nada)
#   py limpiar_duplicados.py --apply    -> aplica cambios + backup
# ================================================================

import sys
import json
from datetime import datetime
from bson import ObjectId

APLICAR = '--apply' in sys.argv

from app.config.database_config import db


# ---------- 1. Backup completo ----------
def backup_pedidos():
    ruta = f"backup_pedidos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    pedidos = list(db.pedidos.find({}))

    def serial(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"No serializable: {type(obj)}")

    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(pedidos, f, default=serial, ensure_ascii=False, indent=2)
    print(f"✅ Backup guardado en: {ruta} ({len(pedidos)} pedidos)")
    return ruta


# ---------- 2. Detectar duplicados ----------
def detectar_grupos():
    return list(db.pedidos.aggregate([
        {'$group': {
            '_id': '$numero_pedido',
            'count': {'$sum': 1},
            'ids': {'$push': '$_id'}
        }},
        {'$match': {'count': {'$gt': 1}}},
        {'$sort': {'_id': 1}}
    ]))


# ---------- 3. Construir plan ----------
def construir_plan(grupos):
    plan = []
    for g in grupos:
        numero = g['_id']
        pedidos = list(db.pedidos.find(
            {'_id': {'$in': g['ids']}},
            {'numero_pedido': 1, 'created_at': 1, 'usuario_id': 1, 'estado': 1}
        ).sort('created_at', -1))  # más reciente primero

        for i, p in enumerate(pedidos):
            if i == 0:
                continue  # el más reciente se conserva
            nuevo = f"{numero}-DUP{i}"
            plan.append({
                'pedido_id': p['_id'],
                'numero_viejo': numero,
                'numero_nuevo': nuevo,
                'usuario_id': p.get('usuario_id'),
                'estado': p.get('estado'),
                'created_at': p.get('created_at'),
            })
    return plan


# ---------- 4. Aplicar ----------
def aplicar_plan(plan):
    for item in plan:
        db.pedidos.update_one(
            {'_id': item['pedido_id']},
            {'$set': {'numero_pedido': item['numero_nuevo']}}
        )


# ---------- 5. Índice único ----------
def crear_indice_unico():
    try:
        # Por si acaso quedó uno a medio construir
        try:
            db.pedidos.drop_index('numero_pedido_1')
            print("ℹ️ Índice previo 'numero_pedido_1' eliminado (estaba incompleto).")
        except Exception:
            pass

        db.pedidos.create_index(
            [('numero_pedido', 1)],
            unique=True,
            name='numero_pedido_1'
        )
        print("✅ Índice único 'numero_pedido_1' creado.")
        return True
    except Exception as e:
        print(f"❌ No se pudo crear índice único: {e}")
        return False


# ---------- 6. Contador ----------
def inicializar_contador(year=2026):
    ultimo = db.pedidos.find_one(
        {'numero_pedido': {'$regex': f'^ORION-{year}-\\d{{4}}$'}},
        sort=[('numero_pedido', -1)]
    )
    inicial = 0
    if ultimo:
        try:
            inicial = int(ultimo['numero_pedido'].rsplit('-', 1)[-1])
        except Exception:
            inicial = 0
    contador_id = f'contador_pedidos_{year}'
    db.contadores.update_one(
        {'_id': contador_id},
        {'$set': {'secuencia': inicial}},
        upsert=True
    )
    print(f"✅ Contador '{contador_id}' inicializado en {inicial}")


# ---------- MAIN ----------
def main():
    print("=" * 60)
    print("LIMPIEZA DE DUPLICADOS numero_pedido")
    print("Modo:", "APLICAR" if APLICAR else "DRY RUN (no modifica nada)")
    print("=" * 60)

    grupos = detectar_grupos()
    print(f"\nGrupos duplicados detectados: {len(grupos)}")
    for g in grupos:
        print(f"  {g['_id']}  ({g['count']} pedidos)")

    if not grupos:
        print("\n✅ No hay nada que limpiar.")
        return

    plan = construir_plan(grupos)
    print(f"\nPlan de renombrado ({len(plan)} pedidos a renombrar):")
    for item in plan:
        print(f"  {item['numero_viejo']}  ->  {item['numero_nuevo']}   "
              f"(id={item['pedido_id']}, user={item['usuario_id']}, "
              f"estado={item['estado']}, fecha={item['created_at']})")

    if not APLICAR:
        print("\nDRY RUN: no se ha modificado nada.")
        print("Revisa el plan. Si estás de acuerdo, ejecuta:")
        print("    py limpiar_duplicados.py --apply")
        return

    print("\n⚠️  Modo APLICAR. Se hará backup primero...")
    backup_pedidos()

    print("\nAplicando plan...")
    aplicar_plan(plan)
    print(f"✅ {len(plan)} pedidos renombrados.")

    print("\nCreando índice único...")
    crear_indice_unico()

    print("\nInicializando contador...")
    inicializar_contador(2026)

    print("\n" + "=" * 60)
    print("✅ LIMPIEZA COMPLETADA")
    print("=" * 60)


if __name__ == '__main__':
    main()