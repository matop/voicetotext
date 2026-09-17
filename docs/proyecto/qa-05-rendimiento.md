# QA #5, de dónde sale la latencia y qué la baja

El usuario venía de Wispr Flow, que le daba buena latencia pero tenía un límite semanal de palabras.
La pregunta era si se puede cerrar esa brecha en local. Este documento mide de dónde sale.

## La brecha no es velocidad de modelo

Los 904 ms de latencia media que registra Wispr Flow y los 2795 ms que mide el CLI local no miden lo
mismo. Wispr sube el audio mientras el usuario habla, así que al soltar la tecla ya tiene casi todo
transcrito y solo le queda el último fragmento. Handy con Whisper turbo espera a que el usuario termine y
recién entonces procesa el audio entero.

Con la media real de uso, 36 segundos por dictado:

```
Whisper turbo en Vulkan, por lotes    36 s / RTF 12   =  ~3.0 s de espera
Wispr Flow                                               ~0.9 s
```

Igualar eso con un modelo más rápido exigiría RTF cercano a 40, que una iGPU no da. Si la transcripción
ocurre mientras el usuario habla, la duración del dictado deja de importar y la espera pasa a ser casi
constante. Sin viaje de red, el local puede quedar por debajo de los 904 ms.

## Handy ya tiene el worker de streaming

`managers/transcription.rs` tiene `start_stream`, recepción de frames en vivo y un handshake de
`finalize`. `actions.rs:505` lo activa según `model_supports_streaming`, que sale del catálogo. No hay
que escribir el mecanismo, solo usar un modelo que lo soporte.

`whisper-large-v3-turbo` tiene `supports_streaming = false`. De los 8 modelos de streaming del catálogo,
dos incluyen español:

| modelo | idiomas | tamaño |
|---|---|---|
| Nemotron Streaming 3.5 | 28, incluye es | 716 MB |
| Voxtral Mini 4B Realtime | 13, incluye es | 3.2 GB |

**Sin medir todavía**: si Nemotron transcribe el español técnico del usuario tan bien como Whisper turbo.
Es un modelo de 0.6B optimizado para latencia contra uno de 100 idiomas con mucho entrenamiento en
español. Se puede ganar 2 segundos y perder calidad justo en el vocabulario que costó arreglar. Medirlo
requiere micrófono, así que lo tiene que hacer el usuario.

## Release contra debug, no es la palanca

Todo lo medido hasta el QA #4 fue un build debug. Comparación en caliente, mejor de 4 corridas, Vulkan:

| audio | debug | release |
|---|---|---|
| 19.68 s | 1646 ms, RTF 11.96 | 1490 ms, RTF 13.21 |
| 33.99 s | 2641 ms, RTF 12.87 | 2684 ms, RTF 12.66 |

Un 9% en el clip corto y nada en el largo, dentro del ruido. Era previsible: la inferencia vive en DLLs de
C++ precompiladas, así que optimizar el Rust apenas toca el tiempo de transcripción.

Un detalle lateral que sí importa: **el build release escribe `Transcription result: [REDACTED]` en los
logs**, mientras el debug escribe el texto completo. Al distribuir, usar release también por eso.

## Carga del modelo, una palanca gratis

`model_unload_timeout` viene en `Min5` por defecto y cargar el modelo cuesta entre 800 y 1000 ms. El
usuario dicta a ratos entre sesiones de código, así que cualquier pausa de más de 5 minutos le hace pagar
ese segundo otra vez.

```
dictado de 36 s tras una pausa larga   ~900 ms de carga + ~2800 ms  =  ~3.7 s
mismo dictado con el modelo cargado                        ~2800 ms  =  ~2.8 s
```

Poner `Unload Model` en `Never` cuesta memoria, el modelo Q8 ocupa uno o dos GB, y la máquina tiene 28.8
GB. Es un cambio de un desplegable por casi un segundo.

## El caso de audio corto sigue roto

3.33 s de audio tardan 5975 ms, RTF 0.56, más lento que tiempo real, y producen texto basura en idiomas
aleatorios. Ya estaba anotado en el QA #2. Para dictados cortos la autodetección de idioma se descarrila
y además el coste fijo domina. Fijar el idioma en vez de autodetectar es el arreglo a probar.

## Nemotron medido contra Whisper turbo

Ambos modelos instalados, Vulkan, mejor de 3 corridas, sobre los audios reales del usuario.

| | Whisper turbo | Nemotron Streaming 3.5 |
|---|---|---|
| 19.7 s de audio | 1640 ms, RTF 12.00 | **498 ms, RTF 39.52** |
| 34.0 s de audio | 2635 ms, RTF 12.90 | **787 ms, RTF 43.19** |
| 9.5 s de audio | 1268 ms, RTF 7.52 | **273 ms, RTF 34.95** |
| carga del modelo | ~810 ms | ~670 ms |

Nemotron es 3.3 veces más rápido y llega a RTF 40, que era el número necesario para igualar a Wispr Flow.
Y esto es todavía por lotes, sin usar su capacidad de streaming.

El precio está en el vocabulario técnico:

| dicho | Whisper turbo | Nemotron |
|---|---|---|
| GDES | `GDES` | `Jedes`, `Heads` |
| JWT | `JWT` | `JDT` |
| deploy | `deploy` | `diploy` |
| cuatrocientos cuatro | `404` | `cuatrocientos cuatro` |
| "bueno, a ver" | pierde "a ver" | lo conserva |

Nemotron no convierte números hablados a dígitos, y eso importa dictando a un agente.

### El glosario le hace daño a Nemotron, no al revés

Whisper recibe los términos como `initial_prompt` y por eso `apply_custom_words` se salta. Nemotron no
soporta `InitialPrompt`, así que la pasada difusa **sí corre**, y con ella el bug de sobre-corrección del
QA #3 pasa de dormido a activo.

Medido con los mismos audios:

| | con glosario de 3 términos | con glosario vacío |
|---|---|---|
| | `refactor del middlewaregdes guías` | `refactor del middleware de guías` |
| | `the GDES Middlewaregdes` | `the guides Middleware Service` |

**Hoy, usando Nemotron, el glosario empeora la transcripción.** Conviene vaciarlo mientras se prueba ese
modelo, hasta que el emparejador fonético esté portado.

### El emparejador fonético recupera parte de sus errores

Los fallos propios de Nemotron son justo del tipo que ataca `tools/phonetic-es`. Pasados por el prototipo:

```
✓ JDT    -> JWT      score 0.33
✓ diploy -> deploy   score 0.00
✗ Jedes  -> GDES     rechazado
✗ Heads  -> GDES     empareja mal con otro termino
```

Dos de cinco. Ayuda, pero no rescata solo el problema de jerga.

### Lo que esto cambia en el orden de trabajo

Arreglar la sobre-corrección deja de ser una mejora y pasa a ser urgente. Con Whisper el bug estaba
dormido porque la pasada difusa se saltaba. Con Nemotron está activo y destruyendo texto correcto en cada
dictado.

## Resumen de palancas, por relación valor y esfuerzo

| palanca | ganancia | esfuerzo |
|---|---|---|
| Modelo con streaming | de ~3.0 s a casi constante | un click, calidad sin medir |
| `Unload Model = Never` | ~0.9 s tras pausas | un desplegable |
| Vulkan en vez de CPU | 3x, ya activo | ninguno |
| Build release | 0 a 9% | ninguno, hacerlo igual por los logs |
| Idioma fijo | arregla los dictados cortos | un desplegable, probar |
