# HANDOFF — voicetotext (fork de Handy)

Documento de arranque. Si sos un agente o una persona que llega en frío a este repo, leé esto primero.

## Qué es

Fork de [Handy](https://github.com/cjpais/Handy) (MIT, ~31.8k ⭐, Rust/Tauri) para construir una app de
dictado voz-a-texto **local** en Windows, especializada en **dictar prompts largos a agentes de IA**
(T3, Claude, ChatGPT) con vocabulario técnico propio.

**Decisión cerrada: se forkea, no se reinventa.** No re-discutir esto.

## Estado del repo

- Clonado de `cjpais/Handy` @ `ba10ce1` (2026-09-15). El remote se llama `upstream`, no `origin`.
- **Todavía no existe fork en GitHub** ni remote `origin`. Pendiente de decisión del dueño.
- Cero código propio escrito. Solo este handoff y `docs/proyecto/`.

## Regla de oro del fork

**Minimizar el diff contra upstream.** Handy tiene commits casi a diario; si se puede seguir rebasando,
se heredan mejoras gratis. Por eso:

- No editar `CLAUDE.md`, `AGENTS.md`, `README.md` ni ficheros existentes salvo necesidad real.
- El trabajo propio va en módulos nuevos y en `docs/proyecto/`.
- Cuando haya que tocar código upstream, tocar lo mínimo y dejarlo aislado tras una interfaz.

## Lo que Handy YA resuelve (no reconstruir nada de esto)

Inspección de `src-tauri/src/` — 61 ficheros Rust, 144 TS/TSX:

| Necesidad | Ya está en | Nota |
|---|---|---|
| Captura de audio | `audio_toolkit/audio`, `cpal 0.16` | multiplataforma |
| VAD | `audio_toolkit/vad`, `vad-rs` (fork de cjpais) | Silero |
| ASR Whisper | `transcribe-cpp 0.2.3` | whisper.cpp |
| ASR Parakeet/Moonshine | `transcribe-rs 0.3.8` (feature `onnx`) | ONNX Runtime |
| Hotkey global | `shortcut/`, `tauri-plugin-global-shortcut`, `rdev` | |
| Inyección de texto | `input.rs`, `enigo 0.6`, `secure_input.rs` | |
| **Portapapeles transaccional** | **`paste_tx/`, `clipboard.rs`** | ya preserva/restaura el contenido previo |
| **Overlay** | **`overlay.rs`** | el feedback visual ya existe |
| **Historial persistente** | **`managers/history.rs`** | tiene `update_transcription()` ← el hook para aprender de correcciones |
| **Cliente LLM** | **`llm_client.rs`** | `send_chat_completion_with_schema()`, post-proceso ya cableado |
| Catálogo de modelos | `catalog/`, `managers/model/` | descarga y gestión |

Conclusión: **la infraestructura entera está hecha.** El trabajo propio es casi todo la capa de contexto.

## Hallazgo importante sobre Windows

En `src-tauri/Cargo.toml`, bloque `[target.'cfg(windows)'.dependencies]`, upstream documenta que
**ONNX Runtime en Windows es CPU-only a propósito**: quitaron `ort-directml` porque el ONNX Runtime
precompilado de pyke se compila con baseline global `/arch:AVX2` y crasheaba al arrancar en CPUs
pre-Haswell. Y `transcribe-cpp` solo tiene feature `metal` (macOS); **no hay Vulkan cableado**.

→ En Windows, **ambos motores corren en CPU**. Eso está bien: el Ryzen 7 8845HS tiene AVX-512 (Zen 4) y
GGML lo explota. La idea de usar la iGPU Radeon 780M vía Vulkan **exige parchear `transcribe-cpp`** —
es trabajo extra, no es un flag. **Deprioritizado**: primero medir CPU, que probablemente alcance.

## Lo que sí hay que construir

Por orden. Ver `docs/proyecto/fase-1-mvp.md` para el razonamiento completo.

1. **Build verde en Windows.** Instalar `rustup` MSVC en Windows, compilar, correr Handy tal cual.
   Nada de esto es testeable desde WSL2 — ver `docs/proyecto/target-and-hardware.md`.
2. **Baseline medido.** Grabar audio propio real (español + inglés mezclados, jerga GDES, 1-3 min) y
   medir Whisper large-v3-turbo vs Parakeet TDT v3 **sobre ese audio**, no sobre benchmarks. Sin esto
   cualquier elección de modelo es fe.
3. **Enunciados largos.** El problema técnico real: Whisper usa ventanas de 30s y alucina en silencios.
   Los prompts a agentes duran 1-3 minutos con pausas de pensamiento constantes. Calibrar la segmentación
   por VAD; el default de Silero (silencio > 2s) se come esas pausas.
4. **Glosario auto-aprendido.** Dos fuentes, ninguna pide configuración al usuario:
   - Cosecha de identificadores de `/mnt/c/proyectos/*` (funciones, módulos, repos).
   - Aprendizaje por corrección, enganchado a `HistoryManager::update_transcription()`.
   Podar con TTS: descartar los términos que el ASR **ya acierta**; más hotwords empeoran el recall.
5. **Biasing en decodificación.** `initial_prompt` / `hotwords`, recuperando solo los términos relevantes
   por enunciado (el presupuesto es de ~224 tokens, no cabe un glosario entero).

### Vocabulario real del usuario (semilla del glosario)

De `/mnt/c/proyectos/`: `GDES`, `facturaGdes`, `middlewaregdes`, `guias-middleware`, `lgde-service`,
`jwt-perfilamiento`, `backoffice-adapter`, `persistencia-redis`, `getParametros`, `email-worker`, NestJS.
Estos son exactamente los términos que un ASV genérico destroza y que el LLM receptor **no puede adivinar**.

## Contrato con el proyecto hermano (`docmem`)

Este repo **no depende** de `docmem`. La fase 1 tiene su propio glosario local y se termina sola.

Cuando `docmem` exista, se conecta por una interfaz estrecha y opcional:

```
docmem  --[ consulta: texto parcial → lista de términos relevantes ]-->  voicetotext
```

Regla: si `docmem` no está disponible, el dictado funciona igual con el glosario local.
**Nunca bloquear el proyecto 1 esperando al proyecto 2.**

## Setup pendiente (lo hace el dueño, no un agente)

1. Instalar `rustup` con toolchain **MSVC** en Windows. Hoy no hay Rust ni en WSL ni en Windows.
2. Decidir si se crea el fork público en GitHub (cuenta `matop`) y se añade como `origin`.
3. Verificar `BUILD.md` de upstream para requisitos adicionales de Windows.

## Documentos

- `docs/proyecto/fase-1-mvp.md` — alcance de fase 1 y por qué el receptor-LLM cambia las prioridades.
- `docs/proyecto/target-and-hardware.md` — hardware real y el workflow WSL2→Windows.
- `docs/proyecto/research-landscape.md` — estado del arte, modelos, runtimes, capa de contexto.
