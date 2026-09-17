# QA #1 — Baseline sobre upstream sin modificar (2026-09-16)

Primera sesión de QA. App: Handy v0.9.6 @ `ba10ce1`, build dev, Windows 11, Ryzen 7 8845HS + Radeon 780M.
Modelo: `whisper-large-v3-turbo-Q8_0.gguf` (845 MB).

## Metodología y su límite

Sin micrófono disponible, el audio se **sintetizó con TTS de Windows** (`System.Speech`), 16 kHz mono:
voz `Microsoft Helena Desktop` (es-ES) para los casos en español, `Zira` (en-US) para el inglés.
Los WAV están en `qa-audio/`. Se transcribieron con `handy.exe --transcribe-file`, que corre la ruta
batch sin micrófono ni VAD.

**Límite importante**: es voz sintética, no voz real. Una voz española leyendo términos ingleses los
pronuncia con fonética española, que es un proxy razonable del usuario — pero **los fallos de jerga que
se reportan abajo necesitan confirmarse con audio real antes de darlos por ciertos.**
Tampoco se ejerció la ruta en vivo: micrófono, VAD y segmentación siguen **sin probar**.

## Rendimiento: Vulkan gana claro

| Backend | audio | best_ms | RTF | load_ms |
|---|---|---|---|---|
| **Vulkan0** (Radeon 780M) | 13.91s | **1821** | **7.64x** | 1026 |
| CPU (Zen 4, `ggml-cpu-cascadelake.dll`) | 13.91s | 5693 | 2.44x | 680 |

**Vulkan es 3.1x más rápido que CPU, con texto idéntico.** Queda cerrada la duda: en este hardware se usa GPU.

Dos matices que importan para UX:

- **El RTF mejora con audio más largo**: 7.64x a 14s → **12.20x a 24.8s** (2031 ms). El overhead fijo se
  amortiza. Bueno para el caso de uso: los prompts largos salen casi gratis.
- **Penalización de arranque en frío**: primera pasada 4103 ms vs 1821 ms en caliente (2.3x). La primera
  dictada tras abrir la app se va a sentir lenta. Con `Unload Model = After 5 minutes` por defecto, esto
  se paga cada vez que se vuelve tras una pausa. **Candidato a revisar.**

## Calidad: el code-switching funciona; la jerga no

Entrada 1 (es + jerga técnica) → salida:
> "Necesito que hagas un refactor del middleware de guías, que está en el repo middleware **GEDS**, y que
> revises el **JWT** perfilamiento antes del deploy. El endpoint de factura **GEDS** está tirando un
> timeout en el backoffice adapter."

Entrada 2 (24.8s con pausas y muletillas) → salida:
> "Bueno, a ver. Quiero armar un endpoint nuevo, eh, en el servicio de parámetros. (...) consulte la
> persistencia **Aridis** antes de pegarle a la base. (...) Y que devuelva un **404** si no existe, no un
> **500** como ahora."

Lo que funciona mejor de lo esperado:
- **Anglicismos dentro de frase española**: `refactor`, `deploy`, `endpoint`, `timeout`, `backoffice adapter`. Todos bien.
- **Siglas deletreadas**: "jota doble uve te" → `JWT`.
- **Números hablados → dígitos**: "cuatrocientos cuatro" → `404`, "quinientos" → `500`. Muy útil dictando a agentes.
- **Enunciado largo con pausas**: sin truncado ni alucinación. *Pero esto era la ruta batch; el riesgo real
  estaba en la segmentación por VAD en vivo, que sigue sin probar.*

Lo que falla, y es lo único que falla de forma consistente:
- `GDES` → "GEDS" (dos veces, ambas ocurrencias)
- `redis` → "aridis"

**La hipótesis central del proyecto queda respaldada**: el problema no es el idioma ni la longitud, es la
jerga de dominio.

## Hallazgo principal: las dos capas de corrección son mutuamente excluyentes

Upstream **ya implementa los dos mecanismos** que este proyecto planeaba construir:

1. **Biasing en decodificación** — `managers/transcription.rs:1314`:
   `initial_prompt: Some(settings.custom_words.join(", "))`, para modelos con `Feature::InitialPrompt`.
2. **Post-corrección difusa** — `audio_toolkit/text.rs`: Levenshtein + Soundex + n-gramas hasta 3 palabras,
   umbral por defecto `0.18`.

El problema está en cómo se combinan (`managers/transcription.rs:1777`):

```rust
let corrected = if !settings.custom_words.is_empty() && !custom_words_already_prompted {
    apply_custom_words(&raw, &settings.custom_words, settings.word_correction_threshold)
} else {
    raw
};
```

Whisper turbo **sí** soporta `InitialPrompt` → `custom_words_already_prompted = true` → **`apply_custom_words`
nunca se ejecuta.** La red de seguridad determinista queda desactivada justo para los modelos Whisper.

### Verificación empírica

Se añadieron `GDES`, `Redis` y `middlewaregdes` a Custom Words y se re-transcribió:

| | sin Custom Words | con Custom Words |
|---|---|---|
| | `repo middleware GEDS` | `repo middlewareGEDES` |
| | `factura GEDS` | `facturaGEDES` |
| | `persistencia aridis` | `persistencia Aridis` |

Hubo efecto (fusión de palabras, capitalización) pero **ningún error se corrigió**. Consistente con que
actuó solo el bias blando del prompt: `apply_custom_words` con umbral 0.18 habría producido `GDES` exacto.

*Nota de rigor*: la ruta `--transcribe-file` no emite la línea de log de `initial_prompt`, así que no se
confirmó por log que `custom_words_already_prompted` fuera `true` en esa ruta. El código es explícito y el
resultado observado encaja, pero **conviene confirmarlo con un log antes de escribir el fix.**

Esto es exactamente lo que advierte la literatura: el `initial_prompt` es un sesgo blando que no garantiza
nada, **y por eso la capa de post-proceso sigue siendo valiosa**. Deberían sumarse, no excluirse.

## Segundo hallazgo: Soundex es solo inglés

`audio_toolkit/text.rs:1` → `use natural::phonetics::soundex;`
El propio código lo reconoce en un comentario: *"Soundex is an English/ASCII phonetic algorithm."*

Para un usuario que dicta en español, la capa fonética **no puede emparejar** una pronunciación española mal
transcrita con el término correcto. `aridis` vs `Redis` difieren ya en la primera letra, que Soundex conserva
tal cual. Esta es una carencia real de upstream y una oportunidad concreta de diferenciación:
**matching fonético consciente del español.**

## Tercer hallazgo: el prompt no escala

`settings.custom_words.join(", ")` mete **todos** los términos en el prompt, sin recuperación por enunciado
ni gestión del presupuesto de ~224 tokens. Con 3 términos da igual; con un glosario cosechado de los repos
(cientos de identificadores) degrada el recall y mete distractores.

## Lo que ya existe y este proyecto NO necesita construir

- `Shortcut Behavior`: **Auto / Hold / Toggle**. "Auto" hace hold-para-grabar o tap-para-alternar según
  cómo pulses. **Mejor que la decisión "toggle, no push-to-talk" del handoff, que queda anulada.**
- `Paste Method`: Clipboard (Ctrl+V), configurable.
- `Clipboard Handling`: "Don't Modify Clipboard" — preserva el portapapeles del usuario.
- `Auto Submit` — pulsa Enter tras pegar. Directamente relevante para mandar prompts a agentes.
- `Overlay`: modo "Live" con posición configurable.
- `Voice Activity Detection`, `Remove Filler Words`, `Append Trailing Space`.
- `Language`: Auto Detect.

## Hallazgos de UX

- **69 modelos en lista plana, sin buscador.** Encontrar `Whisper Large v3 Turbo` costó tres scrolls a ciegas.
- **Los 5 modelos recomendados no sirven para es/en**: Parakeet Unified (solo inglés), Nemotron Streaming
  (28 idiomas), Canary 180M (4 idiomas), Cohere Transcribe (1.6 GB), Whisper Medium ("may run a bit slow").
  Turbo, que es el adecuado, está enterrado en la lista larga.
- Warning en arranque dev: `Failed to apply autostart setting (enabled=false): The system cannot find the
  file specified. (os error 2)`. Probablemente artefacto del build dev; baja severidad.

## Nota operativa

El QA se hizo sobre el escritorio real del usuario, con su IDE abierto. `SetForegroundWindow` falla desde
procesos en background, así que un click destinado a Handy aterrizó en otra ventana. **Para la próxima
sesión: verificar el foco antes de cada click, o usar un escritorio/sesión aparte.**

## Siguientes pasos que sugiere este QA

1. Confirmar con log que `custom_words_already_prompted` es `true` en la ruta Whisper.
2. **Fix candidato (pequeño y de alto valor)**: ejecutar `apply_custom_words` *además* del prompt, no en
   lugar de. Es el primer aporte real del fork.
3. Matching fonético para español, reemplazando o complementando Soundex.
4. Recuperación por enunciado para el `initial_prompt` en vez de `join(", ")`.
5. **Repetir todo con audio real grabado por el usuario.** Nada de lo anterior es concluyente sin eso.
6. Probar la ruta en vivo: micrófono, VAD, inyección. Sin tocar todavía.
