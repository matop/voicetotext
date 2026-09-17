"""Compara la clave fonetica espanola contra Soundex sobre datos reales.

Mide dos cosas, porque medir solo aciertos fue lo que hizo fracasar el hotfix
del QA #3: cuantas correcciones reales recupera, y cuanto texto correcto rompe.
"""
import json, re, sqlite3, sys
from es_phonetic import es_key, score, best_match, _lev, _strip_accents, _is_safe_candidate, load_lexicon
print(f'lexico espanol cargado: {load_lexicon()} palabras')

def soundex(w):
    w = re.sub(r"[^a-z]", "", _strip_accents(str(w).lower()))
    if not w:
        return ""
    codes = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"),
             **dict.fromkeys("dt", "3"), "l": "4", **dict.fromkeys("mn", "5"), "r": "6"}
    out, prev = w[0].upper(), codes.get(w[0], "")
    for c in w[1:]:
        cd = codes.get(c, "")
        if cd and cd != prev:
            out += cd
        if c not in "hw":
            prev = cd
    return (out + "000")[:4]

def soundex_match(candidate, glossary, threshold):
    """Aproxima upstream: Levenshtein normalizado con boost si coincide Soundex."""
    best, best_s = None, None
    for t in glossary:
        a = re.sub(r"[^a-z0-9]", "", _strip_accents(str(candidate).lower()))
        b = re.sub(r"[^a-z0-9]", "", _strip_accents(str(t).lower()))
        if not a or not b:
            continue
        d = _lev(a, b) / max(len(a), len(b))
        if soundex(a) and soundex(a) == soundex(b):
            d *= 0.35
        if d <= threshold and (best_s is None or d < best_s):
            best, best_s = t, d
    return best, best_s

# --- set positivo: pares donde el fallo es fonetico ---
PHONETIC = [
    ("PRAMP","prompt"), ("vaquero","backend"), ("vaciend","backend"), ("Tainet","TailNet"),
    ("rhythm","readme"), ("AppDoor","adapter"), ("DQML","XML"), ("Replacement","Deployment"),
    ("promocion","prod"), ("Faker","sidecar"), ("Paxi","cliproxy"), ("inscritos","tailscale"),
    ("PIC y","apikey"), ("git-hash-batches","git-hub-actions"), ("quiqueo","kickea"),
    ("convengo","convenzo"), ("VCs","OBS"), ("eMpKey","api key"), ("MIWSR","mi WSL"),
]
GLOSSARY = sorted({t for _, t in PHONETIC} | {"middlewaregdes","GDES","Redis","endpoint","payload"})

def evaluate(matcher, name, threshold):
    hits, misses = [], []
    for c, t in PHONETIC:
        got = (matcher(c, GLOSSARY, threshold)[0] or "")
        (hits if got.lower() == t.lower() else misses).append((c, t, got))
    # Pares conocidos: si el matcher los "dispara" sobre el corpus no es daño,
    # es justamente la correccion que buscamos. El corpus tiene errores sin corregir.
    good = {(c.lower(), t.lower()) for c, t in PHONETIC}
    # --- set negativo: texto real del usuario, que no hay que tocar ---
    con = sqlite3.connect("file:/tmp/flow.db?mode=ro", uri=True)
    rows = [r[0] for r in con.execute(
        "SELECT formattedText FROM History WHERE formattedText IS NOT NULL LIMIT 320") if r[0]]
    total, bad, examples = 0, 0, []
    for txt in rows:
        words = re.findall(r"[\w@.:/-]+", txt)
        for n in (1, 2):
            for i in range(len(words) - n + 1):
                ng = " ".join(words[i:i + n])
                total += 1
                m, _ = matcher(ng, GLOSSARY, threshold)
                if m and m.lower() != ng.lower():
                    if (ng.lower(), m.lower()) in good:
                        continue  # correccion deseada, no daño
                    bad += 1
                    if len(examples) < 6:
                        examples.append(f"{ng} -> {m}")
    print(f"\n{name}  (umbral {threshold})")
    print(f"  aciertos fonéticos : {len(hits)}/{len(PHONETIC)}")
    print(f"  daño real          : {bad} sobre {total} n-gramas ({100*bad/total:.3f}%)")
    if examples:
        print(f"  ejemplos de daño   : {' | '.join(examples)}")
    if misses and "FONET" in name:
        print("  no recupera        : " + ", ".join(f"{c}->{t}" for c, t, _ in misses))
    return len(hits), bad, total

evaluate(soundex_match, "SOUNDEX (lo que usa upstream)", 0.18)
evaluate(best_match, "FONETICA ESPANOLA (prototipo)", 0.35)
