# Proyecto Fénix

## Sistema de Autorreparación de Infraestructura

**Trabajo Práctico Final – Programación para Automatización II**

## 1. Descripción del proyecto

Fénix es un sistema desarrollado en Python para recibir eventos relacionados con recursos de infraestructura, validarlos, procesarlos de manera asíncrona y ejecutar acciones de autorreparación.

El proyecto utiliza FastAPI para recibir webhooks, Amazon SQS para administrar la mensajería y un Worker encargado de procesar los eventos y ejecutar las operaciones correspondientes.

El entorno de desarrollo utiliza LocalStack para emular servicios de AWS, permitiendo realizar pruebas locales sin administrar infraestructura real.

Además, incorpora registro de eventos, manejo de errores, reintentos, notificaciones y logging estructurado para facilitar la observabilidad del sistema.

## Integrantes, roles y responsabilidades

| Rol | Apellido y nombre | Correo | Módulos | Pruebas defendidas |
|---|---|---|---|---|
| Integrante 1 | Lamas, Joel | joelcaiok@gmail.com | `utils/errors.py`, `utils/validation.py`, `services/events.py` | `test_i1.py` |
| Integrante 2 | Cruz Vargas, Alex | Pendiente | Pendiente | Pendiente |
| Integrante 3 | Mendez, Mateo Joaquin | Pendiente | Pendiente | Pendiente |
| Integrante 4 | Sosa, Santiago Ezequiel | santiagohsosa2019@gmail.com | `logging_json.py`, `notifications.py` | `test_i4.py` |
| Integrante 5 | Lopez, Rocio Ayelen | Pendiente | Pendiente | Pendiente |



## 2. Tecnologías utilizadas

- Python 3.11 o superior.
- FastAPI.
- Uvicorn.
- Boto3.
- AWS SQS, EC2 y S3 mediante LocalStack.
- Requests.
- HTTPX.
- Python-dotenv.
- Pytest.
- Docker Compose.

## 3. Arquitectura y flujo de funcionamiento

El sistema sigue un flujo de procesamiento asíncrono:

1. Un emisor prepara un evento y genera su firma.
2. El receptor HTTP recibe el webhook.
3. Se verifica la firma y se valida el contenido del evento.
4. Se consulta el inventario para comprobar que el recurso esté autorizado.
5. El evento validado se publica en la cola de trabajo SQS.
6. El Worker recibe el mensaje y ejecuta el procesamiento.
7. Se realiza la acción de remediación correspondiente.
8. Se registra el resultado y se gestiona la notificación.
9. Si el procesamiento finaliza correctamente, el Worker confirma el mensaje en SQS.
10. Si ocurre un error procesable, el mensaje puede volver a intentarse y, según la política de redrive, llegar a la DLQ.

## 4. Estructura del proyecto

```text
fenix/
├── data/
│   ├── inventory.json
│   └── events.json
├── examples/
│   └── node-event.json
├── logs/
├── src/
│   └── fenix/
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── cloud_support.py
│       │   ├── demo.py
│       │   ├── events.py
│       │   ├── messaging.py
│       │   ├── notifications.py
│       │   ├── receiver.py
│       │   ├── remediation.py
│       │   ├── sqs.py
│       │   └── worker.py
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── crypto.py
│       │   ├── errors.py
│       │   ├── logging_json.py
│       │   ├── state.py
│       │   └── validation.py
│       ├── __init__.py
│       └── cli.py
├── tests/
│   ├── test_base.py
│   ├── test_contracts.py
│   ├── test_fenix.py
│   ├── test_i1.py
│   ├── test_i4.py
│   └── test_scenarios.py
├── compose.yaml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## 5. Requisitos previos

Para ejecutar el proyecto se necesita:

- Python 3.11 o superior.
- Docker Desktop con Docker Compose.
- Git.
- La imagen de LocalStack aprobada por la cátedra.
- El token de activación de LocalStack, cuando corresponda.

## 6. Instalación

### 6.1. Clonar el repositorio

```powershell
git clone https://github.com/SantiS156/Proyecto_Fenix.git
cd Proyecto_Fenix
```

### 6.2. Crear el entorno virtual

```powershell
python -m venv .venv
```

Activarlo en PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 6.3. Instalar dependencias

```powershell
python -m pip install --upgrade pip
pip install -e .
```

La instalación editable permite importar el paquete `fenix` desde el entorno virtual.

## 7. Configuración de variables de entorno

Crear el archivo `.env` a partir de `.env.example`:

```powershell
Copy-Item .env.example .env
```

Completar las variables necesarias:

| Variable | Descripción |
|---|---|
| `AWS_ENDPOINT_URL` | Endpoint local de LocalStack |
| `AWS_ACCESS_KEY_ID` | Credencial ficticia para el emulador |
| `AWS_SECRET_ACCESS_KEY` | Clave ficticia para el emulador |
| `AWS_DEFAULT_REGION` | Región de AWS |
| `GROUP_ID` | Identificador del grupo |
| `QUEUE_PREFIX` | Prefijo de las colas SQS |
| `PROJECT` | Identificador del proyecto |
| `WEBHOOK_SECRET` | Secreto compartido para verificar firmas |
| `NOTIFY_PROVIDER` | Proveedor de notificaciones |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | Identificador del chat de Telegram |
| `SLACK_WEBHOOK_URL` | URL de webhook de Slack |
| `LOCALSTACK_AUTH_TOKEN` | Token de activación de LocalStack, si corresponde |
| `LOCALSTACK_IMAGE` | Imagen de LocalStack utilizada |

**Importante:**

- `WEBHOOK_SECRET` debe contener al menos 16 caracteres.
- Las credenciales `test` son ficticias y están destinadas al emulador.
- `NOTIFY_PROVIDER=console` es el proveedor configurado en el ejemplo.
- Para utilizar Telegram deben configurarse `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
- No se debe publicar el archivo `.env` ni compartir secretos reales.

## 8. Iniciar LocalStack

El archivo `compose.yaml` configura el servicio LocalStack con:

- Puerto `4566`, publicado en `127.0.0.1`.
- Servicios SQS, S3 y EC2.
- `EC2_VM_MANAGER=mock`.
- Imagen configurable mediante `LOCALSTACK_IMAGE`.

Iniciar LocalStack:

```powershell
docker compose up -d
```

Comprobar el estado:

```powershell
docker compose ps
```

Consultar los registros:

```powershell
docker compose logs -f localstack
```

Python se ejecuta directamente en el host y se conecta al endpoint local:

```text
http://localhost:4566
```

La configuración EC2 utiliza el administrador `mock`, por lo que no administra máquinas virtuales reales.

## 9. Inicialización de las colas SQS

Con LocalStack iniciado y el entorno virtual activado, ejecutar:

```powershell
python -m fenix.cli init-queues
```

El comando crea dos colas estándar:

- Cola principal: `{QUEUE_PREFIX}-events`.
- Dead Letter Queue: `{QUEUE_PREFIX}-dlq`.

### Configuración de las colas

| Parámetro | Cola principal | DLQ |
|---|---:|---:|
| Tipo | Estándar | Estándar |
| Retención | 4 días | 14 días |
| Visibility Timeout | 45 segundos | No configurado explícitamente |
| Máximo de recepciones | 3 | No configurado explícitamente |

La cola principal utiliza una política `RedrivePolicy` para derivar mensajes que superan el límite de recepciones a la DLQ.

## 10. Ejecución del sistema

Se recomienda utilizar terminales separadas para ejecutar el receptor y el Worker.

### 10.1. Iniciar el receptor HTTP

En una terminal, activar el entorno virtual y ejecutar:

```powershell
python -m uvicorn fenix.services.receiver:app --reload
```

El receptor queda disponible en:

```text
http://127.0.0.1:8000
```

Endpoint de recepción:

```text
POST /webhook
```

El receptor verifica la firma del webhook, valida el evento y lo publica en SQS.

### 10.2. Iniciar el Worker

En otra terminal, activar el entorno virtual y ejecutar:

```powershell
python -m fenix.cli worker
```

Para ejecutar un solo ciclo de consulta:

```powershell
python -m fenix.cli worker --once
```

El Worker recibe mensajes de SQS, ejecuta el procesamiento y confirma los mensajes exitosos.

### 10.3. Enviar un evento de prueba

Con el receptor y el Worker en ejecución:

```powershell
python -m fenix.cli send examples/node-event.json
```

El comando lee el archivo, genera la firma del contenido y envía el webhook al receptor local.

El evento de ejemplo corresponde a una instancia EC2 identificada como `node-01`.

## 11. Comandos de demostración

El CLI también permite ejecutar operaciones de demostración.

Preparar los recursos de demostración:

```powershell
python -m fenix.cli setup-demo
```

Inyectar una falla en la instancia EC2:

```powershell
python -m fenix.cli fault node-01
```

Inyectar una falla en el bucket S3:

```powershell
python -m fenix.cli fault bucket-01
```

Estos comandos utilizan los recursos definidos en la configuración del proyecto.

## 12. Inventario de infraestructura

El archivo `data/inventory.json` contiene el grupo y los recursos autorizados para el procesamiento.

Actualmente contempla:

- `node-01`: recurso de tipo EC2, con su identificador y datos de configuración.
- `bucket-01`: recurso de tipo S3, con su nombre y región.

El receptor consulta este inventario para validar que los eventos correspondan a recursos conocidos y autorizados.

## 13. Registro de eventos

El archivo `data/events.json` conserva información del procesamiento de los eventos.

Entre sus campos se encuentran:

| Campo | Descripción |
|---|---|
| `event` | Contenido del evento |
| `attempts` | Cantidad de intentos |
| `repair_done` | Indica si la reparación fue completada |
| `repair_result` | Resultado de la reparación |
| `notified` | Estado de la notificación |
| `status` | Estado del procesamiento |

Entre los resultados de remediación se contemplan:

- `repaired`: se realizó una acción correctiva.
- `already_ok`: el recurso ya estaba en el estado deseado.

El Worker actualiza el estado del evento a `acknowledged` después de confirmar el mensaje en SQS.

## 14. Reintentos y manejo de errores

El Worker centraliza la recepción y el procesamiento de mensajes.

Cuando ocurre un error durante el procesamiento:

1. Se registra el error.
2. Se intenta modificar la visibilidad del mensaje mediante `retry_later()`.
3. El mensaje puede volver a estar disponible para un nuevo intento.
4. La política de redrive de SQS controla su derivación a la DLQ.

El tiempo de espera se calcula utilizando el número de recepción:

```text
min(30, 2 ** número_de_recepción)
```

El sistema también contempla errores de validación, errores de procesamiento y fallos de comunicación con los servicios de AWS.

## 15. Observabilidad y notificaciones

El proyecto incorpora logging estructurado en formato JSON mediante `src/fenix/utils/logging_json.py`.

La implementación utiliza:

- `QueueHandler` y `QueueListener` para gestionar los registros mediante una cola.
- `RotatingFileHandler` para rotar archivos de log.
- Compresión GZIP de los archivos rotados.
- Campos de contexto para facilitar el seguimiento de las operaciones.

Entre los campos registrados se encuentran:

- `event_id`
- `message_id`
- `resource_id`
- `attempt`
- `action`
- `status`

El módulo `notifications.py` gestiona las notificaciones mediante el proveedor configurado.

La configuración de ejemplo utiliza `console`. También se contempla la integración con Telegram mediante las variables de entorno correspondientes.

## 16. Pruebas

Para ejecutar la suite completa:

```powershell
python -m pytest -v
```

Para ejecutar únicamente las pruebas marcadas como base:

```powershell
python -m pytest -m base -q
```

Para ejecutar las pruebas marcadas como pendientes:

```powershell
python -m pytest -m pendiente -q
```

Las pruebas de integración pueden requerir que LocalStack esté iniciado y correctamente configurado.

**Resultado de verificación:** en la última ejecución realizada por el equipo se aprobaron 67 pruebas.

## 17. Seguridad

El proyecto incorpora las siguientes medidas:

- No almacenar credenciales reales en el código fuente.
- Mantener `.env` fuera del repositorio.
- Validar el endpoint de conexión para permitir únicamente LocalStack local.
- Verificar la firma de los webhooks antes de procesarlos.
- Limitar el tamaño del cuerpo HTTP a 16 KiB.
- Rechazar JSON con claves duplicadas.
- Validar los recursos contra el inventario.
- Evitar registrar información sensible de autenticación.

## 18. Alcance del entorno

Fénix utiliza LocalStack para desarrollar y probar localmente el flujo de recepción, validación, mensajería, procesamiento, remediación y observabilidad.

Las operaciones se ejecutan sobre servicios emulados. La configuración EC2 utiliza `mock` y no representa la administración de máquinas virtuales reales.

---

**Proyecto Fénix**  
Trabajo Práctico Final – Programación para Automatización II
