# QA #4, prototipo de emparejamiento fonético español

Respuesta al siguiente paso que dejó abierto `qa-03-hotfix-retirado.md`: sustituir Soundex por algo que
entienda cómo un hispanohablante pronuncia términos técnicos en inglés.

Está en `tools/phonetic-es/`. Es un prototipo en Python, **no está integrado en la app**. Se prototipó
fuera de Rust para poder iterar sin pagar un build por intento.

## Qué problema ataca

Un hispanohablante lee "prompt" aplicando fonología española. El ASR oye fonemas españoles y escribe la
palabra española más cercana. El resultado es `PRAMP`. Soundex compara grafías inglesas entre sí, así que
no puede unir las dos puntas.

La clave fonética lleva los dos lados, lo que el ASR escribió y el término del glosario, a un mismo
alfabeto de fonemas españoles, y compara ahí. Las reglas que aplica son colapsos que un hispanohablante
hace de verdad: b y v son el mismo fonema, seseo para s, z y c, yeísmo, h muda, x como ks, y los grupos
consonánticos finales que el español no cierra, de modo que "prompt" queda en "promt".

## Resultados sobre datos reales

19 pares de corrección del historial del usuario donde el fallo es fonético. Como conjunto negativo, 30628
n-gramas extraídos de sus propias transcripciones, texto que no hay que tocar.

| | aciertos | daño real |
|---|---|---|
| Soundex, lo que usa upstream | 3/19 (16%) | 102 (0.333%) |
| Fonética española | **7/19 (37%)** | **46 (0.150%)** |

Mejora en los dos ejes: recupera 2.3 veces más correcciones y rompe menos de la mitad de texto. De los 46
casos de daño que quedan, varios son correcciones correctas que no estaban etiquetadas en el conjunto de
prueba, por ejemplo `Tilescale` a `tailscale` y `li WSL` a `mi WSL`. El daño verdadero es menor que 46.

## Las tres guardas, y por qué existe cada una

Medir solo aciertos fue lo que hundió el hotfix del QA #3, así que cada guarda nació de un daño observado.

**Palabras funcionales.** Un n-grama que contenga "de", "el", "que" o similares casi nunca es un término
técnico mal transcrito. Esta guarda existe porque el matcher de upstream convirtió "middleware de" en
"middlewaregdes".

**Doble umbral con léxico.** Si el candidato no existe en español, es casi seguro un fallo del ASR y se
puede ser laxo, umbral 0.35. Si es una palabra española real, se exige 0.18. Sin esto aparecían
`contexto` a `convenzo`, `puedes` a `Redis` y `máquina` a `backend`. No sirve un filtro de diccionario
duro, porque varios fallos reales son palabras españolas válidas fuera de contexto, como `vaquero` por
backend o `promoción` por prod.

**N-gramas que ya contienen el término.** Sin esta guarda, "backend ir" colapsaba en "backend" y se comía
una palabra.

## Lo que no recupera

12 de los 19 pares siguen sin resolverse:

```
vaquero->backend      rhythm->readme        AppDoor->adapter     DQML->XML
promocion->prod       Faker->sidecar        Paxi->cliproxy       inscritos->tailscale
PIC y->apikey         git-hash-batches->git-hub-actions          VCs->OBS
eMpKey->api key
```

Se reparten en dos grupos. Unos tienen distancia acústica demasiado grande, como `Faker` por `sidecar`.
Otros no son errores fonéticos sino abreviaturas o reescrituras del usuario, como `promocion` por `prod`
y `eMpKey` por `api key`, y ninguna clave fonética los va a resolver. Conviene no contarlos como objetivo.

## Límites de esta medición

El conjunto de prueba son 19 pares, no 1089. La cifra de 1089 que aparece en `qa-02-datos-reales.md` es la
suma de `numWordsCorrected`, que cuenta palabras, no sustituciones. La extracción de pares del historial
da 48 sustituciones, de las cuales 19 son de origen fonético.

El conjunto negativo son las propias transcripciones del usuario, que contienen errores sin corregir. Eso
infla el recuento de daño en ambas columnas por igual, así que la comparación se sostiene aunque el valor
absoluto no sea exacto.

## Siguiente paso

Portar `es_phonetic.py` a Rust dentro de `audio_toolkit/text.rs`, junto a Soundex y no en su lugar, y
elegir uno u otro según el idioma de la transcripción. Después reabrir la pregunta del QA #3 sobre correr
la capa difusa además del prompt, que con este emparejador ya puede tener otra respuesta.

Reproducir la medición:

```bash
cd tools/phonetic-es
curl -sL -o palabras_es.txt https://raw.githubusercontent.com/lorenbrichter/Words/master/Words/es.txt
python3 eval.py
```

El script lee el historial exportado, que vive fuera del repo por privacidad.
