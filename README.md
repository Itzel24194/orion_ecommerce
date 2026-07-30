# 🛍️ ORION – Ecommerce 

**ORION** es una plataforma de comercio electrónico de última generación, diseñada para ofrecer una experiencia de compra similar a la de grandes retailers como Liverpool, pero con un componente innovador: un **espejo virtual** que permite a los usuarios probarse prendas de forma digital mediante realidad aumentada (AR) o simulación de tallas.

El proyecto integra un potente backend en Flask, una base de datos MongoDB, un frontend responsivo con Bootstrap y JavaScript, y múltiples módulos de Inteligencia Artificial para personalizar la experiencia, predecir el comportamiento del cliente y optimizar las ventas.

---

##  Características Principales

###  Gestión de Productos y Catálogo
- Catálogo completo con categorías, atributos (talla, color, SKU), imágenes y stock.
- Búsqueda avanzada y filtrado por categorías, precios y atributos.
- Vista detallada de productos con imágenes, descripciones y recomendaciones.

###  Carrito de Compras Inteligente
- Carrito persistente en sesión con actualización dinámica.
- Cálculo automático de descuentos por volumen (hasta 25% para compras al por mayor).
- Aplicación de cupones y promociones con validación en tiempo real.

###  Promociones y Cupones Automatizados
- **Asignación automática de segmentos**: el sistema analiza el descuento, tipo y monto mínimo para asignar promociones a los segmentos correctos (VIP, Frecuentes, Inactivos, Nuevos) sin intervención manual del administrador.
- Cupones con códigos únicos, fechas de validez, usos máximos y restricciones por categoría/producto.
- Módulo de administración para crear, editar, eliminar y visualizar estadísticas de promociones y cupones.

###  Inteligencia Artificial y Machine Learning
- **Segmentación de Clientes (K-Means)**: agrupa clientes por frecuencia de compra, gasto total y días de inactividad. Incluye método del codo, índice de silueta y visualización PCA.
- **Predicción de Abandono (Random Forest y Regresión Logística)**: modelo supervisado que predice la probabilidad de que un cliente abandone la plataforma, con importancia de características y matriz de confusión.
- **Predicción de Ventas (Random Forest Regressor)**: estima las ventas futuras basándose en tendencias históricas, días de la semana y promociones activas.
- **Árboles de Decisión**: módulo separado para clasificación binaria de abandono con visualización interactiva.

###  Espejo Virtual (Realidad Aumentada)
- Permite a los usuarios **"probarse"** prendas de forma virtual utilizando la cámara de su dispositivo.
- Superposición de imágenes de productos sobre el reflejo del usuario (simulación de talla y ajuste).
- Tecnología basada en la detección de puntos de referencia faciales y corporales (MediaPipe / TensorFlow.js).
- Mejora la confianza de compra y reduce la tasa de devolución.

###  Gestión de Usuarios y Roles
- Registro, inicio de sesión y perfiles de usuario.
- Roles: **admin** (acceso total al panel de administración) y **cliente** (acceso a su historial de pedidos, cupones y promociones).
- Segmentación dinámica de clientes basada en su comportamiento de compra.

###  Reportes y Analíticas
- Panel de administración con estadísticas de ventas, pedidos, promociones y cupones.
- Exportación de reportes en CSV y PDF.
- Gráficos interactivos con Chart.js para visualizar tendencias.

###  Seguridad y Buenas Prácticas
- Autenticación con sesiones seguras.
- Sanitización de entradas y protección contra inyecciones.
- Uso de variables de entorno para configuraciones sensibles.

---

##  Estructura del Proyecto
proyecto/
├── app/
│ ├── models/ # Modelos de datos (MongoDB)
│ │ ├── usuarios_model.py
│ │ ├── productos_model.py
│ │ ├── pedidos_model.py
│ │ ├── promocion_model.py
│ │ └── cupon_model.py
│ ├── controllers/ # Lógica de negocio y controladores
│ │ ├── carrito_controller.py
│ │ ├── pedido_controller.py
│ │ ├── promociones_controller.py
│ │ ├── cupon_controller.py
│ │ └── ml_controller.py
│ ├── services/ # Servicios externos y lógica compleja
│ │ └── ml_service.py # Servicios de Machine Learning
│ ├── routes/ # Definición de rutas (web.py)
│ ├── static/ # Archivos estáticos (CSS, JS, imágenes)
│ └── templates/ # Plantillas HTML (Jinja2)
│ ├── admin/ # Panel de administración
│ └── tienda/ # Frontend para clientes
├── models/ # Archivos de modelos entrenados (.pkl)
├── .env # Variables de entorno
├── requirements.txt # Dependencias del proyecto
├── run.py # Punto de entrada de la aplicación
└── README.md # Este archivo

text

---

##  Tecnologías Utilizadas

| Área               | Tecnologías                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| **Backend**         | Python 3.10+, Flask, Flask-Login, Flask-Session                            |
| **Base de Datos**   | MongoDB (PyMongo)                                                          |
| **Frontend**        | HTML5, CSS3, Bootstrap 5, JavaScript (ES6), Chart.js                       |
| **Machine Learning**| scikit-learn, pandas, numpy, joblib                                        |
| **Realidad Aumentada** | MediaPipe, TensorFlow.js (para el espejo virtual)                         |
| **Herramientas**    | Git, pip, virtualenv                                                       |

---

##  Instalación y Configuración

### Prerrequisitos
- Python 3.10 o superior.
- MongoDB instalado y en ejecución (local o en la nube).
- Git (opcional).

### Pasos

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/orion_ecommerce.git
   cd orion-ecommerce
Crear y activar un entorno virtual

bash
python -m venv venv
source venv/bin/activate   # En Windows: venv\Scripts\activate
Instalar dependencias
bash
pip install -r requirements.txt
Configurar variables de entorno
Crea un archivo .env en la raíz con el siguiente contenido:
env
SECRET_KEY=tu_clave_secreta
MONGO_URI=mongodb://localhost:27017/orion_db
Iniciar la aplicación
bash
python run.py
Acceder a la aplicación
Abre tu navegador en http://localhost:5000.
Uso
Para Clientes
Navega por el catálogo, busca productos y agrégalos al carrito.
Aplica cupones o promociones automáticas según tu segmento.
Utiliza el espejo virtual para probarte prendas desde la página del producto.
Realiza el pago y sigue el estado de tu pedido.
Para Administradores
Accede al panel de administración (/admin/dashboard).
Gestiona usuarios, productos, categorías, pedidos y atributos.
Crea promociones y cupones (los segmentos se asignan automáticamente).
Entrena y visualiza modelos de Machine Learning en la sección "Análisis Supervisado".
Exporta reportes de ventas en CSV o PDF.
 Módulos de Machine Learning
Segmentación de Clientes: El modelo K-Means se entrena con datos de pedidos y genera clusters que se nombran automáticamente (VIP, Frecuente, Ocasional, Inactivo) mediante un sistema de puntuación.
Predicción de Abandono: Modelo Random Forest que predice la probabilidad de que un cliente abandone la plataforma, con una precisión superior al 80%.
Predicción de Ventas: Modelo Random Forest Regressor que estima las ventas de los próximos 7 días.
Árboles de Decisión: Módulo dedicado a la clasificación binaria con visualización de importancia de características y matriz de confusión.
Espejo Virtual: Utiliza técnicas de visión por computadora para simular el ajuste de prendas en tiempo real.
 Dependencias Principales
Las dependencias están listadas en requirements.txt. Algunas de las más importantes son:
Flask
Flask-Login
PyMongo
scikit-learn
pandas
numpy
joblib
python-dotenv
bootstrap (vía CDN)
Chart.js (vía CDN)
 Contribución
Si deseas contribuir al proyecto, por favor sigue estos pasos:
Haz un fork del repositorio.
Crea una rama con tu funcionalidad: git checkout -b mi-nueva-funcionalidad.
Realiza tus cambios y haz commit: git commit -m 'Añadir nueva funcionalidad'.
Sube tus cambios: git push origin mi-nueva-funcionalidad.
Abre un Pull Request describiendo tus cambios.
Asegúrate de seguir las buenas prácticas de código y añadir pruebas cuando sea posible.
 Licencia
Este proyecto está bajo la Licencia MIT. Consulta el archivo LICENSE para más información.
 Autores
Tu Nombre – Desarrollo y arquitectura – tu-email@ejemplo.com
 Contacto
Para cualquier consulta o sugerencia, no dudes en contactar al equipo de desarrollo a través del correo: soporte@orion.com.
¡Gracias por elegir ORION! 

