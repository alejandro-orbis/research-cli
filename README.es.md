# research-cli

Un asistente de investigación personal para la terminal. Le haces una pregunta, busca en la web, lee las fuentes y redacta un informe en Markdown con cada afirmación citada.

[Read in English](README.md)

![tests](https://github.com/alejandro-orbis/research-cli/actions/workflows/tests.yml/badge.svg)

```
$ python research.py "¿Qué ventajas tiene n8n frente a Make?" --lang es
🧠 Planning searches...
🌐 Searching sources...
  🔎 n8n vs Make ventajas y diferencias
  🔎 n8n self hosting frente a Make
  🔎 n8n vs Make comparativa precios y limitaciones
   8 unique sources
✍️  Writing report...
💾 Saved to reports/20261122-1504-que-ventajas-tiene-n8n-frente-a-make.md
```

📄 **[Ver un informe de ejemplo completo](examples/n8n-vs-make.md)**

## Cómo funciona

```
pregunta ──► 1. Planificar ──► 2. Buscar ──► 3. Sintetizar ──► 4. Guardar
             (Gemini)          (Tavily)      (Gemini)          reports/*.md
```

1. **Planificar**: Gemini divide la pregunta en varias búsquedas web concretas.
2. **Buscar**: Tavily ejecuta cada búsqueda y devuelve el contenido completo de las páginas, no solo los enlaces. Se eliminan las URL duplicadas.
3. **Sintetizar**: Gemini redacta un informe usando **solo** esas fuentes y cita cada afirmación como `[n]`.
4. **Guardar**: el informe se guarda en un archivo Markdown con fecha y hora, seguido de la lista de fuentes que realmente cita.

Separar la búsqueda de la redacción y basar la respuesta en fuentes recuperadas hace que el resultado sea más fácil de verificar que preguntar directamente a un chatbot.

## Características

- **Respuestas citadas**: cada afirmación apunta a una fuente numerada.
- **Detección de sesgo**: se señalan las fuentes publicadas por un fabricante sobre su propio producto, y se priorizan las independientes cuando no coinciden.
- **Detección de contradicciones**: si las fuentes no coinciden, el informe lo dice en vez de elegir una sin avisar.
- **Lista de fuentes limpia**: solo aparecen las fuentes citadas en el informe, con su número original para que cada `[n]` siga coincidiendo.
- **Resistente a caídas de la API**:
  - Los errores temporales del servidor (5xx) se reintentan con espera creciente.
  - Si un modelo sigue sin responder, pasa al siguiente de tu lista.
  - Cada petición tiene un límite de 60 segundos, así que nunca se queda colgado sin avisar.
  - Los errores del cliente (clave incorrecta, modelo inexistente) fallan a la primera con un mensaje claro.
  - Si una petición tarda demasiado, pasa directamente al siguiente modelo.
- **Informes bilingües**: en inglés o español con `--lang`.
- **Modo profundo**: con `--deep`, el asistente revisa su propio borrador, busca lo que falta (información ausente, afirmaciones con una sola fuente, discrepancias) y reescribe el informe con las fuentes nuevas.

## Requisitos

- Python 3.10 o superior
- Una [clave de API de Gemini](https://aistudio.google.com/apikey) (tiene plan gratuito)
- Una [clave de API de Tavily](https://app.tavily.com) (tiene plan gratuito)

## Instalación

```bash
git clone https://github.com/<tu-usuario>/research-cli.git
cd research-cli
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Después abre `.env` y añade tus claves.

## Uso

```bash
python research.py "¿Qué ventajas tiene n8n frente a Make?" --lang es
```

| Opción | Descripción | Por defecto |
|---|---|---|
| `--lang en\|es` | Idioma del informe | `en` |
| `--searches N` | Número de búsquedas web | `3` |
| `--results N` | Resultados por búsqueda | `3` |
| `--no-save` | Muestra el informe sin guardarlo | desactivado |
| `--exclude a.com,b.com` | Excluye estos dominios | ninguno |
| `--include a.com,b.com` | Busca solo en estos dominios | todos |
| `--deep` | Revisa el borrador, busca lo que falta y lo reescribe | desactivado |

Los informes se guardan en `reports/` (excluida de git).

## Configuración

| Variable | Obligatoria | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | sí | Clave de la API de Google Gemini |
| `TAVILY_API_KEY` | sí | Clave de la API de búsqueda de Tavily |
| `GEMINI_MODEL` | no | Lista de modelos separados por comas, en orden de preferencia |
| `EXCLUDE_DOMAINS` | no | Dominios que excluir siempre, separados por comas (`--exclude` tiene prioridad) |

Orden por defecto:

```
GEMINI_MODEL=gemini-3.5-flash,gemini-3.7-flash,gemini-3.5-flash-lite
```

El primero se usa por calidad; el `-lite` del final sirve de red de seguridad, porque casi nunca se satura.

## Solución de problemas

| Error | Causa | Solución |
|---|---|---|
| `Missing environment variable` | Falta el `.env` o el nombre de la variable está mal | Comprueba que `.env` está junto a `research.py` |
| `404 NOT_FOUND` (modelo) | Google ha renombrado o retirado el modelo | Actualiza `GEMINI_MODEL` (puedes listar los disponibles con `client.models.list()`) |
| `503 UNAVAILABLE` | Modelo saturado | Se gestiona solo; si fallan todos, prueba más tarde |
| `InvalidAPIKeyError` | Clave de Tavily incorrecta | Empieza por `tvly-`; sin comillas ni espacios |

## Hoja de ruta

- [x] Tests con pytest y GitHub Actions
- [x] Búsquedas en paralelo
- [x] Modo profundo (`--deep`): detectar lagunas y lanzar una segunda ronda de búsquedas
- [x] Incluir o excluir dominios (por ejemplo, vídeos y foros)
- [ ] Preguntas de seguimiento sobre un informe (`--chat`)
- [ ] Historial local de informes (SQLite)

## Sobre el proyecto

Creado con ayuda de IA, y después probado, depurado y ampliado por mí como proyecto de aprendizaje y portfolio.

## Licencia

[MIT](LICENSE)
