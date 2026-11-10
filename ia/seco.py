"""Vídeo seco: só os takes com a fala da modelo, cortes secos com troca de zoom (jump cut). Sem texto/música (exceto a PALAVRA do comenta, opcional). 1080x1920.
uso: python3 seco.py cfg.json out.mp4   cfg = {"segs": [[src, ini, fim, zoom], ...]}"""
import json, subprocess, sys
cfg = json.load(open(sys.argv[1])); out = sys.argv[2]
ins, fc = [], []
for i, (src, a, b, z) in enumerate(cfg["segs"]):
    d = b - a
    ins += ["-ss", str(a), "-t", str(d), "-i", src]
    w, h = int(1080 * z) // 2 * 2, int(1920 * z) // 2 * 2
    fc.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,scale={w}:{h},crop=1080:1920:(iw-1080)/2:(ih-1920)/2.6,fps=30,setsar=1,format=yuv420p[v{i}]")
    fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.02,afade=t=out:st={d-0.03:.3f}:d=0.03[a{i}]")
n = len(cfg["segs"])
pal = cfg.get("palavra")  # {"texto": "CUBO", "ini": s, "fim": s} no tempo do vídeo final (regra do Leonardo 10/11)
vout = "[vc]" if pal else "[v]"
fc.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1{vout}[a0]")
if pal:
    font = cfg.get("fonte", "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf")
    fc.append(f"[vc]drawtext=fontfile={font}:text='{pal['texto']}':fontsize=150:fontcolor=white:borderw=10:bordercolor=black:"
              f"x=(w-text_w)/2:y=h*{pal.get('y', 0.64)}:enable='between(t,{pal['ini']},{pal['fim']})'[v]")
fc.append("[a0]loudnorm=I=-14:TP=-1.5[a]")
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", out], check=True)
print("ok", out)
