#!/usr/bin/env python
r"""
enchant_mods.py -- read unit-enchantment / passive-ability stat modifiers straight out of the LIVE
AoWEPACK.dpl, by disassembling each class's stat getters.

WHY THIS EXISTS
---------------
Every modifier in this install has moved at least twice (the 5% conversion doubled it, the DAM/HP
pass doubled damage, the buff re-grade dropped several onto odd values). Any hand-written table of
these numbers is wrong within a session. The Ziggurat Manual therefore renders them from HERE, and
this module reads the binary -- so the manual cannot drift from the game.

    from enchant_mods import extract
    for e in extract():
        print(e.display, e.mods)      # e.g. "Fury"  {'ATK': 5, 'DEF': -2}

HOW IT WORKS -- driven by the CLASS HIERARCHY, not by any list kept here
------------------------------------------------------------------------
Every VMT in the image is enumerated (class-name ShortString -> the dword pointing at it is the
vmtClassName field -> VMT base = that + 0x20), each class's ancestry is walked, and it is kept if it
descends from one of the engine's two families:

  * `TUnitEnchantmentAbility` (VMT 0x55722364) -- a real UNIT ENCHANTMENT: an object on the unit,
    dispellable, what `TAbstractUnit.AbilityToEnchantment @0x5577F3B4` tests for. 21 classes.
  * `TDurationAbility` (VMT 0x5571DD68) -- a TEMPORARY STATUS: expires on its own, not dispellable,
    no enchantment object. 13 classes.

⚠ THE NAMES LIE, so never bucket by name. Eight `...Ability`-suffixed classes that look like
enchantments are statuses (Bloodlust, Cursed, High Prayer Blessing, Nature's Blessing, Poisoned,
Stunned, Vertigo, Webbed), and the near-identical pairs sit in DIFFERENT families:
**Webbed(status) vs Entangled(enchantment)**, **Stunned(status) vs Frozen(enchantment)**.

Stat modifiers are read from fixed VMT slots (+0x5C ATK, +0x60 DEF, +0x64 RES, +0x68 DAM). A slot
still holding `TAbility`'s own implementation (`33 C0 C3`) means "no modifier" and is skipped --
which is why 14 of the 21 enchantments legitimately carry no numbers at all.

⚠ MULTIPLE ENCODINGS -- all of these appear in this binary and all must decode:
    B0 nn           mov al, imm8        (the common form)
    83 C8 nn        or  eax, imm8       sign-extended, NEGATIVE values (Poisoned ATK/DAM, Fury DEF)
    31 C0 / 33 C0   xor eax, eax        = 0
    B8 nn nn nn nn  mov eax, imm32
A reader keyed on only `mov al` silently reports 0 or garbage for the or-form entries -- that exact
mistake has bitten this project before, so `decode_getter` refuses anything it does not recognise
instead of guessing.

⚠ WHAT THIS DOES *NOT* COVER (by design -- the caller must handle these separately):
  * Leadership: its bonus is a per-level TABLE at 0x5580F0C0 / 0x5580F0C8, not a constant --
    `leadership_table()` below reads it.
  * Conditional combat boosts (Monster Slaying, Assassin, Charge, Parry): those are inline `add`
    instructions inside the strike-building code, not class getters -- `combat_boosts()` reads the
    engine copies.
  * Anything whose effect is not a stat delta (immunities, movement, extra strikes).
"""
import os, re, struct, sys
from collections import OrderedDict

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
IMAGE_BASE = 0x55700000
# stat getters live in fixed VMT slots; TAbility's own impls are `33 C0 C3` (xor eax,eax; ret)
# and mean "no modifier", so a slot equal to the base pointer is skipped.
SLOTS = OrderedDict([("ATK", 0x5C), ("DEF", 0x60), ("RES", 0x64), ("DAM", 0x68)])
VMT_CLASSNAME = 0x20      # classname-pointer field sits this far BELOW the VMT base
VMT_PARENT = 0x18         # pointer-to-parent-VMT-pointer (deref twice)

# Display names for the classes whose symbol name is not what a player sees.
DISPLAY = {
    # ⚠ TBlessedEnchantment and THighPrayerBlessingAbility BOTH resolve to the resource string
    # "Blessed" in game. Two identically-named rows would be unreadable, so the manual
    # disambiguates the second one.
    "TNaturesBlessingAbility": "Nature's Blessing", "TEnchantedWeaponAbility": "Enchanted Weapon",
    "THighPrayerBlessingAbility": "High Prayer Blessing", "TBlessedEnchantment": "Blessed",
    "TDarkGiftEnchantment": "Dark Gift", "TStoneSkinAbility": "Stone Skin",
    "TBloodlustAbility": "Bloodlust", "TFuryAbility": "Fury", "TCursedAbility": "Cursed",
    "TPoisonedAbility": "Poisoned", "TVertigoAbility": "Vertigo", "TWebbedAbility": "Webbed",
    "TStunnedAbility": "Stunned", "TEntangledAbility": "Entangled", "TFrozenAbility": "Frozen",
    "TCosmeticSurgeryAbility": "Cosmetic Surgery", "TFireAuraEnchantment": "Fire Halo",
    "TFreeMovementAbility": "Free Movement", "THolyChampionEnchantment": "Holy Champion",
    "TUnholyChampionEnchantment": "Unholy Champion", "TLiquidFormEnchantment": "Liquid Form",
    "TSlowEnchantmentAbility": "Lethargy", "TTurnedUndeadAbility": "Turned Undead",
    "TWaterWalkingEnchantment": "Water Walking", "TWindWalkingEnchantment": "Wind Walking",
    "TFireProtectionEnchantment": "Fire Protection", "TConcealmentEnchantment": "Concealment",
    "TSummonedAbility": "Summoned", "THasteAbility": "Haste", "THolyFear": "Holy Fear",
    "TPanickedAbility": "Panicked", "TBurningAbility": "Burning", "TDecayAbility": "Decay",
    "TCrusaderAbility": "Crusader",
}


class Entry(object):
    __slots__ = ("cls", "display", "kind", "mods", "sites", "vmt")

    def __init__(self, cls, display, kind, mods, sites, vmt):
        self.cls, self.display, self.kind = cls, display, kind
        self.mods, self.sites, self.vmt = mods, sites, vmt

    def __repr__(self):
        return "<%s %s %s>" % (self.kind, self.display, self.mods)


class _PE(object):
    def __init__(self, path):
        self.d = open(path, "rb").read()
        e = struct.unpack_from("<I", self.d, 0x3C)[0]
        n = struct.unpack_from("<H", self.d, e + 6)[0]
        opt = struct.unpack_from("<H", self.d, e + 20)[0]
        s, self.secs = e + 24 + opt, []
        for _ in range(n):
            vs, va, rs, raw = struct.unpack_from("<IIII", self.d, s + 8)
            self.secs.append((va, vs, raw, rs)); s += 40

    def off(self, va):
        rva = va - IMAGE_BASE
        for va0, vs, raw, rs in self.secs:
            if va0 <= rva < va0 + max(vs, rs):
                return raw + (rva - va0)
        return None

    def o2va(self, o):
        for va0, vs, raw, rs in self.secs:
            if raw <= o < raw + rs:
                return IMAGE_BASE + va0 + (o - raw)
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.d[o:o + n] if o is not None else None

    def dw(self, va):
        o = self.off(va)
        return struct.unpack_from("<I", self.d, o)[0] if o is not None else None

    def clsname(self, vmt):
        p = self.dw(vmt - VMT_CLASSNAME)
        if not p:
            return None
        o = self.off(p)
        if o is None or not (1 <= self.d[o] <= 60):
            return None
        s = self.d[o + 1:o + 1 + self.d[o]]
        return s.decode("latin-1") if all(0x20 <= c < 0x7F for c in s) else None

    def parent(self, vmt):
        """Delphi vmtParent is a POINTER TO the parent's VMT pointer -- deref twice."""
        pp = self.dw(vmt - VMT_PARENT)
        if not pp or not (IMAGE_BASE <= pp < IMAGE_BASE + 0x300000):
            return None
        v = self.dw(pp)
        return v if v and self.clsname(v) else None

    def all_vmts(self):
        out = {}
        # Delphi ShortString: a length byte then the chars. Class names here are 3..60 long.
        for m in re.finditer(rb"[\x03-\x3c]T[A-Za-z0-9_]{2,59}", self.d):
            ln = self.d[m.start()]
            nm = self.d[m.start() + 1:m.start() + 1 + ln]
            if len(nm) != ln or not all(0x20 <= c < 0x7F for c in nm):
                continue
            nva = self.o2va(m.start())
            if nva is None:
                continue
            p = self.d.find(struct.pack("<I", nva))
            if p < 0:
                continue
            vmt = self.o2va(p)
            if vmt is None:
                continue
            vmt += VMT_CLASSNAME
            name = nm.decode("latin-1")
            if self.clsname(vmt) == name:
                out[name] = vmt
        return out


def decode_getter(pe, va):
    """-> (value, immVA, form). Raises on an encoding this module does not positively recognise."""
    b = pe.read(va, 8)
    if b is None:
        raise ValueError("VA %08X is not mapped" % va)
    if b[0] == 0xB0:                                    # mov al, imm8
        v = b[1]
        return (v - 0x100 if v > 0x7F else v), va + 1, "mov"
    if b[0] == 0x83 and b[1] == 0xC8:                   # or eax, imm8 (sign-extended)
        v = b[2]
        return (v - 0x100 if v > 0x7F else v), va + 2, "or"
    if b[0] in (0x31, 0x33) and b[1] == 0xC0:           # xor eax, eax
        return 0, None, "xor"
    if b[0] == 0xB8:                                    # mov eax, imm32
        v = struct.unpack_from("<i", b, 1)[0]
        return v, va + 1, "mov32"
    raise ValueError("unrecognised getter encoding at %08X: %s -- a new form has appeared, teach "
                     "decode_getter about it rather than guessing" % (va, b[:4].hex(" ")))


def extract(path=None, include_zero=False, kinds=("enchantment", "status")):
    """-> [Entry] for every class in either family, discovered from the CLASS HIERARCHY.

    No hardcoded class list: every VMT in the image is enumerated, its ancestry walked, and the
    class kept if it descends from TUnitEnchantmentAbility (a real, dispellable unit enchantment)
    or TDurationAbility (a temporary combat/day status). Classes with no stat modifier are RETAINED
    with empty `mods` -- 14 of the 21 enchantments are like that, and a section that dropped them
    would be a list of numbers rather than a list of enchantments.
    """
    pe = _PE(path or DLL)
    vmts = pe.all_vmts()
    roots = {}
    for root, kind in (("TUnitEnchantmentAbility", "enchantment"), ("TDurationAbility", "status")):
        if root in vmts:
            roots[vmts[root]] = kind
    if not roots:
        raise ValueError("neither family root VMT found -- wrong binary?")

    def kind_of(vmt):
        seen, cur = set(), pe.parent(vmt)
        while cur and cur not in seen:
            if cur in roots:
                return roots[cur]
            seen.add(cur); cur = pe.parent(cur)
        return None

    base = {pe.dw(vmts["TAbility"] + o) for o in SLOTS.values()} if "TAbility" in vmts else set()
    out = []
    for name, vmt in vmts.items():
        kind = kind_of(vmt)
        if kind is None or kind not in kinds:
            continue
        mods, sites = OrderedDict(), OrderedDict()
        for stat, slot in SLOTS.items():
            fn = pe.dw(vmt + slot)
            if not fn or fn in base:                    # not overridden -> no modifier
                continue
            val, imm, form = decode_getter(pe, fn)
            if val == 0 and not include_zero:
                continue
            mods[stat] = val
            sites[stat] = (fn, imm, form)
        out.append(Entry(name, DISPLAY.get(name, re.sub(r"^T|Ability$|Enchantment$", "", name)),
                         kind, mods, sites, vmt))
    out.sort(key=lambda e: (e.kind != "enchantment", e.display.lower()))
    return out


def leadership_table(path=None):
    """-> {'ATK': [l1..l4], 'DEF': [l1..l4]}, the per-level bonus.

    ⚠ Two different storage schemes, and which one is live depends on the binary:
      * VANILLA reads flat 4-entry tables `LeadershipAttackProgression` @0x558E83E8 and
        `LeadershipDefenseProgression` @0x558E83EC (one value repeated -- Leadership had a single
        level).
      * ZIGGURAT's build_leadership4.py made it a real 4-level ability and repointed both getters'
        disp32 at its own 5-byte tables in a code cave (0x5580F0C0 / 0x5580F0C8, index = level, so
        entry 0 is unused padding).
    Reading the cave out of a pristine DLL yields zeros -- the cave is not there -- which would
    render a bogus "+0/+0/+0/+0" vanilla column. So: use the cave when it holds anything, else fall
    back to the vanilla progression tables.

    ⚠ The ramp is sliced to the ability's actual LEVEL CAP, read from the constructor
    (`mov dword [esi+0x28], N` @0x55766187, imm32 at +3). Vanilla caps Leadership at ONE level, so
    its table's entries 2..4 are unreachable -- printing the raw vanilla table as a four-step ramp
    would claim a progression the game never offered.
    """
    pe = _PE(path or DLL)
    cap = 4
    capb = pe.read(0x5576618A, 4)
    if capb and pe.read(0x55766187, 3) == b"\xC7\x46\x28":
        cap = max(1, min(8, struct.unpack("<I", capb)[0]))
    atk, dfn = pe.read(0x5580F0C0, 5), pe.read(0x5580F0C8, 5)
    if atk and dfn and (any(atk[1:5]) or any(dfn[1:5])):        # Ziggurat cave, index = level
        return OrderedDict([("ATK", list(atk[1:1 + cap])), ("DEF", list(dfn[1:1 + cap]))])
    va, vd = pe.read(0x558E83E8, 4), pe.read(0x558E83EC, 4)     # vanilla progression tables
    if va and vd and (any(va) or any(vd)):
        return OrderedDict([("ATK", list(va[1:1 + cap])), ("DEF", list(vd[1:1 + cap]))])
    return None


# Conditional bonuses: inline `add` sites in the strike builders, keyed by the instruction shape.
# ⚠ The immediate offset is NOT uniform -- it follows the full ModRM/SIB/disp of each encoding:
#     80 C3 nn          add bl, imm8                 -> imm at +2
#     80 04 24 nn       add byte [esp], imm8         -> imm at +3
#     80 44 24 dd nn    add byte [esp+dd], imm8      -> imm at +4  (the disp8 sits BEFORE it --
#                                                      reading +3 yields the displacement, not the
#                                                      value; that bug shipped once, hence this note)
#     83 43 04 nn       add dword [ebx+4], imm8      -> imm at +3
#     83 03 nn          add dword [ebx], imm8        -> imm at +2
# Several bonuses exist in MORE THAN ONE copy (different strike tables). All copies are listed so
# combat_boosts() can assert they agree -- a divergence means a partial re-tune.
#   name, stat, instruction VA, opcode prefix, immediate offset, sign
_BOOSTS = [
    # --- MELEE branches. Each bonus is applied in up to three strike builders (StrikeDV and the
    #     two TMeleeRound tables); all copies are listed so a partial re-tune is caught.
    ("Monster Slaying (melee)", "ATK", 0x5576658A, b"\x80\xC3",     2, +1),
    ("Monster Slaying (melee)", "ATK", 0x5576792A, b"\x83\x03",     2, +1),
    ("Monster Slaying (melee)", "DAM", 0x5576658D, b"\x80\x04\x24", 3, +1),
    ("Monster Slaying (melee)", "DAM", 0x5576792D, b"\x83\x43\x04", 3, +1),
    ("Assassin (melee)",        "ATK", 0x5580E0CD, b"\x80\xC3",     2, +1),
    ("Assassin (melee)",        "ATK", 0x5580E17C, b"\x83\x03",     2, +1),
    ("Assassin (melee)",        "DAM", 0x5580E0D0, b"\x80\x44\x24", 4, +1),
    ("Assassin (melee)",        "DAM", 0x5580E17F, b"\x83\x43\x04", 3, +1),
    ("Charge",                  "DAM", 0x55767872, b"\x83\x43\x04", 3, +1),
    ("Charge",                  "DAM", 0x55767BCA, b"\x83\x43\x04", 3, +1),
    ("Holy Champion (melee)",   "ATK", 0x55766522, b"\x80\xC3",     2, +1),
    ("Holy Champion (melee)",   "ATK", 0x557678C6, b"\x83\x03",     2, +1),
    ("Holy Champion (melee)",   "ATK", 0x55767C1A, b"\x83\x03",     2, +1),
    ("Holy Champion (melee)",   "DAM", 0x55766525, b"\x80\x04\x24", 3, +1),
    ("Holy Champion (melee)",   "DAM", 0x557678C2, b"\x83\x43\x04", 3, +1),
    ("Holy Champion (melee)",   "DAM", 0x55767C1D, b"\x83\x43\x04", 3, +1),
    ("Unholy Champion (melee)", "ATK", 0x5576655D, b"\x80\xC3",     2, +1),
    ("Unholy Champion (melee)", "ATK", 0x55767901, b"\x83\x03",     2, +1),
    ("Unholy Champion (melee)", "ATK", 0x55767C55, b"\x83\x03",     2, +1),
    ("Unholy Champion (melee)", "DAM", 0x55766560, b"\x80\x04\x24", 3, +1),
    ("Unholy Champion (melee)", "DAM", 0x557678FD, b"\x83\x43\x04", 3, +1),
    ("Unholy Champion (melee)", "DAM", 0x55767C58, b"\x83\x43\x04", 3, +1),
    # --- RANGED branches, all four in build_ranged_slayers.py's cave at 0x5580E190.
    #     ⚠ In that cave body [esp] is DAMAGE and [esp+8] is ATTACK (operand-swap trap, documented
    #     in the script). And `add byte [esp+8], imm8` = 80 44 24 dd nn -- disp8 BEFORE the value.
    ("Monster Slaying (ranged)", "DAM", 0x5580E1BF, b"\x80\x04\x24", 3, +1),
    ("Monster Slaying (ranged)", "ATK", 0x5580E1C3, b"\x80\x44\x24", 4, +1),
    ("Holy Champion (ranged)",   "DAM", 0x5580E1FF, b"\x80\x04\x24", 3, +1),
    ("Holy Champion (ranged)",   "ATK", 0x5580E203, b"\x80\x44\x24", 4, +1),
    ("Unholy Champion (ranged)", "DAM", 0x5580E23D, b"\x80\x04\x24", 3, +1),
    ("Unholy Champion (ranged)", "ATK", 0x5580E241, b"\x80\x44\x24", 4, +1),
    ("Assassin (ranged)",        "DAM", 0x5580E288, b"\x80\x04\x24", 3, +1),
    ("Assassin (ranged)",        "ATK", 0x5580E28C, b"\x80\x44\x24", 4, +1),
    # Parry SUBTRACTS from the attacker's attack, so its immediate is reported negated.
    ("Parry",           "ATK", 0x55767889, b"\x83\x2B",     2, -1),
    ("Parry",           "ATK", 0x55767BE1, b"\x83\x2B",     2, -1),
    # Invisible target, attacker WITHOUT True Vision -- also subtractions. Melee and ranged carry
    # different penalties, so they are separate rows. ⚠ the ranged site is
    # `sub byte [esp+4], imm8` = 80 6C 24 dd nn: a disp8 sits before the immediate (offset 4).
    ("Invisible target (melee)",  "ATK", 0x5580E396, b"\x80\xEB",     2, -1),
    ("Invisible target (melee)",  "ATK", 0x5580E3D6, b"\x83\x2B",     2, -1),
    ("Invisible target (ranged)", "ATK", 0x5580E428, b"\x80\x6C\x24", 4, -1),
]


def combat_boosts(path=None, strict=True):
    """-> OrderedDict(name -> {stat: value}) for the conditional melee bonuses.

    Every bonus is read from ALL its known copies; with strict=True a disagreement raises rather
    than silently reporting whichever copy happened to be read last."""
    pe = _PE(path or DLL)
    seen = OrderedDict()
    for name, stat, va, opc, ioff, sign in _BOOSTS:
        b = pe.read(va, ioff + 1)
        if b is None or not b.startswith(opc):
            continue                       # shape moved -- report nothing rather than a wrong number
        v = b[ioff]
        seen.setdefault((name, stat), []).append((va, sign * (v - 0x100 if v > 0x7F else v)))
    out = OrderedDict()
    for (name, stat), copies in seen.items():
        vals = {v for _va, v in copies}
        if len(vals) != 1 and strict:
            raise ValueError("%s %s disagrees across copies: %s -- a partial re-tune"
                             % (name, stat, ", ".join("%08X=%+d" % c for c in copies)))
        out.setdefault(name, OrderedDict())[stat] = copies[0][1]
    return out


def main():
    print("unit enchantments / passive stat modifiers, read from %s\n" % os.path.basename(DLL))
    for e in extract():
        mods = "  ".join("%s %+d" % (k, v) for k, v in e.mods.items())
        print("  %-22s %-28s %s" % (e.display, mods, e.cls))
    lt = leadership_table()
    if lt:
        print("\n  %-22s %s" % ("Leadership (by level)",
              "  ".join("%s %s" % (k, "/".join("+%d" % x for x in v)) for k, v in lt.items())))
    cb = combat_boosts()
    if cb:
        print("\n  conditional combat boosts:")
        for nm, mods in cb.items():
            print("    %-20s %s" % (nm, "  ".join("%s %+d" % (k, v) for k, v in mods.items())))


if __name__ == "__main__":
    main()
