"""Find every hardcoded ability-ID query in a module, grouped by WHICH VMT slot it calls.

Answers "will this ability work when granted by an item?" -- see Investigation_Items.md §0.6.
AoW1 has two parallel ability-query APIs on THero and only one of them searches items:

    SELF-ONLY  (TAbilityOwner, THero does NOT override):
        +0x4c  GetAbSet      +0x84  GetAbLevel      +0x88  GetAbEnabled     +0x54  GetAbCount
    ITEM-AWARE (TAbstractUnit/THero overrides, resolve self -> equipped -> itUse inventory):
        +0x14c GetAbilitySet +0x144 GetAbilityLevel +0x148 GetAbilityEnabled +0x158 GetAbilityCount
    TCombatUnit forwards: +0xa8 GetAbilityEnabled -> [cu+0x4c].vtable[0x148]  (item-aware)
                          +0xb8 GetAbilityOwner   -> mov eax,[eax+0x4c]; ret  (source unit)

A consumer reading the SELF-ONLY slots on a hero cannot see item-granted abilities -- from an
equipped slot OR a use slot.  That is the whole bug class.

Idiom matched:  mov edx, <imm <= 0xF0>   ...(<=6 instrs)...   call dword ptr [reg + SLOT]

⚠ TRAPS THIS TOOL EXISTS TO AVOID
 1. `capstone.disasm()` is a GENERATOR THAT STOPS at the first undecodable byte -- sweeping a whole
    CODE section in one call silently covers only the first few instructions.  This resyncs.
 2. A disp32 of 0x148 is 0x148 for EVERY class.  Slot numbers are per-hierarchy: on TCombatUnit
    +0x148 is TCombatObject.DoDamage, not GetAbilityEnabled.  READ THE SYMBOL COLUMN and judge; the
    owning-function name tells you which hierarchy the register holds.
 3. Ghidra's `PTR_..._<addr>` for a class is the vmtSelfPtr slot -- the real VMT base is +0x40 from
    it.  Getting that wrong shifts every slot number by 0x40.

Usage:
  abquery.py AoWEPACK.dpl                 # all slots
  abquery.py AoWEPACK.dpl --slot 0x88     # one slot
  abquery.py AoWEPACK.dpl --id 0x20       # one ability across all slots (e.g. Marksmanship)
"""
import bisect
import os
import sys

import capstone

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(TOOLS, "..", ".."))
sys.path.insert(0, TOOLS)
from aowsyms import get_symbols

SLOTS = {
    0x04C: "SELF   GetAbSet",
    0x054: "SELF   GetAbCount",
    0x084: "SELF   GetAbLevel",
    0x088: "SELF   GetAbEnabled",
    0x144: "ITEM   GetAbilityLevel",
    0x148: "ITEM   GetAbilityEnabled",
    0x14C: "ITEM   GetAbilitySet",
    0x158: "ITEM   GetAbilityCount",
    0x0A8: "CBTU   GetAbilityEnabled (-> +0x148, item-aware)",
    0x0B8: "CBTU   GetAbilityOwner   (-> source unit, loses item provenance)",
}

# Ability IDs established elsewhere in Modding Resources/ (Ability_ID_Budget.md, Inioch/).
ABN = {
    0x14: "MagicStrike", 0x20: "Marksmanship", 0x27: "NightVision", 0x2A: "Tunneling",
    0x2E: "Leadership", 0x2F: "Healing", 0x34: "Spellcasting", 0x3C: "DispelMagic",
    0x46: "DeathProt", 0x48: "HolyProt", 0x49: "PoisonProt", 0x73: "ExtraStrike",
    0x76: "LifeStealing", 0x92: "Slaying92", 0x93: "Slaying93", 0x9A: "EnchantedWeapon",
    0xA0: "Slaying A0", 0xA1: "Slaying A1", 0xA8: "Bloodlust", 0xA9: "LifeSteal2",
}


def sweep(pe, base):
    """Resyncing linear disassembly of the CODE section -> list of capstone insns."""
    code = None
    for nm, vaddr, vsize, raw, rsize in pe.sections:
        if nm == "CODE":
            code = (vaddr, vsize, raw, rsize)
    if code is None:
        sys.exit("no CODE section")
    vaddr, vsize, raw, rsize = code
    blob = pe.data[raw:raw + min(vsize, rsize)]
    cbase = base + vaddr
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    out, pos = [], 0
    while pos < len(blob):
        moved = False
        for i in md.disasm(blob[pos:], cbase + pos):
            out.append(i)
            pos = (i.address - cbase) + i.size
            moved = True
        if not moved:
            pos += 1          # resync past an undecodable byte
    print("%s: CODE %d bytes @%08X, %d instrs decoded" % (
        os.path.basename(pe.path) if hasattr(pe, "path") else "module",
        len(blob), cbase, len(out)))
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    mod = sys.argv[1]
    only_slot = only_id = None
    if "--slot" in sys.argv:
        only_slot = int(sys.argv[sys.argv.index("--slot") + 1], 0)
    if "--id" in sys.argv:
        only_id = int(sys.argv[sys.argv.index("--id") + 1], 0)

    pe, base, names, _iat = get_symbols(mod)
    insns = sweep(pe, base)

    sym = sorted(names.items())
    addrs = [a for a, _ in sym]

    def owner(va):
        k = bisect.bisect_right(addrs, va) - 1
        if k < 0:
            return "?"
        a, n = sym[k]
        if va - a > 0x2000:
            return "?"
        return n.replace("@23EDC2EF", "") + "+0x%X" % (va - a)

    hits = {s: [] for s in SLOTS}
    for idx, i in enumerate(insns):
        if i.mnemonic != "call" or "ptr [" not in i.op_str:
            continue
        for slot in SLOTS:
            if ("+ 0x%x]" % slot) not in i.op_str:
                continue
            abid = None
            for j in range(max(0, idx - 6), idx):
                m = insns[j]
                if m.mnemonic == "mov" and m.op_str.startswith("edx, "):
                    tok = m.op_str.split(", ", 1)[1]
                    try:
                        v = int(tok, 0)
                    except ValueError:
                        continue
                    if v <= 0xF0:
                        abid = v
            if abid is not None:
                hits[slot].append((i.address, abid))
            break

    for slot in sorted(SLOTS):
        if only_slot is not None and slot != only_slot:
            continue
        rows = [(va, ab) for va, ab in hits[slot]
                if only_id is None or ab == only_id]
        print("\n===== slot +0x%03X  %s  : %d site(s)" % (slot, SLOTS[slot], len(rows)))
        grouped = {}
        for va, ab in rows:
            grouped.setdefault(ab, []).append(va)
        for ab in sorted(grouped):
            sites = grouped[ab]
            print("   id 0x%02X %-16s x%-3d %s" % (
                ab, ABN.get(ab, ""), len(sites), owner(sites[0])))
            if only_id is not None or len(sites) <= 4:
                for va in sites:
                    print("        %08X  %s" % (va, owner(va)))


if __name__ == "__main__":
    main()
