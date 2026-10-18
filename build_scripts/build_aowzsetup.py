#!/usr/bin/env python
r"""
build_aowzsetup.py -- builds Ziggurat\AoWzSetup.exe, the settings program and launcher that replaces
AoWSetup.exe (owner, 2026-10-18).  Source: Modding Resources\AoWzSetup\AoWzSetup.cs.

Compiled with the .NET Framework 4 C# compiler that ships with Windows
(%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe), x86, WinForms.  No new dependency for players:
.NET Framework 4.8 is part of Windows 10 and 11.

LOOK (owner, 2026-10-18: "the same artistic elements as AoWSetup")
    Taken at build time from the VANILLA root files and embedded as resources: TLoaderForm's
    MainImage (398x449 BMP, DFM Picture.Data) -> main.bmp, AoWSetup.exe's icon -> setup.ico (also the
    exe icon), startbtn.wav (AoWSetup plays <exe dir>\startbtn.wav on Play!; Ziggurat never had a
    copy, so the Ziggurat AoWSetup was silent).  Home = borderless MainImage with the four flat bold
    buttons at AoWSetup's DFM rectangles (y 416); Settings = AoWSetup's two-tab dialog at its DFM
    coordinates, Window Zoom in the row Language used.  Scaled for DPI.

WHAT IT REPLACES (AoWSetup.exe TLoaderForm, read 2026-10-18; Zig notes/07-ui.md §22)
    Every AoWSetup setting, same registry values and encodings under
    HKCU\Software\Triumph Studios\Age of Wonders Z, plus Video\"Window Zoom" (build_window_zoom.py):
    Video mode (Window = Display Mode 0 at 640x480, else 1 + size; sizes from the same 16-bit
    DirectDraw enumeration), Allow Resolution Switches, Sound Quality (0-3, default 3), Use
    DirectSound, Detail Level (Workspace, 0-2, default 2), Skip Intro, Auto Save (default 1),
    Log Token Events, Auto Debug Save, Startup Directory, SMTP Server, Attachment Directory
    (trailing backslash added, as AoWSetup does), Local Email Address.
    Left out: Language (AoWSetup's list holds only "English") and Debug Mode (AoWSetup shows it
    but never writes it).  Play / Editor save, then start AoWz.exe / AoWzEd.exe from the setup's
    own folder (AoWSetup started Root Directory\AoWz.exe and a nonexistent aowed.exe).

USAGE
    python build_aowzsetup.py           compile into Modding Resources\AoWzSetup\ (dry run)
    python build_aowzsetup.py --apply   compile to Ziggurat\AoWzSetup.exe
    python build_aowzsetup.py --undo    delete Ziggurat\AoWzSetup.exe
"""
import os, sys, struct, subprocess
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
assert os.path.isdir(os.path.join(GAME, "Release")), "GAME does not look like the Ziggurat folder"
SRC_DIR = os.path.join(GAME, "Modding Resources", "AoWzSetup")
SRC = os.path.join(SRC_DIR, "AoWzSetup.cs")
ICO = os.path.join(SRC_DIR, "AoWzSetup.ico")
BMP = os.path.join(SRC_DIR, "main.bmp")
WAV = os.path.join(SRC_DIR, "startbtn.wav")
ROOT = os.path.dirname(GAME)                 # the vanilla install: AoWSetup.exe, startbtn.wav
TARGET = os.path.join(GAME, "AoWzSetup.exe")
CSC = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "Framework", "v4.0.30319", "csc.exe")


def extract_icon(exe, out):
    """First RT_GROUP_ICON of exe -> .ico file."""
    import pefile
    pe = pefile.PE(exe)
    groups, icons = None, {}
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id == 14 and groups is None:
            groups = t.directory.entries[0].directory.entries[0].data.struct
        if t.id == 3:
            for e in t.directory.entries:
                icons[e.id] = e.directory.entries[0].data.struct
    assert groups is not None, "no icon group in %s" % exe
    grp = pe.get_data(groups.OffsetToData, groups.Size)
    _r, _t, count = struct.unpack_from("<HHH", grp, 0)
    entries, blobs = [], []
    for i in range(count):
        w, h, cc, r, planes, bpp, size, nid = struct.unpack_from("<BBBBHHIH", grp, 6 + 14 * i)
        blob = pe.get_data(icons[nid].OffsetToData, icons[nid].Size)
        entries.append((w, h, cc, r, planes, bpp, len(blob)))
        blobs.append(blob)
    off = 6 + 16 * count
    head = struct.pack("<HHH", 0, 1, count)
    for (w, h, cc, r, planes, bpp, size), blob in zip(entries, blobs):
        head += struct.pack("<BBBBHHII", w, h, cc, r, planes, bpp, size, off)
        off += size
    open(out, "wb").write(head + b"".join(blobs))


def extract_main_image(exe, out):
    """TLoaderForm's MainImage bitmap from the DFM: Picture.Data = vaBinary(len) + 'TBitmap' + size + BMP."""
    d = open(exe, "rb").read()
    form = d.find(b"TPF0\x0bTLoaderForm")
    assert form > 0, "TLoaderForm DFM not found in %s" % exe
    obj = d.find(b"\x09MainImage", form)
    prop = d.find(b"\x0cPicture.Data\x0a", obj)
    assert 0 < obj < prop < obj + 200, "MainImage Picture.Data not where expected"
    o = prop + len(b"\x0cPicture.Data\x0a")
    n = struct.unpack_from("<I", d, o)[0]
    blob = d[o + 4:o + 4 + n]
    assert blob[:8] == b"\x07TBitmap", "Picture.Data is not a TBitmap"
    size = struct.unpack_from("<I", blob, 8)[0]
    bmp = blob[12:12 + size]
    assert bmp[:2] == b"BM", "no BMP header"
    w, h = struct.unpack_from("<ii", bmp, 18)
    assert w == 398 and abs(h) >= 449, "MainImage is %dx%d, expected 398x449 or taller" % (w, h)
    open(out, "wb").write(bmp)


def compile_to(out):
    # AoWSetup's own look: its icon, MainImage and Play! sound, from the VANILLA files in the game
    # root (the Ziggurat copy of AoWSetup.exe is withheld from releases and may be absent).
    van_setup = os.path.join(ROOT, "AoWSetup.exe")
    extract_icon(van_setup, ICO)
    extract_main_image(van_setup, BMP)
    import shutil
    shutil.copyfile(os.path.join(ROOT, "startbtn.wav"), WAV)
    cmd = [CSC, "/nologo", "/target:winexe", "/platform:x86", "/optimize+", "/out:" + out,
           "/win32icon:" + ICO, "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
           "/resource:%s,main.bmp" % BMP, "/resource:%s,setup.ico" % ICO,
           "/resource:%s,startbtn.wav" % WAV, SRC]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    for f in (ICO, BMP, WAV):                # extracted vanilla assets: embedded now, not kept
        os.remove(f)
    if r.returncode != 0:
        sys.exit("ABORT: csc failed")
    print("  built %s (%d B)" % (out, os.path.getsize(out)))


def main():
    print("build_aowzsetup")
    if "--undo" in sys.argv:
        if os.path.exists(TARGET):
            os.remove(TARGET)
            print("  removed %s" % TARGET)
        else:
            print("  nothing to remove")
        return
    if "--apply" in sys.argv:
        compile_to(TARGET)
    else:
        compile_to(os.path.join(SRC_DIR, "AoWzSetup.dryrun.exe"))
        print("\n(dry run -- Ziggurat\\AoWzSetup.exe not written)")


if __name__ == "__main__":
    main()
