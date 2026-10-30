"""Monta o config do render_v4 automaticamente a partir de um produto.json e da narração.
v5: cenas podem ser fotos ({"img": arquivo}); "rating" + "rating_img" criam a cena de nota a partir da palavra "NOTA".
Uso: python3 auto.py produto.json ig|tt   -> gera cfg_<modo>.json (e words_<modo>.json)
produto.json: {"source", "narr_ig", "narr_tt", "script_ig", "script_tt", "blur_band",
               "shots": [{"src":[a,b], "title"?, "sub"?, "big"?, "cx"?, "blur"?, "zoom"?}],   # cenas antes do CTA
               "cta_src": [a,b], "keyword": "POTE", "cta_cx"?}
"""
import json, re, subprocess, sys, difflib
from faster_whisper import WhisperModel

prod = json.load(open(sys.argv[1])); mode = sys.argv[2]
narr_in = prod[f"narr_{mode}"]; script = prod[f"script_{mode}"]
narr = f"narr_{mode}.wav"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", narr_in, "-af", "atempo=1.12", "-ar", "44100", "-ac", "1", narr], check=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", narr],
                           capture_output=True, text=True).stdout)

model = WhisperModel("small", compute_type="int8")
segs, _ = model.transcribe(narr, language="pt", word_timestamps=True)
hw = [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]
norm = lambda x: re.sub(r"[^\wà-ú]", "", x.lower())

# alinha as palavras do roteiro (grafia certa) com os tempos do whisper
sw = script.split()
sm = difflib.SequenceMatcher(None, [norm(x) for x in sw], [norm(x[2]) for x in hw], autojunk=False)
times = [None] * len(sw)
for a, b, n in sm.get_matching_blocks():
    for k in range(n):
        times[a + k] = hw[b + k][0]
times[0] = times[0] if times[0] is not None else 0.0
for i in range(len(sw)):  # interpola faltantes
    if times[i] is None:
        j = next((j for j in range(i + 1, len(sw)) if times[j] is not None), None)
        nxt = times[j] if j is not None else dur
        times[i] = times[i - 1] + (nxt - times[i - 1]) / ((j or len(sw)) - i + 1)
words = [[w.upper().rstrip(",:.!?"), round(t, 2)] for w, t in zip(sw, times)]
json.dump(words, open(f"words_{mode}.json", "w"), ensure_ascii=False)

total = round(dur + 0.45, 2)
# legenda: blocos de até 4 palavras, quebra após pontuação
chunks, cur = [], []
for w, raw in zip(words, sw):
    cur.append(w)
    if len(cur) >= 4 or re.search(r"[.!?,:]$", raw):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
caps = [{"start": c[0][1], "end": (chunks[i + 1][0][1] if i + 1 < len(chunks) else total), "words": c} for i, c in enumerate(chunks)]

# início do CTA = palavra "COMENTA"/"CORRE"
cta_i = max(i for i, w in enumerate(words) if norm(w[0]) in ("comenta", "corre"))
cta_t = words[cta_i][1] - 0.05
# cena da nota (estrelas + slogan) começa na última palavra "NOTA"
rate_t = None
if prod.get("rating"):
    ni = max(i for i, w in enumerate(words) if norm(w[0]) == "nota")
    rate_t = round(words[ni][1] - 0.05, 2)
end_t = rate_t or cta_t
# cortes antes do CTA: divide igual e encaixa no início de bloco de legenda mais próximo
shots = prod["shots"]; n = len(shots)
starts = [c["start"] for c in caps if 0.3 < c["start"] < end_t - 0.6]
bounds = [0.0]
for k in range(1, n):
    ideal = end_t * k / n
    cand = min(starts, key=lambda x: abs(x - ideal)) if starts else ideal
    if abs(cand - ideal) > 0.6 or cand - bounds[-1] < 0.9: cand = ideal
    bounds.append(round(cand, 2))
bounds.append(round(end_t, 2))
segments = []
for k, s in enumerate(shots):
    seg = dict(s); seg["start"], seg["end"] = bounds[k], bounds[k + 1]
    seg.setdefault("zoom", [[1.0, 1.04], [1.04, 1.0], [1.0, 1.05], [1.03, 1.0]][k % 4])
    segments.append(seg)
if rate_t:
    segments.append({"start": rate_t, "end": round(cta_t, 2), "img": prod["rating_img"], "title": f"NOTA {prod['rating']}", "big": True,
                     "title_y": 175, "stars": True, "stars_y": 300, "sub": "eu garimpo, você aproveita", "sub_y": 1330, "zoom": [1.0, 1.03]})
if mode == "ig":
    end_title, end_sub = f"Comenta {prod['keyword']}", "que eu te mando o link"
else:
    end_title, end_sub = "Link na bio", f"produto nº {prod['vitrine_n']} da vitrine"
segments.append({"start": round(cta_t, 2), "end": total, "src": prod["cta_src"], "cx": prod.get("cta_cx", 0.5),
                 "title": end_title, "big": True, "box": True, "title_y": 760, "sub": end_sub, "sub_y": 950, "zoom": [1.0, 1.05],
                 **({"blur": prod["cta_blur"]} if "cta_blur" in prod else {})})
cfg = {"source": prod["source"], "narration": narr, "segments": segments, "captions": caps, "cap_y": prod.get("cap_y", 1420),
       "blur_band": prod.get("blur_band")}
json.dump(cfg, open(f"cfg_{mode}.json", "w"), ensure_ascii=False, indent=1)
print(f"{mode}: total {total}s, cortes {bounds}, CTA {cta_t:.2f}")
