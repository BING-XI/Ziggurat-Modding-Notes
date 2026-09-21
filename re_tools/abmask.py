"""Dump every ability's OWNER-TYPE MASK (`TAbility+0x20`) — which owners may legally carry it.

This is the answer to "can I put ability X on item type Y?".  AoW1 gates ability *acquisition* on a
bitmask handshake:

    TAbility.CanExpand @0x5574e8b8 (ability, owner):
        if owner.GetAbSet(id):                       return false   ; already has it
        return (owner.vtable[0x8c]() & ability[+0x20]) != 0         ; GetAbilitySelectionTypes

Owner side (`GetAbilitySelectionTypes`, VMT +0x8c) — live-read constants:
    TAbilityOwner  0x0000      TAbstractUnit (units) 0x0001 = bit 0    THero 0x0200 = bit 9
    TItem returns ONE bit chosen by item type (`TItem.GetAbilitySelectionTypes@0x557944ac`):
        itHead 0x0002(b1)  itTorso 0x0004(b2)  itAttack 0x0008(b3)
        itDefense 0x0010(b4)  itRing 0x0020(b5)  itUse 0x0040(b6)
        itScroll -> the `default:` arm -> **0x0000** (no ability may ever live on a scroll)

So the bit layout is: b0=unit, b1..b6=the six item categories, b9=hero.

⚠ THE MASK IS NOT ENFORCED FOR ITEMS AT RUNTIME.  `TAbilityOwner.ValidateOwnerTypeAbilities`
(@0x5574f154), which strips illegal abilities, has exactly ONE caller —
`TUnitResource.ReadWrite@0x55784f5e`.  Nothing validates a `TItem`.  An ability the mask forbids is
therefore *kept* on the item and silently ignored by consumers, rather than removed.  The mask
describes DESIGN INTENT + the editor/level-up picker, not a runtime guarantee.

⚠ `Ability.pfs` record ids are NOT ability ids — but there IS a join, and it is simply
**record id = ability id + 10**.  Verified 2026-09-09 against the AoWDevEd Abilities tab:
ability 97 Webbed -> record 107 (tag 9 = 0x03E, tag 6 = 0) and ability 88 Black Breath ->
record 98 (0x3FF, 20), both matching the editor exactly.  `build_shield.py` ("record for ability
0xB0 is id 0xB0+10 = 186") and `build_vision9.py` ("record 74 = ability id 0x40 + 10") both write
records through this rule.
    Earlier revisions of this docstring said "do not join it to ability ids" and cited record 0x2F
as Leadership's description.  Both were wrong and the pair cost a whole analysis pass: 0x2F is
ability 37 Bard's Skills; Leadership (ability 46) is record 0x38.  Reading record ids AS ability
ids yields a plausible-looking table of the wrong abilities, with no error anywhere.

⚠ The masks are initialised in code, in each class's `.Create` — but `Ability.pfs` tag 9
**overwrites** them at load through `AoWE.TAbility.ReadWrite @0x5574F07C` (tag 9 <-> [ability+0x20],
width 2; tag 6 <-> [ability+0x14]).  For a live answer read tag 9, not the constructor.

The 10 bits, confirmed against the editor's own Selection checklist (2026-09-09):
    b0 Unit          b1..b6 Head/Torso/Attack/Defense/Ring/Use item
    b7 Customize Leader     b8 Hero upgrade     b9 THero (UI label "Editor")
Hero level-up requires **b8 AND b9**, tested in two different places: `CanExpand` matches b9
because that is what `THero.GetAbilitySelectionTypes` returns, and the level-up fill loop
separately tests b8 as `test byte [ability+0x21], 1`.

Usage:  abmask.py [AoWEPACK.dpl] [--use]      # --use = only abilities legal on itUse
"""
import bisect
import os
import re
import sys

import capstone

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
sys.path.insert(0, TOOLS)
from aowsyms import get_symbols

BITS = {1: "Head", 2: "Torso", 3: "Attack", 4: "Defense", 5: "Ring", 6: "USE"}
LIT = re.compile(r"word ptr \[(0x[0-9a-f]+)\]")


def main(argv):
    mod = next((a for a in argv[1:] if not a.startswith("-")), "AoWEPACK.dpl")
    only_use = "--use" in argv

    pe, base, names, _iat = get_symbols(mod)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

    def off(va):
        return pe.rva2off(va - base)

    def rdw(va):
        o = off(va)
        return int.from_bytes(pe.data[o:o+2], "little") if o is not None else None

    sym = sorted(names.items())
    addrs = [a for a, _ in sym]

    def own(va):
        k = bisect.bisect_right(addrs, va) - 1
        return sym[k][1] if k >= 0 and va - sym[k][0] < 0x3000 else "?"

    code = next(s for s in pe.sections if s[0] == "CODE")
    _nm, vaddr, vsize, raw, rsize = code
    blob = pe.data[raw:raw + min(vsize, rsize)]
    cbase = base + vaddr

    insns, pos = [], 0
    while pos < len(blob):                      # resyncing sweep — see fieldrefs.py trap #1
        moved = False
        for i in md.disasm(blob[pos:], cbase + pos):
            insns.append(i)
            pos = (i.address - cbase) + i.size
            moved = True
        if not moved:
            pos += 1

    by_id, by_class = {}, {}
    reg16, cur_id, cur_fn = {}, None, None
    for i in insns:
        fn = own(i.address)
        if fn != cur_fn:
            cur_fn, cur_id, reg16 = fn, None, {}
        if i.mnemonic != "mov":
            continue
        m = re.match(r"dword ptr \[e\w\w \+ 0xc\], (0x[0-9a-f]+|\d+)$", i.op_str)
        if m:
            cur_id = int(m.group(1), 0)
        m = re.match(r"^([acdb]x), (.+)$", i.op_str)
        if m:
            d, s = m.groups()
            lm = LIT.match(s)
            if lm:
                reg16[d] = rdw(int(lm.group(1), 16))
            else:
                try:
                    reg16[d] = int(s, 0)
                except ValueError:
                    reg16.pop(d, None)
        m = re.match(r"^word ptr \[e\w\w \+ 0x20\], (.+)$", i.op_str)
        if m:
            s = m.group(1)
            v = reg16.get(s)
            if v is None:
                try:
                    v = int(s, 0)
                except ValueError:
                    v = None
            if v is not None:
                by_class[cur_fn] = v
                if cur_id is not None:
                    by_id[cur_id] = (v, cur_fn)

    for va, lbl in ((0x5574f144, "TAbilityOwner (base)"),
                    (0x5577ecc8, "TAbstractUnit (units)"),
                    (0x55786b18, "THero (heroes)")):
        w = rdw(va)
        if w is not None:
            print("  %-24s GetAbilitySelectionTypes = 0x%04X" % (lbl, w))

    print("\n  id    mask    unit hero  legal item slots                class")
    print("  " + "-" * 84)
    for aid in sorted(by_id):
        v, fn = by_id[aid]
        if only_use and not v >> 6 & 1:
            continue
        print("  0x%02X  0x%04X   %-4s %-4s  %-30s %s" % (
            aid, v, "yes" if v & 1 else "-", "yes" if v & 0x200 else "-",
            ", ".join(BITS[b] for b in sorted(BITS) if v >> b & 1) or "(none)",
            fn.rsplit(".", 1)[0]))

    print("\n  === every CLASS declaring the itUse bit (descendants inherit unless they "
          "re-write +0x20) ===")
    for fn, v in sorted(by_class.items(), key=lambda x: -x[1]):
        if v >> 6 & 1:
            print("     0x%04X  %s" % (v, fn.rsplit(".", 1)[0]))
    print("\n  %d abilities with a decoded mask, %d classes total." % (len(by_id), len(by_class)))
    print("  Abilities whose .Create takes the id as a PARAMETER show no id — read the class column.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
