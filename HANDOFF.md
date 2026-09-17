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

- 8 commits en la rama `proyecto/handoff`. **Todos son documentación y una herramienta aparte.**
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

**Referencia del competidor.** Wispr Flow registra 904 ms de latencia media de punta a punta. El Vulkan
local hace 34 s de audio en 2795 ms. Son unas 3 veces más rápidos, con GPU en la nube. En latencia pura,
local no va a ganar.

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

## Siguiente alcance

Portar `tools/phonetic-es/es_phonetic.py` a Rust, dentro de `audio_toolkit/text.rs`, **al lado de Soundex
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

Después de eso, por orden de valor:

1. Ampliar `custom_words` de `Vec<String>` a algo como `{phrase, replacement, frequency, source}`. Sin eso
   no se puede aprender de correcciones ni medir mejora.
2. Enganchar el aprendizaje automático a `HistoryManager::update_transcription()`. Wispr Flow ya valida el
   mecanismo: 18 de sus 24 entradas de diccionario se aprendieron solas de las correcciones del usuario.
3. Recuperación por enunciado para el `initial_prompt`, en vez de meter todos los términos.
4. Arreglar el caso de audio corto.
