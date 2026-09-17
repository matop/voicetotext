# QA #3 — El hotfix de "ejecutar las dos capas" se probó y se retiró (2026-09-16)

`qa-01-baseline.md` proponía como primer aporte del fork ejecutar `apply_custom_words` **además** del
`initial_prompt`, en vez de en lugar de. Se implementó, se midió y **se revirtió**. Este documento explica
por qué, porque el resultado negativo es más útil que el fix.

## El cambio

`managers/transcription.rs:1496` — pasar `false` en vez de `model_is_whisper` como
`custom_words_already_prompted`, para que la post-corrección difusa corra también en modelos Whisper.
Compiló en 46s.

## El resultado: regresión peor que el problema original

Mismo WAV real, mismo glosario de 3 términos (`GDES`, `Redis`, `middlewaregdes`):

| | texto |
|---|---|
| **sin el fix** (upstream) | `refactor del **middleware de** guías ... repo **middleware GDES**` |
| **con el fix** | `refactor del **middlewaregdes** guías ... repo **middlewaregdes**` |

El matcher de n-gramas consumió `"middleware de"` —una secuencia perfectamente normal en español— y la
reemplazó por el término del glosario `middlewaregdes`. Se rompió una frase correcta para arreglar un
término que el prompt ya estaba arreglando.

**La exclusividad de upstream no era un descuido: estaba protegiendo contra esto.**

## Por qué el umbral no lo salva

Se reprobó con `word_correction_threshold` en 0.10 y en 0.05 (0.0 = solo coincidencia exacta). **La
sobre-corrección persiste en ambos.**

La causa está en `audio_toolkit/text.rs`: cuando ambos lados soportan Soundex, el match fonético aporta un
boost que hace que la coincidencia se acepte al margen de la distancia de edición. `"middleware de"`
normalizado (`middlewarede`) y `middlewaregdes` colapsan al mismo código Soundex.

## La conclusión que importa

Soundex no es solo *insuficiente* para el español — como se decía en `qa-02`, donde no puede tender el
puente `PRAMP → prompt`. Es **activamente perjudicial** sobre texto español: genera falsos positivos que
destruyen frases correctas.

Esto refuerza y precisa la tesis del producto:

- El problema **no** es que las dos capas no se sumen.
- El problema es que **la capa fonética está construida para inglés** y se aplica a texto español.
- El orden correcto de trabajo es: **primero reemplazar la capa fonética por una consciente del español**,
  y solo entonces plantear ejecutar ambas capas.

Ejecutar las dos capas con el matcher actual es hacer más daño, más rápido.

## Estado

Revertido. `transcription.rs` vuelve a ser idéntico a upstream. El repo no tiene cambios de código propios;
sigue siendo solo documentación, y el fork conserva diff cero contra upstream en código.

Configuración que mejor mide hasta ahora: `custom_words = ["GDES","Redis","middlewaregdes"]`,
`word_correction_threshold = 0.18` (los valores por defecto), acelerador Vulkan.

## Siguiente paso real

Sustituir `natural::phonetics::soundex` por un emparejador fonético español→inglés:
normalizar el token transcrito según reglas del español y compararlo contra la pronunciación hispanizada
esperada de cada término del glosario. Los 1089 pares de corrección reales de `private/wispr-export.json`
son a la vez el conjunto de entrenamiento y el de evaluación.

Sin eso, ningún ajuste de umbral ni de orden de capas va a mover la aguja.
