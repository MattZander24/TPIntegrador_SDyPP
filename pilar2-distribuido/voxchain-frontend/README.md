# VoxChain Frontend

Frontend web de VoxChain, implementado con Angular 19 y Angular Material. Proporciona una interfaz de usuario para consultar la blockchain, ver leyes, monitorear ventanas de votación y proponer nuevas leyes. Se conecta a la API Gateway (`voxchain-api`) vía REST y SSE para actualizaciones en tiempo real.

## Responsabilidades

- Interfaz de usuario para explorar la blockchain de VoxChain.
- Visualización de leyes (propuestas, promulgadas, derogadas, descartadas).
- Monitoreo de ventanas de votación activas e históricas.
- Formulario para proponer nuevas leyes (envía a `voxchain-api`).
- Suscripción a SSE (`/api/events`) para actualizaciones en tiempo real de bloques, ventanas y leyes.
- Health check del sistema (NCT, TrP, Redis, API).

## Estructura

| Directorio/Archivo | Contenido |
|---------------------|-----------|
| `src/main.ts` | Punto de entrada de la aplicación Angular. |
| `src/index.html` | HTML base de la aplicación. |
| `src/styles.scss` | Estilos globales. |
| `src/app/app.config.ts` | Configuración de la aplicación (proveedores, etc.). |
| `src/app/app.routes.ts` | Definición de rutas de la aplicación. |
| `src/app/app.component.ts` | Componente raíz. |
| `src/app/core/` | Servicios core (HTTP client, SSE service, configuración). |
| `src/app/features/` | Módulos de características (chain, laws, windows, propose). |
| `package.json` | Dependencias npm (Angular 19, Angular Material, RxJS). |
| `angular.json` | Configuración de Angular CLI. |
| `tsconfig.json` | Configuración de TypeScript. |
| `nginx.conf` | Configuración de nginx para producción. |
| `Dockerfile` | Multi-stage build (Node → nginx). |

## Ejecución

```bash
# Desarrollo local (requiere voxchain-api ejecutándose en localhost:8000)
npm install
npm start
# Abre http://localhost:4200

# Build de producción
npm run build
# Output en dist/voxchain-frontend/

# Vía docker-compose (recomendado), desde pilar2-distribuido/
docker compose up --build voxchain-frontend
# Sirve en http://localhost:80 (nginx)
```

## Características

- **Explorador de blockchain**: vista de bloques con navegación por índice.
- **Gestor de leyes**: listado de leyes con filtros por estado (pending, promulgated, repealed, discarded).
- **Monitor de ventanas**: vista de ventanas de votación activas e históricas con deadlines.
- **Proposición de leyes**: formulario para crear nuevas leyes con texto y acción (promulgación/derogación).
- **Actualizaciones en tiempo real**: integración con SSE para reflejar cambios sin recargar.
- **Health dashboard**: indicadores de estado de NCT, TrP, Redis y API.
- **UI responsiva**: diseño adaptativo con Angular Material.

## Configuración

La aplicación se configura vía `src/app/core/` services. Por defecto se conecta a:

- API base URL: `http://localhost:8000` (desarrollo) o `/api` (producción detrás de nginx)
- SSE endpoint: `/api/events`

Para producción, nginx proxyea las requests a `voxchain-api` y sirve los estáticos de Angular.

## Decisiones de diseño

- **Angular 19 con standalone components**: arquitectura modular sin NgModules tradicionales.
- **Angular Material**: componentes UI consistentes y accesibles out-of-the-box.
- **Multi-stage Docker build**: stage de Node para build, stage de nginx alpine para producción (imagen pequeña).
- **Nginx como servidor**: sirve estáticos y proxyea API a `voxchain-api` en el mismo network Docker.
- **SSE para real-time**: en lugar de polling, se suscribe a eventos del backend para actualizaciones instantáneas.
- **TypeScript estricto**: tipado fuerte para reducir errores en tiempo de compilación.
- **RxJS para manejo de async**: streams reactivos para SSE y llamadas HTTP.
