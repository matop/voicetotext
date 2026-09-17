# Prompt para arrancar un chat nuevo

Copiar desde aquí:

---

Trabajo en `C:\Proyectos\voicetotext` (ojo, P mayúscula en el path, si lo escribís en minúscula
el build de Vite se rompe). Es un fork de Handy para dictado de voz local en Windows.

Leé primero `HANDOFF.md` en la raíz, y después `docs/proyecto/qa-04-fonetica-espanola.md`.
Ahí está todo el contexto: qué es el proyecto, el entorno, las trampas ya conocidas, y los
resultados de cuatro sesiones de QA.

Tres cosas que no quiero repetir:

1. El repo es un fork **público**. Los datos míos viven en `private/` y `qa-audio/`, ambos
   gitignoreados. Nunca commitear nada de ahí, ni mi email ni vocabulario de negocio en los docs.
2. Compilar y probar se hace en Windows, no en WSL. Levantar con `bun run tauri dev` desde
   `C:\Proyectos\voicetotext`. Si el puerto 1420 está ocupado, matar el proceso node que lo tiene.
3. Para medir no hace falta la UI. `src-tauri\target\debug\handy.exe --transcribe-file <WAV>
   --device-index 0 --json` transcribe headless. `--device-index 0` es Vulkan, `1` es CPU.

**La tarea:** portar `tools/phonetic-es/es_phonetic.py` a Rust, dentro de
`src-tauri/src/audio_toolkit/text.rs`, al lado de Soundex y no en su lugar, eligiendo uno u otro
según el idioma de la transcripción.

Criterio de aceptación: reproducir desde Rust los números que el prototipo ya saca en Python,
medidos sobre 19 pares de corrección reales y 30628 n-gramas de mi corpus.

| | aciertos | daño real |
|---|---|---|
| Soundex, lo que hay hoy | 3/19 (16%) | 102 (0.333%) |
| Fonética española | 7/19 (37%) | 46 (0.150%) |

Tiene que mejorar en los dos ejes a la vez. Medir solo aciertos ya me hizo fracasar un fix antes,
está contado en `docs/proyecto/qa-03-hotfix-retirado.md`.

El prototipo lleva tres guardas y cada una nació de un daño que medimos, así que hay que portarlas
todas: palabras funcionales del español, doble umbral según si el candidato existe en el léxico
español, y rechazo de n-gramas que ya contienen el término del glosario.

Antes de escribir código Rust, verificá que el prototipo de Python sigue dando esos números:

```bash
cd tools/phonetic-es
curl -sL -o palabras_es.txt https://raw.githubusercontent.com/lorenbrichter/Words/master/Words/es.txt
python3 eval.py
```

Empezá leyendo el handoff y decime tu plan antes de tocar `text.rs`.

---

Hasta aquí.
