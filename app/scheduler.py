from app import create_app
from app.models.chat_model import Chat

app = create_app()
with app.app_context():
    # Previsualizar cuántas se eliminarían
    preview = Chat.previsualizar_retencion(dias=365)
    print(preview)

    # Ejecutar retención ahora
    eliminadas = Chat.eliminar_sesiones_archivadas(dias=365)
    print(f"Eliminadas: {eliminadas}")

    # Ejecutar archivado de inactivas
    archivadas = Chat.archivar_sesiones_inactivas(dias=30)
    print(f"Archivadas: {archivadas}")