# Arquitectura de la base

```text
CLI de desarrollo / futuro STT / futura GUI Windows
                       ↓
          Socket Unix privado → Core
                       ↓
       intención conocida / consulta de estado
          ├─ respuesta local inmediata
          └─ resolución insuficiente → intérprete opcional
                       ↓
     capacidad registrada / especialista / pregunta / bloqueo
                       ↓
        Policy → cola → trabajador → evidencia → resultado
                       ↓
           aviso de voz / consulta de detalle

Audio de salida → RMS → esfera ASCII independiente
```

El Core decide; un modelo propone. El catálogo describe capacidades realmente
conectadas. Los roles son programación, PC, diseño 3D e impresión 3D; General
sirve para conversación e interpretación, sin ser un paso obligatorio.

## Responsabilidades

- `router.py`: atajos conservadores de intención completa; el resto no se ejecuta
  por coincidencia de una palabra. Un proveedor opcional resuelve lenguaje libre.
- `providers.py`: protocolo de interpretación y validación estricta; adaptador
  Ollama local opcional. No descarga ni selecciona un modelo por el usuario.
- `agents.py`, `contracts/`: catálogo y contratos cargados por el runtime.
- `core.py`: propiedad de tarea/pregunta, planificación, cancelación y resultados.
- `store.py`: SQLite, eventos, proyectos e idempotencia; sin modelo de memoria paralelo.
- `capabilities.py`: operaciones concretas, tipadas y verificables.
- `policy.py`: autorización por operación y huella; no concede autoridad a prompts.
- `server.py`, `transport.py`: proceso persistente, IPC local y exclusión de doble Core.
- `voice.py`, `console.py`: reproducción/medición y superficie visual desacopladas.
- `codex_probe.py`: diagnóstico de compatibilidad, no ejecución Engineering.

## Estado verdadero

QUEUED significa aceptado y en cola; RUNNING significa que un trabajador
posee esa tarea. WAITING_INPUT libera el trabajador y conserva el ID.
BLOCKED significa que falta una integración o que solo se obtuvo una propuesta.
COMPLETED exige resultado de una capacidad. FAILED conserva un error seguro.
INTERRUPTED requiere revisión antes de volver a ejecutar.

Cada solicitud tiene un ID y digest. Se reserva antes de posibles efectos;
los reintentos confirmados devuelven la respuesta original. Si Core cae antes
de confirmar, el mismo ID no vuelve a ejecutar. La investigación del resultado
incierto es explícita.

Las consultas de estado y los comandos locales no esperan a la inferencia.
La cola está acotada a 64 y hay dos trabajadores por defecto. El acceso de
especialistas al mismo proyecto se serializa. No se mantienen modelos
cargados por cada agente. El intérprete opcional comparte un slot local.
No existen conversaciones de agentes entre sí ni un servicio de mensajería extra.

## Continuidad y contexto

Una tarea posee su proyecto, objetivo, capacidad, argumentos, preguntas,
respuestas y eventos. Una respuesta explícita continúa el mismo ID. El nombre
exacto de un proyecto puede resolver una única pregunta de proyecto pendiente.
Las respuestas ambiguas se aclaran; saludos y consultas no se convierten en
respuestas a una pregunta pendiente.

`thread_id` reserva el enlace futuro con sesiones de proveedor; no se afirma
que una sesión Codex ya exista. No se carga el historial completo en un modelo.
Solo se suministran datos del proyecto/tarea seleccionados.

## Límites de autorización

El socket y datos son privados al usuario. Procesos de ese mismo usuario forman
parte del perímetro de confianza. Esto no es aislamiento frente a software
malicioso ejecutado por la misma cuenta.

No hay un ejecutor genérico de shell. Git recibe argumentos fijos y desactiva
fsmonitor; STL y G-code solo admiten archivos acotados del proyecto. No se
envían contenidos de fuentes ni credenciales a proveedores.
No se considera un análisis de STL/G-code aprobación para imprimir.

## Próximos bloques

1. Conectar Codex con hilos por tarea, bridge de herramientas, contexto filtrado
   y pruebas reales de implementación/verificación.
2. STT, TTS y activación de voz sobre el punto de entrada existente. Consumidor
   de avisos, interrupción, eco y validación con micrófono físico.
3. Capacidades Linux para aplicaciones y una integración Blender comprobable.
4. Actualización por voz con candidato, hash, pruebas, aprobación, activación
   y rollback. Nunca reemplazar el proceso en mitad de una operación incierta.
5. Integración de impresora con perfil, artefacto, aprobación y monitorización.
6. GUI Windows reutilizando el Core y adaptadores de plataforma.

Los conectores externos se añaden cuando su flujo se puede probar de extremo
a extremo. Hasta entonces se muestran como ausentes, no como agentes operativos.
