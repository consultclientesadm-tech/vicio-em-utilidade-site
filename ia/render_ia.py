"""Edição v-IA: takes do Veo com a modelo falando + legenda palavra a palavra (topo) + selos (base) + trilha baixa com ducking.
uso: python3 render_ia.py cfg.json out.mp4"""
import json, subprocess, sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
W, H, FPS, SR = 1080, 1920, 30, 48000
F_BIG = "/usr/share/fonts/truetype/higgsfield/Montserrat-ExtraBold.ttf"
F_CAP = "/usr/share/fonts/truetype/higgsfield/Metropolis-ExtraBold.ttf"
YEL, WHITE, INK, PINK = (255, 221, 0), (255, 255, 255), (20, 20, 20), (255, 64, 129)

def pill(text, size, fg, bg, pad=(34, 18), radius=28):
    f = ImageFont.truetype(F_BIG, size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    l, t, r, b = tmp.textbbox((0, 0), text, font=f)
    w, h = r - l + pad[0] * 2, b - t + pad[1] * 2
    im = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 10, w + 8, h + 10), radius, fill=(0, 0, 0, 110))
    d.rounded_rectangle((0, 0, w, h), radius, fill=bg + (255,))
    d.text((pad[0] - l, pad[1] - t), text, font=f, fill=fg)
    return im

def caption(words, act, size=78, maxw=960):
    f = ImageFont.truetype(F_CAP, size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    sp = tmp.textlength(" ", font=f)
    lines, cur, cw = [], [], 0
    for i, w in enumerate(words):
        ww = tmp.textlength(w, font=f)
        if cur and cw + sp + ww > maxw:
            lines.append(cur); cur, cw = [], 0
        cur.append((i, w, ww)); cw += (sp if len(cur) > 1 else 0) + ww
    lines.append(cur)
    lh = int(size * 1.18)
    im = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for li, ln in enumerate(lines):
        tw = sum(x[2] for x in ln) + sp * (len(ln) - 1)
        x = (W - tw) / 2
        for i, w, ww in ln:
            d.text((x, 20 + li * lh), w, font=f, fill=YEL if i == act else WHITE, stroke_width=11, stroke_fill=(0, 0, 0))
            x += ww + sp
    return im

def music(total):
    t = np.arange(int(SR * total)) / SR
    out = np.zeros_like(t); beat = 60 / 112
    prog = [(130.8, [261.6, 329.6, 392]), (110, [220, 261.6, 329.6]), (87.3, [174.6, 220, 261.6]), (98, [196, 246.9, 293.7])]
    for i, st in enumerate(np.arange(0, total, beat * 4)):
        bass, chord = prog[i % 4]
        seg = (t >= st) & (t < st + beat * 4); tt = t[seg] - st
        for f in chord:
            out[seg] += 0.035 * np.sin(2 * np.pi * f * tt) * (0.55 + 0.45 * np.sin(2 * np.pi * 1.0 * tt))
        out[seg] += 0.10 * np.sin(2 * np.pi * bass * tt) * np.exp(-((tt % beat) * 4))
    for st in np.arange(0, total, beat):
        seg = (t >= st) & (t < st + 0.25); tt = t[seg] - st
        out[seg] += 0.30 * np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
    rng = np.random.default_rng(3)
    for st in np.arange(beat / 2, total, beat):
        seg = (t >= st) & (t < st + 0.05); tt = t[seg] - st
        out[seg] += 0.05 * rng.uniform(-1, 1, seg.sum()) * np.exp(-tt * 90)
    return out

def main(cfg_path, out):
    cfg = json.load(open(cfg_path)); os.makedirs("ov", exist_ok=True)
    segs = cfg["segments"]; t0 = 0; ins = []; vparts = []; aparts = []
    events = []  # (png, x, y, start, end)
    n = 0
    for si, s in enumerate(segs):
        dur = s["end"] - s["start"]
        ins += ["-ss", str(s["start"]), "-t", str(dur), "-i", s["src"]]
        vparts.append(f"[{si}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1[v{si}]")
        mute = "".join(f"volume=enable='between(t,{a},{b})':volume=0," for a, b in s.get("mute", []))
        aparts.append(f"[{si}:a]{mute}aresample={SR},aformat=channel_layouts=stereo,afade=t=in:d=0.04,afade=t=out:st={dur-0.06}:d=0.06[a{si}]")
        words = s.get("words", [])
        # grupos de até 3 palavras
        groups = [words[i:i + 3] for i in range(0, len(words), 3)]
        for gi, g in enumerate(groups):
            txt = [w[0] for w in g]
            for k, w in enumerate(g):
                a = t0 + w[1] - s["start"]
                if k + 1 < len(g):
                    nxt = g[k + 1][1]
                else:
                    nxt = min(w[2] + 0.35, s["end"])
                    if gi + 1 < len(groups): nxt = min(nxt, groups[gi + 1][0][1])
                b = t0 + nxt - s["start"]
                if b <= a: continue
                p = f"ov/{n}.png"; caption(txt, k).save(p); n += 1
                events.append((p, 0, cfg.get("cap_y", 150), a, b))
        for st in s.get("stickers", []):
            im = pill(st["text"], st.get("size", 64), INK if st.get("bg", "yel") == "yel" else WHITE,
                      YEL if st.get("bg", "yel") == "yel" else (PINK if st.get("bg") == "pink" else INK))
            p = f"ov/{n}.png"; im.save(p); n += 1
            x = (W - im.width) // 2 if st.get("x") is None else st["x"]
            events.append((p, x, st.get("y", 1600), t0 + st["t0"], t0 + st.get("t1", dur)))
        t0 += dur
    total = t0
    for st in cfg.get("global", []):
        im = pill(st["text"], st.get("size", 34), WHITE, (0, 0, 0), pad=(18, 10), radius=16)
        p = f"ov/{n}.png"; im.save(p); n += 1
        events.append((p, st.get("x", 40), st.get("y", 60), 0, total))
    # trilha
    m = music(total)
    m = (m / (np.abs(m).max() + 1e-9) * 0.9 * 32767).astype(np.int16)
    np.stack([m, m], 1).tofile("mus.raw")
    k = len(segs)
    ins += ["-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "mus.raw"]
    for e in events: ins += ["-loop", "1", "-t", str(total), "-i", e[0]]
    fc = vparts + aparts
    fc.append("".join(f"[v{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0[vb]")
    fc.append("".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[voice]")
    fc.append("[voice]asplit[vo1][vo2]")
    fc.append(f"[{k}:a]volume={cfg.get('music_vol', 0.22)}[mu]")
    fc.append("[mu][vo1]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[mud]")
    fc.append("[vo2][mud]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5[aout]")
    last = "vb"
    for j, (p, x, y, a, b) in enumerate(events):
        fc.append(f"[{last}][{k+1+j}:v]overlay={x}:{y}:enable='between(t,{a:.3f},{b:.3f})'[o{j}]"); last = f"o{j}"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[aout]",
                    "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    print("ok", out, round(total, 2))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
