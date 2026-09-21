# 5% conversion — itemised inventory of doubled ATK / DEF / RES sources

**GENERATED FILE — do not hand-edit.** Rendered from `build_scripts/fivepct_manifest.json` by
`build_scripts/gen_doubled_inventory.py`; re-run it after any manifest change.
Companion to `FivePct_Conversion_Manifest.md`, which holds the decisions and the traps.

**CONFIRMED WORKING (2026-08-24)** — applied 2026-08-20, validated in-game by the user.

| | ATK | DEF | RES | total |
|---|---|---|---|---|
| code immediates doubled | 117 | 18 | 30 | 167 |
| `.pfs` data bytes doubled | 217 | 217 | 217 | 651 |
| skill-point prices **halved** | 2 | 2 | 2 | 6 |

(The two `NO-DOUBLE` rows inside stage 11 are Turn Undead's rounding addends, which move with
its `shr` and are not stats. Counts above exclude them from ATK/DEF/RES.)

## Stage 1 — Base stats, clamps and caps (16)

*unit/hero stat ceilings and the AI's stat thresholds.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55782a1b` | ATK | 20 → 40 | TUnit.GetAttack ORIGINAL tail clamp — currently DEAD CODE, must be mirrored |
| `AoWEPACK.dpl` | `0x55782a83` | DEF | 30 → 60 | TUnit.GetDefense upper clamp |
| `AoWEPACK.dpl` | `0x55782b2b` | RES | 30 → 60 | TUnit.GetResistance upper clamp — NOT in the original audit |
| `AoWEPACK.dpl` | `0x55786cd3` | SKILL-POINT-PRICE (halved) | 6 → 3 | THero.UsedSkillPoints — ATTACK skill-point price (second copy of the SetUnitAttack price) |
| `AoWEPACK.dpl` | `0x55786cda` | SKILL-POINT-PRICE (halved) | 12 → 6 | THero.UsedSkillPoints — DEFENCE skill-point price |
| `AoWEPACK.dpl` | `0x55786cee` | SKILL-POINT-PRICE (halved) | 4 → 2 | THero.UsedSkillPoints — RESISTANCE skill-point price |
| `AoWEPACK.dpl` | `0x557877d8` | ATK | 30 → 60 | THero.SetUnitAttack — cap on (base ATK + bought ATK) |
| `AoWEPACK.dpl` | `0x557877f2` | ATK (halved) | 6 → 3 | THero.SetUnitAttack — skill-point cost per +1 ATK |
| `AoWEPACK.dpl` | `0x55787824` | DEF | 20 → 40 | THero.SetUnitDefense — cap on (base DEF + bought DEF). ⚠ THE BRIEF IS WRONG: live is 20, n |
| `AoWEPACK.dpl` | `0x5578783e` | DEF (halved) | 12 → 6 | THero.SetUnitDefense — skill-point cost per +1 DEF |
| `AoWEPACK.dpl` | `0x55787954` | RES | 20 → 40 | THero.SetUnitResistance — cap on (base RES + bought RES). DECISION REQUIRED |
| `AoWEPACK.dpl` | `0x5578796e` | RES (halved) | 4 → 2 | THero.SetUnitResistance — skill-point cost per +1 RES. DECISION REQUIRED (RES doubles) |
| `AoWEPACK.dpl` | `0x55787a64` | ATK | 10 → 20 | THero.ExecuteUpgradeHeroAI — ATK stat threshold ('upgrade ATK only while total ATK < N') |
| `AoWEPACK.dpl` | `0x55787a89` | DEF | 10 → 20 | THero.ExecuteUpgradeHeroAI — DEF stat threshold |
| `AoWEPACK.dpl` | `0x55787ab1` | RES | 10 → 20 | THero.ExecuteUpgradeHeroAI — RES stat threshold |
| `AoWEPACK.dpl` | `0x5580c133` | ATK | 20 → 40 | TUnit.GetAttack upper clamp (LIVE copy, inside Ziggurat cave 0x5580C0F7) |

## Stage 2 — `.pfs` unit and hero base stats

*%s.* Written by `build_statdouble.py` as in-place 1-byte pokes, CRC repaired after.
Tag → field mapping verified from `THeroResource.ReadWrite @0x55789FD4` and cross-checked
against its `UsedSkillPoints` cost multipliers.

| file | records | ATK tag | DEF tag | RES tag | bytes |
|---|---|---|---|---|---|
| `Unitres.pfs` | 179 | `0x0E` | `0x0F` | `0x13` | 537 |
| `HERORES.PFS` | 38 | `0x0F` | `0x10` | `0x14` | 114 |

⚠ **`HERORES.PFS` ATTACK has since been doubled AGAIN** by
`build_hero_chassis_atkdam.py` (2026-08-20, a deliberate balance change on top of this
conversion), together with chassis DAMAGE. So its ATK column reads 4..16, not the 2..8
stage 2 left. See `Hero_Chassis_ATK_DAM_Double.md` — **it also fixes the undo order.**

Verification without the game: **every one of those 651 bytes is now even.** A single odd
value would prove the doubling incomplete, because the pre-conversion tables contained odd
values throughout.

## Stage 3 — Ability and enchantment stat modifiers (18)

*the buff/debuff stack on `PassiveAb.*`.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x557b9cc9` | RES | 2 → 3 | PassiveAb.TNaturesBlessingAbility.GetResistance |
| `AoWEPACK.dpl` | `0x557b9db5` | ATK | 2 → 3 | PassiveAb.TBloodlustAbility.GetAttack |
| `AoWEPACK.dpl` | `0x557b9db9` | DEF | -1 → -2 | PassiveAb.TBloodlustAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557b9e6a` | ATK | -2 → -3 | PassiveAb.TPoisonedAbility.GetAttack — OR-FORM, needs re-encoding |
| `AoWEPACK.dpl` | `0x557b9fed` | DEF | -2 → -4 | PassiveAb.TEntangledAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557ba0b5` | DEF | 2 → 3 | PassiveAb.TFrozenAbility.GetDefense (Ziggurat flipped the sign vs vanilla) |
| `AoWEPACK.dpl` | `0x557ba321` | DEF | -2 → -4 | PassiveAb.TWebbedAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557ba551` | DEF | -2 → -4 | PassiveAb.TStunnedAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557bac5d` | ATK | -2 → -3 | PassiveAb.TVertigoAbility.GetAttack |
| `AoWEPACK.dpl` | `0x557bac61` | DEF | -2 → -3 | PassiveAb.TVertigoAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557bad91` | DEF | -2 → -4 | PassiveAb.TCursedAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557bad95` | RES | -2 → -4 | PassiveAb.TCursedAbility.GetResistance |
| `AoWEPACK.dpl` | `0x557baf41` | DEF | 2 → 3 | PassiveAb.TStoneSkinAbility.GetDefense |
| `AoWEPACK.dpl` | `0x557bb0ed` | ATK | 2 → 3 | PassiveAb.TEnchantedWeaponAbility.GetAttack |
| `AoWEPACK.dpl` | `0x557bb35d` | ATK | 3 → 5 | PassiveAb.TFuryAbility.GetAttack |
| `AoWEPACK.dpl` | `0x557bb362` | DEF | -1 → -2 | PassiveAb.TFuryAbility.GetDefense — OR-FORM, needs re-encoding |
| `AoWEPACK.dpl` | `0x557bb5e9` | RES | 2 → 3 | PassiveAb.TBlessedEnchantment.GetResistance |
| `AoWEPACK.dpl` | `0x557bb811` | RES | 1 → 3 | PassiveAb.THighPrayerBlessingAbility.GetResistance |

## Stage 4 — Effect-roll powers vs Resistance (17)

*the attack side of every resistance check.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55766914` | RES | 5 → 10 | Strike side-effect roll 1 power (attacker must have ability id 0x33, target must NOT have  |
| `AoWEPACK.dpl` | `0x5576694e` | RES | 7 → 14 | Strike side-effect roll 2 power (gated on attacker ability id 0x77; roll is power − TComba |
| `AoWEPACK.dpl` | `0x55780beb` | RES | 4 → 8 | TAbstractUnit.ExecuteLifeMasteryFearRole power (vs vmt+0xCC GetResistance) |
| `AoWEPACK.dpl` | `0x55780cb3` | RES | 6 → 12 | TAbstractUnit.ExecuteDeathMasteryCurseRole power (vs vmt+0xCC GetResistance) |
| `AoWEPACK.dpl` | `0x55781c20` | RES | 2 → 4 | Protection bonus #1 — `add edi,2` on the saved RES when the unit carries the matching prot |
| `AoWEPACK.dpl` | `0x55781c31` | RES | 5 → 10 | Effect-roll power #1 (mask bit si&1, ability-immunity id 7) |
| `AoWEPACK.dpl` | `0x55781c80` | RES | 2 → 4 | Protection bonus #2 — `add edi,2` (pairs with power #2) |
| `AoWEPACK.dpl` | `0x55781c91` | RES | 5 → 10 | Effect-roll power #2 (mask bit si&4, ability-immunity id 9; extra alignment gate vmt+0x114 |
| `AoWEPACK.dpl` | `0x55781cd2` | RES | 2 → 4 | Protection bonus #3 — `add edi,2` (pairs with power #3) |
| `AoWEPACK.dpl` | `0x55781ce3` | RES | 5 → 10 | Effect-roll power #3 (mask bit si&0x10, ability-immunity id 0xA) |
| `AoWEPACK.dpl` | `0x55781d24` | RES | 2 → 4 | Protection bonus #4 — `add edi,2` (pairs with power #4) |
| `AoWEPACK.dpl` | `0x55781d35` | RES | 5 → 10 | Effect-roll power #4 (mask bit si&0x20, ability-immunity id 0xB) |
| `AoWEPACK.dpl` | `0x55781d76` | RES | 2 → 4 | Protection bonus #5 — `add edi,2` (pairs with power #5) |
| `AoWEPACK.dpl` | `0x55781d87` | RES | 5 → 10 | Effect-roll power #5 (mask bit si&0x40, ability-immunity id 0xC; extra alignment gate vmt+ |
| `AoWEPACK.dpl` | `0x55781dd6` | RES | 2 → 4 | Protection bonus #6 — `add edi,2` (pairs with power #6) |
| `AoWEPACK.dpl` | `0x55781de7` | RES | 5 → 10 | Effect-roll power #6 (mask bit si&2, ability-immunity id 8) |
| `AoWEPACK.dpl` | `0x557ba464` | RES | 10 → 20 | PassiveAb.TBurningAbility.NewCombatTurn power (vs vmt+0xCC GetResistance of the burning un |

## Stage 5 — Touch attacks (12)

*`GetTouchAttack` on the touch abilities.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55769be9` | ATK | 7 → 14 | TPossessAbility.GetTouchAttack (VMT slot +0x10C; TPossessedAbility shares this override) |
| `AoWEPACK.dpl` | `0x5576a20d` | ATK | 7 → 14 | TWebAbility.GetTouchAttack |
| `AoWEPACK.dpl` | `0x5576a811` | ATK | 7 → 14 | TEntangleAbility.GetTouchAttack |
| `AoWEPACK.dpl` | `0x5576b203` | ATK | 9 → 18 | TTurnUndeadAbility.GetTouchAttack — level I arm |
| `AoWEPACK.dpl` | `0x5576b206` | ATK | 10 → 20 | TTurnUndeadAbility.GetTouchAttack — level II arm |
| `AoWEPACK.dpl` | `0x5576b209` | ATK | 11 → 22 | TTurnUndeadAbility.GetTouchAttack — level III arm |
| `AoWEPACK.dpl` | `0x5576b20c` | ATK | 12 → 24 | TTurnUndeadAbility.GetTouchAttack — level IV arm |
| `AoWEPACK.dpl` | `0x5576b20f` | ATK | 4 → 8 | TTurnUndeadAbility.GetTouchAttack — DEFAULT arm (level 0 or >4) |
| `AoWEPACK.dpl` | `0x5576b84d` | ATK | 9 → 18 | TInvokeDeathAbility.GetTouchAttack |
| `AoWEPACK.dpl` | `0x55770665` | ATK | 5 → 10 | TDominateAbility.GetTouchAttack |
| `AoWEPACK.dpl` | `0x55770799` | ATK | 5 → 10 | TCharmAbility.GetTouchAttack |
| `AoWEPACK.dpl` | `0x55770979` | ATK | 5 → 10 | TSeduceAbility.GetTouchAttack |

## Stage 6 — Strategic-map hazards (12)

*storms, grounds, fire, vortex, quake, poison.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x5578074b` | ATK | 8 → 16 | Ice Storm — ATTACK (EBP), storm index 4 |
| `AoWEPACK.dpl` | `0x55780757` | ATK | 8 → 16 | Lightning Storm — ATTACK (EBP), storm index 5 |
| `AoWEPACK.dpl` | `0x55780763` | ATK | 8 → 16 | Death Storm — ATTACK (EBP), storm index 2 |
| `AoWEPACK.dpl` | `0x5578076f` | ATK | 8 → 16 | Divine Storm — ATTACK (EBP), storm index 3 |
| `AoWEPACK.dpl` | `0x5578077b` | ATK | 8 → 16 | Fire Storm — ATTACK (EBP), storm index 1 |
| `AoWEPACK.dpl` | `0x55780787` | ATK | 7 → 14 | Pestilence — ATTACK (EBP), storm index 6 |
| `AoWEPACK.dpl` | `0x5579021d` | ATK | 6 → 12 | Map fire — ATTACK (TArmy.TriggerFireDamage @0x55790110) |
| `AoWEPACK.dpl` | `0x557a1645` | ATK | 8 → 16 | Vortex — ATTACK (TVortexTE.Process @0x557A13CC) |
| `AoWEPACK.dpl` | `0x557b1ce8` | ATK | 7 → 14 | Town quake — ATTACK (TTownQuake.TriggerArmyDamage) |
| `AoWEPACK.dpl` | `0x557c4172` | ATK | 6 → 12 | Poison plant — ATTACK (TPoisonPlant.TriggerArmyDamage) |
| `AoWEPACK.dpl` | `0x557c7f5b` | ATK | 6 → 12 | Holy ground — ATTACK (THolyGround.TriggerArmyDamage @0x557C7E18) |
| `AoWEPACK.dpl` | `0x557c90c8` | ATK | 6 → 12 | Unholy ground — ATTACK (TUnHolyGround.TriggerArmyDamage @0x557C8FA4) |

## Stage 7 — Combat-spell powers (32)

*`TCombatSpell+0x34`, the spell's attack stat.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x557f7abd` | ATK | 8 → 16 | TSolarFlare combat-spell power — TCombatSpell+0x34, spell id 0x64. Opposed to target DEFEN |
| `AoWEPACK.dpl` | `0x557f7bf9` | ATK | 12 → 24 | TTurnUndead combat-spell power — +0x34, spell id 0x65. Opposed to RESISTANCE (TTurnUndead. |
| `AoWEPACK.dpl` | `0x557f7f5d` | ATK | 6 → 12 | THighPrayer combat-spell power — +0x34, spell id 0x66. +0x3c=0 → DEFENCE. Inert for the ca |
| `AoWEPACK.dpl` | `0x557f8311` | ATK | 4 → 8 | TDeathRay combat-spell power — +0x34, spell id 0x67. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f83c9` | ATK | 7 → 14 | TDiseaseCloud combat-spell power — +0x34, spell id 0x68. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f8581` | ATK | 6 → 12 | CombatSpells.TMindDecay.Create — spell attack stat at object field +0x34; read by TMindDec |
| `AoWEPACK.dpl` | `0x557f86fd` | ATK | 7 → 14 | TChainLightning combat-spell power — +0x34, spell id 0x6B. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f87b9` | ATK | 12 → 24 | TColdBreath combat-spell power — +0x34, spell id 0x6C. +0x3c=0 → DEFENCE. (The worked exam |
| `AoWEPACK.dpl` | `0x557f88f1` | ATK | 9 → 18 | CombatSpells.TSlow.Create — spell attack stat +0x34; read by TSlow.CreateCA @0x557F89D1 ag |
| `AoWEPACK.dpl` | `0x557f8ac9` | ATK | 7 → 14 | CombatSpells.TEntangle.Create — spell attack stat +0x34; read by TEntangle.CreateCA @0x557 |
| `AoWEPACK.dpl` | `0x557f8cac` | ATK | 7 → 14 | TTremors combat-spell power — +0x34, spell id 0x70. +0x3c=0 → DEFENCE. (Note: TTremors.Cre |
| `AoWEPACK.dpl` | `0x557f8d45` | ATK | 6 → 12 | TCallFlames combat-spell power — +0x34, spell id 0x71. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f8e01` | ATK | 12 → 24 | TFireBreath combat-spell power — +0x34, spell id 0x72. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f8ebd` | ATK | 5 → 10 | TSwarm combat-spell power — +0x34, spell id 0x73. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f8f79` | ATK | 5 → 10 | TGreatHail combat-spell power — +0x34, spell id 0x74. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f9035` | ATK | 10 → 20 | TFireBall combat-spell power — +0x34, spell id 0x75. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f90ed` | ATK | 9 → 18 | TGeyser combat-spell power — +0x34, spell id 0x76. Opposed to DEFENCE (TGeyser.CreateCA ca |
| `AoWEPACK.dpl` | `0x557f9251` | ATK | 5 → 10 | TIceShards combat-spell power — +0x34, spell id 0x77. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f9309` | ATK | 7 → 14 | TFrostBeams combat-spell power — +0x34, spell id 0x78. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f93c9` | ATK | 12 → 24 | TVaporize combat-spell power — +0x34, spell id 0x79. Opposed to RESISTANCE (TVaporize.Crea |
| `AoWEPACK.dpl` | `0x557f9481` | ATK | 2 → 4 | TStoning combat-spell power — +0x34, spell id 0x7A. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f9539` | ATK | 8 → 16 | TFlamingArrow combat-spell power — +0x34, spell id 0x7B. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f9719` | ATK | 6 → 12 | TSacredWrath combat-spell power — +0x34, spell id 0x7D. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557f9887` | ATK | 8 → 16 | CombatSpells.TFastCombatTerrorCA.Generate — Terror's HARD-CODED power (copy 2 of 3), auto- |
| `AoWEPACK.dpl` | `0x557f9a0b` | ATK | 8 → 16 | CombatSpells.TTacticalCombatTerrorCA.Generate — Terror's HARD-CODED power (copy 3 of 3), t |
| `AoWEPACK.dpl` | `0x557f9a81` | ATK | 8 → 16 | CombatSpells.TTerror.Create — spell attack stat +0x34 (copy 1 of 3; must move with the two |
| `AoWEPACK.dpl` | `0x557f9ca6` | ATK | 8 → 16 | ⭐⭐ TTerror power copy 4/5 — NEW, NOT in the audit. Hard-coded 8 inside TTerror.fcGetDamage |
| `AoWEPACK.dpl` | `0x557f9d8f` | ATK | 8 → 16 | ⭐⭐ TTerror power copy 5/5 — NEW, NOT in the audit. Hard-coded 8 inside TTerror.tcGetDamage |
| `AoWEPACK.dpl` | `0x557f9e61` | ATK | 8 → 16 | TWindsOfFury combat-spell power — +0x34, spell id 0x7E. Opposed to DEFENCE (CreateCA calls |
| `AoWEPACK.dpl` | `0x557f9f06` | ATK | 2 → 4 | ⭐⭐ TWindsOfFury conditional ATTACK bonus +2 — NEW, NOT in the audit and not part of the +0 |
| `AoWEPACK.dpl` | `0x557f9fb9` | ATK | 7 → 14 | TShockwave combat-spell power — +0x34, spell id 0x7F. +0x3c=0 → DEFENCE. |
| `AoWEPACK.dpl` | `0x557fa071` | ATK | 8 → 16 | TSacrificialFlame combat-spell power — +0x34, spell id 0x80. +0x3c=0 → DEFENCE. |

## Stage 8 — Champion / slaying bonuses and ranged attack constants (21)

*conditional ATK and the innate ranged attacks.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55766524` | ATK | 2 → 5 | Holy Champion (ability 0x92 / enchantment 0xA0) ATK bonus vs evil alignment |
| `AoWEPACK.dpl` | `0x5576655f` | ATK | 2 → 5 | Unholy Champion (ability 0x93 / enchantment 0xA1) ATK bonus vs good alignment |
| `AoWEPACK.dpl` | `0x5576658c` | ATK | 3 → 5 | Monster Slaying (attacker 0x70) vs Dragon (target 0x3F) ATK bonus |
| `AoWEPACK.dpl` | `0x5576665f` | ATK | 2 → 4 | Holy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x5576669b` | ATK | 2 → 4 | Unholy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x557678c8` | ATK | 2 → 5 | Holy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x55767903` | ATK | 2 → 5 | Unholy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x5576792c` | ATK | 3 → 5 | Monster Slaying ATK bonus (LIVE here — this copy was never cave-hooked) |
| `AoWEPACK.dpl` | `0x55767c1c` | ATK | 2 → 5 | Holy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x55767c57` | ATK | 2 → 5 | Unholy Champion ATK bonus |
| `AoWEPACK.dpl` | `0x5576f55d` | ATK | 7 → 14 | Shoot Javelin — ranged attack constant (ability id 0x39) |
| `AoWEPACK.dpl` | `0x5576f59c` | ATK | 4 → 8 | Shoot Black Javelin — ranged attack constant (ability id 0x3A) |
| `AoWEPACK.dpl` | `0x5576f5db` | ATK | 2 → 4 | Hurl Stones — ranged attack constant (ability id 0x19) |
| `AoWEPACK.dpl` | `0x5576f61a` | ATK | 5 → 10 | Fire Musket — ranged attack constant (ability id 0x2D) |
| `AoWEPACK.dpl` | `0x5576f659` | ATK | 4 → 8 | Fire Cannon — ranged attack constant (ability id 0x2C) |
| `AoWEPACK.dpl` | `0x5576f698` | ATK | 4 → 8 | Hurl Boulder — ranged attack constant (ability id 0x18) |
| `AoWEPACK.dpl` | `0x5576f6d7` | ATK | 6 → 12 | Venomous Spit — ranged attack constant (ability id 0x3E) |
| `AoWEPACK.dpl` | `0x5576f716` | ATK | 5 → 10 | Call Flames — ranged attack constant (ability id 0x1F) |
| `AoWEPACK.dpl` | `0x5576f755` | ATK | 3 → 6 | Archery — ranged attack constant (ability id 0x16) |
| `AoWEPACK.dpl` | `0x5576f794` | ATK | 3 → 6 | Poison Darts — ranged attack constant (ability id 0x3D) |
| `AoWEPACK.dpl` | `0x5576f7d3` | ATK | 3 → 6 | Doom Gaze — ranged attack constant (ability id 0x37) |

## Stage 9 — Tactical combat (`AoWTCPCK.dpl`) (4)

*the manual-combat wall and terrain values.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWTCPCK.dpl` | `0x405ad8` | DEF | -2 → -4 | CityWall.TCityWall.GetDefense — wall DEFENCE in MANUAL TACTICAL combat |
| `AoWTCPCK.dpl` | `0x41093f` | DEF | -2 → -4 | CombatTerrain.TCombatTerrain — object DEFENCE field [this+0x20], initialised in Activate |
| `AoWTCPCK.dpl` | `0x4671a4` | ATK | 6 → 12 | AoWTC.TCAttack[0] — attack of tactical Wall Crushing (ability 0x75) against a TCityWall |
| `AoWTCPCK.dpl` | `0x4671a8` | ATK | 10 → 20 | AoWTC.TCAttack[1] — attack of a burning fire hex (per combat turn) against walls, terrain  |

## Stage 10 — Walls, Parry, wall-crushing, self-destruct, default units (27)

*the remainder found by audit.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x55725c09` | RES | 3 → 6 | AoWE.TCombatWall.GetResistance — walls have a hard-coded RESISTANCE of 3 |
| `AoWEPACK.dpl` | `0x5576788b` | ATK | 4 → 8 | Parry (defender ability 0x71) — reduces the ATTACKER's attack |
| `AoWEPACK.dpl` | `0x55767be3` | ATK | 4 → 8 | Parry (defender ability 0x71) — reduces the ATTACKER's attack |
| `AoWEPACK.dpl` | `0x55768608` | ATK | 6 → 12 | TWallCrushingAbility.GetDamageValue — ATTACK arg to AoWE.StatisticsToLimitedDV (AI/UI dama |
| `AoWEPACK.dpl` | `0x55768679` | ATK | 6 → 12 | TWallCrushingAbility.GetDamageValueEx — ATTACK arg to StatisticsToLimitedDV. AUDIT-MISSED. |
| `AoWEPACK.dpl` | `0x55768758` | ATK | 6 → 12 | TWallCrushingAbility.fcGetDamageValueEx — ATTACK arg to StatisticsToLimitedDV. AUDIT-MISSE |
| `AoWEPACK.dpl` | `0x55768838` | ATK | 6 → 12 | TWallCrushingAbility.tcGetDamageValueEx — ATTACK arg to StatisticsToLimitedDV (tactical-co |
| `AoWEPACK.dpl` | `0x557688ae` | ATK | 6 → 12 | AoWE.TWallCrushingAbility.GetCombatInfo — ATTACK 6, the auto-resolve twin of AoWTC.TCAttac |
| `AoWEPACK.dpl` | `0x557688f8` | ATK | 6 → 12 | TWallCrushingAbility.fcExecuteCombatCommand — the ATTACK argument to AoWE.CreateDamageCA ( |
| `AoWEPACK.dpl` | `0x55768ba8` | ATK | 8 → 16 | TSelfDestructAbility.GetDamageValue — ATTACK arg to StatisticsToLimitedDV. AUDIT-MISSED. |
| `AoWEPACK.dpl` | `0x55768c4d` | ATK | 8 → 16 | TSelfDestructAbility.GetDamageValueEx — ATTACK arg to StatisticsToLimitedDV. AUDIT-MISSED. |
| `AoWEPACK.dpl` | `0x55768d5c` | ATK | 8 → 16 | TSelfDestructAbility.fcGetDamageValueEx — ATTACK arg to StatisticsToLimitedDV. AUDIT-MISSE |
| `AoWEPACK.dpl` | `0x55768dea` | ATK | 8 → 16 | TSelfDestructAbility.GetCombatInfo — record field 1 = ATTACK |
| `AoWEPACK.dpl` | `0x55768e21` | ATK | 8 → 16 | TSelfDestructAbility.GetOffensiveStrength — ATTACK factor of the AI valuation |
| `AoWEPACK.dpl` | `0x55781b83` | RES | 2 → 4 | TAbstractUnit.ExecuteResistanceRole `sub edi,2` — protection reduces the caller-supplied p |
| `AoWEPACK.dpl` | `0x55783748` | ATK | 4 → 8 | MakeDefaultLevelUnit tier 1 (dl==1) — ATTACK. Field +0x3C on class TAdjustableUnit. |
| `AoWEPACK.dpl` | `0x5578374c` | DEF | 2 → 4 | MakeDefaultLevelUnit tier 1 (dl==1) — DEFENCE. Field +0x3D on TAdjustableUnit. |
| `AoWEPACK.dpl` | `0x55783750` | RES | 3 → 6 | MakeDefaultLevelUnit tier 1 (dl==1) — RESISTANCE. Field +0x3E on TAdjustableUnit. |
| `AoWEPACK.dpl` | `0x55783784` | ATK | 5 → 10 | MakeDefaultLevelUnit tier 2 (dl==2) — ATTACK. |
| `AoWEPACK.dpl` | `0x55783788` | DEF | 3 → 6 | MakeDefaultLevelUnit tier 2 (dl==2) — DEFENCE. |
| `AoWEPACK.dpl` | `0x5578378c` | RES | 3 → 6 | MakeDefaultLevelUnit tier 2 (dl==2) — RESISTANCE. |
| `AoWEPACK.dpl` | `0x557837bd` | ATK | 6 → 12 | MakeDefaultLevelUnit tier 3 (dl==3) — ATTACK. |
| `AoWEPACK.dpl` | `0x557837c1` | DEF | 3 → 6 | MakeDefaultLevelUnit tier 3 (dl==3) — DEFENCE. |
| `AoWEPACK.dpl` | `0x557837c5` | RES | 4 → 8 | MakeDefaultLevelUnit tier 3 (dl==3) — RESISTANCE. |
| `AoWEPACK.dpl` | `0x55783800` | ATK | 6 → 12 | MakeDefaultLevelUnit default branch (dl not in 1..3) — ATTACK. |
| `AoWEPACK.dpl` | `0x55783804` | DEF | 3 → 6 | MakeDefaultLevelUnit default branch — DEFENCE. |
| `AoWEPACK.dpl` | `0x55783808` | RES | 4 → 8 | MakeDefaultLevelUnit default branch — RESISTANCE. |

## Stage 11 — Ziggurat cave constants (13)

*constants owned by five feature build scripts, not by the manifest.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x5580e09e` | ATK | 3 → 6 | Monster Slaying ATK bonus (the LIVE replacement for the dead block at 0x557666C7) |
| `AoWEPACK.dpl` | `0x5580e0cf` | ATK | 3 → 6 | Assassin (attacker ability 0x38) vs hero-class target ATK bonus |
| `AoWEPACK.dpl` | `0x5580e148` | ATK | 3 → 6 | Monster Slaying ATK bonus (the LIVE replacement for the dead block at 0x55767C82) |
| `AoWEPACK.dpl` | `0x5580e17e` | ATK | 3 → 6 | Assassin ATK bonus |
| `AoWEPACK.dpl` | `0x5580e1c7` | ATK | 1 → 2 | Monster Slaying (0x70 vs target marker 0x3F) — ranged ATK +1 |
| `AoWEPACK.dpl` | `0x5580e207` | ATK | 1 → 2 | Holy Champion (0x92 or enchantment 0xA0, vs EVIL target) — ranged ATK +1 |
| `AoWEPACK.dpl` | `0x5580e245` | ATK | 1 → 2 | Unholy Champion (0x93 or enchantment 0xA1, vs GOOD target) — ranged ATK +1 |
| `AoWEPACK.dpl` | `0x5580e290` | ATK | 1 → 2 | Assassin (0x38, vs hero target) — ranged ATK +1 |
| `AoWEPACK.dpl` | `0x5580e2b5` | NO-DOUBLE | 1 → 2 | Turn Undead COMBAT damage cave (build_turnundead_res.py cave_turnundead_dmg @0x5580E2A0, h |
| `AoWEPACK.dpl` | `0x5580e33c` | NO-DOUBLE | 1 → 2 | Turn Undead INFO-CARD display cave (build_turnundead_res.py cave_combatinfo @0x5580E300, j |
| `AoWEPACK.dpl` | `0x5580e398` | ATK | 1 → 2 | Invisible target + attacker lacking True Seeing (0x29) -> melee ATK penalty; reached from  |
| `AoWEPACK.dpl` | `0x5580e3d8` | ATK | 1 → 2 | Same rule, 32-bit accumulator; reached from cave B, resumes into CalculateStrikes' chain |
| `AoWEPACK.dpl` | `0x5580e42c` | ATK | 3 → 6 | Invisible-target ranged ATK penalty (−3), attacker lacking True Vision |

## Stage 12 — Underground ranged malus (1)

*its own stage so it can be written without touching stage 11.*

| module | immediate VA | stat | change | site |
|---|---|---|---|---|
| `AoWEPACK.dpl` | `0x5580c287` | ATK | 2 → 4 | Underground/Cave ranged ATK malus (−2, waived by Night Vision 0x27) |


## What was NOT doubled, and why

Two different reasons. Neither is an oversight; both are recorded decisions.

### Deliberate exceptions — decision D2 (user, 2026-08-18)

> *"Do NOT double: items, medal ranks, morale, Leadership."* These four **become half as influential**
> relative to everything else. That was the point of the exception, not a side effect.

| source | where | live values | effect |
|---|---|---|---|
| **Item bonuses** | `Release/ITEMS.PFS` tags `0x0B` ATK / `0x0C` DEF / `0x0E` RES — 23 / 28 / 23 bytes | 1..3 | a `+2 ATK` sword is now worth `+1` on the doubled scale |
| **Medal rank bonuses** | `AoWE.AttackRankProgression` `0x558E83C8` = `[0,1,2,3]`, `DefenseRankProgression` `0x558E83C4` = `[0,0,0,1]`, `ResistanceRankProgression` `0x558E83D0` = `[0,1,2,3]` | 0..3 | gold medal gives half its former weight |
| **Morale modifiers** | `AoWE.MoraleResistanceModifier` `0x558E83D8` = `[-3,-2,-1,0]`, `MoraleDefenseModifier` `0x558E83E0` = `[-2,-1,0,0]`, plus the morale→ATK bands in cave `0x5580C0F7` (`0x5580C115`, `0x5580C119`) | -3..0 | morale swings matter half as much |
| **Leadership** | the vanilla exports `LeadershipAttackProgression` `0x558E83E8` / `LeadershipDefenseProgression` `0x558E83EC` are **dead** — `build_leadership4.py` repointed `GetAttack`/`GetDefense`'s disp32 to its own 5-byte tables at **`0x5580F0C0` / `0x5580F0C8`**, indexed by level | ATK `1,2,3,4`<br>DEF `1,2,3,4` | not doubled, but **re-tuned 2026-08-20** to a flat +5/+10/+15/+20 pp ramp (was ATK `1,1,2,2` / DEF `0,1,1,2`) — level IV now matches vanilla Leadership's effective strength |

⚠ **Leadership's live curve is the one D2 exception you can still tune freely** — it is data, owned by
`build_leadership4.py` (`ATK_BONUS` / `DEF_BONUS`), and that script re-tunes in place: edit and re-run
with `--apply`, no revert. The other three exceptions are not so easy.
⚠ The three rank tables and the two morale tables are **owned by `build_copper_medal.py`**
(its `STAT_TABLES`), not by `build_statdouble.py`. If D2 is ever reversed, double them there — and add
the current tuning to that script's `PRIOR_TUNINGS` — or its verify will refuse.
⚠ The rank tables are live: read at `0x557829DD`/`0x557829F9` (`TUnit.GetAttack`),
`0x55782A31`/`0x55782A4D` (`GetDefense`), `0x55782B11` (`GetResistance`).

### Undecided — `HEROES.PFS`

`Release/HEROES.PFS` is the library of 50 predefined heroes. `THero.ReadWrite @0x55788880` maps
tag `0x10` = `bAtk_bonus`, `0x11` = `bDef_bonus`, `0x15` = `bRes_bonus` — **39 / 37 / 32 bytes, values
1..3, currently un-doubled.** `build_statdouble.py` records this as *"a separate decision that has not
been taken"*, distinct from the D2 item exception.

It matters because D3+D4 make heroes *"a pure identity"* (costs halve, caps double). A library hero's
stored bonus is stat points, so leaving it un-doubled makes predefined heroes start 1..3 points short on
the doubled scale. Small, but it is the one place where a stated decision and the installed state disagree.
⚠ `HEROES.PFS` and `ITEMS.PFS` carry **no PFS magic and no CRC** — never run the CRC repair over them;
appending one destroys four bytes of real data.

### Correctly untouched

Damage, hit points and movement are not ATK/DEF/RES and must not double, or the identity breaks:
`AoWE.DamageRankProgression` `0x558E83CC` = `[0,0,1,1]`, `HitsRankProgression` `0x558E83D4` (dead),
the `.pfs` damage tags (`ITEMS.PFS 0x0D`, `HEROES.PFS 0x12`), and every `add [esp],1` damage addend in
the stage-11 caves. Probabilities expressed in percent do not double either — including the flat
10% auto-miss / auto-max bands of `ExecuteDamageRole`, which are `RandInt(20)` thresholds.

### How to check the data side without the game

**Parity.** Every doubled `.pfs` stat byte is even; the pre-conversion tables were full of odd values.

| file | ATK/DEF/RES odd values | reading |
|---|---|---|
| `Unitres.pfs` | 0 / 0 / 0 | doubled |
| `HERORES.PFS` | 0 / 0 / 0 | doubled |
| `ITEMS.PFS` | 18 / 20 / 21 | not doubled (D2, intended) |
| `HEROES.PFS` | 37 / 33 / 30 | not doubled (undecided) |

