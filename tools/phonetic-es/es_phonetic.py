"""Clave fonetica para hablantes de espanol que dictan terminos tecnicos en ingles.

El fallo que ataca: un hispanohablante lee "prompt" aplicando fonologia espanola,
el ASR oye fonemas espanoles y escribe la palabra espanola mas cercana ("PRAMP").
Soundex no puede emparejarlos porque compara grafias inglesas entre si.

La idea es llevar ambos lados, lo que el ASR escribio y el termino del glosario,
a una misma clave de fonemas espanoles, y comparar ahi.
"""
import re
import unicodedata

def _strip_accents(s):
    n = unicodedata.normalize("NFD", s)
    return "".join(c for c in n if unicodedata.category(c) != "Mn")

# Colapsos que un hispanohablante hace de verdad al pronunciar.
_RULES = [
    (r"[qk]u?", "k"), (r"c(?=[ei])", "s"), (r"c", "k"), (r"z", "s"), (r"x", "ks"),
    (r"g(?=[ei])", "j"), (r"gu(?=[ei])", "g"), (r"h", ""),
    (r"v", "b"),          # b y v son el mismo fonema en espanol
    (r"ll", "y"), (r"w", "u"), (r"ph", "f"), (r"th", "t"),
    (r"(.)\1+", r"\1"),   # dobles: ss, nn, tt
]

# Vocales a tres grupos: el ASR confunde a/o y e/i en silaba atona.
_VOWELS = {"a": "A", "o": "A", "e": "E", "i": "E", "u": "U", "y": "E"}

def es_key(word, collapse_vowels=True):
    w = _strip_accents(str(word).lower())
    w = re.sub(r"[^a-z0-9]+", "", w)
    if not w:
        return ""
    for pat, rep in _RULES:
        w = re.sub(pat, rep, w)
    # Grupos consonanticos finales que el espanol no cierra: prompt -> promt.
    w = re.sub(r"(mp|nt|kt|pt|ks)$", lambda m: m.group(0)[0], w)
    w = re.sub(r"([bdgkpt])s?$", r"\1", w)
    if collapse_vowels:
        w = "".join(_VOWELS.get(c, c) for c in w)
        w = re.sub(r"([AEU])\1+", r"\1", w)
    return w

def _lev(a, b):
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def score(candidate, term):
    """0.0 es identico, 1.0 es sin relacion. Mismo sentido que el umbral de upstream."""
    a, b = es_key(candidate), es_key(term)
    if not a or not b:
        return 1.0
    d = _lev(a, b) / max(len(a), len(b))
    # Sin colapso de vocales, para no premiar coincidencias que solo existen
    # porque aplastamos a/o y e/i.
    a2, b2 = es_key(candidate, False), es_key(term, False)
    d2 = _lev(a2, b2) / max(len(a2), len(b2))
    return min(d, (d + d2) / 2)

# Palabras funcionales del espanol. Un n-grama que contenga una de estas casi
# nunca es un termino tecnico mal transcrito: es texto correcto. Esta guarda
# existe porque el matcher de upstream reemplazo "middleware de" por
# "middlewaregdes". Ver docs/proyecto/qa-03-hotfix-retirado.md.
_STOP = set("""a al algo ahora ante antes aqui asi aun cada como con contra cual cuando
de del desde donde dos e el ella ellas ello ellos en entre era eran es esa ese eso esta
estan este esto estos fue fui ha han hasta hay la las le les lo los mas me mi mis mucho
muy nada ni no nos o otra otro para pero poco por porque que quien se ser si sin sobre
son su sus tan te ti tu tus un una uno unos y ya yo""".split())

def _is_safe_candidate(candidate):
    """False si el candidato es texto espanol correcto que no hay que tocar."""
    words = [w for w in re.split(r"\s+", str(candidate).strip().lower()) if w]
    if not words:
        return False
    if any(_strip_accents(w).strip(".,;:") in _STOP for w in words):
        return False
    return True

_LEXICON = None

def load_lexicon(path="palabras_es.txt"):
    """Vocabulario espanol. Un candidato que es palabra real puede ser texto
    correcto, asi que se le exige mucho mas parecido antes de reemplazarlo.
    Varios fallos reales son palabras validas fuera de contexto (vaquero por
    backend), asi que un filtro duro de diccionario borraria aciertos."""
    global _LEXICON
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            _LEXICON = {_strip_accents(l.strip().lower()) for l in fh if l.strip()}
    except OSError:
        _LEXICON = set()
    return len(_LEXICON)

def _is_real_word(w):
    if not _LEXICON:
        return False
    return _strip_accents(str(w).lower().strip(".,;:")) in _LEXICON

def best_match(candidate, glossary, threshold, max_edits=3, strict_threshold=0.18):
    if not _is_safe_candidate(candidate):
        return None, None
    # Doble umbral: laxo para lo que no existe en espanol, estricto para lo que si.
    words = str(candidate).split()
    if all(_is_real_word(w) for w in words):
        threshold = min(threshold, strict_threshold)
    best, best_s = int(0) and None, None
    best, best_s = None, None
    ka = es_key(candidate)
    lowered = [w.lower().strip(".,;:") for w in words]
    for t in glossary:
        # Si alguna palabra del n-grama ya ES el termino, no hay nada que corregir:
        # reemplazar colapsaria "backend ir" en "backend" y se comeria una palabra.
        if len(lowered) > 1 and t.lower() in lowered:
            continue
        # Tope absoluto de ediciones, ademas del ratio. Sin el, una cadena larga
        # tolera demasiados cambios y puntua mejor que un acierto corto real.
        if _lev(ka, es_key(t)) > max_edits:
            continue
        s = score(candidate, t)
        if s <= threshold and (best_s is None or s < best_s):
            best, best_s = t, s
    return best, best_s
