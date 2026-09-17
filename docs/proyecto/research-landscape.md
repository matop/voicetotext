# Research: panorama voice-to-text dictation (sept 2026)

Documento vivo. Recoge el estado del arte y las decisiones abiertas para este proyecto.

## 1. Referentes

| Producto | Modelo de ejecución | Licencia | Notas |
|---|---|---|---|
| Wispr Flow | 100% cloud (ASR + Llama fine-tuneado para limpieza) | Propietario | <700ms p99 segun Baseten; sin modo offline; "Privacy Mode" = promesa contractual, no arquitectura |
| Sotto (sotto.to) | Local-first (WhisperKit + Parakeet en Neural Engine), cloud opcional BYO-key | Propietario, pago único | Solo macOS |
| SottoScribe | 100% local | Propietario, £69 one-time | Solo Windows |
| Handy | Local (whisper.cpp GGML + Parakeet V3 CPU), Silero VAD | **MIT**, Rust/Tauri | ~31k estrellas. Diseñado explícitamente para ser "forkable". Win/Mac/Linux |
| VoiceInk | Local Whisper | GPL-3 | Solo macOS, Swift. "Power Mode" = perfiles por app |
| VoiceTypr | Local + cloud opcional | AGPL-3 | Tauri/Rust/React |
| OpenWhispr | whisper.cpp o sherpa-onnx | MIT | Win/Mac/Linux/iOS |

Conclusión: la capa de *transcripción* está commoditizada. El foso está en la capa de **contexto** y en la **fricción de instalación**.

## 2. Anatomía del pipeline

```
hotkey global → captura audio → VAD → ASR → post-proceso LLM → inyección de texto
     ↑                                          ↑
  lo dificil                          aqui esta el diferenciador
  (per-OS)                            (contexto de negocio)
```

## 3. Modelos ASR locales

- **Parakeet TDT 0.6B v3** (NVIDIA): ~6.05% WER agregado, ~1.9% LibriSpeech clean. Transducer → emite texto según lee, sin bucle autoregresivo. ~10x más rápido que whisper-large-v3-turbo. Cubre 25 idiomas europeos (incluye español). Requiere Apple Silicon o GPU NVIDIA; suelo de memoria ~16GB.
- **Whisper large-v3-turbo**: 809M params, ~7.7% WER, 99+ idiomas, ~6GB. Destilado de large-v3, sin traducción. No hace streaming real (ventanas de 30s → suelo de latencia de ~1s).
- **Nemotron Speech Streaming EN 0.6B**: 6.93% WER en streaming con chunks de 1.12s. La mejor opción si se quiere streaming nativo.
- **Moonshine**: el footprint más pequeño, para edge.
- Aviso de realismo: con ruido de fondo, acento y vocabulario técnico, **ambos** caen a 8-12% WER sin importar el benchmark.

### Runtimes
- **whisper.cpp**: el más fácil de embeber (C/C++, single binary, Metal en Mac ~10x RT). VAD nativo ya incluido. Cuidado: cuantización a 4 bits degrada notablemente en audio largo/ruidoso.
- **sherpa-onnx**: ONNX Runtime C++ con VAD+ASR juntos y bindings C++/Swift/Kotlin/Python. Soporta el patrón **2-pass** (modelo streaming pequeño primero, Whisper refina después) — ideal para dictado. Issue abierto #2900: CER >3x peor que faster-whisper con el mismo modelo Tiny → benchmarkear con audio propio antes de comprometerse.
- **faster-whisper**: CTranslate2, el más rápido en GPU NVIDIA. Sin Metal → solo CPU en Apple Silicon. Es Python, mala opción para empaquetar desktop.

Regla de arquitectura: **nunca ejecutar inferencia dentro del callback de audio**. Hilos separados + colas para captura / VAD / inferencia / UI.

## 4. Inyección de texto (la parte fea)

No existe una API única. Hay que implementar una **escalera de fallbacks por plataforma**:

- **Windows**: UIAutomation (limpio, pero Electron/Chromium complica) → SendInput (puede perder caracteres; Slack se come pulsaciones sintéticas) → **clipboard + Ctrl+V** (el más fiable; atraviesa fronteras de privilegio porque el portapapeles no está sujeto a UIPI).
- **macOS**: AX API (`AXUIElement`, `kAXSelectedText`) + `CGEvent`. Requiere permiso de Accesibilidad.
- **Linux/X11**: XTEST, identidad de ventana via `_NET_ACTIVE_WINDOW` + `WM_CLASS`.
- **Linux/Wayland**: el bloqueante real. `wtype` solo funciona en compositores wlroots (Sway), no en Mutter/GNOME ni KWin/KDE. `ydotool` funciona en todas partes vía `/dev/uinput` pero exige setup root una vez (paquete + regla udev + demonio). **AT-SPI** (`org.a11y.Bus`, interfaz `EditableText`) es la alternativa sin permisos extra y cubre GTK/Qt/LibreOffice/muchos Electron.
- Hotkeys en Linux: evdev funciona en cualquier compositor, pero ojo con el feedback loop (el propio listener puede leer las pulsaciones inyectadas por ydotool).

Seguridad UX: el texto va a lo que tenga el foco → indicador visual permanente e imposible de ignorar mientras la inyección está activa.

## 5. Capa de contexto (el diferenciador)

### Biasing en tiempo de decodificación
- `initial_prompt` de Whisper: solo consume los **últimos ~224 tokens**, y los tokens finales pesan más → prompt compacto, términos de más valor al final. Es bias léxico blando, no garantiza nada.
- `hotwords` en faster-whisper (v1.0+) como parámetro dedicado.
- Usar forma *hablada* en el prompt (con disfluencias), no forma escrita → evita alucinaciones.

### Recuperación antes del biasing (para superar el límite de 224 tokens)
No meter el glosario entero: **recuperar solo los hotwords relevantes por enunciado**. Más hotwords = peor recall + distractores.
Truco validado: probar cada término del glosario con TTS y **descartar los que el ASR ya acierta** — solo sesgar sobre fallos empíricos reales. Matching difuso, no exacto.

### Post-proceso
- Determinista: matching fonético + distancia de edición contra lista de entidades.
- LLM few-shot con el glosario en contexto (eficaz sobre todo para errores de *ortografía*, menos para errores de transcripción generales).
- LLM rerank: puntuar plausibilidad de cada segmento independientemente de la confianza del ASR.

### El patrón ganador: dos pasadas
Primera pasada barata → extraer tema/entidades → construir `initial_prompt` compacto y pesado al final → **re-decodificar**. Un paper reporta **-17% WER relativo** en dominio denso en nombres propios, sin reentrenar nada.

## 6. Almacenamiento de contexto local

- **sqlite-vec**: un solo fichero, filtros SQL de metadatos, y **búsqueda híbrida con FTS5** en la misma DB. Zero-ops.
- **LanceDB**: más throughput a escala, multimodal, columnar. Lo usa AnythingLLM.
- Para dictado (glosario + docs personales, miles no millones de chunks) **sqlite-vec gana**: el híbrido FTS5+vector es exactamente lo que necesita la recuperación de jerga, y es un fichero que el usuario puede borrar.
- Gotcha desde el día 1: versionar el índice. Si cambia el modelo de embeddings o el chunk size, hay que reindexar — construir esa ruta desde el principio.

## 7. Fuentes

- https://wisprflow.ai/ · https://kintal.co/thinking/what-wispr-flow-actually-does
- https://github.com/cjpais/Handy · https://sotto.to/ · https://github.com/moinulmoin/voicetypr
- https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks
- https://arxiv.org/pdf/2509.14128 (Canary/Parakeet v3) · https://arxiv.org/pdf/2410.18363 (contextual biasing)
- https://arxiv.org/pdf/2602.18966 (LLM-driven context generation, -17% WER)
- https://dev.to/howmindswork/how-i-inject-text-into-any-windows-app-including-elevated-processes-4jl6
- https://github.com/k2-fsa/sherpa-onnx/issues/2900 (caveat CER)
