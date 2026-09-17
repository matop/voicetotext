# Fase 1 — Dictar prompts a agentes de IA

Caso de uso elegido: dictar dentro de **chats de IA (T3, Claude, ChatGPT)**. El resto de apps
(editor/terminal, email/Slack, documentos) se exploran después.

## Por qué este caso lo cambia todo

El receptor del texto **es un LLM, no una persona.** Eso reordena las prioridades del producto:

- **La capa de limpieza vale mucho menos.** El gran diferenciador de Wispr Flow es su Llama fine-tuneado
  que quita muletillas y ajusta el tono. A un agente de IA le da igual: entiende "eh, quiero que hagas un...
  un refactor de esto" perfectamente. **No hay que competir contra la parte cara de Wispr.**
- **La tolerancia a errores sube muchísimo.** Si el ASR escribe "wisper" en vez de "whisper", el LLM lo
  entiende igual. No hace falta 2% WER; con 8-10% el caso de uso funciona.
- **La tolerancia a latencia también sube.** Vas a esperar 30s a que el agente responda; que la transcripción
  tarde 1.5s en vez de 0.7s es irrelevante. **Se puede elegir calidad sobre velocidad.**
- **El objetivo real es el ratio de entrada**: hablar es ~4x más rápido que escribir. Un prompt de 300
  palabras son 4 minutos escribiendo y 1 minuto hablando. Ese es todo el valor.

### Lo que sí se vuelve crítico (y que ningún competidor prioriza)

1. **Enunciados largos.** Un prompt a un agente son 1-3 minutos hablando, no una frase de Slack.
   Whisper trabaja en ventanas de 30s y **alucina en los silencios**. Esto es *el* problema técnico de
   la fase 1, y es justo el que las apps de dictado tipo Wispr no tienen porque asumen frases cortas.
   → Segmentación por VAD en fronteras de silencio, no ventanas fijas. `min_silence_duration_ms` hay que
     calibrarlo: el default de Silero (2s) es conservador y se come pausas de pensamiento.
2. **Toggle, no push-to-talk.** Wispr es hold-to-talk. Mantener una tecla apretada 2 minutos mientras pensás
   un prompt es absurdo. → Toggle con indicador imposible de ignorar + tecla de cancelar.
3. **Feedback durante el dictado.** Si hablás 2 minutos a ciegas y al final falla, perdiste el prompt entero.
   → Overlay flotante con texto parcial. No es cosmético, es la red de seguridad.
4. **Jerga técnica densa.** Los prompts están llenos de identificadores, rutas, nombres de repo. Es lo único
   donde el error sí duele, porque el LLM no puede adivinar el nombre de tu módulo.

## Alcance de la fase 1

```
hotkey toggle → captura → Silero VAD (segmenta por silencios)
   → whisper.cpp large-v3-turbo (CPU AVX-512; benchmarkear Vulkan)
   → glosario: biasing con hotwords relevantes
   → overlay con parcial + confirmación
   → clipboard + Ctrl+V (restaurando el portapapeles previo)
```

**Modelo**: `large-v3-turbo` como default, no Parakeet. Razón: el usuario mezcla español e inglés en la misma
frase y Whisper es la apuesta más segura ahí. Parakeet queda como candidato a benchmarkear contra audio propio
code-switched — si gana, se cambia, pero no se empieza por él.

**Inyección**: al ser el target un chat en navegador o Electron (Chromium), UIAutomation se complica y no
aporta. Clipboard + Ctrl+V es suficiente y fiable. **La escalera completa no hace falta en fase 1.**

### Fuera de alcance en fase 1

- RAG sobre documentos. El beneficio en dictado es menor de lo que parece y el coste es alto.
- Tono y formato por app. El receptor es un LLM, no le importa.
- Cualquier ruta cloud.

## El glosario: de dónde sale sin configurar nada

El usuario tiene tres fuentes de vocabulario: **código y repos propios, docs de clientes/propuestas, y notas
personales**. Las tres importan, pero no cuestan lo mismo:

| Fuente | Coste | Valor en fase 1 | Cuándo |
|---|---|---|---|
| Identificadores de repos propios | Bajo — se extraen del filesystem, sin embeddings | Alto: es la jerga que aparece en los prompts | **Fase 1** |
| Correcciones del usuario | Bajo — solo hay que observar | Alto y creciente | **Fase 1** |
| Docs de clientes (PDF, propuestas) | Medio — parsing + extracción de entidades | Medio en prompts a IA | Fase 2 |
| Notas / knowledge base | Alto — RAG completo | Bajo en dictado | Fase 3 |

Dos mecanismos, ambos sin que el usuario rellene formularios:

1. **Cosecha de identificadores**: recorrer los repos, extraer nombres de funciones, módulos, ficheros y
   proyectos. Es la jerga que realmente aparece en un prompt a un agente.
2. **Aprendizaje por corrección**: si el usuario dictó X y lo editó a Y antes de enviar, eso es una etiqueta
   de entrenamiento gratis y perfecta. Alimenta el glosario.

**Poda obligatoria** (validado en la literatura): probar cada término candidato con TTS y **descartar los que
el ASR ya acierta**. Más hotwords empeoran el recall y meten distractores. El glosario debe contener solo
fallos empíricos confirmados, no todo el vocabulario.

Recuperación: `sqlite-vec` + FTS5 híbrido. Para nombres propios e identificadores el keyword search rinde
más que el vector — de ahí el híbrido.

## Criterio de éxito de la fase 1

Que el usuario prefiera dictar un prompt largo antes que escribirlo. Concretamente:
- Un dictado de 2 minutos se transcribe entero, sin truncar ni alucinar en las pausas.
- Los identificadores de sus propios repos salen bien escritos.
- Cancelar es tan fácil como empezar.

Nota honesta: hasta aquí no hay producto vendible, hay paridad con cosas que ya existen gratis, más el manejo
de enunciados largos. **El producto empieza cuando el glosario auto-aprendido demuestra que mejora solo.**
