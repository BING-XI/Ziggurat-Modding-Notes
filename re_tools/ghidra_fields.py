"""Instance-field catalogue for AoWEPACK.dpl classes -- THE SOURCE, class-keyed.

Why class-keyed and not offset-keyed: the 2026-08-03 conflict pass found *five* cases where
one offset meant different things on different classes (TUnit vs THero stats, TStructure+0x30,
hexagon +0x10, the +0x4C family, and TStructure's VMT tail).  A table sorted by offset invites
exactly the mistake it is meant to prevent.  **An offset means nothing without its class.**

Unlike the VMT layouts (`ghidra_structs.py`, fully derived), field *meanings* cannot be read out
of the binary -- nothing says "+0x26 is morale".  So this file is hand-curated, and every entry
carries where it came from:

    M = measured this session (decompiled; the strongest evidence available)
    D = stated as fact in a project doc, not independently re-measured
    S = speculative / flagged uncertain in its source

What IS mechanical is the bounds check: a field at or past a class's measured instance size is
wrong, or belongs to a subclass.  `--check` runs it against the sizes derived from RTTI.

Usage:
    python ghidra_fields.py              # bounds-check + summary
    python ghidra_fields.py --md         # (re)write ../Ghidra_Field_Catalogue.md
"""
import os
import sys
import struct
import argparse

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(TOOLS, "..", ".."))
sys.path.insert(0, TOOLS)
import ghidra_structs as G  # noqa: E402

# (offset, size, name, evidence, note)   -- size in bytes; 0 = "spans, see note"
FIELDS = {
    "TAbstractUnit": [
        (0x0C, 4, "ability_bitset_width_bits", "M", "DWORD, not a byte: the ability count in BITS. GetAbilitySet: `if id < unit+0xC`"),
        (0x10, 4, "ability_data_head", "D", "linked list; next at data+0x08 (TAbilityOwner)"),
        (0x18, 4, "unit_id", "D", "network / FindUnit key; Create inits to -1"),
        (0x20, 4, "ai_group_link", "D", ""),
        (0x24, 1, "owner_player_index", "D", ""),
        (0x25, 1, "flags", "D", "bit1 gates the morale/notify block in Changed()"),
        (0x26, 1, "morale_cache", "M", "cached morale VALUE, SIGNED byte clamped to [-25, +125]. loyal >= 41"),
    ],
    "TUnit": [
        (0x3C, 1, "experience", "D", "GetRank recomputes from it"),
        (0x3D, 1, "move_points_cur", "D", ""),
        (0x3E, 1, "hit_points_cur", "D", "signed"),
        (0x40, 4, "resource", "M", "PTR:TUnitResource -- ⚠ THero+0x40 is a DIFFERENT layout"),
        (0x44, 1, "atk_modifier_cache", "M", "GetAttack adds it"),
        (0x45, 1, "def_modifier_cache", "M", "GetDefense adds it"),
        (0x46, 1, "res_modifier_cache", "M", "GetResistance adds it"),
        (0x47, 1, "dam_modifier_cache", "D", "by position; the other three are measured"),
        (0x7C, 0, "casting_cluster", "D", "⚠ MOD ONLY -- vanilla instsize is 0x48. "
                                          "build_spellcast.py grows the class; +0x7C..+0x93 "
                                          "mirror THero's cluster"),
    ],
    "THero": [
        (0x40, 4, "resource", "M", "⚠ stat block is 5 bytes EARLIER than TUnit's"),
        (0x4C, 1, "level_cache", "M", "1 BYTE, not 4. Pure cache of ExperienceToLevel(+0x48); the experience dword at +0x48 is authoritative"),
        (0x54, 1, "upgrade_pending", "D", ""),
        (0x60, 4, "custom_name", "D", "AnsiString"),
        (0x6A, 1, "atk_bonus", "D", ""),
        (0x6B, 1, "def_bonus", "M", "read by THero.GetDefense"),
        (0x6D, 1, "maxhp_bonus", "D", ""),
        (0x6E, 1, "maxmv_bonus", "D", ""),
        (0x6F, 1, "res_bonus", "D", ""),
        (0x70, 4, "items", "M", "PTR:THeroItems; THero.GetDefense reads it"),
        (0x74, 4, "inventory", "D", "THeroInventory, 8 backpack slots"),
        (0x79, 1, "move_points_cur", "D", ""),
        (0x7A, 1, "hit_points_cur", "D", ""),
        (0x7C, 4, "power_source", "D", "not serialized"),
        (0x80, 1, "casting_points", "D", "RW tag 0x0D"),
        (0x84, 4, "spell_in_progress", "D", "tag 0x0E"),
        (0x88, 4, "casting_progress", "D", "tag 0x1F"),
        (0x8C, 4, "mana_required", "D", "tag 0x22"),
        (0x90, 4, "library_hero_id", "M", "tag 0x23, -1 = not a library hero; paired with the "
                                          "library set name at +0x94. THero.GetLibraryHero is "
                                          "`cmp [eax+0x90],-1; setnz al`. NOT a casting-ready "
                                          "event-log id -- no such field exists on THero"),
    ],
    "TUnitResource": [
        (0x18, 4, "gfx_index", "D", ""),
        (0x20, 1, "race", "D", ""),
        (0x24, 4, "own_name", "M", "AnsiString, pfs tag 0x0B -- the unit's OWN name (\"Rider\", \"Priest\"), NOT a display name"),
        (0x29, 1, "base_attack", "M", "TUnit.GetAttack reads it"),
        (0x2A, 1, "base_defense", "M", "TUnit.GetDefense reads it"),
        (0x2B, 1, "base_damage", "D", ""),
        (0x2C, 1, "base_hits", "D", ""),
        (0x2D, 1, "base_moves", "D", ""),
        (0x2E, 1, "base_resistance", "M", "TUnit.GetResistance reads it"),
        (0x2F, 1, "level_tier", "D", "GetUpkeep = +0x2F + 1"),
        (0x30, 1, "unit_type", "D", "pfs tag 0x15; see UnitType_PARTIAL enum"),
        (0x32, 1, "transport_capacity_MOD", "D", "⚠ INSTALLED ONLY -- moved here from +0x44 "
                                                 "by build_copper_medal.py"),
        (0x38, 4, "ability_owner_rank0", "D", "pfs tag 0x19"),
        (0x3C, 4, "ability_owner_rank1", "D", "vanilla: silver. INSTALLED: copper (tag 0x20)"),
        (0x40, 4, "ability_owner_rank2", "D", "vanilla: gold. INSTALLED: silver (tag 0x1E)"),
        (0x44, 1, "transport_capacity_VANILLA", "M", "1 BYTE in vanilla (pfs tag 0x18); +0x45..+0x47 are padding -- which is exactly what let build_copper_medal.py reuse the dword. INSTALLED: gold ability owner (tag 0x1F)"),
        (0x48, 4, "description_list", "M", "TStringList OBJECT POINTER, not an AnsiString -- reading it as a string is wrong. pfs tag 0x1A"),
        (0x4C, 4, "gold_cost", "D", "pfs tag 0x1B"),
        (0x50, 1, "unit_size", "M", "TUnit.GetUnitSize reads [[unit+0x40]+0x50]"),
    ],
    "TItem": [
        (0x04, 4, "container", "D", "set by TItem.SetOwner"),
        (0x14, 4, "item_id", "D", "RW tag 0x11"),
        (0x18, 4, "name", "D", "tag 8"),
        (0x1C, 1, "flags", "D", "bit0 = activated"),
        (0x2C, 4, "obtain_value", "D", "tag 0x13; GetObtainValue = max(x,10)"),
        (0x34, 1, "item_type", "D", "TItemTypes enum, tag 0x0F"),
        (0x38, 4, "spell_id", "D", "tag 0x14"),
        (0x3C, 4, "ability_list", "D", "TStringList, tag 0x12"),
        (0x40, 4, "gfx_index", "D", "tag 7"),
        (0x44, 1, "unknown_enum", "M", "1 BYTE, not 2 (+0x45 is a proven distinct field). tag 0x10, meaning still unresolved"),
        (0x45, 1, "rarity", "D", "tag 0x0A"),
        (0x46, 1, "atk_bonus", "D", "tag 0x0B"),
        (0x47, 1, "def_bonus", "D", "tag 0x0C"),
        (0x48, 1, "dam_bonus", "D", "tag 0x0D  ⚠ note order: TItem is ATK,DEF,DAM,RES"),
        (0x49, 1, "res_bonus", "D", "tag 0x0E   whereas TUnit caches are ATK,DEF,RES,DAM"),
        (0x4A, 1, "unused_padding", "M", "free zero-init padding in the vanilla 0x4C allocation; "
                                         "NOT claimed in either binary. The 'mod claims it' note "
                                         "came from a design proposal that was never built"),
        (0x4B, 1, "unused_padding2", "M", "as +0x4A -- unbuilt proposal, not a live field"),
    ],
    "TCombatObject": [
        (0x08, 4, "combat", "D", "owning TCombat"),
        (0x0C, 4, "find_id", "D", ""),
        (0x45, 1, "player_side", "D", "GetPlayer"),
        (0x46, 1, "grid_position", "M", "packed party<<4 | slot_in_party, each nibble 0..7; "
                                        "0x80 = wall sentinel. NOT a printable id -- that name came "
                                        "from TCombatUnit.IDStr merely IntToStr-ing it"),
        (0x47, 1, "state_flags", "D", "alive iff (x & 0x09) == 0"),
        (0x48, 1, "conquer_flags", "D", "bit0 = conquer object"),
    ],
    "TCombatUnit": [
        (0x4C, 4, "strategic_unit", "M", "PTR:TAbstractUnit -- ⚠ a TAbstractUnit*, NOT a TUnit*: THero and TLeader live here too. TCombatUnit ONLY; GetAlignment forwards through it. "
                                         "TCombatWall+0x4C is a packed byte, "
                                         "TCombatPredictorUnit+0x4C is signed HP -- the alias "
                                         "behind the 'Blt Error' bug"),
    ],
    "TAoWHexagon": [
        (0x04, 4, "map_field", "D", ""),
        (0x08, 4, "resource", "D", ""),
        (0x10, 3, "transition_image_per_edge", "M", "⚠ 3 BYTES here. On TAoWWaterHexagon "
                                                    "(a SIBLING class) +0x10 is a pointer"),
        (0x13, 1, "transition_flags", "D", "bits 0-2 = edge n has an image"),
    ],
    "TAoWWaterHexagon": [
        (0x10, 4, "dynamic_companion", "M", "lazily created in UpdateTransitions"),
        (0x14, 1, "land_neighbour_mask", "M", "bit d set when the neighbour in dir d+1 IS land "
                                              "-- UpdateTransitions sets it when the neighbour owns "
                                              "no TLowerIsometricHexagon (the WATER family: it is "
                                              "TAoWWaterHexagon's own parent classref 0x558FCD70) "
                                              "and no TBorderHexagon"),
        (0x15, 1, "differing_terrain_mask", "M", "low 6 bits; top 2 preserved (&0xC0) = tile phase"),
        (0x18, 1, "frame_counter", "M", "signed; negative = idle delay"),
        (0x19, 1, "animation_id", "M", "rolled 20-39 / 50-58"),
        (0x1A, 6, "shore_tint_per_dir", "M", "0x28 Snow neighbour, 0x50 Wasteland, else 0"),
    ],
    "TAoWHSMap": [
        (0xA4, 1, "current_turn_player", "D", ""),
        (0xA5, 1, "seated_local_player", "M", "passed to GameOver in TPlayerControl.NewDay"),
        (0x13A, 1, "session_mode", "M", "connection/session enum: 0 = local (single/hotseat), 1 = network MP. Gates the day-1 Randomize -- 'scenario flag' was the wrong label"),
        (0x140, 4, "player_list", "M", "TPlayerList"),
        (0x144, 4, "race_list", "M", "TRaceList -- was recorded only as '(second list)'"),
        (0x158, 4, "turn_limit", "M", "compared to the day counter; triggers GameOver"),
        (0x16C, 1, "turn_order_mode", "M", "== 2 -> GenerateNewTurnOrder"),
        (0x174, 4, "day_counter", "M", "incremented by TPlayerControl.NewDay. NOT 'init state'"),
        (0x188, 4, "global_magic_control", "D", ""),
        (0x19C, 4, "notify_event_list", "M", ""),
        (0x22C, 4, "seed_constant", "M", "written day 1 from RandSeed"),
        (0x230, 4, "seed_state", "M", "MP-lockstep RNG state"),
        (0x23C, 4, "token_manager", "D", ""),
    ],
    "TPlayer": [
        (0x44, 1, "player_status", "M", "1-BYTE tri-state: 0 = still playing, 1 = victory, 2 = defeated. Not a 4-byte bool"),
        (0x48, 4, "busy_lock", "D", ""),
        (0x54, 4, "magic_control", "D", "TPlayerMagicControl"),
        (0xA6, 1, "player_index", "D", ""),
        (0xA7, 1, "player_type", "D", "PlayerType enum; 4 = independent. NOT a bare human/AI bool"),
        (0xC4, 4, "gold", "D", ""),
        (0xD8, 4, "event_logbook", "D", ""),
    ],
    "TStructure": [
        (0x04, 4, "map_field", "D", ""),
        (0x08, 4, "resource", "D", ""),
        (0x1C, 4, "structure_id", "D", ""),
    ],
    "TExplorationSite": [
        (0x30, 1, "defender_strength", "D", "0 none, 1-3 fixed, 4 = editor 'Random'"),
        (0x34, 4, "defenders_army", "D", ""),
    ],
    "TArena": [
        (0x30, 1, "mod_flags", "D", "⚠ INSTALLED ONLY -- bit0 EMPTY, bit1 SEEDED. Legal only "
                                    "because build_arena.py grows instsize 0x30 -> 0x38"),
        (0x34, 4, "mod_roster_seed", "D", "⚠ INSTALLED ONLY"),
    ],
    "TSpell": [
        (0x08, 4, "name", "D", "plain LStr value, no VMT call"),
        (0x10, 4, "spell_id", "D", ""),
        (0x14, 4, "mana_cost", "D", "RW id 0x0D"),
        (0x18, 4, "research_cost", "D", "RW id 0x0F; Create defaults it to 1"),
        (0x1C, 4, "mana_upkeep_per_turn", "M", "RW id 0x0E -- MANA UPKEEP PER TURN, not a casting-point cost. Nothing spends casting points from this field"),
        (0x20, 1, "sphere", "D", "MagicSphere enum, RW id 0x10"),
        (0x21, 1, "research_tier", "D", "ResearchTier enum, RW id 0x11"),
        (0x22, 1, "category", "D", "2 = global enchantment"),
        (0x24, 4, "description", "D", "TStringList, RW id 0x0A"),
        (0x28, 4, "sfx", "D", "RW id 0x0B"),
        (0x2C, 4, "images", "D", "TImageSequenceList, RW id 0x0C; seq 10 = book icon"),
        (0x30, 4, "ai_value", "D", ""),
    ],
    "TRangedAttackAbility": [
        (0x28, 1, "range_tier", "D", "0..3, NOT a hex count"),
        (0x29, 1, "base_ranged_damage", "M", "GetDamageRA reads it"),
        (0x2A, 1, "base_ranged_attack", "D", ""),
        (0x2B, 2, "innate_damage_types", "D", "DamageTypeBits"),
    ],
    "TStrikeCA": [
        (0x0C, 1, "flags", "D", "bit0 = defensive/retaliation"),
        (0x0D, 1, "attacker_id", "D", ""),
        (0x0E, 1, "target_id", "D", ""),
        (0x10, 1, "rolled_damage", "D", "0 = MISS"),
        (0x11, 2, "effective_damage_types", "D", "0 => fully immune"),
        (0x13, 2, "effect_landings", "D", ""),
        (0x15, 1, "applied_damage", "D", "written in Execute"),
        (0x18, 4, "effect_flags", "D", "⚠ TStrikeCA ONLY. TCombatSpellCA+0x18 is the SPELL ID; "
                                       "a ranged CA carries the ability id there"),
    ],
}

try:
    # Bulk-derived entries live in their own module so the hand-curated core stays legible and
    # the two provenances never blur.  They are merged here so every check applies to both.
    from ghidra_fields_derived import DERIVED
    for _c, _rows in DERIVED.items():
        FIELDS.setdefault(_c, []).extend(_rows)
except ImportError:
    DERIVED = {}


ALIASES = [
    ("+0x4C", "TCombatUnit strategic-unit ptr / TCombatWall packed byte / "
              "TCombatPredictorUnit signed HP / TCity WallType / TUnitResource gold / "
              "THero level cache", "caused the 'Blt Error' bug -- twice"),
    ("+0x30", "TStructure: PAST THE END (instsize 0x30) / TExplorationSite defender strength / "
              "TArena mod flags / TCity owner", "three siblings, one byte"),
    ("+0x10", "TAoWHexagon: 3 transition-image bytes / TAoWWaterHexagon: a pointer",
              "sibling classes, different parents"),
    ("+0x40 stats", "TUnit resource stats at +0x29..+0x2E / THero resource stats at +0x24..+0x29",
     "5 bytes apart; both reached via +0x40"),
    ("+0x18 on a CA", "TStrikeCA effect flags / TCombatSpellCA spell id / ranged CA ability id", ""),
]


def ancestors(pris, va2off, off2va, cls):
    """[(class name, instance size)] most-derived first, walking [VMT-0x18] classrefs.

    The chain leaves this module (Engine.TEObject lives in EngineP.dpl); when the parent
    classref dereferences outside the image we stop and assume the imported root is 8 bytes
    (vmt ptr + owner ptr), which is what every local descendant's layout implies.
    """
    def dw(va):
        o = va2off(va)
        return struct.unpack_from("<I", pris, o)[0] if o is not None else None

    def name_at(vmt):
        p = dw(vmt - 0x20)
        o = va2off(p) if p else None
        return pris[o + 1:o + 1 + pris[o]].decode("latin1", "replace") if o is not None else "?"

    v = G.find_vmts(pris, va2off, off2va, cls)
    if not v:
        return []
    out, vmt, seen = [], v[0], set()
    while vmt and vmt not in seen:
        seen.add(vmt)
        out.append((name_at(vmt), dw(vmt - 0x1C)))
        pcell = dw(vmt - 0x18)
        if not pcell:
            break
        pv = dw(pcell)
        if pv is None or va2off(pv) is None:
            out.append(("Engine.TEObject(imported)", 0x08))
            break
        vmt = pv
    return out


def true_owner(pris, va2off, off2va, cls, off):
    """The shallowest ancestor whose instance size still covers `off` -- i.e. who INTRODUCED it.

    A field below an ancestor's instance size is that ancestor's field, not the derived class's.
    Recording it on the derived class duplicates it across every sibling and manufactures the
    'one offset means N things' confusion this catalogue exists to prevent.
    """
    best = cls
    for name, isz in ancestors(pris, va2off, off2va, cls):
        if isz is not None and off < isz:
            best = name
    return best


def check():
    pris, base, secs = G.load(G.PRISTINE)
    va2off, off2va = G.mk_va2off(secs), G.mk_off2va(secs)
    sizes, problems = {}, []
    for cls in FIELDS:
        v = G.find_vmts(pris, va2off, off2va, cls)
        if not v:
            problems.append((cls, None, "class not found in this module"))
            continue
        o = va2off(v[0] - 0x1C)
        sizes[cls] = struct.unpack_from("<I", pris, o)[0]
    for cls, rows in FIELDS.items():
        isz = sizes.get(cls)
        if isz is None:
            continue
        for off, sz, name, ev, note in rows:
            if off >= isz and "MOD" not in note and "INSTALLED" not in note:
                problems.append((cls, off, f"{name}: at/past instsize 0x{isz:X}"))
            elif off >= isz:
                problems.append((cls, off, f"{name}: past vanilla instsize 0x{isz:X} "
                                           f"(expected -- mod-grown)"))
            else:
                ow = true_owner(pris, va2off, off2va, cls, off)
                if ow != cls:
                    problems.append((cls, off, f"{name}: INHERITED -- introduced by {ow}"))
    return sizes, problems


def emit_md(sizes, path):
    with open(path, "w", encoding="utf8", newline="\n") as f:
        w = f.write
        w("# AoWEPACK.dpl instance-field catalogue -- GENERATED from "
          "`re_tools/ghidra_fields.py`\n\n")
        w("Do not hand-edit; edit the script and re-run `--md`. VMT slots are NOT here -- they are "
          "fully derived in `Ghidra_VMT_Layouts.md`.\n\n")
        w("**An offset means nothing without its class.** Evidence: **M** measured by decompile "
          "2026-08-03 · **D** doc-stated · **S** speculative.\n\n")
        w("## Cross-class aliases -- read before using any offset\n\n| offset | means | |\n|---|---|---|\n")
        for off, meanings, why in ALIASES:
            w(f"| `{off}` | {meanings} | {why} |\n")
        w("\n")
        for cls in sorted(FIELDS):
            isz = sizes.get(cls)
            w(f"## {cls}" + (f"  (instance size `0x{isz:X}`)" if isz else "") + "\n\n")
            w("| offset | sz | field | ev | note |\n|---|---|---|---|---|\n")
            for off, sz, name, ev, note in sorted(FIELDS[cls]):
                w(f"| `+0x{off:02X}` | {sz or '-'} | `{name}` | {ev} | {note} |\n")
            w("\n")


import json
import urllib.request
import urllib.error

SERVER = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")
TYPE_BY_SIZE = {1: "byte", 2: "ushort", 3: "byte[3]", 4: "undefined4", 6: "byte[6]"}


def post(path, payload, timeout=90):
    req = urllib.request.Request(
        f"{SERVER}/{path}", data=json.dumps(payload).encode("utf8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf8", "replace")
    except urllib.error.URLError as e:
        sys.exit(f"Ghidra MCP unreachable at {SERVER} ({e})")
    try:
        return json.loads(body)          # some endpoints answer plain text, not JSON
    except ValueError:
        return {"status": "success" if "success" in body.lower() else "?", "message": body.strip()}


def get(path, timeout=90):
    try:
        with urllib.request.urlopen(f"{SERVER}/{path}", timeout=timeout) as r:
            return r.read().decode("utf8", "replace")
    except urllib.error.URLError as e:
        sys.exit(f"Ghidra MCP unreachable at {SERVER} ({e})")


def apply_structs(sizes, this_type=True):
    """Create one struct per class, then point each class's methods' `this` at it.

    ⚠ Ghidra holds the PRISTINE image, so mod-only fields are excluded -- a struct carrying
    build_spellcast.py's grown TUnit cluster would not match the bytes Ghidra is showing.
    """
    made = []
    for cls, rows in sorted(FIELDS.items()):
        isz = sizes.get(cls)
        if not isz:
            print(f"  skip {cls}: not in this module")
            continue
        fields, skipped = [], 0
        for off, sz, name, ev, note in sorted(rows):
            if "MOD ONLY" in note or "INSTALLED ONLY" in note:
                skipped += 1
                continue
            if "PTR:" in note:
                ty = "%s *" % note.split("PTR:")[1].split()[0]
            else:
                ty = TYPE_BY_SIZE.get(sz)
            if ty is None or off + max(sz, 1) > isz:
                skipped += 1
                continue
            fields.append({"name": name, "type": ty, "offset": off})
        # pad to the true instance size so the struct matches the object's real footprint
        last = max((f["offset"] + (4 if f["type"].endswith("*")
                                  else int(TYPE_BY_SIZE_LEN.get(f["type"], 1))) for f in fields),
                   default=0)
        if last < isz:
            fields.append({"name": "_pad_to_instsize", "type": f"byte[{isz - last}]",
                           "offset": last})
        payload = {"name": cls, "fields": json.dumps(fields), "replace_placeholder": True}
        res = post("create_struct", payload)
        body = res.get("result", res)
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                body = {"status": "?", "message": body}
        # Ghidra's Delphi demangler pre-creates some of these; recreate so re-runs are idempotent
        if "already exists" in str(body.get("message", "")):
            res = post("recreate_struct", payload)
            body = res.get("result", res)
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except ValueError:
                    body = {"status": "success" if "success" in body.lower() else "?",
                            "message": body}
        # Don't trust the reply text -- read the struct back.  The endpoints answer in several
        # shapes, and a mis-parsed "failure" silently skipped this-typing on the first run.
        layout = get(f"get_struct_layout?struct_name={cls}")
        ok = f"Size: {isz} bytes" in layout and any(
            f["name"].lstrip("_") .lower() in layout.lower() for f in fields[:1])
        print(f"  {cls:22s} {len(fields):2d} fields (+{skipped} skipped) "
              f"size 0x{isz:X}  {'ok' if ok else 'FAILED: ' + str(body.get('message'))[:70]}")
        if ok:
            made.append(cls)

    if not this_type:
        return
    print("\nthis-typing member functions (RTTI names the owner, so this is exact):")
    for cls in made:
        # Real symbols are dotted -- "AoWE.TUnit.GetDefense@23EDC2EF @ 55782a40".  The underscored
        # form seen in decompiler output is only a display name and matches nothing here.
        # Symbols are <DelphiUnit>.<Class>.<Method>@hash and the unit is NOT always AoWE --
        # the hexagon classes live in AoWHex, so match on the class component instead.
        raw = get(f"search_functions?name_pattern=.{cls}.&limit=500")
        try:
            fns = json.loads(raw)
            items = fns.get("result") or fns.get("functions") or []
            if isinstance(items, str):
                items = [l for l in items.splitlines() if l.strip()]
        except ValueError:
            items = [l for l in raw.splitlines() if " @ " in l]
        n = 0
        for it in items:
            if isinstance(it, dict):
                addr, nm = it.get("address"), it.get("name", "")
            else:
                parts = str(it).rsplit(" @ ", 1)
                if len(parts) != 2:
                    continue
                nm, addr = parts[0].strip(), parts[1].strip()
            # ⚠ the search is a SUBSTRING match, so "TUnit." also returns TAbstractUnit.* --
            # take only functions whose symbol names this EXACT class as the owner component
            parts = str(nm).split(".")
            if len(parts) < 3 or parts[1] != cls:
                continue
            # ⚠ NOT set_function_this_type: Delphi's `register` convention passes Self in EAX,
            # not ECX, so Ghidra sees no implicit `this` ("calling convention 'unknown'") and
            # that endpoint refuses. Self is simply parameter 0 -- type it directly.
            r = post("set_parameter_type", {"function_address": str(addr).strip(),
                                            "parameter_name": "param_1",
                                            "new_type": f"{cls} *"})
            # the endpoints answer as dict, nested-JSON string, or plain text depending on path
            if "success" in str(r).lower() and "error" not in str(r).lower():
                n += 1
        print(f"  {cls:22s} {n} function(s)")


TYPE_BY_SIZE_LEN = {"byte": 1, "ushort": 2, "byte[3]": 3, "undefined4": 4, "byte[6]": 6}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--apply", action="store_true", help="create the structs in Ghidra")
    ap.add_argument("--no-this", action="store_true", help="with --apply: skip this-typing")
    args = ap.parse_args()
    sizes, problems = check()
    n = sum(len(v) for v in FIELDS.values())
    ev = {}
    for rows in FIELDS.values():
        for *_x, e, _n in rows:
            ev[e] = ev.get(e, 0) + 1
    print(f"{len(FIELDS)} classes, {n} fields  evidence={ev}")
    print(f"bounds check: {len(problems)} problem(s)")
    for cls, off, msg in problems:
        loc = f"+0x{off:X}" if off is not None else "-"
        print(f"  {cls:22s} {loc:8s} {msg}")
    if args.md:
        p = os.path.join(GAME, "Modding Resources", "Ghidra_Field_Catalogue.md")
        emit_md(sizes, p)
        print(f"wrote {p}")
    if args.apply:
        print("\napplying to Ghidra:")
        apply_structs(sizes, this_type=not args.no_this)
        print("\ndone -- save the program in Ghidra.")


if __name__ == "__main__":
    main()
