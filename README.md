# RodelSoft POS - Punto de Venta

Maqueta funcional de punto de venta para RodelSoft. Primera fase con interfaz web moderna y API REST completa.

## 🚀 Características

### ✅ Funcionalidades Implementadas
- **Interfaz Web Moderna**: Diseño responsive con colores corporativos de RodelSoft
- **Gestión de Productos**: CRUD completo de productos con categorías
- **Carrito de Compras**: Agregar, modificar cantidades y remover items
- **Procesamiento de Ventas**: Crear ventas con reducción automática de inventario
- **Categorías de Productos**: Organización por categorías con colores personalizados
- **Búsqueda de Productos**: Búsqueda en tiempo real por nombre
- **API REST Segura**: Autenticación JWT y validación de permisos
- **Base de Datos**: Modelos SQLAlchemy con MySQL

### 🎨 Interfaz de Usuario
- **Diseño Corporativo**: Colores RodelSoft (#003366, #0066FF, #00A8E8)
- **Responsive**: Funciona en desktop, tablet y móvil
- **UX Moderna**: Animaciones suaves, hover effects, feedback visual
- **Accesibilidad**: Navegación por teclado, contraste adecuado

## 📁 Estructura del Proyecto

```
rodelsoft-pos/
├── main.py              # API FastAPI principal
├── db.py                # Modelos SQLAlchemy
├── populate_sample_data.py  # Datos de ejemplo
├── requirements.txt     # Dependencias Python
├── Dockerfile          # Contenedor Docker
└── README.md           # Esta documentación
```

## 🛠️ Instalación y Configuración

### 1. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 2. Variables de Entorno
Crear archivo `.env` con:
```env
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=proyecto_user
MYSQL_PASSWORD=proyecto_pass
MYSQL_DATABASE=proyecto_db
SECRET_KEY=tu_clave_secreta_jwt
ALGORITHM=HS256
```

### 3. Crear Tablas en Base de Datos
Las tablas se crean automáticamente al iniciar la aplicación.

### 4. Poblar Datos de Ejemplo
```bash
python populate_sample_data.py
```

## 🚀 Uso

### Iniciar Servidor
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Acceder a la Interfaz
1. Iniciar sesión en el portal principal
2. Navegar a la app POS desde el portal
3. La URL será algo como: `http://localhost/pos?app_id=X&client_id=Y`

### API Endpoints

#### Categorías
- `GET /api/categories` - Listar categorías
- `POST /api/categories` - Crear categoría

#### Productos
- `GET /api/products` - Listar productos (con filtros opcionales)
- `POST /api/products` - Crear producto

#### Ventas
- `GET /api/sales` - Listar ventas
- `POST /api/sales` - Crear venta

#### Interfaz
- `GET /pos` - Interfaz web del POS

## 📊 Datos de Ejemplo

### Categorías Incluidas
- 🥤 **Bebidas**: Refrescos, jugos, agua
- 🍿 **Snacks**: Papas, galletas, chocolates
- 🥛 **Lácteos**: Leche, queso, yogurt
- 🍞 **Panadería**: Pan, pasteles, conchas
- 🧹 **Limpieza**: Jabón, detergente, cloro

### Productos de Ejemplo
Cada categoría tiene 3 productos con:
- Precio de venta y costo
- Control de inventario
- SKU único
- Stock inicial

## 🔒 Seguridad

- **Autenticación JWT**: Verificación de tokens en cada request
- **Validación de Permisos**: Control por usuario, app_id y client_id
- **Headers Seguros**: X-App-Id y X-Client-Id para contexto
- **CORS**: Configurado para integración con portal

## 🎯 Próximas Fases

### Fase 2 - Funcionalidades Avanzadas
- [ ] Códigos de barras / lectores
- [ ] Descuentos y promociones
- [ ] Múltiples métodos de pago
- [ ] Reportes de ventas
- [ ] Gestión de clientes
- [ ] Inventario avanzado

### Fase 3 - Integraciones
- [ ] Impresoras térmicas
- [ ] Cajas registradoras
- [ ] Sistemas de punto de venta físicos
- [ ] Integración con sistemas contables

### Fase 4 - Analytics
- [ ] Dashboard de ventas
- [ ] Análisis de productos populares
- [ ] Tendencias de compra
- [ ] Predicciones de inventario

## 🐳 Docker

### Construir Imagen
```bash
docker build -t rodelsoft-pos .
```

### Ejecutar Contenedor
```bash
docker run -p 8000:8000 --env-file .env rodelsoft-pos
```

## 📝 Notas de Desarrollo

- **Base de Datos**: Usa MySQL con SQLAlchemy ORM
- **API**: FastAPI con Pydantic para validación
- **Frontend**: HTML/CSS/JS vanilla (sin frameworks)
- **Estilos**: CSS moderno con variables CSS
- **Responsive**: Media queries para móviles

## 🤝 Contribución

1. Fork el proyecto
2. Crear rama para feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agrega nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📄 Licencia

Este proyecto es parte de RodelSoft. Todos los derechos reservados.

---

**Desarrollado por RodelSoft** 🏢
**Versión**: 1.0.0 (Maqueta)
**Fecha**: Marzo 2026