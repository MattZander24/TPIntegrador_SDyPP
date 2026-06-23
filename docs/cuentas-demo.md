# Sistema de Cuentas de Prueba para Demo

## Resumen

Se ha implementado un sistema de selección de cuentas de prueba para el frontend de VoxChain, permitiendo a los usuarios elegir entre 5 cuentas preconfiguradas correspondientes a los workers definidos en `demo-deployments.yaml`.

## Cambios Realizados

### Backend (voxchain_api)

**Nuevo archivo:** `voxchain_api/routers/accounts.py`
- Router FastAPI para gestión de cuentas de prueba
- Endpoints:
  - `GET /api/accounts` - Lista todas las cuentas con su estado (available/occupied)
  - `POST /api/accounts/reserve` - Reserva una cuenta para la sesión actual
  - `POST /api/accounts/release` - Libera una cuenta ocupada
  - `GET /api/accounts/{username}` - Obtiene detalles de una cuenta específica

**Modificado:** `voxchain_api/models.py`
- Agregados modelos Pydantic:
  - `DemoAccount` - Representa una cuenta de prueba
  - `ReserveAccountRequest` - Request para reservar cuenta
  - `ReleaseAccountRequest` - Request para liberar cuenta

**Modificado:** `voxchain_api/main.py`
- Import y registro del router `accounts`

### Frontend (voxchain-frontend)

**Nuevo archivo:** `voxchain-frontend/src/app/core/services/accounts.service.ts`
- Servicio Angular para gestionar cuentas de prueba
- Funcionalidades:
  - Generación de session_id único
  - Listado de cuentas disponibles
  - Reserva/liberación de cuentas
  - Persistencia de sesión en localStorage
  - Obtención de clave pública de la cuenta seleccionada

**Nuevo archivo:** `voxchain-frontend/src/app/features/account-selection/account-selection.component.ts`
- Componente UI para selección de cuenta
- Muestra las 5 cuentas en tarjetas con estado visual
- Indica cuentas ocupadas con mensaje de error
- Permite liberar cuenta seleccionada

**Nuevo archivo:** `voxchain-frontend/src/app/core/guards/account-selected.guard.ts`
- Guard de ruta para proteger páginas que requieren cuenta seleccionada
- Redirige a `/select-account` si no hay cuenta seleccionada

**Modificado:** `voxchain-frontend/src/app/app.routes.ts`
- Nueva ruta `/select-account` como página inicial
- Guard `accountSelectedGuard` aplicado a todas las rutas protegidas
- Redirección por defecto a `/select-account`

**Modificado:** `voxchain-frontend/src/app/core/services/identity.service.ts`
- Soporte para modo demo con claves predefinidas
- `exportedPrivkey` puede ser `null` en modo demo
- Nuevo campo `username` y `isDemo` en interfaz Identity
- Método `sign()` lanza error en modo demo (firma manejada por backend)
- Método `getUsername()` para obtener nombre de cuenta demo
- Sincronización automática con cuenta seleccionada

**Modificado:** `voxchain-frontend/src/app/features/identity/identity.component.ts`
- Muestra nombre de cuenta demo cuando está en modo demo
- Botón "Change Account" para cambiar de cuenta demo
- Redirección a selección de cuenta al cambiar

## Funcionamiento del Sistema

### Flujo de Usuario

1. **Acceso al frontend**: Usuario es redirigido a `/select-account`
2. **Selección de cuenta**: Usuario elige una de las 5 cuentas disponibles
3. **Reserva**: Frontend llama a `/api/accounts/reserve` con session_id
4. **Validación**: Backend verifica si la cuenta está libre en Redis
5. **Éxito**: Cuenta marcada como ocupada en Redis (TTL 30 min)
6. **Navegación**: Usuario redirigido al dashboard con identidad establecida
7. **Uso**: Usuario interactúa con la aplicación usando la clave pública de la cuenta
8. **Liberación**: Usuario puede liberar la cuenta desde la página de identidad

### Gestión de Estado en Redis

- **Clave**: `demo_account:{username}`
- **Valor**: JSON con `{status, occupied_by, occupied_at}`
- **TTL**: 30 minutos (1800 segundos)
- **Estrategia**: Si la sesión expira, la cuenta se libera automáticamente

## Cuentas de Prueba Configuradas

Las 5 cuentas corresponden a los workers en `demo-deployments.yaml`:

| Username | Worker ID | Mode | Descripción |
|----------|-----------|------|-------------|
| valentin | worker-standalone | standalone | Worker autónomo |
| gustavo | worker-pool-coordinator | pool-coordinator | Coordinador del pool |
| matt | worker-pool-miner-1 | pool-worker | Miner del pool |
| profesor1 | worker-pool-miner-2 | pool-worker | Miner del pool |
| profesor2 | worker-pool-miner-3 | pool-worker | Miner del pool |

## Claves Privadas: ¿Qué Cambia?

### Sistema Anterior

- **Generación**: El frontend generaba claves ECDSA P-256 dinámicamente
- **Almacenamiento**: Clave privada almacenada en localStorage del navegador
- **Uso**: Clave privada usada localmente para firmar mensajes
- **Seguridad**: Clave nunca salía del navegador

### Nuevo Sistema (Modo Demo)

**Claves Públicas**:
- Las claves públicas son predefinidas en el backend (`DEMO_ACCOUNTS` en `accounts.py`)
- Cada cuenta de prueba tiene una clave pública fija que corresponde a su worker
- El frontend usa la clave pública de la cuenta seleccionada

**Claves Privadas**:
- **No se generan en el frontend** - las claves privadas no existen en el navegador
- **Deben estar en el backend** - para que el sistema de firmas funcione, las claves privadas de las cuentas de prueba deben estar disponibles en el backend (en los workers)
- **Firma en modo demo**: El método `sign()` del frontend lanza un error indicando que la firma es manejada por el backend

### Implementación Pendiente

Para que el sistema de firmas funcione completamente en modo demo:

1. **Configurar claves reales**: Reemplazar los placeholders `demo_*_pubkey_placeholder` en `accounts.py` con las claves públicas reales de los workers
2. **Claves privadas en backend**: Asegurar que los workers tengan sus claves privadas configuradas para poder firmar propuestas
3. **Endpoint de firma backend**: Considerar agregar un endpoint en el backend que firme mensajes en nombre de la cuenta demo (opcional, dependiendo de la arquitectura)

### Alternativa: Sin Firmas en Modo Demo

Si para la defensa no es necesario implementar el sistema de firmas completo:

1. Desactivar `REQUIRE_SIGNATURES` en el backend
2. El frontend puede enviar propuestas sin firma
3. El backend aceptará propuestas sin validación de firma

## Consideraciones de Seguridad

- **Session ID**: Generado aleatoriamente en el frontend, persiste en localStorage
- **TTL Redis**: 30 minutos para liberar cuentas abandonadas automáticamente
- **Validación de ownership**: Solo la sesión que reservó una cuenta puede liberarla
- **Estado compartido**: Redis centralizado permite coordinación entre múltiples instancias del frontend

## Próximos Pasos

1. **Configurar claves reales**: Obtener las claves públicas de los workers y actualizar `DEMO_ACCOUNTS`
2. **Testing**: Probar el flujo completo de selección y uso de cuentas
3. **Decisión sobre firmas**: Determinar si se implementará firma en backend o se desactivará `REQUIRE_SIGNATURES`
4. **UI mejoras**: Considerar agregar auto-refresh del estado de cuentas cada X segundos
5. **Logout automático**: Implementar liberación de cuenta al cerrar el navegador
