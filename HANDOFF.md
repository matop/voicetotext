# HANDOFF, voicetotext

Punto de entrada del repo. Si llegás en frío, leé esto entero antes de tocar nada.
Última actualización: 2026-09-17.

## Qué es

Fork de [Handy](https://github.com/cjpais/Handy) (MIT, Rust/Tauri) para dictado de voz **local** en
Windows, especializado en dictar prompts largos a agentes de IA.

La tesis del producto, y esto ya no es una hipótesis sino un resultado medido: **el dictado en español
falla sobre todo en vocabulario técnico inglés pronunciado con fonología española.** Un hispanohablante
dice "prompt" y el ASR escribe `PRAMP`. Nadie resuelve eso hoy. Ver `docs/proyecto/qa-02-datos-reales.md`.

Dos restricciones que no se negocian:

1. Privacidad por arquitectura. El camino por defecto no manda audio a ningún lado. Si alguna vez hay
   nube, es opt-in explícito y visible en el momento.
2. Contexto de negocio. No es transcripción cruda, conoce la jerga del usuario.

## Estado actual

- 11 commits en la rama `proyecto/handoff`. **Todos son documentación y una herramienta aparte.**
- **El código Rust y TypeScript tiene diff cero contra upstream.** Nada de la app está modificado.
- Se probó un cambio de código y se revirtió. Ver `docs/proyecto/qa-03-hotfix-retirado.md`.
- Hay un prototipo funcional del emparejador fonético en `tools/phonetic-es/`, sin integrar.

## Dónde vive todo

```
C:\Proyectos\voicetotext          repo, ojo con la P mayuscula
  origin    https://github.com/matop/voicetotext   (fork PUBLICO)
  upstream  https://github.com/cjpais/Handy
```

El entorno de desarrollo es WSL2 pero **la app se compila y se prueba en Windows**. Desde WSL no se
compila Tauri para Windows ni se prueban las APIs Win32.

## Cómo levantarlo

```powershell
cd C:\Proyectos\voicetotext
bun run tauri dev
```

Toolchain ya instalado y verificado: VS BuildTools 2022 con workload C++, Windows SDK 10.0.26100,
rustup 1.29.1, rustc y cargo 1.98.1 con host `x86_64-pc-windows-msvc`, cmake 4.4.3, bun 1.4.2,
Vulkan SDK 1.4.357 en `C:\VulkanSDK\1.4.357.0`.

### Trampas que ya mordieron

**El casing del path.** El directorio en disco es `C:\Proyectos` con P mayúscula. Windows no distingue
mayúsculas pero Vite sí. Lanzar desde `C:\proyectos` en minúscula rompe el build con
`[vite:html-inline-proxy] ... No matching HTML proxy module found`. Se reconoce porque el mensaje mezcla
las dos grafías. Usar siempre la grafía exacta del disco.

**`cargo build` no arranca la app.** Compila, pero el binario debug carga el frontend desde el dev server
en `localhost:1420`. Lanzar el `.exe` solo muestra "can't reach this page". Usar `bun run tauri dev`.

**El QA por clicks es peligroso.** `SetForegroundWindow` falla desde procesos en background, así que un
click destinado a la app puede aterrizar en otra ventana del escritorio del usuario. Verificar el foco
antes de cada click, o mejor, usar el CLI.

## El CLI es un banco de pruebas completo

No hace falta construir nada para medir. `handy.exe` ya trae:

```
--transcribe-file <WAV>   transcribe headless, 16 kHz mono, sin microfono ni VAD
--device-index <N>        fuerza el dispositivo, 0 es Vulkan y 1 es CPU
--list-devices            lista los dispositivos de computo
--list-models             lista los 85 modelos del catalogo
--repeat <N>              repite y reporta el mejor tiempo
--json                    salida legible por maquina
--debug                   log verboso
```

Vive en `src-tauri\target\debug\handy.exe`. Lee los settings del store, así que los cambios de glosario
aplican sin relanzar la app.

## Lo que Handy ya resuelve, no reconstruir

| Necesidad | Dónde está |
|---|---|
| Captura de audio | `audio_toolkit/audio`, cpal |
| VAD | `audio_toolkit/vad`, Silero |
| Whisper y Parakeet | `transcribe-cpp` y `transcribe-rs` |
| Hotkey global, con Auto, Hold y Toggle | `shortcut/` |
| Inyección de texto y portapapeles transaccional | `input.rs`, `paste_tx/`, `clipboard.rs` |
| Overlay en vivo | `overlay.rs` |
| Historial persistente con audio | `managers/history.rs`, tiene `update_transcription()` |
| Cliente LLM para post-proceso | `llm_client.rs` |
| Glosario de usuario | `settings.custom_words` y `audio_toolkit/text.rs` |

La infraestructura está entera. El trabajo propio es la capa de contexto en español.

## Hallazgos de las cuatro sesiones de QA

Detalle en `docs/proyecto/qa-0*.md`. Resumen de lo que cambia decisiones:

**Vulkan gana claro.** La Radeon 780M hace 19.7 s de audio en 1775 ms, RTF 11.09. La CPU tarda 5433 ms,
RTF 3.62. Texto idéntico. El RTF mejora con audio más largo porque el overhead fijo se amortiza.

**Audio corto está roto.** 3.3 s tardan 8023 ms, más lento que tiempo real, y producen basura en idiomas
aleatorios. La autodetección de idioma se descarrila con poco audio. Candidato a fijar idioma.

**El glosario funciona, pero no escala.** Con 3 términos corrige `GDS` a `GDES` y `redis` a `Redis`. Con
32 términos se pierden la mayúscula inicial, los acentos y toda la puntuación, y `Redis` sale en minúscula
pese a estar en la lista. `custom_words.join(", ")` produce un prompt en forma de lista y el modelo imita
ese estilo. La recuperación por enunciado es requisito, no optimización.

**Las dos capas de corrección no se pueden sumar tal cual.** Upstream las hace excluyentes a propósito.
Forzar que corran las dos rompe `middleware de` convirtiéndolo en `middlewaregdes`, y bajar el umbral a
0.05 no lo evita porque el boost fonético de Soundex salta el umbral. Soundex no es solo insuficiente para
el español, es perjudicial.

**El TTS no sirve para evaluar calidad de ASR.** Todas las conclusiones de la primera sesión, hecha con voz
sintética, se cayeron al repetirlas con voz real. Sirve para ejercitar el pipeline y poco más.

**El uso real valida el alcance.** De 328 dictados previos del usuario en Wispr Flow: 89% en español, 81%
dirigidos a un chat de agente de IA, media de 58 palabras y 36 segundos por dictado, máximo de 4 minutos.

**La latencia es arquitectura, no velocidad de modelo.** Wispr transcribe mientras el usuario habla, el
local espera y procesa todo al final. Handy ya trae el worker de streaming en `managers/transcription.rs`,
activado por `model_supports_streaming` en `actions.rs:505`. Whisper turbo no lo soporta, Nemotron
Streaming 3.5 sí. Detalle en `docs/proyecto/qa-05-rendimiento.md`.

**Nemotron es 4 veces más rápido y peor en lo que importa.** Sobre el mismo audio real:

| | Whisper turbo | Nemotron Streaming |
|---|---|---|
| 30.9 s de audio | 2808 ms, RTF 11.00 | **692 ms, RTF 44.65** |
| números hablados | `404`, `500`, `30 minutos` | `cuatrocientos cuatro`, `quinientos` |
| puntuación | cuatro frases con punto | ninguna |
| jerga | `GDES`, `JWT`, `deploy`, `backoffice` | `jedes`, `jota WDT`, `diploy`, `back office` |
| defecto propio | alucina colas en otro idioma, `È chiaro` | parte palabras compuestas |

**El bug de sobre-corrección está vivo con Nemotron.** Whisper recibe el glosario como `initial_prompt` y
por eso `apply_custom_words` se salta. Nemotron no soporta `InitialPrompt`, así que la pasada difusa corre
y con ella el fallo del QA #3. Hoy, con Nemotron, un glosario poblado empeora la transcripción.

**Release contra debug no es palanca**, 9% en clips cortos y nada en largos, porque la inferencia vive en
DLLs precompiladas. Pero conviene release igual: redacta el texto transcrito en los logs, el debug lo
escribe entero.

## Privacidad, leer antes de commitear

**El fork es público en GitHub.** Los datos del usuario viven fuera del repo y así tiene que seguir:

```
private/          historial exportado de Wispr, backup de settings
qa-audio/         audio de prueba, incluido qa-audio/real con su voz
```

Ambos están en `.gitignore`. Verificado que no hay nada de eso en el remoto, y que ni su email ni su
vocabulario de negocio aparecen en los documentos publicados. Antes de cada push, revisar:

```bash
git ls-tree -r --name-only origin/proyecto/handoff | grep -E "^(private/|qa-audio/)"
```

## Decisión del usuario sobre el glosario

El usuario pidió **vaciar `custom_words`** y dejar que los términos se redescubran solos con el uso, en vez
de sembrarlos a mano. `custom_words = []` ya está aplicado. Eso convierte el aprendizaje por corrección en
el objetivo del producto, no en una mejora opcional.

## Streaming confirmado, Nemotron es viable

El usuario verificó dictando: **con Nemotron el texto aparece en pantalla mientras habla.** El worker de
streaming funciona de punta a punta. Eso resuelve la brecha de latencia contra Wispr Flow sin escribir
código.

Lo que queda por decidir es cómo recuperar lo que Nemotron pierde. Dos caminos:

1. Quedarse en Nemotron y construir el post-proceso que le falta: números hablados a dígitos y
   restauración de puntuación. Los dígitos son un conversor de español a número, acotado y testeable.
2. Dos pasadas: Nemotron para la vista previa en vivo mientras el usuario habla, Whisper para el texto
   final al soltar la tecla. Handy tiene las dos piezas pero no las combina. Da lo mejor de ambos a costa
   de cargar dos modelos en memoria.

## Pedido del usuario: activar por click, sin teclado

Lo que echa de menos de Wispr Flow es poder arrancar el dictado clickeando un overlay, sin tener las manos
en el teclado para el atajo.

Es factible y es trabajo chico. Lo verificado:

- La ventana de overlay **ya acepta clicks**: `src/overlay/RecordingOverlay.tsx:190` tiene
  `onClick={() => commands.cancelOperation()}`.
- La ventana se crea con `focusable(false)`, `always_on_top(true)`, `decorations(false)` y
  `skip_taskbar(true)` en `src-tauri/src/overlay.rs:417`. Clickearla **no roba el foco** del campo donde
  el usuario va a escribir, que es justo lo que hace falta.
- Ya existe `TranscribeAction` en `ACTION_MAP` (`src-tauri/src/actions.rs:468`), y el CLI trae
  `--toggle-transcription` que se lo manda por IPC a la instancia viva.

Falta: exponer un comando Tauri al frontend que dispare esa acción, y mantener el overlay visible en
reposo, no solo durante la grabación. Hoy aparece al empezar a grabar.

## Siguiente alcance, el glosario que se construye solo

Tres pasos en este orden, los tres tocan `audio_toolkit/text.rs` y el modelo de datos de settings.

**Uno, arreglar la sobre-corrección.** Ya no es una mejora, es urgente: con Nemotron rompe texto en cada
dictado. El matcher de n-gramas consume secuencias correctas como "middleware de". Ver `qa-03`.

**Dos, portar el emparejador fonético.** `tools/phonetic-es/es_phonetic.py` a Rust, **al lado de Soundex
y no en su lugar**, eligiendo uno u otro según el idioma de la transcripción.

El prototipo ya está medido contra 19 pares de corrección reales y 30628 n-gramas del corpus del usuario:

| | aciertos | daño real |
|---|---|---|
| Soundex | 3/19 (16%) | 102 (0.333%) |
| Fonética española | 7/19 (37%) | 46 (0.150%) |

Mejor en los dos ejes. Lleva las tres guardas que hicieron falta: palabras funcionales, doble umbral con
léxico español, y n-gramas que ya contienen el término.

Criterio de aceptación del port: reproducir esos números desde Rust. Si los reproduce, recién entonces
reabrir la pregunta del QA #3 sobre correr la capa difusa además del prompt, que con este emparejador
puede tener otra respuesta.

**Tres, aprender de las correcciones.** Ampliar `custom_words` de `Vec<String>` a algo como
`{phrase, replacement, frequency, source}` y engancharlo a `HistoryManager::update_transcription()`.
Wispr Flow ya valida el mecanismo: 18 de sus 24 entradas de diccionario se aprendieron solas observando
las correcciones del usuario. Esto es lo que el usuario pidió explícitamente.

Después, por orden de valor:

1. Recuperación por enunciado para el `initial_prompt`, en vez de meter todos los términos. Medido: con 32
   términos se pierden mayúsculas, acentos y puntuación.
2. Números hablados a dígitos, si se adopta Nemotron. Whisper lo hace nativo y Nemotron no.
3. Arreglar el caso de audio corto, 3.3 s tardan 6 s y alucinan en idiomas aleatorios.
4. `Unload Model = Never`, un desplegable por casi un segundo tras cada pausa.
