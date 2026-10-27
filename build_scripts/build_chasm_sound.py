#!/usr/bin/env python
r"""
build_chasm_sound.py -- Surtr's Chasm's cast sound: Tremors' own sound made louder (owner
2026-10-25), written to Sfx\Zsp\SurtrQk.wav, which build_surtrs_chasm_pfs.py names in the spell's
sound list in place of TREMORS.WAV (same length, so the list keeps its size).

Sfx\Zsp\Tremors.wav already peaks near full scale (about -2 dBFS, RMS about -10 dBFS), so plain
gain would clip.  Each sample goes through a soft limiter instead, y = tanh(DRIVE * x) / tanh(DRIVE):
quiet parts rise by up to DRIVE / tanh(DRIVE), and the peaks stay under full scale.  The format,
length and channels are Tremors'.  The file is new (ADDED in re_tools/mod_manifest.py), so it
ships with the mod.

    python build_scripts/build_chasm_sound.py            dry run + state
    python build_scripts/build_chasm_sound.py --apply     write the file
    python build_scripts/build_chasm_sound.py --undo      delete it
"""
import io, math, os, struct, sys, wave
sys.dont_write_bytecode = True
import aowepack_patch as P

SRC = os.path.join(P.GAME, "Sfx", "Zsp", "Tremors.wav")
OUT = os.path.join(P.GAME, "Sfx", "Zsp", "SurtrQk.wav")
DRIVE = 2.2


def build():
    w = wave.open(SRC, "rb")
    ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    if sw != 2:
        sys.exit("ABORT: %s has %d-byte samples" % (SRC, sw))
    norm = math.tanh(DRIVE)
    out = [int(round(32767 * math.tanh(DRIVE * v / 32768.0) / norm))
           for v in struct.unpack("<%dh" % (n * ch), raw)]
    bio = io.BytesIO()
    o = wave.open(bio, "wb")
    o.setnchannels(ch)
    o.setsampwidth(2)
    o.setframerate(rate)
    o.writeframes(struct.pack("<%dh" % len(out), *out))
    o.close()
    rms = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs))
    gain = 20 * math.log10(rms(out) / rms(struct.unpack("<%dh" % (n * ch), raw)))
    return bio.getvalue(), gain


def main():
    if not os.path.isfile(SRC):
        sys.exit("ABORT: missing %s" % SRC)
    want, gain = build()
    have = open(OUT, "rb").read() if os.path.isfile(OUT) else None
    state = "absent" if have is None else "current" if have == want else "DIFFERS"
    print("build_chasm_sound -- %s: %s (%d B, %+.1f dB RMS over Tremors)" % (
        os.path.relpath(OUT, P.GAME), state, len(want), gain))
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
