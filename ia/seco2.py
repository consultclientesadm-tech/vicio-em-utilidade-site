"""seco v2: corta as pausas longas (>0,25 s) de cada trecho e usa trim/atrim (sincronia exata).
uso: python3 seco2.py cfg.json out.mp4  cfg = {"segs": [[src, ini, fim, zoom], ...], "palavra": {...}, "pausa": 0.25}"""
import json, subprocess, sys, re
cfg = json.load(open(sys.argv[1])); out = sys.argv[2]
P = cfg.get("pausa", 0.25); PAD = 0.07
def falas(src, a, b):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(a), "-t", str(b - a), "-i", src, "-af",
                        "asetnsamples=1200,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                        "-f", "null", "-"], capture_output=True, text=True).stdout
    lv = [float(x) if x not in ("-inf", "inf") else -99 for x in re.findall(r"RMS_level=(\S+)", r)]
    TH = cfg.get("ruido", -37); st = 0.025
    voz = [v > TH for v in lv]
    cuts, i, n = [], 0, len(voz)
    while i < n:
        if voz[i]:
            j = i
            while j < n:
                if not voz[j]:
                    k = j
                    while k < n and not voz[k]: k += 1
                    if (k - j) * st >= P or k == n: break
                    j = k
                else: j += 1
            cuts.append((max(a, a + i * st - PAD), min(b, a + j * st + PAD))); i = j
        else: i += 1
    return [(round(x * 24) / 24, round(y * 24) / 24) for x, y in cuts if y - x > 0.15]
srcs = sorted({s[0] for s in cfg["segs"]}); idx = {s: i for i, s in enumerate(srcs)}
pieces = []
for src, a, b, z in cfg["segs"]:
    for k, (x, y) in enumerate(falas(src, a, b)):
        pieces.append((src, x, y, z if k % 2 == 0 else z + 0.08))
fc = []
for s in srcs:
    n = sum(1 for p in pieces if p[0] == s); i = idx[s]
    fc.append(f"[{i}:v]split={n}" + "".join(f"[s{i}v{j}]" for j in range(n)))
    fc.append(f"[{i}:a]asplit={n}" + "".join(f"[s{i}a{j}]" for j in range(n)))
used = {s: 0 for s in srcs}; tl = 0.0
for k, (src, x, y, z) in enumerate(pieces):
    i = idx[src]; j = used[src]; used[src] += 1; d = y - x
    w, h = int(1080 * z) // 2 * 2, int(1920 * z) // 2 * 2
    fc.append(f"[s{i}v{j}]trim=start={x}:end={y},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              f"scale={w}:{h},crop=1080:1920:(iw-1080)/2:(ih-1920)/2.6,fps=30,setsar=1,format=yuv420p[v{k}]")
    fc.append(f"[s{i}a{j}]atrim=start={x}:end={y},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=in:d=0.015,afade=t=out:st={d-0.025:.3f}:d=0.025,apad,atrim=end={d}[a{k}]")
    print(f"{tl:6.2f} {src} {x:.2f}-{y:.2f}"); tl += d
n = len(pieces); pal = cfg.get("palavra"); vout = "[vc]" if pal else "[v]"
fc.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1{vout}[a0]")
if pal:
    font = cfg.get("fonte", "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf")
    fc.append(f"[vc]drawtext=fontfile={font}:text='{pal['texto']}':fontsize=150:fontcolor=white:borderw=10:bordercolor=black:"
              f"x=(w-text_w)/2:y=h*{pal.get('y', 0.68)}:enable='between(t,{pal['ini']},{pal['fim']})'[v]")
fc.append("[a0]loudnorm=I=-14:TP=-1.5[a]")
ins = sum((["-i", s] for s in srcs), [])
if "--dry" in sys.argv: sys.exit()
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", out], check=True)
print("ok", out, round(tl, 2))
