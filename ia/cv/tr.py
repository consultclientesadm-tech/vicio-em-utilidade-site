import sys
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
for f in sys.argv[1:]:
    segs, _ = m.transcribe(f, language="pt", word_timestamps=True)
    print("==", f)
    for s in segs:
        print(f"{s.start:.2f}-{s.end:.2f} {s.text}")
        print("   ", " ".join(f"{w.word.strip()}@{w.start:.2f}-{w.end:.2f}" for w in s.words))
