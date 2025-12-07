# Asistente local con wake-word, STT, LLM y TTS

## Qué hace
- Wake-word (Porcupine) o hotkey, con sonidos de inicio/fin.
- STT local (faster-whisper) forzado a español.
- LLM local (llama-cpp) o Gemini opcional.
- TTS local (piper) con cancelación si vuelve a saltar el wake-word.
- Acciones locales en Windows por intents y comandos embebidos en la respuesta del LLM.
- Apertura de apps, ajustes de Windows (`ms-settings:`), enlaces web y URL detectadas en el texto.

## Requisitos rápidos
- Windows + Python 3.10+; audio in/out funcionando.
- Modelos en `models/`:
  - LLM GGUF (ruta en `config.json` → `llm.model_path`).
  - STT CTranslate2 (`models/stt/faster-whisper-medium-ct2`).
  - TTS piper (`models/tts/es/...onnx`).
- CUDA opcional; auto-decide GPU según VRAM libre.

## Configuración
1) Entorno: `python -m venv .venv; .\.venv\Scripts\activate`
2) Deps: `pip install -r requirements.txt`
3) Copia modelos en `models/` y ajusta rutas en `config.json` (prioritario).
4) Claves sensibles en `.env` (no en config):
   - `PORCUPINE_ACCESS_KEY=`
   - `GEMINI_API_KEY=` (solo si usas provider `gemini`).
5) Ajusta `config.json`:
   - `app.wake_word`, `porcupine_keyword_path`, `hotkey`.
   - `stt.language` (ya en `es`).
   - `tts.voice_path`.
6) Comandos allowlist en `commands.json` (apps, ms-settings, webs). El LLM solo puede usar esos con `[CMD:nombre]` al inicio de su respuesta.
7) Ejecuta: `python app.py`.

## Uso de acciones y comandos embebidos
- Decir: “Abre Discord” / “Abre el navegador” → usa intents/aliases y comandos de `commands.json`.
- Decir: “Veo mal las pantallas” → el LLM puede responder `[CMD:configuracion pantallas] Revisa brillo y resolución...` y se abrirá la configuración sin leer el comando.
- Si el LLM inventa un comando que no esté en la lista, se ignora.

## Cancelación de TTS por wake-word
- Si suena TTS y dices la wake-word, se corta el audio y vuelve a escuchar.

## Notas de hardware
- Contexto del sistema (OS/CPU/RAM/GPU/Disco) se añade al prompt para respuestas más útiles.

## Extender
- Añade o edita comandos en `commands.json` (apps, URLs, ms-settings).
- Más intents o lógica: `src/actions.py`.
- Ajustes de pipeline/LLM: `src/pipeline.py` / `src/llm.py`.
