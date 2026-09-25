# -*- coding: utf-8 -*-
"""ability_names.py — resolve ability id -> display name for AoW1.

    from ability_names import names
    names()          # {id: "Marksmanship", ...}

The game stores no ability-name table a player could read: names are Delphi resourcestrings in
AoWEPACK.dpl, bound to ids at registration. Three layers, most-specific first, all measured
2026-08-08 against 109 ids that appear across every unit's four ability owners in Unitres.pfs:

1. `herodlg_cats.ABILITY_CATS` — 100 ids, already curated + screenshot-verified for the hero
   level-up dialog. Reused rather than re-derived.
2. Constructor scan — an ability class sets its id with `mov dword ptr [reg+0xC], imm`; the
   enclosing exported symbol (`AoWE.TTransportAbility.Create`) yields the name. This is what
   named the two the curated map missed: 0x32 TTransportAbility -> Transport, 0x3c
   TDispelMagicAbility -> Dispel Magic. It is the authoritative source and could stand alone,
   but is slower and its names are class-derived ("Dispel Magic" from TDispelMagicAbility), so
   the curated map wins where both have an entry.
3. MODDED — ids this project added, which have no vanilla class: Path of Sand 0x9F, Assassin
   0x38, Magebane 0xAA, Drillmaster 0xAB, the four caster_cost abilities 0xAC–0xAF, Shield
   0xB0 and Reforming Flesh 0xB1.
   Kept here so the map is complete on the installed game. ⚠ An id registered by the DLL but
   missing here prints as `?`; re-check this table whenever a new ability ships. Shield 0xB0
   shipped 2026-08-27 and was missed here until 2026-08-31, so it printed as `?` for four
   days — the check is only as good as the habit of running it.

⚠ **A `T<Name>.Create` symbol is not proof of an ability class.** The constructor scan is gated on
the ctor transitively chaining to `TAbility.Create` (`_ability_ctors`), because `TAISavingsBudget`
writes `[reg+0xC] = 0x96` — a budget figure, not an ability id — and its symbol matches the same
pattern. Ungated, id 0x96 published as "AISavings Budget" and shipped into the manual's ability
picker as a selectable ability; the real owner is `TDominatedAbility`, and Ability.pfs record 160
confirms it ("The unit mindlessly obeys the orders of another"). Fixed 2026-08-09. When an id has
two candidate ctors, the one that reaches `TAbility.Create` is the ability.

Every name a player sees on the abilities display comes through here; getting one wrong ships a
mislabelled ability to every reader, so the constructor scan (ground truth) backstops the rest.
"""
import os, sys, struct, re, bisect, importlib.util

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
DLL_BASE = 0x55700000

# ⚠ This module `import aowsyms` (its sibling), which only resolves when re_tools happens to be
# sys.path[0] -- i.e. when run FROM this directory. Loaded by file path from elsewhere, as
# build_ziggurat_manual.py does, the import failed, both DLL scans were skipped, and `levels()`
# quietly returned its hard-coded fallback: the manual's "read off the live DLL" claim was true
# only when the CLI ran it. Caught 2026-08-09 when a second caller made the warning visible.
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

# ids added by this project — no vanilla ability class carries them
MODDED = {0x9F: "Path of Sand", 0x38: "Assassin", 0xAB: "Drillmaster",
          0xAA: "Magebane",
          # caster_cost, confirmed 2026-08-27 -- each halves one spell family's casting cost
          0xAC: "Evoker", 0xAD: "Conjurer", 0xAE: "Enchanter", 0xAF: "Ritualist",
          # facing/Shield, confirmed working 2026-08-27 -- build_shield.py
          0xB0: "Shield",
          # build_reformingflesh.py, applied 2026-08-31 -- +5 HP at the start of every
          # combat round, clamped at max HP. UNTESTED in game.
          0xB1: "Reforming Flesh",
          # build_embrittle.py, applied 2026-09-01 -- the combat status the Embrittlement
          # spell (id 109) applies: the unit takes DOUBLE physical damage until the battle
          # ends. A TSlowEnchantmentAbility instance with its id poked, so the constructor
          # scan sees only Slow's own 0x84 and cannot reach this. UNTESTED in game.
          0xB2: "Embrittled",
          # build_turnundead_evilcommand.py, applied 2026-09-01 -- an evil Turn Undead user
          # SEIZES the undead instead of damaging it. 0x88 is the hidden controller (a
          # TCommandAbility instance, the caster gains the bit so the revert-on-death
          # ownership gates pass); 0x89 is the commanded status on the seized unit (a
          # TCommandedAbility instance, the sibling of Seduced/Dominated/Charmed).
          # ⚠ BOTH ARE VANILLA GAPS BELOW 170 ON PURPOSE, not new ids at the top: a
          # TTouchAbility descendant at id >= 170 is SELECTABLE (GetControlType & 2) and hits
          # `bound eax, qword ptr [0x4288a8]` at AoWTCPCK.dpl 0x004280D7 -- see ID_Ceilings.md's
          # forward hazard. ⚠ AoWTCPCK.dpl, NOT AoW.exe: the two share the 0x00400000 image base
          # but only AoWTCPCK was compiled with range checks, and AoW.exe has no real BOUND at
          # all. Because both ids are below 0xAA they change neither ceiling LADDER. Both are
          # instance clones with their id poked, so the constructor scan cannot reach them.
          # 0x88 is VISIBLE on the caster's in-combat panel by user ruling 2026-09-01, hence
          # the "Can " prefix. UNTESTED in game.
          # 0x89 was "Turned" until the user ruled it collides with vanilla 0x22
          # "Turned Undead" (Turn Undead's own panic status), which can sit in the same
          # unit's list in the same battle.
          0x88: "Can Command Undead", 0x89: "Commanded Undead",
          # build_weakness.py, applied 2026-09-25 -- the inverse of the Protections: x1.5
          # damage and -4 on the effect Resistance check. UNTESTED in game.
          0xB3: "Fire Weakness", 0xB4: "Cold Weakness", 0xB5: "Lightning Weakness",
          0xB6: "Magic Weakness", 0xB7: "Poison Weakness", 0xB8: "Death Weakness",
          0xB9: "Holy Weakness",
          # build_liquidbody.py, applied 2026-09-25 -- Swimming + Physical Protection + no
          # Burning, as a plain passive for units. UNTESTED in game.
          0xBA: "Liquid Body",
          # build_command_bond.py, applied 2026-09-25 -- the bond on a seized unit and the
          # commander's per-thrall Resistance cost. UNTESTED in game.
          0xBB: "Bound",
          0xBC: "Commanding"}

# Vanilla ids the constructor scan cannot reach cleanly (set via movement-type tables or a
# shared enhancement path, not a T<Name>Ability.Create). Sourced from Investigation_Combat.md
# §"Enhancement" (TrailOfDarkness 0x1A, Dragon 0x3F) and the DLL's own SailingRStr export
# (0x17, carried only by ships). Verified against carriers: 0x17 on Air Galley/Dragon Ship/Cog,
# 0x3F on Beholder/Sandworm/Glacier Drake.
DOC_NAMES = {0x17: "Sailing", 0x1A: "Trail of Darkness", 0x3F: "Dragon"}

# Names confirmed from what the GAME ACTUALLY DISPLAYS (the hero level-up dialog), where that
# differs from every derivable source. These win over everything else - a player recognises the
# string on screen, not the one in the binary.
#   0x39 the game's Ranged column reads "Shoot Bolt"; there is no ShootQuarrel/ShootBolt
#        resourcestring at all (it is a ranged attack, not a registered passive), so the
#        curated map's "Shoot Quarrel" was a guess. Author-confirmed 2026-08-08.
#   0x8B the DLL resourcestring says "Underground Concealment" but the dialog shows
#        "Cave Concealment" - the one id where the string table and the screen disagree.
#   0x92 the curated map's "Evil Slaying" is a description of the EFFECT, not the name. The class
#   0x93 is THolyChampionAbility / TUnholyChampionAbility and the author confirms the game shows
#        "Holy Champion" / "Unholy Champion" (2026-08-09). ⚠ Keep these distinct from 0xA0/0xA1,
#        THolyChampionEnchantment / TUnholyChampionEnchantment: same effect and same description
#        text, but 0x92/0x93 are the hero-buyable skill (Ability.pfs tag 6 = 12 points) while
#        0xA0/0xA1 are the spell-applied enchantment with no purchase cost. Both must stay
#        separately selectable in the editor, so the enchantments keep the longer name.
DISPLAY_OVERRIDES = {0x39: "Shoot Bolt", 0x8B: "Cave Concealment",
                     0x92: "Holy Champion", 0x93: "Unholy Champion"}

# a handful of class-derived names read better spelled out than as the class stem
CLASS_NAME_FIX = {
    "TransportAbility": "Transport", "DispelMagicAbility": "Dispel Magic",
    "SuicidalAbility": "Suicidal", "SailingAbility": "Sailing",
}


def _curated():
    spec = importlib.util.spec_from_file_location(
        "herodlg_cats", os.path.join(TOOLS, "..", "build_scripts", "herodlg_cats.py"))
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
    return {aid: lbl for aid, (_cat, lbl) in hc.ABILITY_CATS.items()}


def _sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s, out = pe + 24 + opt, []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, s + 8)
        out.append((va, max(vs, rs), raw)); s += 40
    return out


TABILITY_CTOR = 0x5574E5F4                # AoWE.TAbility.Create — the root every ability chains to


def _ability_ctors(d, syms, off2va):
    """{function start VA} for every ctor that transitively chains to `TAbility.Create`.

    ⚠ Without this gate the scan below names ids after classes that are not abilities at all.
    `TAISavingsBudget.Create` writes `[reg+0xC] = 0x96` — a budget figure, not an ability id — and
    the symbol matches `T<Name>.Create`, so id 0x96 was published as "AISavings Budget" instead of
    **Dominated** (`TDominatedAbility`, which writes the same id and IS an ability). The bogus name
    then shipped into the manual's ability picker as a selectable ability. Measured 2026-08-09.

    Edges are ctor->ctor only, for the reason recorded in levels(): reachability over arbitrary
    calls is far too permissive. `TAbility.Create` itself is the root, not a member.
    """
    callers = {}
    for o in range(len(d) - 5):
        if d[o] != 0xE8:
            continue
        va = off2va(o)
        if va is None:
            continue
        f = _enclosing_sym(va, syms)
        tgt = (va + 5 + struct.unpack_from("<i", d, o + 1)[0]) & 0xFFFFFFFF
        if f and f[1].endswith(".Create") and syms.get(tgt, "").endswith(".Create"):
            callers.setdefault(tgt, set()).add(f[0])
    out, queue = set(), [TABILITY_CTOR]
    while queue:
        for c in callers.get(queue.pop(), ()):
            if c not in out:
                out.add(c); queue.append(c)
    return out


_SYM_ORDER = None


def _enclosing_sym(va, syms):
    """(start, name) of the exported symbol containing va."""
    global _SYM_ORDER
    if _SYM_ORDER is None or _SYM_ORDER[2] is not syms:
        order = sorted(syms.items())
        _SYM_ORDER = (order, [v for v, _ in order], syms)
    order, vas, _ = _SYM_ORDER
    i = bisect.bisect_right(vas, va) - 1
    return order[i] if i >= 0 else None


def _from_constructors():
    """{id: name} for every `mov dword ptr [reg+0xC], id` inside a real ability class's Create."""
    import aowsyms
    _pe, _base, syms, _iat = aowsyms.get_symbols("AoWEPACK.dpl")
    d = open(DLL, "rb").read()
    secs = _sections(d)

    def off2va(o):
        for va, sz, raw in secs:
            if raw <= o < raw + sz:
                return DLL_BASE + va + (o - raw)

    order = sorted(syms.items())
    vas = [v for v, _ in order]

    def enclosing(va):
        i = bisect.bisect_right(vas, va) - 1
        return order[i][1] if i >= 0 else ""

    real = _ability_ctors(d, syms, off2va)
    out = {}
    # C7 /0 with modrm [reg+disp8]=0x0C : opcodes 0x40 0x41 0x42 0x43 0x46 0x47 (skip 44/45 = SIB/disp)
    for modrm in (0x40, 0x41, 0x42, 0x43, 0x46, 0x47):
        pat = bytes([0xC7, modrm, 0x0C])
        o = -1
        while True:
            o = d.find(pat, o + 1)
            if o < 0:
                break
            aid = struct.unpack_from("<I", d, o + 3)[0]
            if aid > 0x200:
                continue
            va = off2va(o)
            if va is None:
                continue
            f = _enclosing_sym(va, syms)
            if not f or f[0] not in real:      # not a class that chains to TAbility.Create
                continue
            sym = enclosing(va)
            m = re.search(r"\.T(\w+?)(?:Ability)?\.Create$", sym)
            if not m:
                continue
            stem = m.group(1)
            name = CLASS_NAME_FIX.get(stem + "Ability") or CLASS_NAME_FIX.get(stem) \
                or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem)
            out.setdefault(aid, name)
    return out


def _from_resourcestrings():
    """{id: display text} read from the DLL's own RT_STRING table - the authoritative names.

    `PassiveAb.RegisterPassiveAbilities` loads each name with `mov eax,[<RStr global>]` ->
    `LoadResString` shortly before `mov eax,<id>` -> `CreateEnhancementAbility`. The global
    points at a Delphi `TResStringRec` {Module, Identifier}; Identifier indexes RT_STRING as
    block `(id>>4)+1`, entry `id&15`. That yields the exact string a player sees - it is how
    `True Seeing` was recovered where both the curated map ("True Sight") and the export symbol
    name (`TrueVisionRStr`) were wrong. Covers the 21 registered passives.
    """
    import aowsyms
    _pe, _base, syms, _iat = aowsyms.get_symbols("AoWEPACK.dpl")
    d = open(DLL, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s, secs = pe + 24 + opt, []
    for _ in range(nsec):
        nm = d[s:s + 8].rstrip(b"\0").decode(errors="replace")
        vs, va, rs, raw = struct.unpack_from("<IIII", d, s + 8)
        secs.append((nm, va, max(vs, rs), raw)); s += 40

    def va2off(va):
        for _nm, v, sz, raw in secs:
            if v <= va - DLL_BASE < v + sz:
                return raw + (va - DLL_BASE - v)

    def off2va(o):
        for _nm, v, sz, raw in secs:
            if raw <= o < raw + sz:
                return DLL_BASE + v + (o - raw)

    rs = [x for x in secs if x[0] == ".rsrc"]
    if not rs:
        return {}
    RVA, RAW = rs[0][1], rs[0][3]

    def roff(rva):
        return RAW + (rva - RVA)

    def entries(dr):
        o = roff(dr)
        nn, ni = struct.unpack_from("<HH", d, o + 12)
        return [struct.unpack_from("<II", d, o + 16 + 8 * i) for i in range(nn + ni)]

    strdirs = [v & 0x7FFFFFFF for nm, v in entries(RVA)
               if not (nm & 0x80000000) and nm == 6]
    if not strdirs:
        return {}
    tables = {}
    for nm, val in entries(RVA + strdirs[0]):
        langs = entries(RVA + (val & 0x7FFFFFFF))
        de = roff(RVA + (langs[0][1] & 0x7FFFFFFF))
        tables[nm] = struct.unpack_from("<II", d, de)

    def resstring(ident):
        blk, idx = (ident >> 4) + 1, ident & 15
        if blk not in tables:
            return None
        p = roff(tables[blk][0])
        for i in range(16):
            ln = struct.unpack_from("<H", d, p)[0]; p += 2
            t = d[p:p + 2 * ln].decode("utf-16le", "replace"); p += 2 * ln
            if i == idx:
                return t

    rstr_text = {}
    for va, nm in syms.items():
        if not nm.endswith("RStr"):
            continue
        o = va2off(va)
        if o is None:
            continue
        _mod, ident = struct.unpack_from("<II", d, o)
        t = resstring(ident)
        if t:
            rstr_text[va] = t

    out = {}
    for i in range(len(d) - 40):
        if d[i] != 0xE8:
            continue
        va = off2va(i)
        if va is None:
            continue
        if ((va + 5 + struct.unpack_from("<i", d, i + 1)[0]) & 0xFFFFFFFF) != CREATE_ENH:
            continue
        aid = txt = None
        for k in range(i - 1, max(i - 60, 0), -1):
            if aid is None and d[k] == 0xB8:
                v = struct.unpack_from("<I", d, k + 1)[0]
                if v < 0x200:
                    aid = v
            if txt is None and d[k] == 0xA1:
                g = struct.unpack_from("<I", d, k + 1)[0]
                o2 = va2off(g)
                if o2 is not None:
                    tgt = struct.unpack_from("<I", d, o2)[0]
                    if tgt in rstr_text:
                        txt = rstr_text[tgt]
            if aid is not None and txt:
                break
        if aid is not None and txt:
            out.setdefault(aid, txt)
    return out


CREATE_ENH = 0x5576601C

# TMultiLevelAbility.Create — every levelled ability chains through it, and it seeds the cap
# `[self+0x28] = 4` at 0x55765192. A subclass ctor that wants a different ceiling overwrites
# that slot itself (Leadership 4, SpellCasting 5, Transport 7); one that doesn't keeps the 4.
MULTILEVEL_CTOR = 0x55765168
MULTILEVEL_DEFAULT_CAP = 4
_LEVELS_CACHE = {}

# The pristine pre-modding DLL, for "what did vanilla cap this at" comparisons. Kept as a named
# constant because it is the only vanilla code reference this project has -- `Release - Vanilla/`
# holds data files only, so a cap question cannot be answered from there.
VANILLA_DLL = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")


def levels(dll=None):
    """{ability id: max level} for every LEVELLED ability, read from the live DLL.

    `CanExpand` is the authority: it answers "may this ability go up another level", so whatever
    it compares the current level against IS the ceiling. Two families, and BOTH must be handled
    or the answer is half a list:

    1. `TMultiLevelAbility` descendants — `CanExpand` is `SETL` on `level < [self+0x28]`, and
       `[+0x28]` is a plain immediate in the ctor (`Investigation_Abilities_Leadership.md`).
       The base ctor seeds 4; Leadership/SpellCasting/Transport override it.
    2. Classes that are levelled WITHOUT being TMultiLevelAbility — `TTurnUndeadAbility` and
       `TDispelMagicAbility` descend from `TTouchAbility : TAbility` and hard-code the ceiling
       as `call [reg+0x70]` (GetLevel, VMT +0x70) then `cmp eax, imm; jl`. Turn Undead 4,
       Dispel Magic 3. Chasing only family 1 silently drops both.

    Reading the INSTALLED DLL rather than a table is the point: Leadership's vanilla ctor caps
    at 1 and this project raised it to 4, so a hard-coded map would be wrong the moment a cap is
    re-tuned. Cross-checked against `Release/Unitres.pfs` — every cap here is >= the highest
    level the shipped data actually assigns.

    ⚠ Not every id with a `0x32+id` record in an ability owner is levelled: Walking (0x00) has
    no level at all, and the one owner carrying tag 0x32 stores something else there. Trust this
    scan, not the presence of a record.

    ⚠ The ctor chain is TRANSITIVE and the bounds must be a real function, not a byte window. A
    ±256B window around the id write both misses `TTurnUndeadAbility.Create` (it reaches the
    base only via `TTouchAbility.Create`) and invents a levelled Cosmetic Surgery out of a
    neighbouring function's bytes. The DLL exports 10,036 symbols, so bounds are free — use them.
    """
    dll = dll or DLL
    if dll in _LEVELS_CACHE:
        return dict(_LEVELS_CACHE[dll])
    import aowsyms
    # Symbols come from the LIVE package: `.edata` is untouched by this project's patches, and the
    # pristine and live images share their symbol layout, so the same table names both.
    _pe, _base, syms, _iat = aowsyms.get_symbols("AoWEPACK.dpl")
    d = open(dll, "rb").read()
    secs = _sections(d)

    def off2va(o):
        for va, sz, raw in secs:
            if raw <= o < raw + sz:
                return DLL_BASE + va + (o - raw)

    order = sorted(syms.items())
    vas = [v for v, _ in order]

    def func_at(va):
        """(start, name, end) of the exported symbol containing va."""
        i = bisect.bisect_right(vas, va) - 1
        if i < 0:
            return None
        return (order[i][0], order[i][1], order[i + 1][0] if i + 1 < len(order) else 0xFFFFFFFF)

    # ---- one linear pass: per-function call targets, id writes and cap writes -----------------
    callers = {}                                  # callee VA -> {caller function start}
    fcalls = {}                                   # function start -> {callee VA}
    fcaps = {}                                    # function start -> [cap imm]
    idw = []                                      # (function start, name, ability id)
    for o in range(len(d) - 8):
        b = d[o]
        if b == 0xE8:
            va = off2va(o)
            if va is None:
                continue
            tgt = (va + 5 + struct.unpack_from("<i", d, o + 1)[0]) & 0xFFFFFFFF
            f = func_at(va)
            # ONLY ctor->ctor edges. Reachability over arbitrary calls is far too permissive:
            # it marked TConstructAbility (a plain TAbility, no levels) as multi-level through
            # some unrelated helper several hops down.
            if f and f[1].endswith(".Create") and syms.get(tgt, "").endswith(".Create"):
                callers.setdefault(tgt, set()).add(f[0])
                fcalls.setdefault(f[0], set()).add(tgt)
        elif b == 0xC7 and d[o + 1] in (0x40, 0x41, 0x42, 0x43, 0x46, 0x47) and d[o + 2] in (0x0C, 0x28):
            va = off2va(o)
            f = func_at(va) if va is not None else None
            if not f or not (f[0] <= va < f[2]):
                continue
            imm = struct.unpack_from("<I", d, o + 3)[0]
            if d[o + 2] == 0x28:
                if 1 <= imm <= 32:
                    fcaps.setdefault(f[0], []).append(imm)
            elif imm <= 0x200 and re.search(r"\.T\w+?(?:Ability)?\.Create$", f[1]):
                idw.append((f[0], f[1], imm))

    # ---- which ctors are multi-level: reverse reachability from the base ctor -----------------
    multi, queue = set(), [MULTILEVEL_CTOR]
    while queue:
        cur = queue.pop()
        for c in callers.get(cur, ()):
            if c not in multi:
                multi.add(c); queue.append(c)

    def cap_of(start, depth=0):
        """the ctor's own ceiling, else the one it inherits from the ctor it chains to."""
        if start in fcaps:
            return min(fcaps[start])
        if depth < 8:
            for tgt in sorted(fcalls.get(start, ())):
                if tgt in multi or tgt == MULTILEVEL_CTOR:
                    got = cap_of(tgt, depth + 1)
                    if got:
                        return got
        return None

    # ---- family 2: a class with its own CanExpand hard-coding the ceiling --------------------
    # `call [reg+0x70]` (GetLevel) then, within a few bytes, `cmp eax, imm8` (83 F8 ii) — the
    # `jl` that follows is the "still expandable" edge, so imm8 is the ceiling.
    hard = {}
    for va, nm in syms.items():
        m = re.search(r"\.T(\w+?)(?:Ability)?\.CanExpand$", nm)
        if not m:
            continue
        f = func_at(va)
        if not f or f[2] - f[0] > 0x200:
            continue
        lo = None
        for s in secs:
            if s[0] <= va - DLL_BASE < s[0] + s[1]:
                lo = s[2] + (va - DLL_BASE - s[0])
        if lo is None:
            continue
        body = d[lo:lo + (f[2] - f[0])]
        for i in range(len(body) - 6):
            if body[i] == 0xFF and (body[i + 1] & 0xF8) == 0x50 and body[i + 2] == 0x70:
                j = body.find(b"\x83\xF8", i + 3, i + 16)
                if j >= 0 and 1 <= body[j + 2] <= 32:
                    hard[m.group(1)] = body[j + 2]
                    break

    out = {}
    for start, name, aid in idw:
        stem = re.search(r"\.T(\w+?)(?:Ability)?\.Create$", name)
        stem = stem.group(1) if stem else ""
        if stem in hard:
            out[aid] = hard[stem]
        elif start in multi:
            out[aid] = cap_of(start) or MULTILEVEL_DEFAULT_CAP
    _LEVELS_CACHE[dll] = out
    return dict(out)


PUT_THUNK = 0x55702EB4        # IAT thunk -> EngineP.dpl Engine.TIntegerList.Put
_COSTS_CACHE = {}


def costs(dll=None):
    """{ability id: skill points per level} for levelled abilities a HERO CAN ACTUALLY BUY.

    ⚠ `Ability.pfs` tag 6 is NOT the answer for these, and reading it is how the Ziggurat Manual
    printed costs the game never charges. `TAbility.ExpandCost` @0x5574E908 returns tag 6, but the
    levelled classes override it, so the real figure lives in code. Measured 2026-08-09: tag 6
    disagreed for Leadership (says 20, charges 10) and Spell Casting (says 15, charges 20).

    THREE mechanisms, all of which must be handled:

    1. `TMultiLevelAbility` descendants fill a per-level `TIntegerList` at `[ability+0x2C]` from
       their ctor. The cost is the `mov ecx, imm` feeding each `TIntegerList.Put`.
    2. ...except when a mod has replaced that run with a CAVE. Leadership's ctor still sets up
       `mov ecx, 0x14` (20) and then calls `build_leadership4.py`'s cave, which overwrites ecx with
       10 and loops. **Reading the ctor alone gives the stale pre-patch number**, so we follow one
       call/jmp hop out of the ctor and prefer what the cave actually passes. Vision is the same
       shape via `build_vision9.py`.
    3. A class with its OWN `ExpandCost` ignores the list entirely -- `TTurnUndeadAbility` returns
       a flat `mov eax, 5`. Read the immediate out of that function instead.

    ⚠ **This reports the CODE-side default and applies NO filter.** An earlier version of this
    docstring claimed abilities the hero chooser never offers were excluded -- **no such filter
    was ever implemented**, and reading that claim as true led to a published wrong conclusion
    (2026-08-28). Dispel Magic 0x3C IS returned here, with 5, even though no level-up screen can
    ever offer it. Transport is absent for an unrelated reason: its ctor Puts are not found.

    Whether an ability is actually purchasable is decided by `Ability.pfs`, not by the DLL:
    `THeroUpgradeDlg`'s fill requires BOTH `TAbility.CanExpand` (owner mask & ability mask, and
    THero's owner mask is 0x0200) AND `tag 9 & 0x0100` (astHeroUpgrade). And where an ability has
    no `ExpandCost` override, `Ability.pfs` tag 6 is the charged price, not anything here --
    Healing costs 12 by tag 6 while this function does not list it at all.
    **To answer "is it purchasable, and for how much", read the .pfs. See
    `Zig notes/Investigation_Items.md`, "what actually gates the hero chooser".**
    """
    dll = dll or DLL
    if dll in _COSTS_CACHE:
        return dict(_COSTS_CACHE[dll])
    import aowsyms
    _pe, _base, syms, _iat = aowsyms.get_symbols("AoWEPACK.dpl")
    d = open(dll, "rb").read()
    secs = _sections(d)

    def off2va(o):
        for va, sz, raw in secs:
            if raw <= o < raw + sz:
                return DLL_BASE + va + (o - raw)

    def va2off(va):
        for v, sz, raw in secs:
            if v <= va - DLL_BASE < v + sz:
                return raw + (va - DLL_BASE - v)

    order = sorted(syms.items())
    svas = [v for v, _ in order]

    def bounds(va):
        """(start, name, end) — _enclosing_sym gives no end, and a ctor scan needs one."""
        i = bisect.bisect_right(svas, va) - 1
        if i < 0:
            return None
        return (order[i][0], order[i][1],
                order[i + 1][0] if i + 1 < len(order) else order[i][0] + 0x200)

    lv = levels(dll)
    ctors, own_expand = {}, {}
    for va, nm in syms.items():
        m = re.search(r"\.T(\w+?)(?:Ability)?\.ExpandCost$", nm)
        if m:
            own_expand[m.group(1)] = va
    for modrm in (0x40, 0x41, 0x42, 0x43, 0x46, 0x47):
        o = -1
        while True:
            o = d.find(bytes([0xC7, modrm, 0x0C]), o + 1)
            if o < 0:
                break
            aid = struct.unpack_from("<I", d, o + 3)[0]
            va = off2va(o) if aid in lv else None
            if va:
                f = bounds(va)
                if f and f[1].endswith(".Create"):
                    ctors.setdefault(aid, f)

    def put_costs(lo, hi, follow):
        """[costs] from every `mov ecx,imm` feeding a TIntegerList.Put in [lo,hi), plus one hop."""
        a, b = va2off(lo), va2off(hi)
        if a is None or b is None:
            return [], []
        found, hops, i = [], [], a
        while i < b - 5:
            if d[i] == 0xE8 and ((off2va(i) + 5 + struct.unpack_from("<i", d, i + 1)[0])
                                 & 0xFFFFFFFF) == PUT_THUNK:
                for k in range(i - 1, max(i - 20, a) - 1, -1):
                    if d[k] == 0xB9:
                        found.append(struct.unpack_from("<I", d, k + 1)[0]); break
            elif follow and d[i] in (0xE8, 0xE9):
                t = (off2va(i) + 5 + struct.unpack_from("<i", d, i + 1)[0]) & 0xFFFFFFFF
                # ⚠ Only follow into UNNAMED targets. A cave has no export symbol; a named callee
                # is a real function (`@ClassCreate`, `TMultiLevelAbility.Create`, ...) whose own
                # Puts, if it ever grew any, would silently outrank the ctor's -- and "the cave
                # wins" is only sound because a cave genuinely overwrites ecx before its Put.
                if not (lo <= t < hi) and t != PUT_THUNK and t not in syms:
                    hops.append(t)
            i += 1
        return found, hops

    out = {}
    for aid, cap in lv.items():
        f = ctors.get(aid)
        if not f:
            continue
        stem = re.search(r"\.T(\w+?)(?:Ability)?\.Create$", f[1])
        ex = own_expand.get(stem.group(1) if stem else "")
        if ex:                                       # mechanism 3: its own ExpandCost
            eo = va2off(ex)
            for k in range(eo, eo + 0x20):
                if d[k] == 0xB8 and 1 <= struct.unpack_from("<I", d, k + 1)[0] <= 999:
                    out[aid] = struct.unpack_from("<I", d, k + 1)[0]; break
            continue
        got, hops = put_costs(f[0], f[2], True)      # mechanism 1: inline ctor Puts
        for t in hops:                               # mechanism 2: a cave took the run over
            hg, _ = put_costs(t, t + 0x80, False)
            if hg:
                got = hg                             # the cave WINS: it overwrites the ctor's ecx
                break
        if got:
            out[aid] = got[0] if len(set(got)) == 1 else max(got)
    _COSTS_CACHE[dll] = out
    return dict(out)


_CACHE = None


def names():
    """{ability id: display name}. Curated map wins, constructor scan fills gaps, modded ids added."""
    global _CACHE
    if _CACHE is None:
        m = {}
        try:
            m.update(_from_constructors())
        except Exception as exc:                              # noqa: BLE001
            print("ability_names: constructor scan failed (%s) — curated map only" % exc,
                  file=sys.stderr)
        m.update(_curated())          # curated beats the class-derived constructor scan
        try:
            m.update(_from_resourcestrings())   # ...and the game's own strings beat curated
        except Exception as exc:                              # noqa: BLE001
            print("ability_names: resourcestring scan failed (%s)" % exc, file=sys.stderr)
        m.update(DOC_NAMES)
        m.update(DISPLAY_OVERRIDES)   # what the game visibly shows wins over all of it
        m.update(MODDED)
        _CACHE = m
    return dict(_CACHE)


# Caps are mod-tunable immediates read live out of the DLL, so this must not be sized to whatever
# the current data happens to use -- indexing it raised IndexError the moment Vision's cap went
# 4 -> 9. 15 is the real ceiling anywhere sight is involved (TArmy.UpdateVisibilityRanges packs
# base+level into a nibble), and roman() falls back to the digits beyond that rather than raising.
# ⚠ Both must stay ABOVE the __main__ block: they used to sit below it, where the self-test could
# never see them (NameError, not the IndexError it looked like).
_ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX",
          "X", "XI", "XII", "XIII", "XIV", "XV"]


def roman(n):
    """Level numeral, never raises: out-of-range levels degrade to their digits."""
    return _ROMAN[n] if 0 <= n < len(_ROMAN) else str(n)


if __name__ == "__main__":
    m, lv = names(), levels()
    print("%d ability ids named, %d multi-level" % (len(m), len(lv)))
    for aid in sorted(m):
        print("  0x%02X  %-24s %s" % (aid, m[aid],
                                      "levels I-%s" % roman(lv[aid]) if aid in lv else ""))
