# PRD · Sistema de gestión de boletos y reservaciones de eventos

Equipo: Los Kubermates · Integrantes: [@Oswaldo-F](https://github.com/Oswaldo-F) (Flores Herrera Oswaldo), [@FerrRv](https://github.com/FerrRv) (Reyes Vázquez Fernando), [@menavaledo](https://github.com/menavaledo) (Valencia Lerdo Dalia Jimena), [@JavixVP](https://github.com/JavixVP) (Velasco Pacheco Javier) · Fecha: 2026-10-08

## 1. Problema y usuarios

Dificultades para gestionar boletos, disponibilidad, compras y reservaciones de eventos. Los usuarios son asistentes de eventos (usuarios finales).

Hoy este problema se resuelve con plataformas como Ticketmaster, que presentan desafíos importantes cuando hay demanda muy alta: saturación de tráfico, lentitud o interrupciones durante la compra, desactualización de la disponibilidad de lugares, e inconsistencias entre reservaciones, pagos y generación de boletos. También surgen dificultades cuando varios usuarios intentan adquirir los últimos lugares al mismo tiempo, o cuando un pago se procesa pero la confirmación tarda en reflejarse.

## 2. Por qué es un sistema distribuido

El proyecto ataca de frente dos problemas que requieren distribución:

- **Tráfico alto**: el sistema debe soportar muchas solicitudes simultáneas, especialmente sobre un mismo evento popular.
- **Desactualización de disponibilidad**: cuando varios usuarios compiten por los últimos lugares, el sistema debe mantener el conteo de disponibilidad consistente entre todas las copias de los servicios que atienden solicitudes al mismo tiempo.

Como secundario (no el foco principal, pero sí resuelto): la consistencia entre pago y boleto, para evitar que un usuario pague y no reciba su boleto, o que se le cobre dos veces.

## 3. Objetivos y lo que no vamos a hacer

**Dentro del alcance:**
1. Consulta de eventos
2. Reservación y control de disponibilidad
3. Compra, pago y generación de boletos
4. Notificaciones de compra (exitosa o fallida)

**Fuera del alcance:**
- Pagos reales (se simulan)
- Reventa de boletos entre usuarios
- Reembolsos
- Promociones y descuentos

La disponibilidad es **general por cupo** (un contador de "quedan N lugares" por evento), no por asiento numerado.

## 4. El requisito que perseguimos y lo que dejamos atrás

Perseguimos **consistencia de disponibilidad bajo concurrencia** por encima de la velocidad de respuesta al usuario. El mecanismo elegido es **bloqueo pesimista**: cuando un usuario reserva, el sistema aparta el lugar de forma exclusiva mientras se completa el pago.

Lo que sacrificamos a cambio: el **tiempo de espera del usuario**. Si varios usuarios compiten por los últimos lugares, solo los primeros en confirmar la reservación continúan; los demás reciben un mensaje de que los lugares se agotaron.

El servicio de Reservas es responsable de vigilar el tiempo del bloqueo: cada reservación aparta el lugar durante **10 minutos**. Si el pago no se completa en ese tiempo, la reservación expira y el lugar se libera automáticamente.

El bloqueo pesimista vive en la **base de datos compartida** (no en memoria de una sola copia del servicio), porque el servicio de Reservas corre en varias copias y todas deben consultar y modificar los mismos datos para no rebasar el cupo disponible.

## 5. Historias de usuario

### Consulta de eventos
**Como** usuario, **quiero** consultar los eventos disponibles **para** conocer sus fechas, precios y cupo antes de reservar boletos.

Criterios de aceptación:
1. El sistema muestra una lista de eventos disponibles con su nombre, fecha, precio y cupo restante.
2. Al seleccionar un evento, se muestra su información completa.
3. Si no hay eventos disponibles, el sistema muestra un mensaje indicando que no hay eventos para consultar.
4. Si un evento agota su cupo, debe mostrarse sin disponibilidad para nuevas reservaciones.
5. La información mostrada debe coincidir con los datos registrados en el sistema.

### Reservación y control de disponibilidad
**Como** usuario, **quiero** reservar un lugar en un evento **para** tener 10 minutos para completar mi pago antes de que mi reservación expire.

Criterios de aceptación:
1. El sistema permite reservar un lugar únicamente si hay disponibilidad.
2. Al crear una reservación, el sistema aparta el lugar durante 10 minutos para que el usuario complete su pago.
3. Si el usuario no completa el pago en 10 minutos, la reservación expira y el lugar vuelve a estar disponible.
4. Si se agotan los lugares, el sistema impide nuevas reservaciones y muestra un mensaje indicando que no hay disponibilidad.
5. Si varios usuarios intentan reservar los últimos lugares al mismo tiempo, el sistema evita que se rebase el cupo disponible.
6. La disponibilidad se actualiza correctamente para todos los usuarios después de una reservación, un pago confirmado o el vencimiento de una reservación.

### Compra, pago y generación de boletos
**Como** usuario, **quiero** pagar mi reservación y recibir mi boleto digital **para** tener acceso al evento.

Criterios de aceptación:
1. El sistema permite realizar el pago de una reservación vigente y muestra si fue aprobado o rechazado.
2. Si el pago es aprobado, el sistema confirma la compra y genera un boleto digital con un identificador único.
3. Si el pago es rechazado, la compra no se confirma y se libera el lugar de acuerdo con el estado de la reservación.
4. Si el pago es aprobado pero falla la generación del boleto, la compra permanece confirmada y la generación del boleto queda pendiente para reintentarse automáticamente cuando el servicio esté disponible.
5. Los reintentos no deben generar boletos duplicados ni realizar cobros adicionales.
6. Cuando el boleto se genera correctamente, el sistema permite al usuario consultarlo y visualizar su identificador único.

### Notificaciones de compra
**Como** usuario, **quiero** recibir una notificación sobre el resultado de mi compra **para** saber si mi pago fue aprobado y si mi boleto está disponible.

Criterios de aceptación:
1. Si el pago es aprobado y el boleto se genera correctamente, el sistema envía una notificación de compra exitosa con los datos del evento y el identificador del boleto.
2. Si el pago es rechazado, el sistema notifica al usuario que la compra no se completó.
3. Si el pago es aprobado pero falla la generación del boleto, el sistema informa que la compra está confirmada y que el boleto está pendiente de generación.
4. Cuando el boleto pendiente se genera correctamente, el sistema notifica al usuario que ya puede consultarlo.
5. Si falla el envío de una notificación, el sistema registra el error y permite reintentar el envío sin duplicar la compra ni generar boletos adicionales.

## 6. Del monolito a los servicios

**Módulos del monolito inicial:** usuarios, gestión de eventos, reservas, pagos, notificaciones, entradas digitales.

**Servicios resultantes y dueño de cada dato:**

| Servicio | Dueño exclusivo de |
|---|---|
| Usuarios | Datos de los usuarios |
| Eventos | Información de eventos: fechas, lugares, capacidad y precios |
| Reservas | Reservaciones, disponibilidad de boletos, estados y tiempos de expiración |
| Pagos | Registros de pagos, montos y estados de las transacciones |
| Boletos digitales | Generación de boletos y asignación de identificadores únicos |
| Notificaciones | Mensajes enviados y registros de notificaciones a usuarios |

Regla de frontera: si un servicio necesita información de otro, se comunica con el servicio correspondiente — nunca modifica directamente sus datos o tablas.

**Flujo de compra (orden de llamadas):**
1. Reservas: el usuario selecciona un evento y solicita apartar un lugar. Reservas verifica disponibilidad y bloquea temporalmente el cupo.
2. Reservas solicita a Pagos que procese el pago (llamada síncrona, con límite de tiempo).
3. Si el pago es aprobado, Pagos informa el resultado y Reservas confirma la compra. **Este es el punto de no retorno**: a partir de aquí la compra no se cancela automáticamente.
4. Reservas solicita a Boletos digitales que genere el boleto con identificador único.
5. Cuando el boleto se genera, se solicita a Notificaciones que informe al usuario.
6. Si el pago es rechazado, o la reserva vence antes de confirmarse, se libera el lugar y se informa al usuario.

Plan de ramas sugerido, siguiendo el patrón visto en clase: `01-monolito`, `02-separacion`, `03-...` (una rama por etapa de partición).

## 7. Dónde vive cada pieza

| Pieza | Dónde vive | Por qué | Qué pasa si falla |
|---|---|---|---|
| API gateway | Traefik, única puerta de entrada para el cliente | El cliente no necesita conocer las direcciones individuales de cada servicio; Traefik dirige cada solicitud al servicio correspondiente | — |
| Directorio / DNS | Direcciones fijas configuradas en Docker Compose | Suficiente para el alcance del proyecto, sin necesidad de descubrimiento dinámico | — |
| Balanceo | Traefik reparte solicitudes entre copias del servicio de **Reservas** (único servicio con réplicas en esta versión) | Reservas concentra la mayor concurrencia: varios usuarios intentan apartar boletos del mismo evento al mismo tiempo. Eventos solo atiende consultas y Boletos actúa después de una compra ya confirmada, con menor carga; se limita el alcance para no aumentar la complejidad del proyecto. Puede extenderse a otros servicios más adelante | — |
| Datos | PostgreSQL (relacional) en Usuarios, Eventos, Reservas, Pagos y Boletos digitales; base documental en Notificaciones | Reservas necesita transacciones y bloqueos confiables para el control de disponibilidad; Notificaciones almacena mensajes y registros de envío, un caso de uso más documental. Cada servicio usa la base que mejor se ajusta a sus necesidades | — |
| Operaciones entre servicios | Flujo síncrono Reservas → Pagos → Boletos digitales → Notificaciones, orquestado por Reservas | El bloqueo pesimista vive en la base de datos compartida de Reservas, que todas las copias del servicio consultan y modifican, evitando vender más boletos de los disponibles | Si el pago se aprueba pero falla la generación del boleto, la compra queda confirmada y el boleto pendiente; el sistema reintenta automáticamente cuando el servicio se restablece, sin volver a cobrar, usando el identificador único de la compra para evitar duplicados |
| Manejo de fallas | Llamada síncrona Reservas → Pagos con límite de tiempo (timeout); identificador único por transacción para idempotencia | Si Pagos no responde a tiempo, Reservas no debe esperar indefinidamente; el identificador único evita cobrar dos veces si se reintenta una operación que en realidad sí se había completado del lado del servidor | Timeout vencido → Reservas asume fallo y puede reintentar; el identificador único de la transacción evita cobros duplicados o boletos duplicados en el reintento |

## 8. Stack y cómo se levanta

- **Lenguaje y framework:** Python con FastAPI para los microservicios — permite crear APIs REST de forma sencilla y atender solicitudes de manera asíncrona.
- **API Gateway:** Traefik — distribuye las solicitudes entre las distintas copias de los servicios.
- **Orquestación local:** Docker Compose — levanta y conecta todos los contenedores (servicios y bases de datos), facilita la configuración del entorno y la ejecución de varias copias para soportar mayor demanda.
- **Bases de datos:** PostgreSQL (Usuarios, Eventos, Reservas, Pagos, Boletos digitales); base documental (Notificaciones).

## 9. Decisiones de arquitectura

| Decisión | Alternativas descartadas | Por qué |
|---|---|---|
| Bloqueo pesimista para control de disponibilidad | Decremento atómico/optimista; cola de espera | El equipo decidió sacrificar tiempo de espera del usuario a cambio de evitar sobreventa y simplificar el manejo de la condición de carrera |
| Disponibilidad general por cupo (no asiento numerado) | Asiento numerado con bloqueo individual por asiento | Se simplifica el modelo de inventario y el bloqueo pesimista opera sobre un contador, no sobre entidades individuales |
| Bloqueo vive en la base de datos compartida, no en memoria del servicio | Lock en memoria de una sola copia del servicio | El servicio de Reservas corre en varias copias; un lock en memoria de una copia no sería visto por las demás y permitiría sobreventa |
| Reintento con idempotencia para fallas en generación de boletos y pagos | Cancelar la compra automáticamente si falla un paso posterior al pago aprobado | El punto de no retorno ya pasó (pago aprobado + reserva confirmada); cancelar perdería el pago del usuario. Se prefiere reintentar sin duplicar cobros ni boletos |
| Solo el servicio de Reservas tiene réplicas en esta versión | Replicar también Eventos y Boletos digitales | Reservas concentra la mayor concurrencia crítica; Eventos y Boletos tienen menor carga y menos operaciones simultáneas críticas. Se limita el alcance para controlar la complejidad del proyecto |
| Comunicación síncrona Reservas → Pagos con timeout | Comunicación asíncrona vía cola de mensajes | El equipo eligió el enfoque síncrono para esta versión del proyecto |
| Llamada directa entre servicios para el flujo de compra, orquestada por Reservas | Coreografía por eventos / cola de mensajes entre todos los servicios | Mantiene el flujo simple y explícito para el alcance del proyecto |

## 10. Preguntas abiertas y desacuerdos

Ninguna identificada hasta el momento — el equipo acordó todas las decisiones registradas en este documento.
