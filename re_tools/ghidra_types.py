"""Engine enums, applied to the vanilla Ghidra image.

THIS FILE IS THE SOURCE.  Ghidra is the output -- see ../Ghidra_Annotations.md.  Re-running
it rebuilds every enum in a fresh project.

Only enums the docs record COMPLETELY (or completely enough to be safe) are here.  A partial
enum that looks whole is worse than none: a reader sees a gap and concludes the value is
unused, which is exactly the mistake `Ability_ID_Budget.md` warns about ("never treat an
apparent gap below 0xA9 as free").  Partial ones therefore carry a `_PARTIAL` suffix that
shows up at every use site, and the deliberately-omitted ones are listed at the bottom with
the reason.

⚠ Several values below are ZIGGURAT/mod meanings, not vanilla -- terrain 0x0B and 0x0E are
repurposed, and the rank ladder gained a copper tier.  Names say so.

Usage:
    python ghidra_types.py            # dry run
    python ghidra_types.py --apply    # create the enums in Ghidra
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

SERVER = os.environ.get("GHIDRA_MCP_URL", "http://127.0.0.1:8089")

# name -> (byte size, {MEMBER: value}, provenance)
ENUMS = {

    # ---- map / terrain -------------------------------------------------------------
    "TerrainID": (1, {
        "WATER": 0, "GRASS": 1, "DESERT": 2, "SNOW": 3, "STEPPE": 4, "WASTELAND": 5,
        "ICE": 6, "EARTH_WALL": 7, "ROCK_WALL": 8, "LAVA": 9, "CAVE_WATER": 0x0A,
        "CHASM_MOD_WAS_UWASTELAND": 0x0B, "CAVE_DIRT": 0x0C, "CAVE_ICE": 0x0D,
        "SKY_MOD_WAS_COAST": 0x0E, "BORDER": 0x0F,
    }, "Movement_Tables_Terrain_Types.md (the only complete copy; four other docs truncate it)"),

    "OverlayID": (1, {
        "NONE": 0xFF, "MOUNTAIN": 0, "FOREST": 1, "HILL": 2, "VEGETATION": 3, "ROAD": 4,
        "BRIDGE": 5, "RUBBLE": 6, "STRUCTURE": 7, "OBSTACLE": 8, "LIGHT_VEGETATION": 9,
        "SOLID_UNUSED": 0x0A, "OOZE": 0x0B, "FLYING_ONLY_RES_C": 0x0C,
        "RES_D_UNUSED": 0x0D, "RES_E_UNUSED": 0x0E,
    }, "Movement_Tables_Terrain_Types.md; column index = overlay+1, NONE is -1 as a signed byte"),

    "MoveTypeBits": (1, {
        "WALK": 0x01, "FLY": 0x02, "SWIM": 0x04, "FORESTRY": 0x08,
        "CAVE": 0x10, "MOUNTAINEER": 0x20, "FIRE": 0x40, "TUNNELING": 0x80,
    }, "Investigation_Path_Movement.md"),

    "MoveAbilityTable": (1, {
        "WALKING": 0, "SWIMMING": 1, "FLYING_AND_FLOATING": 2, "FORESTRY": 3,
        "CAVE_CRAWLING": 4, "MOUNTAINEERING": 5, "FIRE_IMMUNITY": 6, "TUNNELING": 7,
    }, "Chasm_Sky_Terrain_Design.md - base tables at 0x558E84FC + index*0x100"),

    "RoadConnectionMask": (1, {
        "DIR_1": 0x01, "DIR_2": 0x02, "DIR_3": 0x04, "DIR_4": 0x08, "DIR_5": 0x10,
        "DIR_6": 0x20, "STRAIGHT_3_5": 0x40, "STRAIGHT_2_6": 0x80,
    }, "Hex_Transition_System.md - road+0x10"),

    "BridgeEdgeCode": (1, {
        "NOTHING": 0, "DECK_OR_ROAD": 1, "BANK_RAMP": 2,
    }, "Hex_Transition_System.md - engine bridge, 2 bits per HN direction"),

    "HexBridgeAxis": (1, {
        "DIRS_1_4": 0, "DIRS_2_5": 1, "DIRS_3_6": 2, "NO_VALID_SPAN": 0xFF,
    }, "Hex_Transition_System.md - AoW hexagon bridge +0x11"),

    # ---- players / diplomacy -------------------------------------------------------
    "PlayerType": (1, {
        "HUMAN": 0, "CPU_WARRIOR": 1, "CPU_KNIGHT": 2, "CPU_LORD": 3,
        "INDEPENDENT": 4, "FREE": 5, "CPU_KING": 6, "CPU_EMPEROR": 7,
    }, "Inioch_MP_Race_Setup_Model.md; pid globals at 0x558E8E58 stride 8. player+0xA7"),

    "DiplomaticRelation": (1, {
        "FRIENDLY_ALLIED": 0, "HOSTILE": 1, "SELF": 2, "NEUTRAL": 3,
    }, "AI_Raze_Decision_CodeMap.md"),

    # ---- units ---------------------------------------------------------------------
    "UnitRank": (1, {
        "NONE": 0, "COPPER_MOD_ADDED": 1, "SILVER": 2, "GOLD": 3,
    }, "Copper_Medal_Design.md - MOD ladder; vanilla was None/Silver/Gold with no copper"),

    "BloodType": (1, {
        "NONE_SPLINTERS": 0, "RED": 1, "BLUE": 2, "GREEN": 3,
    }, "AoW1_Blood_Type_Reference_v5.md - vtable+0x110 GetBloodType"),

    "DamageTypeBits": (2, {
        "FIRE": 0x0001, "COLD": 0x0002, "LIGHTNING": 0x0004, "MAGIC": 0x0008,
        "POISON": 0x0010, "DEATH": 0x0020, "HOLY": 0x0040, "PHYSICAL": 0x0080,
    }, "Investigation_Combat.md"),

    "StatusAbilityID": (1, {
        "STUNNED": 0x5C, "CURSED": 0x5D, "ENTANGLED": 0x5E, "FROZEN": 0x5F,
        "POISONED": 0x60, "WEBBED": 0x61, "VERTIGO": 0x62, "BURNING_THAWED": 0x7F,
    }, "Investigation_Status_Debuff_StatModifiers.md - complete set of the status family"),

    "TAbilitySelectionTypes": (2, {
        "ABSTRACT_UNIT": 0x0001, "IT_HEAD": 0x0002, "IT_TORSO": 0x0004,
        "IT_ATTACK": 0x0008, "IT_DEFENSE": 0x0010, "IT_RING": 0x0020,
        "IT_USE": 0x0040, "HERO": 0x0200,
    }, "re_tools/abmask.py - read live from the VMTs, so engine-derived. Bits 7,8,10-15 "
       "unattested; BUILD-YOUR-MOD-MANUAL.md claims different meanings for 7-9, not used here"),

    # ---- items ---------------------------------------------------------------------
    "TItemTypes": (1, {
        "IT_HEAD": 0, "IT_TORSO": 1, "IT_ATTACK": 2, "IT_DEFENSE": 3,
        "IT_RING": 4, "IT_SCROLL": 5, "IT_USE": 6,
    }, "Investigation_Items.md - RTTI names at 0x55708C50, authoritative. item+0x34"),

    "EquipPosition": (1, {
        "ATTACK": 0, "HEAD": 1, "DEFENSE": 2, "RING": 3, "TORSO": 4, "RING_2ND": 5,
        "BACKPACK_0": 6, "BACKPACK_7": 13, "NONE": 0x0F,
    }, "Investigation_Items.md - position->type table at 0x558E8DB0. NOT the inverse of "
       "TItemTypes; the two tables differ"),

    # ---- magic ---------------------------------------------------------------------
    "MagicSphere": (1, {
        "COSMOS": 0, "LIFE": 1, "DEATH": 2, "EARTH": 3, "AIR": 4, "FIRE": 5, "WATER": 6,
    }, "Inioch_Sphere_Selection_Model.md - TMagicSphereRStr array at 0x558E8118"),

    "ResearchTier": (1, {
        "NOT_RESEARCHABLE": 0, "TIER_1": 1, "TIER_2": 2, "TIER_3": 3, "TIER_4": 4,
    }, "Spell_Research_System_2026-07-18.md - MOD feature; cost = 100 << (tier-1)"),

    "HeroLevelUpOption": (1, {
        "ATTACK": 0, "DEFENSE": 1, "RESISTANCE": 2, "DAMAGE": 3, "HITS": 4,
        "LEADERSHIP": 5, "FROST_BOLTS": 6, "SPELLCASTING": 7,
    }, "Investigation_Abilities_Leadership.md"),

    # ---- resources -----------------------------------------------------------------
    "ResourceClassID": (4, {
        "HEXAGON_RESOURCE": 0x20153, "ABSTRACT_ROAD": 0x20164, "TERRAIN_MO": 0x20167,
        "MOUNTAIN_MO": 0x20168, "RAISE_TERRAIN_ANIM": 0x2016A,
        "RAISED_MOUNTAIN": 0x2016B, "UNITGFX_CHILD": 0x20210, "UNITRES_CHILD": 0x20212,
        "UNIT": 0x20213, "HERO": 0x20230, "ITEM": 0x20268, "GUARD_AG": 0x21453,
    }, "assembled from BUILD-YOUR-MOD-MANUAL.md, Hex_Transition_System.md and others"),

    # ---- knowingly incomplete: the suffix is the warning ----------------------------
    "UnitType_PARTIAL": (1, {
        "HUMANOID_RACIAL": 0, "MONSTER_CREATURE": 1, "MACHINE": 2,
    }, "Investigation_Storm_Protections.md - unitres+0x30. Only 0-2 are named; the "
       "roster-filter bitset supports 0-7, so 3-7 exist unnamed"),

    "DecorationCategory_PARTIAL": (1, {
        "TREES": 0, "ROCKS": 1, "BONES": 2, "TOADSTOOLS": 4,
    }, "Inioch_PerHex_Decoration_And_Road_Cost.md - resource+0x44. Value 3 is missing "
       "from the record with no explanation"),

    "MapFieldMsgID_PARTIAL": (4, {
        "MAP_OBJECT_CLEARED_CELL": 0x10, "BATTLEFIELD_INFO_STRENGTH": 0x1108,
        "VISIBILITY_QUERY": 0x110A, "WALLED_TOWER_HEX": 0x1123, "ROAD_CONNECT": 0x1131,
        "ARMY_MAY_I_LEAVE": 0x1140, "ARMY_MAY_I_ENTER": 0x1141, "ARMY_ARRIVED": 0x1142,
        "STORM_DAMAGE_A": 0x1150, "STORM_DAMAGE_B": 0x1151, "AI_TARGET_DISCOVERY": 0x1200,
        "EDITOR_RESOURCE": 0x10005, "NEW_DAY": 0x20020001, "NEW_TURN": 0x20020002,
    }, "assembled from 12 docs; there is no single catalogue. 0x1107 and 0x1120 are seen "
       "but unnamed. The dispatcher lives in HSEPack.dpl, which Ghidra does not have"),
}

# Deliberately NOT created, with the reason.  Revisit only if the gap is closed.
OMITTED = {
    "AbilityID": "only ~100 of the real ids are named (the source list covers just the "
                 "hero-learnable ones with Ability.pfs tag 6). Ability_ID_Budget.md warns "
                 "outright: never read an apparent gap below 0xA9 as free.",
    "SpellID": "3 of 108 ids are named anywhere; the game files store no spell names.",
    "TCombatResult": "the docs disagree on polarity -- Raze_CombatPredictor_Analysis.md has "
                     "3 = attacker wiped, Arena_Rework_Feasibility.md has 3 = attacker won, "
                     "and the predictor was side-swapped by an earlier mod. One enum applied "
                     "to both classes would encode the wrong answer at half the sites.",
    "Alignment": "only {0,1}=good and {4,5}=evil recorded; 2 and 3 undefined.",
    "UnitSize": "Investigation_Combat.md (VMT+0x90, values ~1-5) and the blood-type doc "
                "(VMT+0x178, values 0-3) cannot both be right, and the former flags it as "
                "an open question.",
}


def request(path, payload):
    req = urllib.request.Request(
        f"{SERVER}/{path}", data=json.dumps(payload).encode("utf8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf8", "replace"))
    except urllib.error.URLError as e:
        sys.exit(f"Ghidra MCP not reachable at {SERVER} ({e}). Start Ghidra and enable GhidraMCP.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = sum(len(v[1]) for v in ENUMS.values())
    print(f"{len(ENUMS)} enums, {total} members  ({len(OMITTED)} deliberately omitted)")
    for name, (size, values, why) in sorted(ENUMS.items()):
        print(f"  {name:32s} {size}B  {len(values):3d} members")
        if not args.apply:
            continue
        res = request("create_enum", {"name": name, "size": size,
                                      "values": json.dumps(values)})
        body = res.get("result", res)
        if isinstance(body, str):
            body = json.loads(body)
        status = body.get("status", "?")
        if status != "success":
            print(f"      FAILED: {body.get('message') or body}")

    if not args.apply:
        print("\ndry run -- nothing created.  Use --apply.")
        print("\nomitted on purpose:")
        for name, why in OMITTED.items():
            print(f"  {name}: {why.splitlines()[0]}")
    else:
        print("\ndone -- save the program in Ghidra.")


if __name__ == "__main__":
    main()
