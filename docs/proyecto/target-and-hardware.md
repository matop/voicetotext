# Target, hardware y entorno de desarrollo

## Decidido

- **SO objetivo: Windows 11 nativo.** No Linux escritorio, no macOS, no WSL.
- **Entorno de desarrollo: WSL2**, editando desde la UI de T3.

Esto crea una asimetría que condiciona todo el proyecto: *se edita en Linux, se ejecuta en Windows.*

## Hardware de referencia (la máquina del usuario = el target real)

| | |
|---|---|
| CPU | AMD Ryzen 7 8845HS — Zen 4, 8c/16t, **AVX-512** |
| RAM | 28.8 GB (WSL2 tiene ~14 GB asignados) |
| GPU | Radeon 780M iGPU, ~3 GB. **Sin NVIDIA discreta** |
| NPU | XDNA (Ryzen AI, ~16 TOPS) — presente pero tooling inmaduro en Windows |
| OS | Windows 11 Pro build 26200 |

### Consecuencias directas sobre el ASR

- **faster-whisper queda descartado**: su ventaja es CUDA y aquí no hay NVIDIA. Además es Python, mal para empaquetar.
- **whisper.cpp es el camino natural**: GGML explota AVX-512 de Zen 4 muy bien, y tiene backend **Vulkan** que sí corre en la 780M. Hay que benchmarkear CPU vs Vulkan — en iGPU no está claro cuál gana.
- **Parakeet TDT v3 sigue siendo viable** pese a que la doc habla de "Apple Silicon o NVIDIA": Handy ya embarca una ruta Parakeet V3 optimizada para CPU, y al ser transducer (sin bucle autoregresivo) es barato en CPU. El "suelo de 16 GB" que citan los benchmarks es del caso unified-memory de Apple, no aplica aquí.
- El límite real no es la RAM (28.8 GB sobran para turbo ~6 GB), es la **latencia en CPU**. Objetivo a validar: <1s desde soltar la tecla hasta texto inyectado.
- La NPU XDNA: interesante a futuro vía ONNX Runtime + Vitis AI EP. **No planificar sobre ella**, anotarla como optimización posterior.

### Consecuencias sobre la inyección de texto

Buena noticia: al descartarse Linux, **desaparece el problema de Wayland**, que era el bloqueante más feo del proyecto. En Windows la escalera es conocida y resuelta:

1. UIAutomation donde el control lo soporte (limpio, atómico, sin tocar el portapapeles).
2. `SendInput` para el resto.
3. **Clipboard + Ctrl+V** como fallback universal — funciona incluso contra procesos elevados, porque el portapapeles no está sujeto a UIPI.

Hay que preservar y restaurar el contenido previo del portapapeles al usar (3).

## La trampa del entorno de desarrollo

**No se puede compilar ni probar esta app desde WSL2.** Concretamente:

- Tauri en Windows necesita el toolchain **MSVC** y WebView2. El target `x86_64-pc-windows-gnu` (el único cross-compilable cómodo desde WSL) rompe con Tauri.
- Los hotkeys globales y la inyección de texto son APIs Win32 del host. Desde WSL **no son testeables en absoluto**, ni siquiera parcialmente.

### Workflow que resuelve esto

1. **El repo vive en el sistema de ficheros de Windows** (`/mnt/c/...`), no en `/home/desamato/`. Editar desde WSL vía `/mnt/c` es algo más lento, pero la compilación queda nativa — que es lo que importa.
   *(Al día de hoy el repo está en `/home/desamato/proyectos/VoiceToText` → hay que moverlo antes de escribir código.)*
2. Instalar en **Windows**: `rustup` (toolchain MSVC), Node, y WebView2 (ya viene en Win11).
3. Compilar y ejecutar desde WSL invocando los binarios de Windows por interop: `cargo.exe build`, `pnpm.exe tauri dev`. El proceso corre nativo en el host y se puede probar de verdad.
4. Los tests de lógica pura (glosario, recuperación de contexto, post-proceso) sí pueden correr en WSL. Separar esa lógica en crates sin dependencias de plataforma **desde el principio**, precisamente para poder iterarla rápido desde el entorno de dev.

### Estado del toolchain (verificado 2026-09-16)

- WSL: Node 24.19, pnpm 11.11, Python 3.14, gcc 15.2. **Sin Rust, sin cmake.**
- Windows: Node 24.14. **Sin Rust.**
