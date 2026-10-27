#!/usr/bin/env python
r"""
build_flask_sound.py -- the impact sound of Throw Explosive Flask (Dwarven Satchels): a shatter
with a quieter explosion under it (owner 2026-10-25), mixed from two of the game's own sounds into
Sfx\Zatk\FlaskBurst.wav, which build_satchels_pfs.py names as the attack's second sound (the one
TfxHS plays when a missile's path ends, 0x0042A0AE).

    SHATTER    Sfx\Attack\Ice.WAV       Ice Shards' and Grip of Winter's sound, 16-bit stereo 44.1 kHz
    EXPLOSION  Sfx\Attack\Explod1.wav   8-bit mono 16 kHz, resampled (linear) to the shatter's format,
                                        at EXPLOSION_GAIN and EXPLOSION_DELAY after the shatter starts

The output keeps the shatter's format.  Samples are summed and clipped to 16 bits.  The file is new
(ADDED in re_tools/mod_manifest.py), so it ships with the mod.

    python build_scripts/build_flask_sound.py            dry run + state
    python build_scripts/build_flask_sound.py --apply     write the file
    python build_scripts/build_flask_sound.py --undo      delete it
"""
import os, struct, sys, wave
sys.dont_write_bytecode = True
import aowepack_patch as P

SFX = os.path.join(P.GAME, "Sfx")
SHATTER = os.path.join(SFX, "Attack", "Ice.WAV")
EXPLOSION = os.path.join(SFX, "Attack", "Explod1.wav")
OUT = os.path.join(SFX, "Zatk", "FlaskBurst.wav")
SHATTER_GAIN, EXPLOSION_GAIN, EXPLOSION_DELAY = 0.85, 0.45, 0.05


def read(path):
    """-> (rate, channels, [float samples per channel])"""
    w = wave.open(path, "rb")
    ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    if sw == 2:
        vals = [v / 32768.0 for v in struct.unpack("<%dh" % (n * ch), raw)]
    elif sw == 1:
        vals = [(b - 128) / 128.0 for b in raw]
    else:
        sys.exit("ABORT: %s has %d-byte samples" % (path, sw))
    return rate, ch, [vals[c::ch] for c in range(ch)]


def resample(chan, src, dst):
    n = int(len(chan) * dst / src)
    out = []
    for i in range(n):
        x = i * src / dst
        k = int(x)
        a = chan[k]
        b = chan[k + 1] if k + 1 < len(chan) else 0.0
        out.append(a + (b - a) * (x - k))
    return out


def build():
    rate, ch, shatter = read(SHATTER)
    erate, ech, expl = read(EXPLOSION)
    expl = [resample(c, erate, rate) for c in expl]
    while len(expl) < ch:
        expl.append(expl[0])
    lag = int(EXPLOSION_DELAY * rate)
    n = max(len(shatter[0]), lag + len(expl[0]))
    frames = []
    for i in range(n):
        for c in range(ch):
            v = SHATTER_GAIN * (shatter[c][i] if i < len(shatter[c]) else 0.0)
            j = i - lag
            if 0 <= j < len(expl[c]):
                v += EXPLOSION_GAIN * expl[c][j]
            frames.append(max(-32768, min(32767, int(round(v * 32767)))))
    pcm = struct.pack("<%dh" % len(frames), *frames)
    return rate, ch, pcm


def wav_bytes(rate, ch, pcm):
    import io
    bio = io.BytesIO()
    w = wave.open(bio, "wb")
    w.setnchannels(ch)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(pcm)
    w.close()
    return bio.getvalue()


def main():
    for p in (SHATTER, EXPLOSION):
        if not os.path.isfile(p):
            sys.exit("ABORT: missing %s" % p)
    rate, ch, pcm = build()
    want = wav_bytes(rate, ch, pcm)
    have = open(OUT, "rb").read() if os.path.isfile(OUT) else None
    state = "absent" if have is None else "current" if have == want else "DIFFERS"
    print("build_flask_sound -- %s: %s (%d B, %.2f s)" % (
        os.path.relpath(OUT, P.GAME), state, len(want), len(pcm) / (2.0 * ch * rate)))
    if "--apply" in sys.argv and state != "current":
        open(OUT, "wb").write(want)
        print("  WRITTEN")
    elif "--undo" in sys.argv and have is not None:
        os.remove(OUT)
        print("  DELETED")
    elif not ({"--apply", "--undo"} & set(sys.argv)):
        print("\n(dry run -- nothing written)")


if __name__ == "__main__":
    main()
