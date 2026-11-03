"""Monta o config do render_v7 (formato LOOP) a partir de um produto.json e da narração.
- Cortes distribuídos pelo vídeo inteiro (sem cena de nota nem tela final parada).
- O último corte repete o primeiro, e a última frase do roteiro puxa a primeira: o vídeo recomeça sem emenda.
- CTA no MEIO: selo "Comenta X" (IG) ou "Link na bio" (TT) a partir da palavra COMENTA/LINK, por ~2,4 s.
- Selo de nota com estrelas a partir da palavra NOTA, por ~2,2 s.
Uso: python3 auto_v7.py produto.json ig|tt   -> gera cfg_<modo>.json
produto.json: {"source", "narr_ig", "narr_tt", "script_ig", "script_tt", "blur_band"?, "crop"?,
               "shots": [{"src":[a,b] | "img":arq, "title"?, "big"?, "blur"?}], "keyword", "vitrine_n", "rating"}
"""
import json, re, subprocess, sys, difflib
from faster_whisper import WhisperModel

prod = json.load(open(sys.argv[1])); mode = sys.argv[2]
narr_in = prod[f"narr_{mode}"]; script = prod[f"script_{mode}"]
narr = f"narr_{mode}.wav"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", narr_in, "-af", "atempo=" + str(prod.get("atempo", 1.12)) + "", "-ar", "44100", "-ac", "1", narr], check=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", narr],
                           capture_output=True, text=True).stdout)

model = WhisperModel("small", compute_type="int8")
segs, _ = model.transcribe(narr, language="pt", word_timestamps=True)
hw = [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]
norm = lambda x: re.sub(r"[^\wà-ú]", "", x.lower())

sw = script.split()
sm = difflib.SequenceMatcher(None, [norm(x) for x in sw], [norm(x[2]) for x in hw], autojunk=False)
times = [None] * len(sw)
for a, b, n in sm.get_matching_blocks():
    for k in range(n):
        times[a + k] = hw[b + k][0]
times[0] = times[0] if times[0] is not None else 0.0
for i in range(len(sw)):
    if times[i] is None:
        j = next((j for j in range(i + 1, len(sw)) if times[j] is not None), None)
        nxt = times[j] if j is not None else dur
        times[i] = times[i - 1] + (nxt - times[i - 1]) / ((j or len(sw)) - i + 1)
words = [[w.upper().rstrip(",:.!?"), round(t, 2)] for w, t in zip(sw, times)]
json.dump(words, open(f"words_{mode}.json", "w"), ensure_ascii=False)

# loop: termina logo depois da última palavra (sem respiro longo), pra emendar no começo
total = round(dur + 0.12, 2)
chunks, cur = [], []
for w, raw in zip(words, sw):
    cur.append(w)
    if len(cur) >= 4 or re.search(r"[.!?,:]$", raw):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
caps = [{"start": c[0][1], "end": (chunks[i + 1][0][1] if i + 1 < len(chunks) else total), "words": c} for i, c in enumerate(chunks)]

# cortes pelo vídeo todo, encaixando no início de bloco de legenda; último corte curto (~1,3 s) = volta do primeiro
shots = prod["shots"] + [{k: v for k, v in prod["shots"][0].items() if k not in ("title", "big")}]
n = len(shots)
last_start = round(total - min(1.4, total * 0.11), 2)
starts = [c["start"] for c in caps if 0.3 < c["start"] < last_start - 0.6]
bounds = [0.0]
for k in range(1, n - 1):
    ideal = last_start * k / (n - 1)
    cand = min(starts, key=lambda x: abs(x - ideal)) if starts else ideal
    if abs(cand - ideal) > 0.6 or cand - bounds[-1] < 0.9: cand = ideal
    bounds.append(round(cand, 2))
bounds += [last_start, total]
segments = []
for k, s in enumerate(shots):
    seg = dict(s); seg["start"], seg["end"] = bounds[k], bounds[k + 1]
    seg.setdefault("zoom", [[1.0, 1.04], [1.04, 1.0], [1.0, 1.05], [1.03, 1.0]][k % 4])
    segments.append(seg)
# último corte termina no zoom em que o primeiro começa (emenda visual)
segments[-1]["zoom"] = [1.03, segments[0]["zoom"][0]]

overlays = []
wn = [norm(w[0]) for w in words]
cta_key = "comenta" if mode == "ig" else "link"
if cta_key in wn:
    t0 = words[wn.index(cta_key)][1] - 0.05
    if mode == "ig":
        overlays.append({"t0": t0, "t1": t0 + 2.4, "title": f"Comenta {prod['keyword']}", "sub": "que eu te mando o link", "box": True, "y": 700})
    else:
        overlays.append({"t0": t0, "t1": t0 + 2.4, "title": "Link na bio", "sub": f"produto nº {prod['vitrine_n']} da vitrine", "box": True, "y": 700})
if "nota" in wn:
    t0 = words[wn.index("nota")][1] - 0.05
    overlays.append({"t0": t0, "t1": t0 + 2.2, "title": f"NOTA {prod['rating']}", "stars": True, "y": 330, "stars_y": 470,
                     "sub": "eu garimpo, você aproveita"})

cfg = {"source": prod["source"], "narration": narr, "segments": segments, "captions": caps, "cap_y": prod.get("cap_y", 1420),
       "blur_band": prod.get("blur_band"), "crop": prod.get("crop"), "overlays": overlays,
       **{k: prod[k] for k in ("price", "price_t0", "price_x", "price_y", "punch", "shake") if k in prod}}
json.dump(cfg, open(f"cfg_{mode}.json", "w"), ensure_ascii=False, indent=1)
print(f"{mode}: total {total}s, cortes {bounds}, selos {[(round(o['t0'],2), o['title']) for o in overlays]}")
