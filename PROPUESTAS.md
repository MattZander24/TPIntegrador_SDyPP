
**Lo que el escenario debe justificar:**
- Transacciones entre entidades (el TP dice "usuario A → usuario B → monto", pero puede ser cualquier transferencia de valor)
- Proof of Work real: nodos compitiendo para resolver un hash y ganar el derecho a escribir un bloque
- Un coordinador (NCT) que forma bloques, define dificultad y valida resultados
- RabbitMQ distribuyendo tareas de minería entre workers
- Redis persistiendo la cadena
- Al menos 2 réplicas por servicio en Kubernetes

---

Algunas variantes concretas para pensar:

**1. Elección de coordinador en una red de sensores / IoT**
Nodos distribuidos geográficamente (estaciones meteorológicas, sensores industriales) necesitan elegir quién agrega y publica el estado global. En lugar de elegir por ID o por heartbeat, compiten con PoW. El ganador es el "coordinador de turno" y escribe el bloque de estado del sistema. Las "transacciones" son lecturas de sensores que el coordinador valida y agrupa.

**2. Asignación de recursos en un cluster HPC**
Varios equipos compiten por tiempo de cómputo en un recurso compartido (una GPU cara, un storage especial). Hacen PoW para ganar el slot. Queda registrado en la blockchain quién usó qué recurso y cuándo — inmutable, auditable, sin árbitro central.

**3. Tu idea directa: votación por esfuerzo**
N equipos distribuidos quieren tomar una decisión colectiva (elegir algoritmo, elegir parámetro de configuración, elegir líder). Cada equipo que quiere votar tiene que primero "ganar el derecho" resolviendo un desafío PoW. Solo los que lo resuelven dentro de una ventana de tiempo tienen voto válido. El resultado de la votación se escribe en la blockchain. Esto evita que un nodo con mala conexión pero mucho poder de vóto bloquee decisiones — si no puede hacer el trabajo computacional, no vota.

---

## El problema central con el pool

El pool (P5) es el componente más complejo del TP: subdivide tareas en rangos de nonce, recibe keep-alives de los mineros GPU, y escala dinámicamente mineros CPU si no hay GPU disponibles. Para que eso tenga sentido narrativo, el escenario necesita:

- Trabajo computacional **variable en volumen** (a veces hay mucho, a veces poco)
- Múltiples participantes con **capacidad heterogénea** (algunos con GPU, otros sin)
- Una razón para que **la velocidad de resolución importe** (si tardás mucho, perdés algo)

Con eso en mente, estas son mis tres propuestas:

---

### 🔴 Propuesta A — Red de auditoría de logs distribuida

**Escenario:** Varios servicios en producción (microservicios de una empresa, o nodos de una red académica) generan eventos de log continuamente. Cada cierta cantidad de eventos, el sistema debe "sellar" ese lote en un bloque para garantizar que no fue alterado retroactivamente — útil para compliance, auditoría forense o detección de fraude.

**Cómo mapea al TP:**
- **Transacciones** = eventos de log (servicio origen, servicio destino, tipo de evento, timestamp)
- **PoW** = sellado criptográfico del lote, garantiza inmutabilidad
- **Pool** = el volumen de logs es impredecible; en horas pico hay miles de eventos por segundo y el pool necesita escalar mineros CPU automáticamente; en horas valle los GPU están ociosos
- **Coordinador** = decide cuándo un lote está lleno y lo manda a minar
- **Blockchain** = historial auditable e inmutable de todos los eventos

**Por qué suma al pool:** el volumen variable de logs hace que el autoscaling del pool sea demostrable con datos reales durante las pruebas de carga del Pilar 3.

---

### 🟡 Propuesta B — Mercado de recursos computacionales entre nodos

**Escenario:** Varios nodos en una red (podrían ser universidades, laboratorios, equipos de investigación) tienen recursos computacionales que a veces sobran y a veces faltan. Un nodo que necesita procesar un trabajo grande puede "comprar" tiempo de cómputo de otros nodos. Las transacciones son esas transferencias de recursos, y la blockchain garantiza que nadie haga trampa (que nadie cobre sin haber trabajado).

**Cómo mapea al TP:**
- **Transacciones** = "nodo A cede X unidades de cómputo a nodo B por Y créditos"
- **PoW** = para escribir esa transacción en la cadena, algún minero tiene que trabajar — el costo de minado es el "fee" del mercado
- **Pool** = cuando hay muchas transacciones pendientes simultáneamente, el pool las subdivide y distribuye entre todos los workers disponibles; cuando el mercado está tranquilo, destruye instancias
- **Coordinador** = forma bloques con las transacciones pendientes, ajusta dificultad según la velocidad de la red

**Por qué suma al pool:** la demanda del mercado fluctúa naturalmente, lo que hace que el comportamiento de autoscaling del pool sea el corazón del sistema, no un agregado.

---

### 🟢 Propuesta C — Sistema de certificación de resultados científicos distribuidos (la que yo elegiría)

**Escenario:** Varios equipos de investigación distribuidos ejecutan experimentos computacionales (simulaciones, entrenamientos de modelos pequeños, procesamiento de datos). Cuando un equipo quiere **publicar un resultado** en el sistema compartido, no puede simplemente escribirlo — otro nodo de la red tiene que **verificar y minar ese resultado** para que quede registrado. Esto garantiza que ningún equipo puede falsificar resultados unilateralmente.

**Cómo mapea al TP:**
- **Transacciones** = "equipo A publica resultado X del experimento Y, con hash de los datos de entrada Z"
- **PoW** = un minero independiente tiene que hacer el trabajo para validar y sellar ese resultado
- **Pool** = cuando varios equipos publican resultados simultáneamente (fin de una ronda experimental), el pool explota en demanda y necesita escalar; esto es exactamente el escenario que justifica HPA + mineros CPU efímeros
- **Coordinador** = agrupa resultados relacionados en bloques temáticos, ajusta dificultad según cuántos equipos están activos
- **Blockchain** = registro inmutable de qué equipo publicó qué resultado y cuándo — reproducibilidad científica garantizada criptográficamente

**Por qué la elegiría:** conecta directamente con el contexto académico (UNLu, investigación), el pool tiene una justificación narrativa perfecta porque los "picos de publicación" son predecibles y demostrables en las pruebas, y la inmutabilidad de la blockchain tiene un valor concreto y explicable en el informe y en el video.

---

## Mi recomendación concreta

Si tuvieras que elegir una para el TP, iría por **C**. Tiene tres ventajas prácticas: el escenario es fácil de explicar en el video sin conocimiento previo del evaluador, el pool tiene un rol protagonista y no decorativo, y las métricas del Pilar 3 (carga variable, dificultad creciente) tienen una narrativa natural dentro del escenario.

¿Querés que desarrolle alguna de estas en detalle, o las combinás con tu idea de votación?