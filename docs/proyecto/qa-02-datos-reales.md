# QA #2 — Voz real y datos de uso previos (2026-09-16)

Continuación de `qa-01-baseline.md`. Aquí ya hay **voz real del usuario**, no TTS, y además el historial
de uso de Wispr Flow que el usuario venía acumulando.

> **Privacidad**: los datos crudos (audio, transcripciones, vocabulario de negocio) viven en `qa-audio/real/`
> y `private/`, ambos en `.gitignore`. **Este repo es un fork público: nada de eso puede commitearse.**
> Este documento solo contiene agregados y conclusiones.

## Correcciones a QA #1

Dos conclusiones anteriores estaban equivocadas, ambas por culpa del audio sintético:

1. **"Custom Words no corrige nada" — FALSO.** Con voz real y el mismo WAV:

   | | sin glosario | con glosario |
   |---|---|---|
   | | `middleware GDS` | `middleware GDES` ✓ |
   | | `persistencia redis` | `persistencia Redis` ✓ |

   Con TTS no funcionaba porque la distancia acústica era demasiado grande. **La capa sirve.**

2. **"El pipeline en vivo degrada frente a batch" — NO SOSTENIDO.** De cuatro tomas, tres dan texto
   idéntico por ambas rutas. La única que difirió encaja mejor con no-determinismo del decoder.

3. **La falta de puntuación era artefacto del diseño de prueba.** Las tomas *leídas de un guion* salen sin
   puntuar; la toma hablada de forma natural salió perfectamente puntuada. Leer en voz alta aplana la
   prosodia y Whisper pierde los límites de frase. No es un bug.

Lección de método: **el TTS no sirve para evaluar calidad de ASR.** Sirve para ejercitar el pipeline y poco más.

## Rendimiento con voz real

| audio | Vulkan | CPU | RTF Vulkan |
|---|---|---|---|
| 19.7s | 1775 ms | 5433 ms | 11.09x |
| 34.0s | 2795 ms | — | 12.16x |
| 9.5s | 1772 ms | — | 5.38x |
| **3.3s** | **8023 ms** | — | **0.42x** |

Vulkan se mantiene ~3x sobre CPU y el RTF escala con la duración.

**Bug real: audio corto.** 3.3s tardó 8023 ms (más lento que tiempo real) y produjo basura en idiomas
aleatorios — cirílico en la ruta en vivo, islandés en batch. Con `Language = Auto Detect` y poco audio, la
detección de idioma se descarrila. Afecta a cualquier dictado corto. **Candidato a fijar el idioma por
defecto en vez de autodetectar.**

## Datos de uso previos: 328 dictados reales

El usuario ya usaba Wispr Flow. Su base local tiene 328 dictados con un esquema muy informativo.

### Lo que valida la fase 1, con datos y no con suposiciones

| métrica | valor |
|---|---|
| Dictados | 328 |
| Idioma detectado | **es 236 / en 28 → 89% español** |
| App de destino | **T3 Code: 229 de 283 → 81%** |
| Palabras por dictado | media **57.8**, máx **372** |
| Duración hablada | media **36.3 s**, máx **240.8 s** |
| Palabras corregidas por el usuario | 1089 acumuladas |
| Reemplazos de diccionario disparados | 503 |

Las tres decisiones de la fase 1 quedan confirmadas empíricamente:
- **Español primero**: 89% del uso.
- **Dictar a agentes de IA**: 81% del uso va a T3 Code. No era una apuesta, es el caso real.
- **Enunciados largos**: media de 36 s y máximo de 4 minutos. Muy lejos de una frase de Slack.

### Latencia de referencia del competidor

Wispr Flow registra `e2eLatency` media de **904 ms** (mín 271, máx 2274) para una media de 36 s de habla.
Nuestro Vulkan local hace 34 s en 2795 ms. **Wispr es ~3x más rápido de punta a punta**, con GPU en la nube.
Ese es el hueco competitivo real, y conviene tenerlo escrito: local no va a ganar en latencia pura.

### Su glosario se auto-construye

De 24 entradas del diccionario de Wispr, **18 tienen `source = user_edits`**: se aprendieron solas
observando las correcciones del usuario, no se configuraron a mano. El esquema guarda `frequencyUsed`,
`manualEntry`, `observedSource` e `isStarred`.

**El mecanismo que este proyecto planeaba inventar ya está validado en producción por el competidor.**

## El hallazgo central: fonética española sobre grafía inglesa

Extrayendo los pares `texto dictado → texto corregido por el usuario` del historial, el patrón de fallo
no es aleatorio. Es sistemáticamente **vocabulario técnico inglés pronunciado con fonética española**:

```
PRAMP        -> prompt
MIWSR        -> mi WSL
Replacement  -> Deployment
rhythm.      -> readme.
AppDoor      -> adapter
HDP          -> http o https
escúchalo    -> pushealos      (push + sufijo español)
```

El modelo oye fonemas españoles y elige la palabra española —o inglesa— más cercana, cuando lo que el
hablante dijo era un término técnico inglés hispanizado.

**Esto es lo que ninguna herramienta resuelve hoy, y es la tesis del producto:**

- Soundex (lo que usa upstream) es un algoritmo **inglés/ASCII**. No puede tender ese puente: compara
  grafías inglesas entre sí, no pronunciación española contra grafía inglesa.
- El `initial_prompt` es un sesgo blando y por sí solo no lo garantiza.
- Lo que hace falta es **matching fonético cruzado**: normalizar el token transcrito a fonemas según reglas
  del español y compararlo contra la pronunciación *hispanizada esperada* de cada término del glosario.

Ese es el trabajo de diferenciación del fork, y ahora está respaldado por 1089 correcciones reales.

## Funcionalidades de Wispr Flow que vale la pena portar

Deducidas de su esquema de datos, ordenadas por relación valor/coste para este caso de uso:

| Funcionalidad | Evidencia en su esquema | Vale la pena |
|---|---|---|
| Glosario aprendido de correcciones | `Dictionary.source='user_edits'`, `frequencyUsed` | **Sí, lo primero** |
| Métricas de corrección | `numWordsCorrected`, `editDistanceToDictated`, `numDictionaryReplacements` | **Sí**, sin esto no se mide mejora |
| Contexto de la app activa | `app`, `url`, `axText`, `axHTML`, `textboxContents` | Sí, pero después |
| Confianza por transcripción | `averageLogProb` | Sí, barato y útil para decidir cuándo corregir |
| Dos modelos con divergencia | `defaultAsrText`/`fallbackAsrText` + `*DivergenceScore` | Interesante; caro en local |
| Ajuste de tono | `toneMatchedText`, `toneMatchPairs` | **No** para este caso: el receptor es un LLM |
| Snippets por frase clave | `Dictionary.isSnippet`, `replacement` | Sí, barato (upstream no lo tiene: sus custom words no mapean reemplazo) |

Nota sobre el modelo de datos: el `custom_words: Vec<String>` de upstream **solo guarda el término**, sin
`replacement`, sin frecuencia y sin origen. Para aprender de correcciones hace falta ampliarlo a algo como
`{phrase, replacement, frequency, source, last_used}`. Es el primer cambio de esquema del fork.

## Experimento: el glosario no escala (medido)

Se midió el mismo WAV real con tres tamaños de glosario, todo lo demás igual:

| glosario | salida |
|---|---|
| **0 términos** | `...repo middleware GDS ... antes del deploy. El endpoint ... adapter.` |
| **3 términos** | `...repo middleware GDES ... antes del deploy. El endpoint ... tirando un timeout ... adapter.` |
| **32 términos** | `necesito ... middleware de guias ... GDES ... antes del deploy el endpoint ... adapter` |

Con 32 términos se degrada de forma medible:
- se pierde la **mayúscula inicial** de la frase,
- se pierde el **acento** de "guías",
- se pierde **toda la puntuación** (con 3 términos había puntos),
- y `Redis`, que estaba en la lista de 32, salió **en minúscula** — cuando con 3 términos salía correcto.

**Añadir términos rompió un término que ya funcionaba.** Es el efecto distractor descrito en la literatura:
`custom_words.join(", ")` produce un prompt que es una lista de palabras separadas por comas, y el modelo
imita ese estilo — sin puntuación ni capitalización.

Conclusión operativa: **la recuperación por enunciado no es una optimización, es un requisito.** Un glosario
cosechado de los repos tendrá cientos de identificadores; metidos todos en el prompt, empeoran el resultado.
Configuración que mejor midió hoy: 3 términos. Ese es el punto de partida hasta que exista recuperación.

## Siguientes pasos

1. Ampliar el modelo de `custom_words` a entrada con reemplazo, frecuencia y origen.
2. Enganchar el aprendizaje por corrección a `HistoryManager::update_transcription()`.
3. Matching fonético español→inglés, complementando Soundex en vez de reemplazarlo.
4. Ejecutar `apply_custom_words` **además** del `initial_prompt` (ver QA #1).
5. Arreglar el caso de audio corto: idioma fijo en vez de autodetección.
6. Instrumentar métricas de corrección desde el día 1, o no habrá forma de saber si algo mejora.
