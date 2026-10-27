# Grupo Sazón · AI screening agent

Un agente de voz llama a los candidatos y les hace el screening; los recruiters lo siguen en una app web.

```
app web ──► Supabase ──► worker ──► 📞 candidato ◄──► agente de voz
               ▲                                          │
               └──────────────── resultado ───────────────┘
```

### Arrancar

```bash
cd infra/livekit && docker compose up -d && cd ../..   # LiveKit + SIP
python -m venv .venv && .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                    # rellena tus datos
python telephony/create_outbound_trunk.py               # solo la primera vez
```

### Llamar sin la app

```bash
python telephony/call_me.py --to 4444                            # eco gratis de Zadarma
python telephony/call_me.py --to +34611222333 --agent zadarma-agent
```

Con `--record` se graba el audio en `infra/livekit/recordings/`.

### Agente

`voice/agent.py` es el agente de screening (`zadarma-agent`): espera a que el teléfono
descuelgue, dice la apertura y pasa cada turno del candidato al grafo de LangGraph
(`src/pipeline.py`). Speech-to-text con Deepgram y text-to-speech con Cartesia
(`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY` en `.env`). Al terminar el screening cuelga
borrando la sala. La conversación se guarda con el número de teléfono como id.

```bash
python -m voice.agent                 # hablar con él desde el micrófono, sin teléfono
python -m voice.agent dev             # registrarse en LiveKit y esperar llamadas
python telephony/call_me.py --to +34611222333 --agent zadarma-agent
```

Si despachas un agente que no está corriendo, la llamada funciona igual.

## Instrucciones para un agente (Claude Code u otro)

Objetivo: dejar corriendo el sistema completo y comprobarlo paso a paso, hasta una llamada
real en la que el agente de voz hace el screening. Ejecuta todo desde la raíz del repo.
Cada paso indica cómo saber que ha ido bien; si no, para y mira *Problemas frecuentes*.

### Reglas

- **Las llamadas cuestan dinero y llegan a personas reales.** Solo llama a `4444` (eco gratuito
  de Zadarma) o a `MY_PHONE_NUMBER`, y a este último solo cuando el humano diga que está listo
  para contestar. Nunca a otro número sin permiso explícito.
- Al terminar cualquier prueba, cuelga siempre: `python telephony/hangup.py`.
- No muestres ni copies valores de `.env` ni de `infra/livekit/*.yaml`; comprueba solo que las
  variables existen. No los subas a git.
- Si falta una clave o un fichero, pídeselo al humano; no lo inventes.

### 0. Requisitos (comprobar, no instalar a ciegas)

- Python ≥ 3.10 y Docker en marcha: `docker info` responde sin error.
- `infra/livekit/livekit.yaml`, `sip.yaml` y `egress.yaml` existen (no están en git: llevan el
  secreto de LiveKit, que debe coincidir en los tres y con `LIVEKIT_API_SECRET`). Se crean desde
  las plantillas del repo:

  ```bash
  cd infra/livekit
  for f in livekit sip egress; do cp $f.yaml.example $f.yaml; done
  # sustituye CAMBIA_ESTE_SECRETO... por el mismo secreto (openssl rand -hex 32) en los tres
  # y ponlo también en LIVEKIT_API_SECRET del .env
  ```
- `.env` existe (copia de `.env.example`) con estas variables no vacías:

  | Para | Variables |
  |---|---|
  | LiveKit self-hosted | `LIVEKIT_URL=http://localhost:7880`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
  | Zadarma | `ZADARMA_SIP_SERVER`, `ZADARMA_SIP_LOGIN`, `ZADARMA_SIP_PASSWORD`, `ZADARMA_API_KEY`, `ZADARMA_API_SECRET` |
  | Voz | `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY` |
  | Screening | `ANTHROPIC_API_KEY` (o `CLAUDE`), `JEV` (o `classifier.provider: claude` en `config/config.yaml`), `NOMINATIM_CONTACT` |
  | Prueba | `MY_PHONE_NUMBER` (formato `+34...`) |

  Comprobar sin mostrar valores: `grep -oE '^[A-Z_]+=.' .env | cut -d= -f1`

### 1. Instalar y pasar los tests

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
```
OK: todos los tests en verde (`63 passed`).

### 2. Levantar LiveKit + SIP

```bash
cd infra/livekit && docker compose up -d && docker compose ps && cd ../..
```
OK: `livekit`, `redis`, `sip` y `egress` en estado `running`. `docker compose logs sip` sin errores.

### 3. Trunk saliente y cuenta de Zadarma

```bash
python telephony/create_outbound_trunk.py   # idempotente
python telephony/zadarma_status.py
```
OK: `Trunk creado: ST_...` o `El trunk ya existe: ST_...`; el estado muestra saldo > 0 y la línea SIP.

### 4. Probar la telefonía sin agente (gratis)

Lanza en segundo plano y cuelga a los ~15 s:
```bash
python telephony/call_me.py --to 4444
python telephony/hangup.py
```
OK: imprime `Llamada contestada`. Si falla con un código SIP, ver *Problemas frecuentes*.

### 5. Arrancar el agente de voz

En segundo plano (queda escuchando; no termina solo):
```bash
python -m voice.agent dev
```
OK: en el log aparece `registered worker` con `agent_name` = `zadarma-agent`.
Alternativa en Docker: `cd infra/livekit && docker compose --profile agent up -d --build`
(no lances los dos a la vez: se repartirían las llamadas).

### 6. Llamada real con el agente (necesita al humano)

Pregunta antes al humano si está listo para contestar en `MY_PHONE_NUMBER`. Entonces:
```bash
python telephony/call_me.py --agent zadarma-agent
```
OK: el teléfono suena; al descolgar, el agente saluda en español (incluye el aviso de que es
una IA) y hace las preguntas del screening. Al terminar se despide y la llamada se corta sola
(el agente borra la sala). `call_me.py` termina con `El teléfono ha colgado.`

### 7. Comprobar que la conversación se ha guardado

```bash
python -c "import os; from src.pipeline import Screening; c = Screening().conversation(os.environ['MY_PHONE_NUMBER']); print(c.status, len(c.messages), 'mensajes') if c else print('sin conversación')"
```
(con `.env` cargado: `src.config` lo carga solo al importarse). OK: un estado (`finished`,
`disqualified`, `in_progress`...) y varios mensajes. El id de la conversación es el número llamado.

### 8. Limpiar

```bash
python telephony/hangup.py                    # por si quedó alguna llamada abierta
# parar el proceso de `python -m voice.agent dev`
cd infra/livekit && docker compose down       # opcional
```

### Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| `Falta la variable X en .env` | Añadirla (pedírsela al humano). |
| `No existe el trunk 'zadarma-outbound'` | Paso 3 sin hacer. |
| `No se puede conectar con LiveKit` | Docker parado, o `LIVEKIT_URL` apunta a LiveKit Cloud en vez de `http://localhost:7880`. |
| SIP 407 / 403 | Usuario o contraseña SIP de Zadarma incorrectos. |
| SIP 480 / 486 | El teléfono no contestó o comunicaba. |
| La llamada conecta pero el agente no habla | El agente no está corriendo (paso 5) o `AGENT_NAME` no coincide con `--agent`. |
| El agente no oye / no hay audio | Puertos UDP RTP (10000-10100) o `node_ip` en `livekit.yaml` mal configurados. |
| Error 401 de Deepgram o Cartesia en el log del agente | `DEEPGRAM_API_KEY` / `CARTESIA_API_KEY` vacías o inválidas. |
| `sip request timed out` (también con `4444`) | El router se come las respuestas UDP al puerto 5060 (SIP ALG). Pon `ZADARMA_SIP_TRANSPORT=tcp` y `python telephony/create_outbound_trunk.py --recreate`. |
| SIP 503 y en el historial de Zadarma el destino sale como `3434...` | El número se marcó sin `+`: Zadarma lo toma como nacional y antepone otro 34. Usa siempre `+34...`. |
| El agente corta al candidato cuando duda | Sube `voice.max_delay` en `config/config.yaml` (lo que espera cuando el modelo de fin de turno cree que no ha terminado). |
| En el log: `cloud turn detector failed (401)` | Normal en self-hosted: LiveKit cae al modelo local de fin de turno. |

## App web de recruiters

https://sazon-talent.vercel.app (código en `web/`). Una vez: ejecuta `web/supabase/schema.sql` en
Supabase y pon `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` en `.env`.

Para una demo, con Docker ya en marcha:

```bash
python -m worker.reset_demo   # tablero limpio con 30 candidatos de ejemplo
python -m voice.agent dev     # agente de voz
python -m worker              # hace las llamadas que se piden desde la app
```

En la app: *Add candidates* → número → *Call now*. Al colgar, la tarjeta pasa a su columna.
`CALL_ALLOWLIST` en `.env` limita a qué números se llama (`*` = cualquiera).
