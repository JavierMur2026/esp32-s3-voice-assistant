#!/usr/bin/env python3
"""Generate the two embedded sounds for the ESP32-S3 Voice Assistant:

  esphome/aviso.h                  -> wake chime, raw 16-bit PCM (16 kHz mono),
                                      played through the announcement mixer source
                                      (`speaker.play ... data: !lambda return aviso_raw;`)
  esphome/sounds_timer_finished.wav-> timer-finished beep, WAV 16 kHz mono 16-bit,
                                      embedded with the `file:` component (~812 ms)

No ffmpeg needed (plain stdlib). Run from the repo root:
    python3 tools/generate_sounds.py
"""
import math
import os
import struct
import wave

SR = 16000          # sample rate used by the speaker config
PEAK = 0.7          # 70 % amplitude, as the production firmware
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "esphome")


def tone_samples(freqs_durations, peak=PEAK):
    """Piecewise sine with exponential decay per segment. freqs_durations =
    list of (freq_hz, duration_s). Returns list of 16-bit signed ints."""
    samples = []
    for freq, dur in freqs_durations:
        n = int(SR * dur)
        for i in range(n):
            t = i / SR
            env = math.exp(-3.0 * t / dur)          # decay inside the segment
            v = (math.sin(2 * math.pi * freq * t) * 0.8
                 + math.sin(2 * math.pi * freq * 2 * t) * 0.2)
            samples.append(int(v * env * peak * 32767))
    return samples


def fade(samples, edge=160):
    """Short fade in/out to avoid clicks."""
    for i in range(min(edge, len(samples))):
        samples[i] = samples[i] * i // edge
    for i in range(min(edge, len(samples))):
        j = len(samples) - 1 - i
        samples[j] = samples[j] * i // edge


def main():
    os.makedirs(OUT, exist_ok=True)

    # ---- wake chime: two-note "ding-dong", 0.8 s total -------------------
    chime = tone_samples([(1568.0, 0.40), (1318.5, 0.40)])   # G6 -> E6
    fade(chime)
    with open(os.path.join(OUT, "aviso.h"), "w") as f:
        f.write("// Generic activation chime: 0.8 s, 16 kHz mono, 16-bit PCM,\n")
        f.write("// 70 % amplitude. Regenerate with tools/generate_sounds.py.\n")
        f.write("std::vector<unsigned char> aviso_raw = {\n")
        b = b"".join(struct.pack("<h", s) for s in chime)
        for i in range(0, len(b), 12):
            f.write(", ".join(f"0x{x:02x}" for x in b[i:i + 12]) + ",\n")
        f.write("};\n")
    print(f"aviso.h: {len(chime)} samples ({len(chime)/SR:.2f} s)")

    # ---- timer beep: 3 short 880 Hz beeps inside ~812 ms -----------------
    beep = []
    for k in range(3):
        seg = tone_samples([(880.0, 0.18)])
        fade(seg, 80)
        beep += seg
        if k < 2:
            beep += [0] * int(SR * 0.06)             # 60 ms gap
    beep += [0] * (int(SR * 0.812) - len(beep))      # pad to 812 ms
    with wave.open(os.path.join(OUT, "sounds_timer_finished.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", s) for s in beep))
    print("sounds_timer_finished.wav: 812 ms")


if __name__ == "__main__":
    main()
