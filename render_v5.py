"""Vídeo v5: cenas do vendedor (deitado = inteiro sobre fundo desfocado) + fotos da galeria em alta
+ narração IA + legenda palavra a palavra + cena de nota com estrelas.
Uso: python3 render_v5.py config.json saida.mp4
"""
import json, math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
F_BIG = "/usr/share/fonts/truetype/higgsfield/Montserrat-ExtraBold.ttf"
F_CAP = "/usr/share/fonts/truetype/higgsfield/Metropolis-ExtraBold.ttf"
ORANGE, YELLOW, WHITE, INK = (255, 94, 58), (255, 214, 10), (255, 255, 255), (28, 22, 40)
SR = 44100


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def pop(t):
    t = max(0.0, min(1.0, t))
    return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2


PHOTO_W, PHOTO_TOP, VID_CY = 940, 380, 860


def build_base(cfg, out):
    """Monta cada cena em 1080x1920:
    - {"img": arquivo}: foto da galeria inteira (940 px) sobre fundo desfocado da própria foto;
    - vídeo em pé: preenche a tela (é 9:16, não corta nada);
    - vídeo deitado: largura total, produto inteiro, sobre fundo desfocado.
    blur/blur_band = faixa (fração da altura do vídeo original) com texto do vendedor a borrar; null = sem blur."""
    parts = []
    src_w, src_h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                                            "-of", "csv=p=0", cfg["source"]], capture_output=True, text=True).stdout.strip().split(","))
    landscape = src_w > src_h
    for i, s in enumerate(cfg["segments"]):
        dur = s["end"] - s["start"]
        p = f"seg{i}.mp4"
        bg = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:3,eq=brightness=-0.18:saturation=1.1"
        if s.get("img"):
            vf = (f"[0:v]format=rgb24,split[a][b];[b]{bg}[bg];[a]scale={PHOTO_W}:{PHOTO_W}:flags=lanczos[fg];"
                  f"[bg][fg]overlay=({W}-{PHOTO_W})/2:{PHOTO_TOP},fps={FPS}")
            inp = ["-loop", "1", "-framerate", str(FPS), "-i", s["img"]]
        else:
            speed = (s["src"][1] - s["src"][0]) / dur
            band = s.get("blur", cfg.get("blur_band"))
            head = f"[0:v]trim={s['src'][0]}:{s['src'][1]},setpts=(PTS-STARTPTS)/{speed},fps={FPS}"
            if landscape and not s.get("cover"):
                fh = int(W * src_h / src_w) // 2 * 2
                fg = f"scale={W}:{fh}:flags=lanczos"
                if band:
                    y0, y1 = band
                    fg += (f",split[fa][fb];[fb]crop={W}:{max(2, int(fh*(y1-y0)))}:0:{int(fh*y0)},boxblur=20:2[fbl];"
                           f"[fa][fbl]overlay=0:{int(fh*y0)}")
                vf = f"{head},split[a][b];[b]{bg}[bg];[a]{fg}[fg];[bg][fg]overlay=0:{VID_CY - fh // 2}"
            else:
                vf = f"{head},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
                if band:
                    y0, y1 = band
                    vf += (f",split[a][b];[b]crop={W}:{int(H*(y1-y0))}:0:{int(H*y0)},boxblur=44:3,eq=saturation=0.35[bl];"
                           f"[a][bl]overlay=0:{int(H*y0)}")
            inp = ["-i", cfg["source"]]
        vf += ",eq=saturation=1.08:contrast=1.04,unsharp=5:5:0.5"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inp, "-filter_complex", vf, "-an",
                        "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", p], check=True)
        parts.append(p)
    with open("list.txt", "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", out], check=True)


def stars_img(n=5, size=92, gap=14):
    im = Image.new("RGBA", (n * size + (n - 1) * gap + 16, size + 16), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for k in range(n):
        cx, cy, r = 8 + k * (size + gap) + size / 2, 8 + size / 2, size / 2
        pts = [(cx + (r if j % 2 == 0 else r * 0.45) * math.sin(math.pi * j / 5),
                cy - (r if j % 2 == 0 else r * 0.45) * math.cos(math.pi * j / 5)) for j in range(10)]
        dr.polygon(pts, fill=YELLOW, outline=(0, 0, 0), width=5)
    return im


def text_img(text, fnt, fill, stroke=10, box=None, pad=26, maxw=960, gap=8):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if tmp.textlength(test, font=fnt) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    a, d = fnt.getmetrics(); lh = a + d
    tw = max(int(tmp.textlength(l, font=fnt)) for l in lines)
    im = Image.new("RGBA", (tw + 2 * pad + 2 * stroke, lh * len(lines) + gap * (len(lines) - 1) + 2 * pad + 2 * stroke), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    if box:
        dr.rounded_rectangle([0, 0, im.width - 1, im.height - 1], 30, fill=box)
    y = pad + stroke
    for l in lines:
        x = (im.width - dr.textlength(l, font=fnt)) / 2
        if box:
            dr.text((x, y), l, font=fnt, fill=fill)
        else:
            dr.text((x, y), l, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += lh + gap
    return im


def paste(frame, im, cx, cy, s=1.0, alpha=1.0, rot=0):
    if s <= 0.02 or alpha <= 0.02:
        return
    t = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)
    if rot:
        t = t.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        t.putalpha(t.getchannel("A").point(lambda v: int(v * alpha)))
    frame.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))


def caption(words, active, fnt, t_in):
    """words: lista de (texto, start). Mostra as já faladas; a ativa em amarelo, com leve 'pop'."""
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    sp = tmp.textlength(" ", font=fnt)
    shown = [w for w in words if w[1] <= t_in + 1e-6] or words[:1]
    lines, cur, cw = [], [], 0
    for w in shown:
        ww = tmp.textlength(w[0], font=fnt)
        if cur and cw + sp + ww > 900:
            lines.append(cur); cur, cw = [], 0
        cur.append((w[0], ww, w is active)); cw += (sp if len(cur) > 1 else 0) + ww
    lines.append(cur)
    a, d = fnt.getmetrics(); lh = a + d + 6
    im = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for li, line in enumerate(lines):
        tot = sum(x[1] for x in line) + sp * (len(line) - 1)
        x = (W - tot) / 2
        for txt, ww, act in line:
            dr.text((x, 20 + li * lh), txt, font=fnt, fill=YELLOW if act else WHITE, stroke_width=12, stroke_fill=(0, 0, 0))
            x += ww + sp
    return im


def music(total, cuts):
    t = np.arange(int(SR * total)) / SR
    out = np.zeros_like(t)
    rng = np.random.default_rng(11)
    beat = 60 / 120
    prog = [(110, [220, 261.6, 329.6]), (87.3, [174.6, 220, 261.6]), (130.8, [261.6, 329.6, 392]), (98, [196, 246.9, 293.7])]
    for i, st in enumerate(np.arange(0, total, beat * 4)):
        bass, chord = prog[i % 4]
        seg = (t >= st) & (t < st + beat * 4); tt = t[seg] - st
        for f in chord:
            out[seg] += 0.03 * np.sin(2 * np.pi * f * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 2 * tt))
        out[seg] += 0.12 * np.sin(2 * np.pi * bass * tt) * np.exp(-((tt % (beat / 2)) * 5))
    for st in np.arange(0, total, beat):
        seg = (t >= st) & (t < st + 0.3); tt = t[seg] - st
        out[seg] += 0.45 * np.sin(2 * np.pi * (45 + 110 * np.exp(-tt * 28)) * tt) * np.exp(-tt * 10)
    for st in np.arange(beat / 2, total, beat / 2):
        seg = (t >= st) & (t < st + 0.04); tt = t[seg] - st
        out[seg] += 0.04 * rng.uniform(-1, 1, seg.sum()) * np.exp(-tt * 120)
    sfx = np.zeros_like(t)
    for c in cuts:
        st = c - 0.2
        seg = (t >= st) & (t < st + 0.32); tt = t[seg] - st
        n = np.convolve(rng.uniform(-1, 1, seg.sum()), np.ones(5) / 5, mode="same")
        sfx[seg] += 0.30 * n * np.sin(np.pi * tt / 0.32) ** 2
    return out, sfx


def main(cfg_path, out_path):
    cfg = json.load(open(cfg_path))
    build_base(cfg, "base.mp4")
    total = cfg["segments"][-1]["end"]
    n = int(total * FPS)

    # áudio: narração + trilha com ducking + whoosh nos cortes
    narr = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", cfg["narration"], "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                          capture_output=True, check=True).stdout
    v = np.frombuffer(narr, np.int16).astype(np.float32) / 32768
    voice = np.zeros(int(SR * total)); voice[: min(len(v), len(voice))] = v[: len(voice)]
    cuts = [s["start"] for s in cfg["segments"][1:]]
    mus, sfx = music(total, cuts)
    env = np.convolve(np.abs(voice), np.ones(int(SR * 0.15)) / (SR * 0.15), mode="same")
    duck = 1 - 0.65 * np.clip(env * 12, 0, 1)
    mix = voice * 1.25 + mus * 0.55 * duck + sfx
    fade = np.minimum(1, (total - np.arange(len(mix)) / SR) / 0.4)
    mix = np.tanh(mix * fade * 1.1) * 0.95
    with wave.open("mix.wav", "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((mix * 32000).astype(np.int16).tobytes())

    f_cap = ImageFont.truetype(F_CAP, 74)
    f_big = ImageFont.truetype(F_BIG, 104)
    f_mid = ImageFont.truetype(F_BIG, 62)
    chunks = cfg["captions"]  # [{start,end,words:[[txt,start],...]}]
    titles = []
    for s in cfg["segments"]:
        ti = text_img(s["title"], f_big if s.get("big") else f_mid, INK if s.get("box") else WHITE,
                      box=WHITE + (255,) if s.get("box") else None) if s.get("title") else None
        su = text_img(s["sub"], f_mid, WHITE, box=ORANGE + (255,)) if s.get("sub") else None
        titles.append((ti, su))
    st_im = stars_img()

    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", "base.mp4", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-i", "mix.wav", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    cache = {}
    starts = [s["start"] for s in cfg["segments"]]
    for fi in range(n):
        raw = dec.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        t = fi / FPS
        i = max(j for j in range(len(starts)) if starts[j] <= t + 1e-9)
        s = cfg["segments"][i]; lt = t - s["start"]; p = lt / (s["end"] - s["start"])
        img = Image.frombytes("RGB", (W, H), raw)
        z = s.get("zoom", [1.0, 1.04]); zoom = z[0] + (z[1] - z[0]) * p + 0.03 * (1 - ease_out(lt / 0.3))
        if zoom != 1:
            cw, ch = W / zoom, H / zoom
            fy = s.get("focus_y", 0.5)
            box = (int((W - cw) / 2), int((H - ch) * fy), int((W + cw) / 2), int((H - ch) * fy + ch))
            img = img.crop(box).resize((W, H), Image.BILINEAR)
        frame = img.convert("RGBA")
        ti, su = titles[i]
        if ti is not None:
            paste(frame, ti, W / 2, s.get("title_y", 330), pop(lt / 0.35))
        if su is not None:
            paste(frame, su, W / 2, s.get("sub_y", 520), pop((lt - 0.3) / 0.35), rot=-2)
        if s.get("stars"):
            paste(frame, st_im, W / 2, s.get("stars_y", 300), pop((lt - 0.15) / 0.35))
        ch_ = next((c for c in chunks if c["start"] <= t < c["end"]), None)
        if ch_:
            ws = [tuple(w) for w in ch_["words"]]
            act = [w for w in ws if w[1] <= t + 1e-6]
            active = act[-1] if act else ws[0]
            key = (id(ch_), active)
            if key not in cache:
                cache[key] = caption(ws, active, f_cap, t)
            ci = cache[key]
            frame.alpha_composite(ci, (0, int(cfg.get("cap_y", 1420))))
        d = ImageDraw.Draw(frame)
        d.rectangle([0, 0, W, 12], fill=(0, 0, 0, 120)); d.rectangle([0, 0, int(W * t / total), 12], fill=ORANGE)
        if i > 0 and lt < 0.08:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(170 * (1 - lt / 0.08)))))
        enc.stdin.write(frame.convert("RGB").tobytes())
    enc.stdin.close(); enc.wait(); dec.kill(); dec.wait()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
