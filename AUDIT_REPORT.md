# AUDIT_REPORT.md — VoxChain (auditoría defensiva, read-only)

> Auditoría estática del repositorio VoxChain contra `AGENT.md` (§3, §4, §5, §7, §10) y `DOC.md`.
> No se modificó código. Cada hallazgo cita archivo y línea y pega el fragmento mínimo que lo evidencia.
> Nota de fuente: el documento `Democracia_Via_BlockChain.md` exigido por el prompt **no existe** en el repo
> (ver §5 Cobertura). Se usó `AGENT.md` + `DOC.md` como contrato; `CONTEXTO.md`/`FUNCIONAMIENTO.md` como apoyo.

## 1. Resumen ejecutivo

| Severidad | Cantidad |
|---|---|
| CRÍTICO | 0 |
| ALTO | 4 |
| MEDIO | 13 |
| BAJO | 4 |
| INFO | 3 |

**Top 5 hallazgos**

1. **ALTO A-01** — Propuestas y nonces no se firman; el NCT no verifica firma → suplantación de cualquier autor (más allá del Sybil documentado).
2. **ALTO A-02** — Redis desplegado sin AUTH/ACL y sin NetworkPolicy → cualquier workload del clúster puede reescribir la cadena.
3. **ALTO A-03** — `adminPassword = "voxchain"` hardcodeado en IaC trackeada (`main.tf:321`) → credencial estática en repo, viola "Zero static keys".
4. **ALTO A-04** — `append_block` no atómico y sin compare-and-set sobre el tip de la cadena → fork posible durante la ventana de solapamiento de split-brain (agrava lo declarado en §9).
5. **MEDIO M-01** — Buffer overflow en el kernel CUDA: `buf[256]` se llena con `base_len = strlen(argv[1])` sin validación de longitud.

**Aspecto positivo relevante (no es hallazgo):** el NCT **recalcula** el hash y valida el conteo de ceros antes de sellar (`verify_nonce`, `coordinator.py:245`), cumpliendo NCT.3 / §5/P4. Un minero que mienta sobre el nonce no puede promulgar con prueba falsa. Esto evita el escenario CRÍTICO típico.

---

## 2. Hallazgos

### [ALTO] A-01 — Propuestas y nonces sin firma; el NCT no verifica identidad
- Componente: dominio | cripto
- Archivo:línea: `pilar2-distribuido/scripts/propose_law.py:48-58`, `pilar2-distribuido/voxchain_api/routers/laws.py:78-110`, `pilar2-distribuido/nct-coordinator/nct/coordinator.py:100-135` y `:221-243`
- Categoría: seguridad | correctitud-dominio
- Evidencia:
    ```python
    law = {
        "law_id": args.law_id or f"ley-{uuid.uuid4().hex[:8]}",
        "author_pubkey": args.author,   # se acepta cualquier pubkey, sin firma
        "text_hash": text_hash,
        ...
    }
    ```
    ```python
    # handle_proposal: usa author tal cual, nunca valida una firma
    author = law.get("author_pubkey")
    ...
    # handle_nonce_response: winning_node_or_pool es texto libre sin verificar
    winner = sol.get("winning_node_or_pool", "")
    ```
    Grep de `sign|verify_signature|ecdsa|ed25519` sobre todo `pilar2-distribuido/**.py` → **0 resultados**.
- Impacto: cualquiera puede proponer/derogar en nombre de un `author_pubkey` ajeno y disparar su cooldown (DoS de identidad), o reclamar la autoría/recompensa de un nonce ajeno. Permite además evadir la regla "el autor no gana su propia ventana" (§3.4) firmando como otro. El frontend genera un par ECDSA con capacidad `sign` (`identity.service.ts:31-42`) que nunca se usa para firmar. Esto excede el Sybil documentado (§9): Sybil = crear identidades propias; acá se **suplanta** una identidad existente.
- Regla violada: AGENT.md §3.1 ("Identidad = par de claves… nadie puede votar en nombre de otro"), §7.1.
- Recomendación: firmar `propuesta` y `respuesta_nonce` con la clave privada del autor/pool y que el NCT verifique la firma contra el `author_pubkey`/`winning_node_or_pool` antes de encolar o sellar. Rechazar mensajes sin firma válida.

### [ALTO] A-02 — Redis sin AUTH/ACL y sin NetworkPolicy
- Componente: redis | k8s
- Archivo:línea: `pilar3-despliegue/kubernetes/infrastructure/redis-statefulset.yaml:20`, `pilar3-despliegue/kubernetes/infrastructure/redis-service.yaml`, `pilar2-distribuido/common/config.py:23`
- Categoría: seguridad
- Evidencia:
    ```yaml
    command: ["redis-server", "--appendonly", "yes"]   # sin --requirepass ni ACL
    ```
    ```python
    REDIS_URL = get("REDIS_URL", "redis://redis:6379/0")  # sin credenciales
    ```
    `grep -r "kind: NetworkPolicy" kubernetes/` → **0 resultados**.
- Impacto: el estado canónico (cadena de bloques, cooldowns, lease de liderazgo `nct:leader`) es accesible sin autenticación a cualquier pod del clúster. Sin NetworkPolicy, un workload comprometido puede leer/reescribir la cadena, robar el liderazgo del NCT (`SET nct:leader`) o ejecutar `FLUSHALL`. El Service es `ClusterIP` (no expuesto a Internet), por eso es ALTO y no CRÍTICO, pero el AGENT.md §6.1 exige que Vault custodie las credenciales de Redis y aquí no hay ninguna.
- Regla violada: AGENT.md §6.1 (credenciales de Redis gestionadas por secretos), DOC "Zero static keys / credenciales por ambiente".
- Recomendación: habilitar `requirepass`/ACL inyectado desde el secret manager, añadir NetworkPolicies que restrinjan el acceso a Redis solo al NCT y al API, y activar `--protected-mode yes`.

### [ALTO] A-03 — Credencial estática hardcodeada en IaC (Grafana admin)
- Componente: secrets | cicd
- Archivo:línea: `pilar3-despliegue/terraform/gke/main.tf:321`
- Categoría: seguridad
- Evidencia:
    ```hcl
    grafana = {
      adminPassword = "voxchain"
    ```
- Impacto: contraseña de administrador en archivo versionado; queda en el historial de git aunque se borre (DOC). Viola explícitamente "Zero static keys". gitleaks con reglas por defecto puede no detectar una asignación HCL genérica de password, por lo que el pipeline no la frena (ver B-01).
- Regla violada: DOC "Seguridad / Zero static keys", "No commitear credenciales".
- Recomendación: mover `adminPassword` a una variable sensible resuelta desde GCP Secret Manager / GitHub Secrets (`var.grafana_admin_password`, `sensitive = true`); rotar la credencial ya expuesta.

### [ALTO] A-04 — Append de cadena no atómico y sin CAS sobre el tip → fork posible en split-brain
- Componente: redis | dominio
- Archivo:línea: `pilar2-distribuido/common/storage/redis_store.py:235-239`, `pilar2-distribuido/nct-coordinator/nct/coordinator.py:264-291`
- Categoría: correctitud-dominio | seguridad
- Evidencia:
    ```python
    def append_block(self, block: Block) -> None:
        self.r.hset(f"block:{block.block_hash}", mapping={...})  # op 1
        self.r.rpush("chain", block.block_hash)                  # op 2 (no atómica)
    ```
    ```python
    block = seal_block(previous_hash=self.store.last_block_hash(), ...)  # lee el tip
    self.store.append_block(block)  # lo agrega sin verificar que el tip no cambió
    ```
- Impacto: el guard atómico `try_seal_window` (SETNX) protege contra dos cierres de **la misma** ventana, pero durante la ventana de solapamiento de split-brain (§9/§11.4, hasta `HEARTBEAT_INTERVAL`) dos NCTs líderes tienen ventanas **distintas**; ambos leen el mismo `last_block_hash` y hacen `append_block`, produciendo dos bloques que encadenan del mismo `previous_hash` → **fork** de la única cadena canónica que DOC declara como invariante central. §9 documenta la pérdida del cómputo de la ventana, no un fork de la cadena: esto lo agrava.
- Regla violada: AGENT.md §7.3 (integridad de cadena / `previous_hash`), DOC "única blockchain canónica".
- Recomendación: sellar con un script Lua atómico que dentro de Redis verifique `LINDEX chain -1 == previous_hash` antes de `RPUSH` (compare-and-set sobre el tip) y agrupe `HSET`+`RPUSH` en la misma operación; abortar el sellado si el tip cambió.

### [MEDIO] M-01 — Buffer overflow en kernel CUDA por `base_len` sin validar
- Componente: minero-cuda
- Archivo:línea: `pilar1-minero/gpu/src/05_brute_force_range.cu:37-44`, `:61`
- Categoría: seguridad
- Evidencia:
    ```cpp
    unsigned char buf[256], hash[16];
    for (int i = 0; i < (int)base_len; i++) buf[i] = base[i];   // base_len sin tope
    ...
    int nlen = ull_to_str(nonce, buf + base_len);               // escribe más allá
    ```
    ```cpp
    size_t base_len = strlen(argv[1]);   // sin chequeo contra 256
    ```
- Impacto: si el `partial_hash_base` (= `law_id + text_hash + voting_window_id + action`) supera ~236 bytes, se desborda el buffer de pila del kernel (corrupción de memoria del device, resultados inválidos o crash). El `partial_hash_base` se construye con datos que entran al sistema vía propuesta; sin firma (A-01) un atacante controla `law_id`/`text_hash`.
- Regla violada: checklist minero CUDA (bounds checking del string de entrada).
- Recomendación: validar `base_len + 20 < sizeof(buf)` en host antes de lanzar y abortar con error; pasar el tamaño del buffer al kernel y truncar/rechazar.

### [MEDIO] M-02 — Escritura del resultado sin operación atómica en el device
- Componente: minero-cuda
- Archivo:línea: `pilar1-minero/gpu/src/05_brute_force_range.cu:42-49`
- Categoría: seguridad | correctitud-dominio
- Evidencia:
    ```cpp
    if (*found_nonce != ~0ULL) return;            // lectura no atómica
    ...
    *found_nonce = nonce;                          // escritura no atómica
    for (int j = 0; j < 16; j++) found_hash[j] = hash[j];
    ```
- Impacto: dos threads que encuentran nonce a la vez escriben `found_nonce` y `found_hash` sin atomicidad ni sincronización; el `found_hash` reportado puede pertenecer a un nonce distinto del `found_nonce` (resultado corrupto). El NCT recomputa el hash, por lo que no se promulga prueba inválida, pero el minero puede reportar un par (nonce, hash) inconsistente y la elección del ganador es no determinista.
- Regla violada: checklist minero CUDA (race conditions device / escritura del ganador).
- Recomendación: usar `atomicCAS` sobre `found_nonce` y escribir `found_hash` solo el thread que gana el CAS; o devolver únicamente el nonce y que el host recompute el hash.

### [MEDIO] M-03 — Ausencia total de chequeo de errores CUDA
- Componente: minero-cuda
- Archivo:línea: `pilar1-minero/gpu/src/05_brute_force_range.cu:69-91`
- Categoría: seguridad
- Evidencia:
    ```cpp
    cudaMalloc(&d_base, base_len + 1);    // sin verificar retorno
    cudaMemcpy(...);                      // idem
    brute_force_range_kernel<<<blocks, threads>>>(...);
    cudaDeviceSynchronize();              // sin cudaGetLastError()
    ```
- Impacto: errores de asignación, copia o lanzamiento del kernel se silencian; el proceso puede reportar "no encontrado" cuando en realidad el kernel nunca corrió, produciendo expiraciones de ventana espurias o resultados corruptos sin detección.
- Regla violada: checklist minero CUDA (chequeo tras cada llamada CUDA).
- Recomendación: envolver cada llamada en una macro `CUDA_CHECK(...)` que verifique `cudaError_t` y `cudaGetLastError()` tras el lanzamiento, abortando con mensaje.

### [MEDIO] M-04 — Lecturas/loops fuera de rango por prefijo y nonce sin validar
- Componente: minero-cuda
- Archivo:línea: `pilar1-minero/gpu/src/05_brute_force_range.cu:21-26`, `:41`, `:60-63`
- Categoría: seguridad
- Evidencia:
    ```cpp
    __device__ bool check_prefix(const unsigned char* hash, const char* prefix, int hex_len) {
        for (int i = 0; i < hex_len; i++) {
            int hn = ... hash[i/2] ...;   // hex_len>32 ⇒ lee fuera de hash[16]
    ```
    ```cpp
    for (unsigned long long nonce = range_min + tid; nonce < range_max; nonce += step)
    // nonce += step puede envolver (wraparound) si range_max ≈ ~0ULL → reproceso/loop
    ```
- Impacto: `hex_len` (= `strlen(prefijo)`) no se acota; con prefijo > 32 hex se leen bytes fuera de `hash[16]`. Con `range_max = ~0ULL` (default), `nonce += step` puede envolver y reprocesar el espacio (Hit #7: búsqueda fuera de rango / loop). Sin solución, el kernel no termina por sí mismo salvo por el guard de `found_nonce`.
- Regla violada: checklist minero CUDA (overflow de rango de nonces, off-by-one de prefijo).
- Recomendación: validar `hex_len <= 32` en host; detectar wraparound (`nonce + step < nonce`) y cortar; documentar el rango máximo seguro.

### [MEDIO] M-05 — Ack incondicional en `finally`: mensajes con error se pierden, sin dead-letter
- Componente: rabbitmq
- Archivo:línea: `pilar2-distribuido/common/messaging/rabbitmq.py:168-177`
- Categoría: seguridad
- Evidencia:
    ```python
    def _cb(ch, method, properties, body):
        try:
            payload = json.loads(body.decode())
            handler(payload)
        except Exception:
            log.exception("error procesando mensaje en %s", method.routing_key)
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)   # ack aun ante excepción
    ```
- Impacto: un mensaje que provoca excepción (handler o JSON malformado) se **acka igual** y se descarta silenciosamente: pérdida de propuestas/nonces válidos cuyo handler falló transitoriamente. No hay cola dead-letter para análisis. (Lado positivo: evita el bucle de poisoned-message, pero a costa de pérdida de datos.)
- Regla violada: checklist RabbitMQ (ack strategy / dead-letter).
- Recomendación: ackear solo en éxito; ante excepción, `basic_nack(requeue=False)` hacia una DLX configurada con límite de reintentos.

### [MEDIO] M-06 — Sin validación de esquema ni de tamaño de los mensajes
- Componente: rabbitmq
- Archivo:línea: `pilar2-distribuido/common/messaging/rabbitmq.py:170-172`
- Categoría: seguridad
- Evidencia:
    ```python
    payload = json.loads(body.decode())   # sin límite de tamaño ni validación de esquema
    handler(payload)
    ```
- Impacto: payloads no confiables se parsean y pasan al handler sin esquema; un cuerpo enorme consume memoria (DoS) y campos inesperados llegan a la lógica de dominio (p. ej. `nonce` no entero → `int(nonce)` lanza, mensaje perdido por M-05).
- Regla violada: checklist RabbitMQ (validación/deserialización, límites de tamaño).
- Recomendación: validar contra un esquema (pydantic/jsonschema), imponer `max-length`/`max-message-size` en las colas y rechazar payloads fuera de contrato.

### [MEDIO] M-07 — El tópico de desafío no controla quién publica ni firma el desafío
- Componente: rabbitmq | dominio
- Archivo:línea: `pilar2-distribuido/common/messaging/rabbitmq.py:99-100`, `pilar2-distribuido/nct-coordinator/nct/coordinator.py:212-216`
- Categoría: seguridad | correctitud-dominio
- Evidencia:
    ```python
    def publish_challenge(self, challenge):
        self._publish(EXCHANGE_DESAFIO, DESAFIO_ROUTING_KEY, challenge)  # sin firma
    ```
- Impacto: cualquier nodo con acceso al exchange `desafio_activo` puede publicar un desafío falso (otro `n_zeros_required`, `partial_hash_base` o `deadline`) suplantando al NCT; los pools/workers minarían el desafío del atacante. No hay permisos de RabbitMQ por rol ni firma del NCT sobre el desafío.
- Regla violada: AGENT.md §5/P2 (el desafío lo publica el NCT), checklist RabbitMQ (control de publicador del tópico de coordinación).
- Recomendación: restringir por ACL de RabbitMQ el `write` al exchange de desafío solo al rol NCT y/o firmar el desafío con la clave del NCT, que los workers verifiquen.

### [MEDIO] M-08 — Contenedores sin `securityContext`
- Componente: k8s
- Archivo:línea: todos los manifests bajo `pilar3-despliegue/kubernetes/` (grep `securityContext` → 0 resultados)
- Categoría: seguridad
- Evidencia:
    ```
    $ grep -rln securityContext pilar3-despliegue/kubernetes/  →  (vacío)
    ```
- Impacto: los pods corren como root con el rootfs escribible y todas las capabilities por defecto; una RCE en cualquier servicio escala más fácil dentro del nodo.
- Regla violada: checklist Kubernetes (runAsNonRoot, readOnlyRootFilesystem, allowPrivilegeEscalation:false, drop capabilities).
- Recomendación: añadir `securityContext` con `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true` y `capabilities.drop: [ALL]` a cada deployment/statefulset.

### [MEDIO] M-09 — Falta de `resources.requests/limits` en la mayoría de los workloads
- Componente: k8s
- Archivo:línea: `pilar3-despliegue/kubernetes/applications/*.yaml`, `pilar3-despliegue/kubernetes/gpu-cluster/*-deployment.yaml` (solo `redis-statefulset.yaml` define `resources:`)
- Categoría: seguridad | rendimiento
- Evidencia:
    ```
    $ grep -rln "resources:" pilar3-despliegue/kubernetes/
    pilar3-despliegue/kubernetes/gpu-cluster/kustomization.yaml
    pilar3-despliegue/kubernetes/infrastructure/redis-statefulset.yaml  (solo storage)
    ```
- Impacto: NCT, API, frontend, workers y pool-coordinator no declaran límites; un pico de consumo (o un mensaje gigante, M-06) puede provocar starvation/OOM del nodo y tumbar servicios vecinos.
- Regla violada: checklist Kubernetes (requests/limits; sin límites → DoS de nodo).
- Recomendación: definir `requests` y `limits` de CPU/memoria por contenedor.

### [MEDIO] M-10 — Sin NetworkPolicies
- Componente: k8s
- Archivo:línea: `pilar3-despliegue/kubernetes/` (grep `NetworkPolicy` → 0 resultados)
- Categoría: seguridad
- Evidencia: `grep -r "kind: NetworkPolicy" kubernetes/` → vacío.
- Impacto: tráfico este-oeste sin restricción; cualquier pod alcanza Redis (A-02), RabbitMQ y el management de RabbitMQ. Amplifica A-02.
- Regla violada: checklist Kubernetes (NetworkPolicies).
- Recomendación: políticas default-deny por namespace y allowlists explícitas (API→Redis, NCT→Redis/RabbitMQ, workers→RabbitMQ).

### [MEDIO] M-11 — Redis y RabbitMQ con una sola réplica (SPOF de infraestructura)
- Componente: k8s
- Archivo:línea: `pilar3-despliegue/kubernetes/infrastructure/redis-statefulset.yaml:8`, `pilar3-despliegue/kubernetes/infrastructure/rabbitmq-statefulset.yaml:8`
- Categoría: seguridad
- Evidencia:
    ```yaml
    replicas: 1    # redis
    replicas: 1    # rabbitmq
    ```
- Impacto: los dos servicios que custodian el estado y el transporte son puntos únicos de falla; su caída detiene toda la red y, para Redis, la recuperación depende solo del AOF del PVC. DOC P1 exige mínimo 2 réplicas por servicio. (El NCT sí cumple HA con primary+standby = 2 pods.)
- Regla violada: DOC P1 ("mínimo 2 réplicas por servicio").
- Recomendación: Redis con replica/Sentinel o cluster; RabbitMQ con quorum queues y ≥3 nodos; documentar el trade-off si se mantiene 1 por costo.

### [MEDIO] M-12 — Reparto del espacio de nonces en el pool con gaps y duplicados
- Componente: rendimiento
- Archivo:línea: `pilar2-distribuido/worker/worker_pkg/pool_coordinator/coordinator.py:149-162`
- Categoría: rendimiento | correctitud-dominio
- Evidencia:
    ```python
    fragment = self._pending_fragments[0]
    chunk = max(1, space // total)
    rmin = fragment["range_min"] + idx * chunk
    rmax = min(fragment["range_min"] + (idx + 1) * chunk, fragment["range_max"])
    ...
    self._pending_fragments.popleft()
    for _ in range(idx):
        dup = fragment.copy(); dup["range_min"] = rmin; dup["range_max"] = rmax
        self._pending_fragments.appendleft(dup)   # reinserta el MISMO sub-rango idx veces
    ```
- Impacto: al asignar el sub-rango `idx` se descarta el fragmento original y se reinsertan `idx` copias del sub-rango **ya asignado**, no de los sub-rangos restantes. Resultado: rangos no cubiertos (soluciones que existen y nunca se prueban → expiraciones espurias) y trabajo duplicado entre miners. La partición no garantiza cobertura ni disjunción del espacio de nonces (P5/§3.9).
- Regla violada: checklist rendimiento (partición del espacio de nonces: solapamiento/gaps), DOC P5.
- Recomendación: precomputar sub-rangos disjuntos del fragmento y reinsertar exactamente los no asignados; cubrir todo `[range_min, range_max)` exactamente una vez.

### [MEDIO] M-13 — Clave privada persistida en `localStorage` en texto plano
- Componente: cripto
- Archivo:línea: `pilar2-distribuido/voxchain-frontend/src/app/core/services/identity.service.ts:44-46`
- Categoría: seguridad
- Evidencia:
    ```ts
    const identity: Identity = { pubkey, exportedPrivkey };
    localStorage.setItem(this.storageKey, JSON.stringify(identity));   // privkey en claro
    ```
- Impacto: la clave privada (PKCS#8 base64) queda en `localStorage` sin cifrar, exfiltrable ante cualquier XSS en el frontend. No viola §10 estricto (no se envía a Redis/Vault/RabbitMQ y no sale del nodo), pero contradice el espíritu de §3.1 ("ni siquiera para almacenamiento"). La generación en sí es correcta (`crypto.subtle.generateKey`, CSPRPNG).
- Regla violada: AGENT.md §3.1 (almacenamiento de la clave privada).
- Recomendación: usar `CryptoKey` no exportable (`extractable: false`) almacenada en IndexedDB, o cifrar la privkey con una passphrase del usuario antes de persistir.

### [BAJO] B-01 — Acciones de CI ancladas por tag móvil, no por SHA
- Componente: cicd
- Archivo:línea: `.github/workflows/ci-checks.yml:13,16,27,28`, `.github/workflows/01-infra.yml:25,29,35`, `.github/workflows/03-apps.yml:58,62,82`
- Categoría: seguridad
- Evidencia:
    ```yaml
    - uses: actions/checkout@v4
    - uses: gitleaks/gitleaks-action@v2
    - uses: google-github-actions/auth@v2
    ```
- Impacto: los tags `@v4`/`@v2` son mutables; un compromiso de la acción upstream ejecutaría código arbitrario en el pipeline con acceso a los secrets de CI (supply chain).
- Regla violada: checklist secretos/supply chain (pinning por SHA).
- Recomendación: anclar cada acción a un commit SHA completo y usar Dependabot para actualizarlas.

### [BAJO] B-02 — Backend remoto de OpenTofu deshabilitado (state local)
- Componente: cicd | k8s
- Archivo:línea: `pilar3-despliegue/terraform/gke/versions.tf:23-28`
- Categoría: seguridad
- Evidencia:
    ```hcl
    # Descomentar para usar GCS backend:
    # backend "gcs" {
    #   bucket = "voxchain-terraform-state"
    ```
- Impacto: con el backend comentado el `terraform.tfstate` queda local (puede contener outputs sensibles) y sin bloqueo de concurrencia; riesgo de corrupción/fuga de estado.
- Regla violada: checklist Kubernetes/IaC (backend remoto, sin secretos en el state).
- Recomendación: habilitar el backend GCS con versionado y, si aplica, cifrado.

### [BAJO] B-03 — Defaults de conexión con credenciales débiles/ausentes
- Componente: secrets | cripto
- Archivo:línea: `pilar2-distribuido/common/config.py:22-23`
- Categoría: seguridad
- Evidencia:
    ```python
    RABBITMQ_URL = get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    REDIS_URL    = get("REDIS_URL", "redis://redis:6379/0")
    ```
- Impacto: si el entorno no inyecta las variables, el sistema arranca contra `guest:guest` y Redis sin auth. Es un default de desarrollo, pero invita a desplegar sin credenciales reales (relacionado con A-02).
- Regla violada: DOC "Zero static keys / credenciales por ambiente".
- Recomendación: fallar el arranque (fail-closed) si las URLs no traen credenciales en entornos no-dev, o eliminar el default con credenciales.

### [BAJO] B-04 — Secret de K8s con placeholder commiteado y `.secrets/` fuera del `.gitignore`
- Componente: secrets
- Archivo:línea: `pilar3-despliegue/.secrets/rabbitmq-credentials.yaml:9-11`, `.gitignore`
- Categoría: seguridad
- Evidencia:
    ```yaml
    stringData:
      username: "voxchain-worker"
      password: "CHANGE_ME_IN_PROD"
      keda-host: "amqps://voxchain-worker:CHANGE_ME_IN_PROD@placeholder.voxchain.local:5671/"
    ```
- Impacto: es un placeholder (no un secreto real), pero el manifiesto `Secret` con `stringData` está versionado y `.secrets/` no figura en `.gitignore`; el patrón habilita que un futuro valor real se comitee por inercia. El `.sops.yaml` solo cifra `*.enc.yaml`, no este archivo.
- Regla violada: DOC "No commitear secrets; `.gitignore` apropiado desde el inicio".
- Recomendación: añadir `pilar3-despliegue/.secrets/` (salvo `*.enc.yaml`) al `.gitignore`, renombrar a `.example` y depender exclusivamente de `ExternalSecret`/GCP Secret Manager (que ya existe en `infrastructure/rabbitmq-external-secret.yaml`).

### [INFO] I-01 — `verify_nonce` usa `startswith` (semántica PoW correcta, no es bug)
- Componente: dominio
- Archivo:línea: `pilar2-distribuido/common/blockchain/challenge.py:64-73`
- Categoría: correctitud-dominio
- Evidencia:
    ```python
    ok = hash_hex.startswith(prefix_for_zeros(n_zeros_required))
    ```
- Impacto: el checklist menciona "exactamente n ceros"; la implementación acepta "al menos n ceros", que es la semántica estándar de PoW y preserva la asimetría n/n+1 (`n_zeros_for_action`, `:39-49`). Un hash con n+1 ceros para una promulgación es válido y más difícil de obtener: no rompe el modelo. Se documenta para trazabilidad, **no es hallazgo**.
- Regla violada: ninguna.
- Recomendación: ninguna; si se quisiera "exactamente n", documentarlo explícitamente, pero no es lo deseable en PoW.

### [INFO] I-02 — MD5 device asume host/device little-endian
- Componente: minero-cuda
- Archivo:línea: `pilar1-minero/gpu/include/md5.cuh:80-92`
- Categoría: correctitud-dominio
- Evidencia:
    ```cpp
    uint32_t block[16] = {0};
    unsigned char* b = (unsigned char*)block;   // empaquetado byte→word asume LE
    ```
- Impacto: el empaquetado de los bytes del mensaje en `uint32_t` vía alias depende de endianness; las GPUs NVIDIA son little-endian, por lo que es correcto en el target. Se anota porque el aliasing `unsigned char* ↔ uint32_t*` es UB formal en C++ y rompería en un device big-endian hipotético.
- Regla violada: ninguna en la práctica.
- Recomendación: empaquetar las words con shifts explícitos para evitar el aliasing y la dependencia de endianness.

### [INFO] I-03 — `text_hash` usa SHA-256 (cumple §7.1); MD5 solo para el PoW iterativo
- Componente: cripto
- Archivo:línea: `pilar2-distribuido/scripts/propose_law.py:40`, `pilar2-distribuido/common/blockchain/challenge.py:59-61`
- Categoría: correctitud-dominio
- Evidencia:
    ```python
    text_hash = hashlib.sha256(args.text.encode()).hexdigest()   # identidad de ley = SHA-256
    ```
    ```python
    return hashlib.md5(f"{partial_hash_base}{nonce}".encode()).hexdigest()  # PoW = MD5 (ok)
    ```
- Impacto: confirma la separación correcta exigida por DOC Hit #4 / AGENT.md §7.1: SHA-256 para la integridad de identidad de la ley y `block_hash` (`block.py:53`), MD5 solo para el desafío iterativo. **No es hallazgo**; se lista como verificación positiva.
- Regla violada: ninguna.
- Recomendación: ninguna.

---

## 3. Verificación manual requerida

Clases de bug plausibles que no pude confirmar solo con el código disponible:

- **Provisión real del usuario de RabbitMQ.** El `rabbitmq-statefulset.yaml` solo inyecta `erlang-cookie` (opcional) y no define `RABBITMQ_DEFAULT_USER/PASS`; el usuario `voxchain-worker` aparece en secrets/ExternalSecret pero no veo dónde se crea en el broker. Verificar si el broker queda con `guest` (restringido a localhost) y si los workers externos pueden autenticarse realmente sobre el LoadBalancer `:5671`.
- **Exposición del management de RabbitMQ.** El puerto 15672 (no TLS) está en el contenedor; el Service externo solo publica 5671, pero conviene confirmar que ningún Ingress/Service expone 15672/15671 a Internet.
- **Contenido real de GCP Secret Manager** (claves `rabbitmq-user/pass/tls-*`): no auditable desde el repo; confirmar que no haya credenciales débiles ni claves privadas de identidad allí.
- **Ejecución efectiva de gitleaks como gate.** `gitleaks-action@v2` está en `ci-checks.yml`; confirmar en un run real que falla el job ante un secret (y considerar reglas custom para asignaciones HCL como A-03, que las reglas por defecto podrían no detectar).
- **Comportamiento del kernel CUDA bajo overflow (M-01/M-04):** requiere ejecución con `compute-sanitizer` para confirmar el desbordamiento y las lecturas fuera de rango.
- **Whitepaper de dominio `Democracia_Via_BlockChain.md`:** no existe en el repo; si contiene reglas normativas adicionales, parte del contrato de dominio no pudo cotejarse.

---

## 4. Limitaciones conocidas confirmadas (AGENT.md §9 — no son defectos)

- **Sybil (§9):** confirmado — no hay verificación de identidad real ni firma (ver A-01, que es la parte que **excede** lo documentado: suplantación, no solo identidades propias).
- **Pérdida de estado de la ventana en falla del NCT (§4, §9):** confirmado — `_active` vive solo en memoria (`coordinator.py:72`); `become_leader` limpia y abre ventana nueva (`:313-329`). No se persiste para recuperación, tal como se declara.
- **Split-brain del NCT (§9, §11.4):** confirmado el mecanismo declarado — `renew_leadership` (Lua, `redis_store.py:320-332`) y `step_down` (`coordinator.py:331-349`) con ventana de solapamiento de hasta `HEARTBEAT_INTERVAL`. A-04 señala que el fork de cadena durante ese solapamiento **agrava** la limitación declarada.
- **Concentración de poder (§9):** confirmado como decisión de diseño; el pool agrega capacidad y compite como un nodo (`pool_coordinator/coordinator.py`). No se mitiga, por diseño.
- **MinIO (§7.1, opcional):** el texto de la ley se almacena comprimido en Redis (`text_compressed`), no en MinIO; coherente con "opcional".

---

## 5. Cobertura

**Auditado:**
- Dominio/consenso: `nct-coordinator/nct/coordinator.py`, `queue_logic.py`, `common/blockchain/{challenge,block,chain}.py`, `common/queue.py` (vía reexport), `common/storage/redis_store.py`.
- Minero CUDA/CPU: `pilar1-minero/gpu/src/05_brute_force_range.cu`, `gpu/include/md5.cuh`, `cpu/src/brute_force.py`.
- Mensajería: `common/messaging/rabbitmq.py`, worker `pool_coordinator/coordinator.py`, `worker/worker_pkg/miner.py`.
- API/propuesta: `voxchain_api/routers/laws.py`, `scripts/propose_law.py`, frontend `identity.service.ts`.
- Secretos/CI: `.gitignore`, `.gitleaks.toml`, `.github/workflows/ci-checks.yml` (+ `01/03`), `.secrets/*`, ExternalSecret/SecretStore, historial de git (`git log -p`).
- K8s/IaC: manifests bajo `pilar3-despliegue/kubernetes/**`, `terraform/gke/{main,versions,terraform.tfvars}.tf(vars)`.
- Config: `common/config.py`.

**Auditado parcialmente / no abierto en profundidad (sin hallazgos nuevos aparentes):** `nct/bully.py`, `nct/monitor.py`, `worker/worker_pkg/{pool_worker,standalone_worker,admin_server}.py`, `voxchain_api/services/*`, `common/{health,metrics,logging_setup}.py`, tests. Se recomienda una segunda pasada sobre `bully.py`/`monitor.py` para la lógica fina de elección PoW.

**No encontrado en el repo:**
- `Democracia_Via_BlockChain.md` (documento de dominio exigido por el prompt) — **ausente**.
- **Vault** como tal: AGENT.md §6.1 nombra Vault, pero la implementación usa **GCP Secret Manager** vía External Secrets (`secretstore.yaml`, `rabbitmq-external-secret.yaml`). Es una desviación de la fuente de verdad que conviene documentar en el informe (no es un defecto de seguridad por sí mismo).
- **MinIO** (opcional, §7.1): no desplegado; el texto se guarda comprimido en Redis.
- **Descubrimiento P2P** (§3.8): no se observa implementación; la coordinación es centralizada vía RabbitMQ/NCT.
