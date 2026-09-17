# Prompt para arrancar un chat nuevo

Actualizado 2026-09-17, tras la sesión de rendimiento. Copiar desde aquí:

---

Trabajo en `C:\Proyectos\voicetotext` (ojo, P mayúscula en el path, si lo escribís en minúscula
el build de Vite se rompe). Es un fork de Handy para dictado de voz local en Windows, en español.

Leé `HANDOFF.md` en la raíz antes de nada. Después `docs/proyecto/qa-05-rendimiento.md` y
`docs/proyecto/qa-04-fonetica-espanola.md`, que son los dos más recientes.

Tres reglas del entorno que no quiero repetir:

1. El repo es un fork **público**. Mis datos viven en `private/` y `qa-audio/`, ambos gitignoreados.
   Nunca commitear nada de ahí, ni mi email ni vocabulario de negocio en los docs.
2. Compilar y probar se hace en Windows, no en WSL. Levantar con `bun run tauri dev` desde
   `C:\Proyectos\voicetotext`. Si el puerto 1420 está ocupado, matar el proceso node que lo tiene.
3. Para medir no hace falta la UI. Desde `src-tauri\target\release\` corré
   `handy.exe --transcribe-file <WAV> --device-index 0 --repeat 3 --json`.
   `--device-index 0` es Vulkan y `1` es CPU. `--model <id>` elige modelo. Mis audios reales
   están en `qa-audio/real/`.

## Dónde quedamos

Tengo dos modelos instalados y medidos sobre el mismo audio real:

| | Whisper turbo | Nemotron Streaming 3.5 |
|---|---|---|
| 30.9 s de audio | 2808 ms, RTF 11.00 | 692 ms, RTF 44.65 |
| números hablados | `404`, `500` | `cuatrocientos cuatro` |
| puntuación | frases con punto | ninguna |
| jerga | `GDES`, `JWT`, `deploy` | `jedes`, `jota WDT`, `diploy` |

Nemotron es 4 veces más rápido y soporta streaming, que es lo que cierra la brecha de latencia contra
Wispr Flow. Pero pierde dígitos, puntuación y mi jerga.

**Vacié `custom_words` a propósito.** No quiero sembrar términos a mano, quiero que el programa los
redescubra solo observando mis correcciones mientras lo uso.

## La tarea

El glosario que se construye solo. Tres pasos, en este orden:

**Uno, arreglar la sobre-corrección en `apply_custom_words`.** Es urgente, no es una mejora. Con
Nemotron la pasada difusa sí corre (no soporta `InitialPrompt`) y rompe texto en cada dictado: el
matcher de n-gramas se come secuencias correctas como "middleware de". Está contado en
`docs/proyecto/qa-03-hotfix-retirado.md`. Ya intenté un fix y lo reverti, leé por qué antes de repetirlo.

**Dos, portar `tools/phonetic-es/es_phonetic.py` a Rust** dentro de `audio_toolkit/text.rs`, al lado de
Soundex y no en su lugar, eligiendo uno u otro según el idioma. Criterio de aceptación, reproducir desde
Rust los números del prototipo:

| | aciertos | daño real |
|---|---|---|
| Soundex, lo que hay hoy | 3/19 (16%) | 102 (0.333%) |
| Fonética española | 7/19 (37%) | 46 (0.150%) |

Tiene que mejorar en los dos ejes a la vez. Medir solo aciertos ya me hizo fracasar un fix.
Hay que portar las tres guardas del prototipo, cada una nació de un daño medido.

**Tres, aprender de mis correcciones.** Ampliar `custom_words` de `Vec<String>` a algo como
`{phrase, replacement, frequency, source}` y engancharlo a `HistoryManager::update_transcription()`.
Wispr Flow ya valida el mecanismo: 18 de sus 24 entradas se aprendieron solas de correcciones del usuario.

## Confirmado: el streaming funciona

Con Nemotron el texto me aparece en pantalla mientras hablo. La latencia percibida deja de ser el
problema. Falta decidir cómo recupero lo que Nemotron pierde, y hay dos caminos abiertos en el handoff:
construirle el post-proceso que le falta (números a dígitos, puntuación), o dos pasadas con Nemotron en
vivo y Whisper para el texto final.

## Lo otro que quiero, y es aparte

Poder arrancar el dictado **clickeando el overlay**, sin tener las manos en el teclado. Es lo único que
echo de menos de Wispr Flow. Ya está verificado que se puede: el overlay acepta clicks
(`RecordingOverlay.tsx:190`), la ventana es `focusable(false)` así que no roba el foco, y existe
`TranscribeAction` en `ACTION_MAP`. Falta exponer un comando Tauri al frontend y dejar el overlay visible
en reposo, no solo al grabar. Los detalles están en el handoff.

Empezá leyendo el handoff y decime tu plan antes de tocar `text.rs`.

---

Hasta aquí.
