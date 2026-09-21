"""Annotate the VANILLA Ghidra image with where the LIVE DLL has been patched.

Ghidra holds the pristine AoWEPACK.dpl (see ../Ghidra_Toolchain.md).  That makes it a
clean vanilla reference and ZERO evidence about what is installed -- the recurring, expensive
mistake in this project is reading a vanilla decompile and concluding "X is unpatched".

This script makes the staleness self-announcing.  It derives, from the bytes themselves, every
place the live DLL differs from pristine, attributes each site to the build script that owns it,
and writes a comment there in Ghidra so the warning appears in the decompiler and the listing.

Nothing here is hand-maintained: the site list comes from a live-vs-pristine byte diff and the
attribution from grepping build_scripts/, so it is correct the day a new feature is added.

Usage:
    python ghidra_annots.py                 # dry run: inventory + what would be written
    python ghidra_annots.py --json out.json # dump the inventory as JSON
    python ghidra_annots.py --apply         # write the comments into Ghidra
    python ghidra_annots.py --undo          # remove only the comments this script wrote

Requires the Ghidra MCP plugin serving on 127.0.0.1:8089 with the vanilla program open.
"""
import os
import sys
import re
import json
import struct
import argparse
import urllib.request
import urllib.error

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    _MD = Cs(CS_ARCH_X86, CS_MODE_32)
except ImportError:      # snapping is a nicety; the inventory still works without it
    _MD = None

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(TOOLS, "..", ".."))

LIVE = os.path.join(GAME, "AoWEPACK.dpl")
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")
SCRIPTS = os.path.join(GAME, "Modding Resources", "build_scripts")
SERVER = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")

# every comment we write starts with this, so --undo can find its own work and nothing else
MARKER = "[LIVE-PATCH]"
# differing bytes closer together than this are treated as one site
GAP = 16


# ---------------------------------------------------------------- PE plumbing

def sections(data):
    """[(name, va_start, vsize, file_off, raw_size)] plus the image base."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    out = []
    tbl = pe + 24 + optsz
    for i in range(nsec):
        e = tbl + i * 40
        name = data[e:e + 8].rstrip(b"\0").decode("latin1")
        vsz, va, rsz, ptr = struct.unpack_from("<IIII", data, e + 8)
        out.append((name, base + va, vsz, ptr, rsz))
    return base, out


def off_to_va(secs, off):
    """File offset -> VA.  Per-section: a flat delta is wrong outside CODE."""
    for name, va, vsz, ptr, rsz in secs:
        if ptr <= off < ptr + rsz:
            return va + (off - ptr), name
    return None, "?"


def va_to_off(secs, va):
    for name, sva, vsz, ptr, rsz in secs:
        if sva <= va < sva + max(vsz, rsz):
            return ptr + (va - sva)
    return None


def snap_to_instruction(pris, secs, va):
    """Move `va` back to the start of the instruction containing it.

    A diff run begins at the first byte that DIFFERS, which is usually an immediate
    operand in the middle of an instruction -- e.g. the road cost lives at 0x557710F5,
    inside `sub eax,0xa` at 0x557710F3.  Ghidra only renders a comment at a code-unit
    boundary, so an unsnapped address means a comment that silently never appears.

    x86 has no way to decode backwards, so this decodes forward from several different
    lead-ins and takes the most common answer; a wrong lead-in desyncs but the wrong
    alignments rarely agree with each other.
    """
    off = va_to_off(secs, va)
    if off is None or _MD is None:
        return va
    votes = {}
    for lead in (6, 10, 14, 20, 28, 40, 56):
        start = off - lead
        if start < 0:
            continue
        for ins in _MD.disasm(pris[start:off + 16], va - lead):
            if ins.address <= va < ins.address + ins.size:
                votes[ins.address] = votes.get(ins.address, 0) + 1
                break
            if ins.address > va:
                break
    if not votes:
        return va
    return max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0]


# ---------------------------------------------------------------- the diff

def diff_runs(live, pris):
    """Contiguous-ish runs where the two files disagree, as (start_off, end_off)."""
    runs = []
    i, n = 0, min(len(live), len(pris))
    while i < n:
        if live[i] != pris[i]:
            end, gap, k = i, 0, i
            while k < n and gap < GAP:
                if live[k] != pris[k]:
                    end, gap = k, 0
                else:
                    gap += 1
                k += 1
            runs.append((i, end))
            i = end + 1
        else:
            i += 1
    return runs


def build_sites():
    """Every live-vs-pristine difference that has a vanilla counterpart, attributed."""
    for path in (LIVE, PRISTINE):
        if not os.path.exists(path):
            sys.exit(f"missing: {path}")
    live = open(LIVE, "rb").read()
    pris = open(PRISTINE, "rb").read()
    _, secs = sections(pris)

    owners = script_index()
    sites, caves = [], 0
    for a, b in diff_runs(live, pris):
        va, sec = off_to_va(secs, a)
        if va is None:
            continue
        length = b - a + 1
        # A run whose PRISTINE bytes are all zero is cave space -- it is not code in
        # vanilla, so there is nothing in Ghidra to annotate.
        if not any(pris[a:b + 1]):
            caves += 1
            continue
        anchor = snap_to_instruction(pris, secs, va) if sec == "CODE" else va
        sites.append({
            "va": anchor,          # where the comment goes: an instruction boundary
            "diff_va": va,         # where the bytes actually start differing
            "section": sec,
            "length": length,
            "pristine": pris[a:a + min(length, 8)].hex(" "),
            "live": live[a:a + min(length, 8)].hex(" "),
            "owners": attribute(va, length, owners),
        })

    # Two nearby runs can snap onto the same instruction; one address takes one comment,
    # so merge them rather than letting the second silently overwrite the first.
    merged = {}
    for s in sites:
        prev = merged.get(s["va"])
        if prev is None:
            merged[s["va"]] = s
        else:
            prev["length"] += s["length"]
            prev["owners"] = sorted(set(prev["owners"]) | set(s["owners"]))
            prev["merged"] = prev.get("merged", 1) + 1
    return sorted(merged.values(), key=lambda s: s["va"]), caves


# ---------------------------------------------------------------- attribution

VA_RE = re.compile(r"\b(?:0x)?(55[0-9A-Fa-f]{6})\b")
OFF_RE = re.compile(r"\b0x([0-9A-Fa-f]{4,6})\b")
SKIP_DIRS = {"backups", "AoW1 Modding", "idr", "__pycache__", ".git"}
DOC_EXT = (".md", ".txt", ".py")


def script_index():
    """{VA: {source names}} for every address a project file names.

    Two literal forms are indexed, because scripts and docs disagree about which they use:
      * a VA        (`0x557710F3`, or bare `557710F3` in prose)
      * a FILE OFFSET (`0x704F3`) -- resolved through the PE section table, since the
        VA->offset delta is per-section (CODE +0x55700C00, DATA +0x55701200).
    A file-offset literal that happens to mean something else is harmless: it only
    matters if it also lands inside a diff run, which is a narrow coincidence.
    """
    idx = {}
    if not os.path.exists(PRISTINE):
        return idx
    _, secs = sections(open(PRISTINE, "rb").read())
    root = os.path.join(GAME, "Modding Resources")

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(DOC_EXT):
                continue
            # Only build_scripts/ .py files are patch authors.  Indexing re_tools/ would
            # make this script attribute sites to its own docstring.
            if fn.endswith(".py") and os.path.basename(dirpath) == "re_tools":
                continue
            try:
                text = open(os.path.join(dirpath, fn), "r",
                            encoding="utf8", errors="replace").read()
            except OSError:
                continue
            for m in VA_RE.finditer(text):
                idx.setdefault(int(m.group(1), 16), set()).add(fn)
            for m in OFF_RE.finditer(text):
                va, sec = off_to_va(secs, int(m.group(1), 16))
                if va is not None:
                    idx.setdefault(va, set()).add(fn)
    return idx


def attribute(va, length, owners):
    """Scripts naming any address in (or just around) this run.

    Hooks are usually referenced by the exact site address, but a script may cite the
    instruction before or the resume point after, so allow a small window.
    """
    hits = set()
    for probe in range(va - GAP, va + length + GAP):
        if probe in owners:
            hits |= owners[probe]
    return sorted(hits)


# ---------------------------------------------------------------- Ghidra I/O

def request(path, payload=None, timeout=120):
    url = f"{SERVER}/{path.lstrip('/')}"
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf8"),
            headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf8", "replace")
    except urllib.error.URLError as e:
        sys.exit(f"Ghidra MCP not reachable at {SERVER} ({e}).\n"
                 f"Start Ghidra, open the vanilla program, enable the GhidraMCP plugin.")


def check_program():
    """Refuse to write into anything that is not the vanilla AoWEPACK image."""
    meta = request("get_metadata")
    name = ""
    for line in meta.splitlines():
        if line.startswith("Program Name:"):
            name = line.split(":", 1)[1].strip()
    if "AoWEPACK" not in name:
        sys.exit(f"open program is '{name}', not an AoWEPACK image -- refusing to write")
    if "Base Address: 55700000" not in meta:
        sys.exit("open program is not based at 55700000 -- refusing to write")
    return name


def owner_label(site):
    """Who to blame, shortest useful form.

    A build script is authoritative (it wrote the bytes); a doc is second best.  Sites
    named by neither are almost always pre-project Ziggurat changes -- they predate the
    recording convention -- and those are the ones a reader is most likely to be misled by,
    so say so plainly rather than leaving it blank.
    """
    scripts = [o for o in site["owners"] if o.endswith(".py")]
    docs = [o for o in site["owners"] if not o.endswith(".py")]
    picked = scripts or docs
    if not picked:
        # Ziggurat was hex-edited by hand 2020-2025, before the script+doc convention, so a
        # site with no paper trail is expected rather than missing.  The author is the user:
        # ask, do not reverse-engineer the intent.
        return "Ziggurat hand edit (2020-25, no script/doc by design) - ask the author"
    shown = ", ".join(picked[:2])
    if len(picked) > 2:
        shown += f" (+{len(picked) - 2} more)"
    return shown


def comment_for(site):
    # "named in" not "patched by": grep proves a file MENTIONS this address, which is
    # strong evidence but not authorship -- another modder's reference script may cite
    # a site this project never touched.
    return (f"{MARKER} live DLL differs here ({site['length']}B): "
            f"{site['pristine']} -> {site['live']} | named in: {owner_label(site)} | "
            f"VANILLA SHOWN - verify with re_tools/dasm.py AoWEPACK.dpl "
            f"{site['va']:08X} {site['length']:#x}")


def push(sites, clear=False):
    dec, dis = [], []
    for s in sites:
        text = "" if clear else comment_for(s)
        addr = f"{s['va']:08X}"
        dec.append({"address": addr, "comment": text})
        dis.append({"address": addr, "comment": text})
    # chunked: one 400-site POST would blow the endpoint's timeout budget
    done = 0
    for i in range(0, len(dec), 50):
        request("batch_set_comments", {
            "decompiler_comments": dec[i:i + 50],
            "disassembly_comments": dis[i:i + 50],
        })
        done += len(dec[i:i + 50])
        print(f"  ...{done}/{len(dec)}")
    return done


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the comments into Ghidra")
    ap.add_argument("--undo", action="store_true", help="clear the comments this script wrote")
    ap.add_argument("--json", metavar="FILE", help="dump the site inventory as JSON")
    ap.add_argument("--limit", type=int, default=25, help="rows to print in the dry-run table")
    args = ap.parse_args()

    sites, caves = build_sites()
    scripted = [s for s in sites if any(o.endswith(".py") for o in s["owners"])]
    doc_only = [s for s in sites if s["owners"] and not any(o.endswith(".py") for o in s["owners"])]
    orphans = [s for s in sites if not s["owners"]]

    print(f"live vs pristine: {len(sites)} patched sites with a vanilla counterpart "
          f"({caves} cave runs skipped -- no vanilla code there)")
    print(f"  owned by a build script:  {len(scripted)}")
    print(f"  named only by a doc:      {len(doc_only)}")
    print(f"  named by NEITHER:         {len(orphans)}   <- undocumented / pre-project")
    by_script = {}
    for s in sites:
        for o in s["owners"]:
            if o.endswith(".py"):
                by_script[o] = by_script.get(o, 0) + 1
    print(f"  distinct owning scripts:  {len(by_script)}")

    if args.json:
        with open(args.json, "w", encoding="utf8") as f:
            json.dump({"sites": sites, "caves_skipped": caves}, f, indent=1)
        print(f"wrote {args.json}")

    if not (args.apply or args.undo):
        print(f"\n-- first {args.limit} sites --")
        for s in sites[:args.limit]:
            who = ", ".join(s["owners"]) or "(unattributed)"
            print(f"  {s['va']:08X} [{s['section']}] {s['length']:4d}B  {who}")
        print("\n-- top owners --")
        for name, n in sorted(by_script.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {n:4d}  {name}")
        print("\ndry run -- nothing written.  Use --apply to annotate Ghidra.")
        return

    name = check_program()
    print(f"\nprogram: {name}")
    if args.undo:
        print(f"clearing {len(sites)} comments...")
        print(f"cleared {push(sites, clear=True)}")
    else:
        print(f"writing {len(sites)} comments...")
        print(f"wrote {push(sites)}")
        print("Remember to save the program in Ghidra (File > Save).")


if __name__ == "__main__":
    main()
