# AoWEPACK.dpl VMT layouts — DERIVED, not hand-written

Produced 2026-08-03 by 18 parallel agents walking each class's VMT and resolving every slot to its real RTTI symbol. **No slot here is a guess.**

## ⭐ The finding that makes this cheap: the DLL exports its whole symbol table

`AoWEPACK.dpl` is a Delphi 3 runtime **package**, and its `.edata` exports **10,036 named symbols** covering essentially every method. The export directory *is* a complete symbol table, parseable straight out of the file — **you do not need Ghidra to name a VMT slot.** Map slot -> target VA -> export name.

Corollaries worth knowing:

- **Slots that look nameless in Ghidra are import thunks.** e.g. 12 of `TAbstractUnit`'s slots point at `FF 25 <iat>` jumps in a thunk table around `0x557030xx`; Ghidra defines no function there, so a Ghidra-only walk reports them blank. Resolving the IAT names them — all 12 are `Engine.TEObject` methods in **EngineP.dpl**.
- **The class hierarchy leaves this module.** `TAbstractUnit -> TAbilityOwner -> TCustomAbilityList -> Engine.TEObject`, and that last one is imported, so a naive parent-walk stops at `TCustomAbilityList`.
- **A VMT's end is detectable**: the first slot that does not point into CODE. The class-name ShortString usually sits immediately after, so the 'pointer' reads as ASCII.

## ⚠ Delphi 3 negative VMT header — `Destroy` is at a NEGATIVE offset

```
-0x40 vmtSelfPtr    -0x20 vmtClassName   -0x1C vmtInstanceSize   -0x18 vmtParent
-0x14 SafeCallException   -0x10 DefaultHandler   -0x0C NewInstance
-0x08 FreeInstance        -0x04 Destroy
```

**If you are hooking a destructor, it is at `VMT-0x04`, not in the positive slot table.** Delphi 3 has no AfterConstruction/BeforeDestruction/Dispatch entries (unlike Delphi 4+).

## ⚠ Abstract stubs return 0 — overriding them is the whole point

On `TAbstractUnit`, `+0xA8..+0xB4` (GetInherent*) and `+0xC0..+0xD4` (GetAttack/GetDefense/GetDamage/GetResistance/GetHits/GetMoves) plus `+0x114`, `+0x128`, `+0x12C`, `+0x134` are 4-byte `33 C0 C3 90` (`xor eax,eax; ret`) stubs; `+0x130 SetCastingPoints` is a bare `ret`. They exist to be overridden by `TUnit`/`THero`.

## ⚠ The combat ability slots are NOT uniformly nil-safe — `+0xB0` only behind `+0xA8`

On `TCombatUnit` the ability accessors all reach the strategic unit through `[combatobj+0x4C]`,
but only some of them check it first (live bytes, byte-identical to pristine — vanilla design):

```
55725004  +0xA8 GetAbilityEnabled:  mov ecx,[eax+0x4C] / test ecx,ecx / je -> return 0   GUARDED
55725028  +0xB0 GetAbilityLevel:    mov eax,[eax+0x4C] / mov ecx,[eax] / call [ecx+0x144]  NOT
55725034  +0xB4 GetAbilityCount:    mov edx,[eax+0x4C] / test edx,edx / je -> return 0    GUARDED
```

**A nil `[combatobj+0x4C]` is therefore a normal engine state, not corruption** — the engine only
ever reaches `+0xB0` behind a `+0xA8` test. The rule for our caves: **call `GetAbilityLevel`
(`+0xB0`) only directly behind a `GetAbilityEnabled` (`+0xA8`) gate on the same object in the same
function.** A gate set in an earlier function (a flag stashed in `Generate` and read in `Execute`)
does not count — by then the attacker may have died or detached. Walls are safe automatically:
`TCombatObject.GetAbilityOwner @0x557268D0` / `GetAbilityEnabled @0x557268D4` /
`GetAbilityLevel @0x557268DC` are all `xor eax,eax; ret`.

Audited 2026-08-28: our only ungated `+0xB0` is the vanilla dispatch at `0x5576B56C` that
`build_turnundead_res.py` reads (safe today — a Turn Undead attacker is never a wall — but it is
the Generate/Execute shape, so re-timing that ability re-opens it). `build_arena.py:676` also
calls `[ecx+0xB0]`, but on the army/unit-list class, where the slot means something else entirely.
Item-facing detail in `Investigation_Items.md` §3.3d.

## Extents

| class | VMT | instance size | VMT ends | slots |
|---|---|---|---|---|
| `AoWE.TPlayer` | `0x5570C508` | `0xDC` | `0x4C` | 19 |
| `AoWE.TSpell` | `0x55722D7C` | `0x34` | `0x9C` | 44 |
| `AoWHex.TAoWWaterHexagon` | `0x5579A5F8` | `0x20` | `0x128` | 74 |
| `TAbility` | `0x5570F254` | `0x24` | `0x10C` | 67 |
| `TAbstractUnit` | `0x55710740` | `0x3C` | `0x1B8` | 110 |
| `TAoWHSMap` | `0x5570E874` | `0x41C` | `0x130` | 76 |
| `TAoWHexagon` | `0x5579A1D0` | `0x14` | `0x124` | 73 |
| `TArena` | `557D6240` | `0x30` | `0x1F0` | 124 |
| `TCombatObject` | `0x557158EC` | `0x4C` | `0x134` | 77 |
| `TCombatUnit` | `0x55715A94` | `0x5C` | `0x13C` | 79 |
| `TExplorationSite` | `0x557C1440` | `0x38` | `0x204` | 129 |
| `THero` | `0x55711FEC` | `0x9C` | `0x1C8` | 114 |
| `TItem` | `0x5570FAFC` | `0x4C` | `0xB4` | 45 |
| `TRangedAttackAbility` | `0x5571E8D4` | `0x30` | `0x120` | 72 |
| `TStrikeCA` | `0x5571E344` | `0x1C` | `0x70` | 28 |
| `TStructure` | `0x55713C18` | `0x30` | `0x1F0` | 124 |
| `TUnit` | `0x55710CAC` | `0x48` | `0x1B8` | 110 |
| `TUnitResource` | `0x55710A64` | `0x54` | `0x74` | 29 |

## AoWE.TPlayer  —  VMT `0x5570C508`, instance `0xDC`, 19 slots, ends `0x4C`

<details><summary>derivation notes</summary>

```
VMT = 0x5570C508 .. 0x5570C553 inclusive. 19 virtual slots (+0x00..+0x48); first offset past the end is +0x4C.

WHY +0x4C IS THE END (three independent proofs, not just "pointer looks wrong"):
1. [VMT+0x4C] = 0x0000000E, not a CODE pointer (CODE = 0x55701000-0x558E7918).
2. vmtInitTable at [VMT-0x34] = 0x5570C554 = VMT+0x4C exactly, i.e. the compiler placed the field-init table immediately after the last VMT slot. That 0x0E is tkRecord, the InitTable's kind byte.
3. TPlayer's parent Engine.TEObject also has a 19-slot VMT: of 86 direct TEObject descendants in AoWEPACK, 60 end at exactly +0x4C. TPlayer declares NO new virtual methods at all — it only overrides existing TEObject slots.

TPlayer OVERRIDES exactly 5 methods (4 in the positive VMT + Destroy at -0x04): ReadWrite, Create, ClassID, MsgProc, Destroy. Everything else is an inherited Engine.TEObject jmp-thunk. All 14 inherited slots resolve to `jmp dword ptr [IAT]` stubs importing from EngineP.dpl; names taken from the PE import-name table (ground truth, not inference), and independently corroborated by counting how many sibling classes leave each slot un-overridden: +0x18 ReadWrite x163, +0x1C MainReadWrite x706, +0x20 Create x65, +0x24 ClassID x357, +0x44 MsgProc x546, +0x48 SetArrayOwner x722.

NEGATIVE (metadata + the 5 standard Delphi virtuals). NOTE these are real callable slots and one of them is a TPlayer override:
  -0x40 vmtSelfPtr        = 0x5570C508  (equals the VMT address itself - this is what pins the base)
  -0x3C vmtIntfTable      = 0
  -0x38 vmtAutoTable      = 0
  -0x34 vmtInitTable      = 0x5570C554
  -0x30 vmtTypeInfo       = 0
  -0x2C vmtFieldTable     = 0
  -0x28 vmtMethodTable    = 0
  -0x24 vmtDynamicTable   = 0
  -0x20 vmtClassName      = 0x5570C57E -> ShortString 07 "TPlayer"
  -0x1C vmtInstanceSize   = 0xDC (220)
  -0x18 vmtParent         = 0x558FC92C -> IAT slot, EngineP.dpl :: "Engine..TEObject@BD8FE92F"
  -0x14 SafeCallException = 0x557010C8 -> VCL30.dpl :: System.TObject.SafeCallException@23EDC2EF
  -0x10 DefaultHandler    = 0x557010D0 -> VCL30.dpl :: System.TObject.DefaultHandler@23EDC2EF
  -0x0C NewInstance       = 0x55701098 -> VCL30.dpl :: System.TObject.NewInstance@23EDC2EF
  -0x08 FreeInstance      = 0x557010A0 -> VCL30.dpl :: System.TObject.FreeInstance@23EDC2EF
  -0x04 Destroy           = 0x55751154 -> AoWE.TPlayer.Destroy@23EDC2EF  *** TPlayer OVERRIDE ***

⚠ CORRECTION TO THE VMT RECIPE IN THE BRIEF (worth propagating to the docs). The recipe given ([VMT-0x20]=name, [VMT-0x1C]=instsize, [VMT-0x18]=parent) is CORRECT for this binary, but it is NOT the textbook Delphi 3 layout (which puts ClassName at -12 and the standard virtuals at POSITIVE 0..28). AoWEPACK uses the older Delphi 2-style layout: the 5 standard TObject virtuals sit at NEGATIVE -0x14..-0x04 and user-declared virtuals start at +0x00. Verified empirically, so the project's convention is safe to keep:
  - vmtSelfPtr is at -0x40 and holds the VMT address itself. This is a self-checking fingerprint: scanning CODE for "dword at A whose value == A+0x40" enumerates every VMT in the module (found 893 classes) with zero false positives. That is a better VMT finder than the string search, and it needs no class name.
  - Destroy landing at exactly -0x04 (canonical vmtDestroy for this layout) confirms the base independently.
If the textbook Delphi 3 constants had been used, every offset in this project's docs would be shifted by 0x14. They are not.

PARENT CHAIN STOPS HERE: TPlayer's immediate parent Engine.TEObject lives in EngineP.dpl, which is NOT loaded in Ghidra, so the chain above TEObject cannot be walked from this module. TEObject's own 19 virtual methods are fully named above regardless (from the import table), so the whole inherited surface is known even though the ancestor's binary is absent.

BONUS - managed fields, derived from the InitTable at 0x5570C554 (kind=0x0E tkRecord, count=4). TPlayer has exactly 4 compiler-managed AnsiString fields (typeinfo = VCL30.dpl :: 
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | Engine.TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | Engine.TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | Engine.TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | Engine.TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x18` | `0x5575314C` | `AoWE.TPlayer.ReadWrite@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.ReadWrite) |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | Engine.TEObject |
| `0x20` | `0x55750EA8` | `AoWE.TPlayer.Create@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.Create) |
| `0x24` | `0x557516C8` | `AoWE.TPlayer.ClassID@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.ClassID) |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | Engine.TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | Engine.TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | Engine.TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | Engine.TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | Engine.TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | Engine.TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | Engine.TEObject |
| `0x44` | `0x55752F08` | `AoWE.TPlayer.MsgProc@23EDC2EF` | AoWE.TPlayer (OVERRIDE of Engine.TEObject.MsgProc) |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | Engine.TEObject |

## AoWE.TSpell  —  VMT `0x55722D7C`, instance `0x34`, 44 slots, ends `0x9C`

<details><summary>derivation notes</summary>

```
DERIVATION (all VAs at the DPL's preferred base 0x55700000; the module rebases at runtime).

VMT LOCATION. Class-name ShortString "\x06TSpell" at 0x55722E2A; the only dword pointing at it is
at 0x55722D5C, so VMT = 0x55722D5C + 0x20 = 0x55722D7C. Cross-checked against the self-pointer:
[VMT-0x40] == 0x55722D7C == VMT itself. Ghidra's read_memory at 0x55722D7C byte-for-byte matches
Modding Resources/AoWEPACK_original_backup.dpl, so file and Ghidra image agree.

VMT HEADER (Delphi 3, 64-byte header — CONFIRMED empirically by the imported symbol names, not
assumed). Layout verified as:
  -0x40 SelfPtr        = 0x55722D7C  (points at the VMT)
  -0x3C IntfTable      = 0
  -0x38 AutoTable      = 0
  -0x34 InitTable      = 0x55722E18
  -0x30 TypeInfo       = 0
  -0x2C FieldTable     = 0
  -0x28 MethodTable    = 0
  -0x24 DynamicTable   = 0   <- no dynamic methods; every virtual is in the table above
  -0x20 ClassName      = 0x55722E2A
  -0x1C InstanceSize   = 0x34 (52 bytes)
  -0x18 Parent         = 0x558FC92C
  -0x14 SafeCallException / -0x10 DefaultHandler / -0x0C NewInstance / -0x08 FreeInstance
  -0x04 Destroy        = 0x557791F4 = AoWE.TSpell.Destroy  (TSpell overrides the destructor)
Note the ordering: vmtDestroy is at -0x04, NOT at +0x08. The four System.TObject slots at
-0x14..-0x08 name themselves via the import table, which pins the whole header layout.

ANCESTRY. [VMT-0x18] = 0x558FC92C is an .idata (IAT) slot, i.e. the parent classref is IMPORTED:
EngineP.dpl!Engine..TEObject@BD8FE92F. So the chain is
  System.TObject -> Engine.TEObject (EngineP.dpl) -> AoWE.TSpell
with NO intermediate class. TSpell is a DIRECT descendant of TEObject.

INHERITED SLOTS ARE IMPORT THUNKS. Because TEObject lives in another package, every inherited slot
points at an 8-byte thunk in this module's CODE section of the form
  FF 25 <abs IAT>   jmp dword ptr [imp]      (+ 8B C0 padding)
e.g. +0x00 -> 0x55703074 = "jmp [0x558FC724]" -> EngineP.dpl!Engine.TEObject.ClassVersion.
Ghidra has no function objects at these thunk addresses (get_function_by_address returns "No
function found"), so the names above were resolved by walking this DLL's import descriptors and
reading the IMAGE_IMPORT_BY_NAME entry each IAT slot references. That is ground truth, not a guess.
IMPORTANT FOR HOOKING: patching a 557030xx thunk changes that call for EVERY AoWEPACK class that
inherits the slot, not just TSpell. Redirect the VMT slot itself, not the thunk.

TEObject's own VMT is exactly 0x4C bytes (19 slots, +0x00..+0x48). TSpell's newly-introduced
virtuals therefore start at +0x4C. The base names for slots +0x00..+0x48 were confirmed by scanning
all 893 VMTs in the module, taking the 86 that are direct TEObject descendants, and reading the
un-overridden thunk in each slot — every one of the 19 slots is left un-overridden by at least one
sibling, so all 19 names are directly observed. In particular this pins the two slots TSpell
overrides: +0x18 = TEObject.ReadWrite (51 of 86 siblings override it) and +0x20 = TEObject.Create
(64 of 86 override it, it is a virtual constructor).

END OF VMT. [VMT+0x9C] = 0x0000000E, which is not in the executable range (CODE = 0x55701000..
0x558E7A00) — so the VMT is 39 slots, +0x00..+0x98, ending at +0x9C. This is not a heuristic stop:
0x55722D7C + 0x9C = 0x55722E18, which is exactly the value of the InitTable pointer at [VMT-0x34].
The InitTable record begins there (its first dword 0x0000000E is a type-kind tag), so the VMT ends
where the init table begins. Nothing follows the VMT that could be mistaken for a 40th slot.

MEMBERS THAT ARE NOT VIRTUAL. Ghidra's symbol table lists 28 AoWE.TSpell.* methods; 22 of them
(plus Destroy) appear above. The six that are NOT in the VMT are non-virtual/static methods and
cannot be hooked by slot replacement:
  0x557797A0 AICastSpellExpenseMade     0x557796E4 AIRequestCastSpellExpense
  0x557794BC CastingDone                0x557794E8 CombatCastingDone
  0x5577954C CombatSpellCast
(DynamicTable is nu
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `-0x14` | `0x557010C8` | `System.TObject.SafeCallException@23EDC2EF` | System.TObject |
| `-0x10` | `0x557010D0` | `System.TObject.DefaultHandler@23EDC2EF` | System.TObject |
| `-0x0C` | `0x55701098` | `System.TObject.NewInstance@23EDC2EF` | System.TObject |
| `-0x08` | `0x557010A0` | `System.TObject.FreeInstance@23EDC2EF` | System.TObject |
| `-0x04` | `0x557791F4` | `AoWE.TSpell.Destroy@23EDC2EF` | AoWE.TSpell |
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | Engine.TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | Engine.TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | Engine.TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | Engine.TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | Engine.TEObject |
| `0x18` | `0x55779234` | `AoWE.TSpell.ReadWrite@23EDC2EF` | AoWE.TSpell |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | Engine.TEObject |
| `0x20` | `0x55779178` | `AoWE.TSpell.Create@23EDC2EF` | AoWE.TSpell |
| `0x24` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | Engine.TEObject |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | Engine.TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | Engine.TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | Engine.TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | Engine.TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | Engine.TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | Engine.TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | Engine.TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | Engine.TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | Engine.TEObject |
| `0x4C` | `0x5577956C` | `AoWE.TSpell.PlayDefaultCastEffects@23EDC2EF` | AoWE.TSpell |
| `0x50` | `0x55779670` | `AoWE.TSpell.ExecuteTE@23EDC2EF` | AoWE.TSpell |
| `0x54` | `0x557796C4` | `AoWE.TSpell.CreateCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x58` | `0x557796D4` | `AoWE.TSpell.SetupCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x5C` | `0x55779824` | `AoWE.TSpell.AIPrefetchCastSpellActions@23EDC2EF` | AoWE.TSpell |
| `0x60` | `0x55779828` | `AoWE.TSpell.AIExecuteCastSpellAction@23EDC2EF` | AoWE.TSpell |
| `0x64` | `0x55779230` | `AoWE.TSpell.GetEnabled@23EDC2EF` | AoWE.TSpell |
| `0x68` | `0x557792D0` | `AoWE.TSpell.CanActivate@23EDC2EF` | AoWE.TSpell |
| `0x6C` | `0x55779354` | `AoWE.TSpell.Activate@23EDC2EF` | AoWE.TSpell |
| `0x70` | `0x557793A4` | `AoWE.TSpell.CanActivateCombat@23EDC2EF` | AoWE.TSpell |
| `0x74` | `0x557793B4` | `AoWE.TSpell.ActivateCombat@23EDC2EF` | AoWE.TSpell |
| `0x78` | `0x55779450` | `AoWE.TSpell.CreateCA@23EDC2EF` | AoWE.TSpell |
| `0x7C` | `0x5577945C` | `AoWE.TSpell.GetCombatInfo@23EDC2EF` | AoWE.TSpell |
| `0x80` | `0x5577948C` | `AoWE.TSpell.GetCombatDamageValue@23EDC2EF` | AoWE.TSpell |
| `0x84` | `0x55779490` | `AoWE.TSpell.GetCombatDamageValueEx@23EDC2EF` | AoWE.TSpell |
| `0x88` | `0x5577969C` | `AoWE.TSpell.tcGetDamageValueEx@23EDC2EF` | AoWE.TSpell |
| `0x8C` | `0x557796B8` | `AoWE.TSpell.tcGetDamageValue@23EDC2EF` | AoWE.TSpell |
| `0x90` | `0x55779694` | `AoWE.TSpell.fcPrefetchCombatCommands@23EDC2EF` | AoWE.TSpell |
| `0x94` | `0x55779698` | `AoWE.TSpell.fcExecuteCombatCommand@23EDC2EF` | AoWE.TSpell |
| `0x98` | `0x5577967C` | `AoWE.TSpell.fcGetDamageValueEx@23EDC2EF` | AoWE.TSpell |

## AoWHex.TAoWWaterHexagon  —  VMT `0x5579A5F8`, instance `0x20`, 74 slots, ends `0x128`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
VMT located by the RTTI recipe on Modding Resources\AoWEPACK_original_backup.dpl: exactly ONE dword in the image points at the ShortString "TAoWWaterHexagon" (@0x5579A720), so VMT = that dword's VA + 0x20 = 0x5579A5F8. No ambiguity. Cross-checked with Ghidra read_memory at 0x5579A5F8 len 304 — Ghidra's bytes are byte-identical to the file-derived table, so both views agree.
VMT file offset (preferred base 0x55700000, CODE VA 0x55701000 / raw 0x400): 0x999F8. VMT slot N is at file offset 0x999F8 + N.

END OF VMT
74 slots, +0x000..+0x124 inclusive; first non-CODE dword is at +0x128 = 0x6F415410, which is the class's OWN name ShortString (10 "TAoWWaterHexagon" — 0x5579A5F8+0x128 = 0x5579A720, exactly the vmtClassName target). So vmt_end = 0x128 and it is self-evidently the end, not a guess.

*** ALMOST EVERY SLOT IS AN IMPORT THUNK, NOT LOCAL CODE ***
Only 5 slots point at real AoWEPACK code. The other 69 point at 6-byte `jmp dword ptr [IAT]` stubs inside AoWEPACK whose IAT entry names the implementing package. I resolved every one through AoWEPACK's import directory (name table), which is why the symbols are exact rather than inferred. Ghidra has no function defined at some of these stubs (e.g. 0x5579A148, 0x5579A140) — get_function_by_address returns "No function found" there; the import-table walk is the reliable resolver.
Module map for the symbols above (derivable from the unit prefix):
  Engine.*    -> EngineP.dpl
  HSEngine.*  -> HSEPack.dpl
  IsoHex.*    -> HSEPack.dpl
  AoWHex.*    -> local, inside AoWEPACK.dpl (the 5 own overrides)
The three IsoHex thunks sit next to the VMT rather than in the module-wide thunk block: 0x5579A148 = jmp [0x558FCD58] (DynamicIsometricHexagonClass), 0x5579A150 = jmp [0x558FCD54] (Disconnect), 0x5579A158 = jmp [0x558FCD50] (NeighbourTerrainChanged).
PATCHING IMPLICATION: to change inherited behaviour for water hexagons only, overwrite the VMT slot (file offset 0x999F8+N) — do NOT patch the thunk, it is shared by other classes, and do not expect the implementation to be in AoWEPACK at all.

THE 5 SLOTS TAoWWaterHexagon ACTUALLY IMPLEMENTS (all local AoWEPACK code, Ghidra-symbolled)
  +0x020 Create            0x5579AD40  body 5579AD40-5579AD8F  (TAoWWaterHexagon*, char)
  +0x024 ClassID           0x5579AD90  body 5579AD90-5579AD95  (6 bytes: mov eax,0002073D; ret -> ClassID = 0x2073D)
  +0x0A8 Show              0x5579AEAC  body 5579AEAC-5579AFB1
  +0x11C UpdateTransitions 0x5579AD98  body 5579AD98-5579AEAB
  +0x124 ShowDynamic       0x5579AFB4  body 5579AFB4-5579B54E  (by far the largest — the water animation path)

ANCESTOR CHAIN (derived, not assumed — walked through HSEPack.dpl's own VMTs; the vmtParent field at VMT-0x18 is an .idata slot = import 'IsoHex..TLowerIsometricHexagon@D76F96D2' from HSEPack.dpl)
  TEObject (EngineP.dpl)
    -> HSEngine.THexagonSprite        VMT 0x55603694  instsize 0x08  vmt_end +0x108
    -> HSEngine.TMapObject            VMT 0x55604190  instsize 0x10  vmt_end +0x11C
    -> HSEngine.TAbstractHexagon      VMT 0x556047CC  instsize 0x10  vmt_end +0x120
    -> IsoHex.TIsometricHexagon       VMT 0x556190D8  instsize 0x18  vmt_end +0x128
    -> IsoHex.TLowerIsometricHexagon  VMT 0x55619640  instsize 0x18  vmt_end +0x128
    -> AoWHex.TAoWWaterHexagon        VMT 0x5579A5F8  instsize 0x20  vmt_end +0x128
(HSEPack VAs are at HSEPack.dpl's own preferred base, a different module.)
Consequences worth recording:
- TAoWWaterHexagon introduces NO new virtual methods — its vmt_end equals its parent's (0x128). All 5 local slots are overrides.
- Slot ownership boundaries: TAbstractHexagon's VMT ends at +0x120, so +0x11C (UpdateTransitions) is the last slot it declares; TIsometricHexagon adds +0x120 (DynamicIsometricHexagonClass) and +0x124 (ShowDynamic).
- TLowerIsometricHexagon contributes ZERO slots to this VMT even though it is the direct parent: it exports overrides of ClassID, UpdateTransitions and ShowDynamic, and TAoWWaterHexagon re-overrides all th
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557021F4` | `HSEngine.TMapObject.ReadWrite@23EDC2EF` | TMapObject |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5579AD40` | `AoWHex.TAoWWaterHexagon.Create@23EDC2EF` | TAoWWaterHexagon |
| `0x24` | `0x5579AD90` | `AoWHex.TAoWWaterHexagon.ClassID@23EDC2EF` | TAoWWaterHexagon |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557021B4` | `HSEngine.TMapObject.GetTerrain@23EDC2EF` | TMapObject |
| `0x50` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x557021CC` | `HSEngine.TMapObject.GetOverlay@23EDC2EF` | TMapObject |
| `0x5C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x557022FC` | `HSEngine.TAbstractHexagon.GetLevel@23EDC2EF` | TAbstractHexagon |
| `0x68` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702164` | `HSEngine.TMapObject.GetXhx@23EDC2EF` | TMapObject |
| `0x78` | `0x5570216C` | `HSEngine.TMapObject.GetYhx@23EDC2EF` | TMapObject |
| `0x7C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x55701DC4` | `HSEngine.THexagonSprite.GetXYL@23EDC2EF` | THexagonSprite |
| `0x84` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557022F4` | `HSEngine.TAbstractHexagon.GetShowPriority@23EDC2EF` | TAbstractHexagon |
| `0x90` | `0x55702214` | `HSEngine.TMapObject.Connect@23EDC2EF` | TMapObject |
| `0x94` | `0x5579A150` | `IsoHex.TIsometricHexagon.Disconnect@23EDC2EF` | TIsometricHexagon |
| `0x98` | `0x55701E24` | `HSEngine.THexagonSprite.CanChangeTerrain@23EDC2EF` | THexagonSprite |
| `0x9C` | `0x5570231C` | `HSEngine.TAbstractHexagon.ChangeTerrain@23EDC2EF` | TAbstractHexagon |
| `0xA0` | `0x55702324` | `HSEngine.TAbstractHexagon.TerrainChanged@23EDC2EF` | TAbstractHexagon |
| `0xA4` | `0x5579A158` | `IsoHex.TIsometricHexagon.NeighbourTerrainChanged@23EDC2EF` | TIsometricHexagon |
| `0xA8` | `0x5579AEAC` | `AoWHex.TAoWWaterHexagon.Show@23EDC2EF` | TAoWWaterHexagon |
| `0xAC` | `0x5570222C` | `HSEngine.TMapObject.PlaceOnMap@23EDC2EF` | TMapObject |
| `0xB0` | `0x55702234` | `HSEngine.TMapObject.RemoveFromMap@23EDC2EF` | TMapObject |
| `0xB4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55702224` | `HSEngine.TMapObject.Loaded@23EDC2EF` | TMapObject |
| `0xCC` | `0x5570233C` | `HSEngine.TAbstractHexagon.MapFieldMsgProc@23EDC2EF` | TAbstractHexagon |
| `0xD0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x55702314` | `HSEngine.TAbstractHexagon.Activate@23EDC2EF` | TAbstractHexagon |
| `0xE4` | `0x55702254` | `HSEngine.TMapObject.Deactivate@23EDC2EF` | TMapObject |
| `0xE8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55701D44` | `HSEngine.THexagonSprite.UpdateMapField@23EDC2EF` | THexagonSprite |
| `0xF0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557021A4` | `HSEngine.TMapObject.CanSelect@23EDC2EF` | TMapObject |
| `0xFC` | `0x557021E4` | `HSEngine.TMapObject.Select@23EDC2EF` | TMapObject |
| `0x100` | `0x557021EC` | `HSEngine.TMapObject.Unselect@23EDC2EF` | TMapObject |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x5570230C` | `HSEngine.TAbstractHexagon.SetResource@23EDC2EF` | TAbstractHexagon |
| `0x114` | `0x5570232C` | `HSEngine.TAbstractHexagon.CanPlace@23EDC2EF` | TAbstractHexagon |
| `0x118` | `0x55702334` | `HSEngine.TAbstractHexagon.PlaceHX@23EDC2EF` | TAbstractHexagon |
| `0x11C` | `0x5579AD98` | `AoWHex.TAoWWaterHexagon.UpdateTransitions@23EDC2EF` | TAoWWaterHexagon |
| `0x120` | `0x5579A148` | `IsoHex.TIsometricHexagon.DynamicIsometricHexagonClass@23EDC2EF` | TIsometricHexagon |
| `0x124` | `0x5579AFB4` | `AoWHex.TAoWWaterHexagon.ShowDynamic@23EDC2EF` | TAoWWaterHexagon |

## TAbility  —  VMT `0x5570F254`, instance `0x24`, 67 slots, ends `0x10C`

<details><summary>derivation notes</summary>

```
DERIVATION / GROUND TRUTH
Source bytes: "Modding Resources/AoWEPACK_original_backup.dpl" (same image Ghidra holds as AoWEPACK_vanilla.dpl). Preferred base 0x55700000; the DPL rebases at runtime, so treat VAs as base+RVA.

RTTI header (Delphi 3 layout, all verified empirically, not assumed):
  [VMT-0x40] 0x5570F254 = self-pointer (equals the VMT VA -> confirms VMT location)
  [VMT-0x34] 0x5570F360 = init table  == VMT+0x10C  (see END-OF-VMT proof)
  [VMT-0x20] 0x5570F372 -> ShortString 08 "TAbility"
  [VMT-0x1C] 0x00000024 = instance size (36 bytes)
  [VMT-0x18] 0x558FC92C = .idata cell "EngineP.dpl!Engine..TEObject@BD8FE92F"
  [VMT-0x14] 0x557010C8 -> thunk VCL30.dpl!System.TObject.SafeCallException
  [VMT-0x10] 0x557010D0 -> thunk VCL30.dpl!System.TObject.DefaultHandler
  [VMT-0x0C] 0x55701098 -> thunk VCL30.dpl!System.TObject.NewInstance
  [VMT-0x08] 0x557010A0 -> thunk VCL30.dpl!System.TObject.FreeInstance
  [VMT-0x04] 0x5574E65C = AoWE.TAbility.Destroy@23EDC2EF  <-- REAL OVERRIDE, lives outside the 0x00+ walk. Anyone hooking TAbility destruction must patch -0x04, not a positive slot.

ANCESTRY: TAbility's immediate parent is Engine.TEObject in EngineP.dpl. There is NO intermediate class inside AoWEPACK. TEObject itself is not in this module, so its own VMT cannot be walked here.

END-OF-VMT PROOF (three independent lines):
 1. VMT+0x10C reads 0x0000000E, not a CODE pointer.
 2. vmtInitTable ([VMT-0x34]) == 0x5570F360 == VMT+0x10C exactly -> the class's data tables begin where the VMT ends; 0x0E is the tkRecord type-kind byte of that init table.
 3. Descendant cross-check: TDurationAbility (VMT 0x5571DD68, instsize 0x2C, parent TAdjustableAbility) reproduces slots 0x00..0x108 with identical semantics (overriding some) and then adds TDurationAbility.GetDuration at +0x10C and TDurationAbility.GetTotalDuration at +0x110, ending at 0x114. So 0x108 is genuinely TAbility's last slot.

HOW SYMBOLS WERE RESOLVED
- Delphi packages export every method; I parsed AoWEPACK.dpl's export directory (10036 names / 10033 distinct VAs) into a VA->symbol map. That is the same source Ghidra derives its names from. Spot-checked against Ghidra get_function_by_address for 0x5574E65C, 0x5574F07C, 0x5574E978 -> exact match.
- The 17 inherited slots do NOT point at AoWEPACK code: they hold 6-byte `jmp dword ptr [IAT]` thunks in the cluster 0x55703074..0x55703104 (8-byte stride). Ghidra has no function objects there (get_function_by_address returns "No function found"), so these resolve only through the import table. The `target_va` I report is the thunk address inside AoWEPACK; the `symbol` is the imported EngineP.dpl method it forwards to.

TRAP FOR FUTURE WORK: the thunk cluster contains 19 TEObject thunks but only 17 appear in TAbility's VMT. Engine.TEObject.ReadWrite (thunk 0x557030FC) and Engine.TEObject.Copy (thunk 0x557030CC) are absent — ReadWrite because TAbility overrides that slot (its thunk is the `inherited` call; confirmed in the decompile of TAbility.ReadWrite, which calls Engine_TEObject_ReadWrite first), Copy because it is called non-virtually elsewhere in the module. Do NOT infer VMT membership from membership of the thunk cluster.

TWO OVERRIDES IN THE INHERITED REGION: +0x018 (ReadWrite) and +0x020 (Create, a virtual constructor). Every other slot in 0x00..0x048 is a straight TEObject passthrough.

TAbility INTRODUCES 48 NEW VIRTUALS: +0x04C through +0x108 inclusive. All 67 slots resolved to a real symbol; none unnamed.

STUB WARNING: several targets are 3-4 byte default stubs, e.g. AbilityDataClass at 0x5574E978 has body 0x5574E978-0x5574E97A (3 bytes, Ghidra-confirmed), and 0x5574E990/994/998/99C/9A0 (GetAttack/GetDefense/GetResistance/GetDamage/GetMoveTypes) sit 4 bytes apart — base implementations that return a constant and exist purely to be overridden. Hooking these by displacing bytes will run into the neighbouring function.

FIELD EVIDENCE for instance size 0x24: TAbility.Create writes +0x10 (TStringList), +0x18 (TSFXLibra
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `EngineP.dpl!Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x5574F07C` | `AoWE.TAbility.ReadWrite@23EDC2EF` | TAbility (override of TEObject.ReadWrite) |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5574E5F4` | `AoWE.TAbility.Create@23EDC2EF` | TAbility (override of TEObject.Create, virtual constructor) |
| `0x24` | `0x55703094` | `EngineP.dpl!Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5570307C` | `EngineP.dpl!Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `EngineP.dpl!Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `EngineP.dpl!Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `EngineP.dpl!Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574EF2C` | `AoWE.TAbility.Execute@23EDC2EF` | TAbility |
| `0x50` | `0x5574E9AC` | `AoWE.TAbility.GetHidden@23EDC2EF` | TAbility |
| `0x54` | `0x5574EF1C` | `AoWE.TAbility.GetAbilityType@23EDC2EF` | TAbility |
| `0x58` | `0x5574E97C` | `AoWE.TAbility.GetName@23EDC2EF` | TAbility |
| `0x5C` | `0x5574E990` | `AoWE.TAbility.GetAttack@23EDC2EF` | TAbility |
| `0x60` | `0x5574E994` | `AoWE.TAbility.GetDefense@23EDC2EF` | TAbility |
| `0x64` | `0x5574E998` | `AoWE.TAbility.GetResistance@23EDC2EF` | TAbility |
| `0x68` | `0x5574E99C` | `AoWE.TAbility.GetDamage@23EDC2EF` | TAbility |
| `0x6C` | `0x5574E9A0` | `AoWE.TAbility.GetMoveTypes@23EDC2EF` | TAbility |
| `0x70` | `0x5574E9B0` | `AoWE.TAbility.GetLevel@23EDC2EF` | TAbility |
| `0x74` | `0x5574EEF4` | `AoWE.TAbility.GetEnabled@23EDC2EF` | TAbility |
| `0x78` | `0x5574EF00` | `AoWE.TAbility.GetImmunityTypes@23EDC2EF` | TAbility |
| `0x7C` | `0x5574EF0C` | `AoWE.TAbility.GetProtectionTypes@23EDC2EF` | TAbility |
| `0x80` | `0x5574E958` | `AoWE.TAbility.GetSkillPoints@23EDC2EF` | TAbility |
| `0x84` | `0x5574E73C` | `AoWE.TAbility.GetCombatMode@23EDC2EF` | TAbility |
| `0x88` | `0x5574E8AC` | `AoWE.TAbility.GetWallCombatFeatures@23EDC2EF` | TAbility |
| `0x8C` | `0x5574E704` | `AoWE.TAbility.GetSourceName@23EDC2EF` | TAbility |
| `0x90` | `0x5574E948` | `AoWE.TAbility.GetInherent@23EDC2EF` | TAbility |
| `0x94` | `0x5574E954` | `AoWE.TAbility.GetInherentLevel@23EDC2EF` | TAbility |
| `0x98` | `0x5574E730` | `AoWE.TAbility.GetControlType@23EDC2EF` | TAbility |
| `0x9C` | `0x5574E784` | `AoWE.TAbility.fcValidRoundDistance@23EDC2EF` | TAbility |
| `0xA0` | `0x5574EF24` | `AoWE.TAbility.fcPrefetchCombatCommands@23EDC2EF` | TAbility |
| `0xA4` | `0x5574EF28` | `AoWE.TAbility.fcExecuteCombatCommand@23EDC2EF` | TAbility |
| `0xA8` | `0x5574EF30` | `AoWE.TAbility.NewDay@23EDC2EF` | TAbility |
| `0xAC` | `0x5574EF34` | `AoWE.TAbility.NewTurn@23EDC2EF` | TAbility |
| `0xB0` | `0x5574EF40` | `AoWE.TAbility.CanActivate@23EDC2EF` | TAbility |
| `0xB4` | `0x5574EF68` | `AoWE.TAbility.Activate@23EDC2EF` | TAbility |
| `0xB8` | `0x5574EFDC` | `AoWE.TAbility.CanActivateCombat@23EDC2EF` | TAbility |
| `0xBC` | `0x5574F004` | `AoWE.TAbility.ActivateCombat@23EDC2EF` | TAbility |
| `0xC0` | `0x5574EF18` | `AoWE.TAbility.ListSpells@23EDC2EF` | TAbility |
| `0xC4` | `0x5574E8B8` | `AoWE.TAbility.CanExpand@23EDC2EF` | TAbility |
| `0xC8` | `0x5574E908` | `AoWE.TAbility.ExpandCost@23EDC2EF` | TAbility |
| `0xCC` | `0x5574E8F4` | `AoWE.TAbility.ExpandName@23EDC2EF` | TAbility |
| `0xD0` | `0x5574E90C` | `AoWE.TAbility.Expand@23EDC2EF` | TAbility |
| `0xD4` | `0x5574E91C` | `AoWE.TAbility.Remove@23EDC2EF` | TAbility |
| `0xD8` | `0x5574E740` | `AoWE.TAbility.GetDamageValue@23EDC2EF` | TAbility |
| `0xDC` | `0x5574E744` | `AoWE.TAbility.GetDamageValueEx@23EDC2EF` | TAbility |
| `0xE0` | `0x5574E9B4` | `AoWE.TAbility.GetOffensiveStrength@23EDC2EF` | TAbility |
| `0xE4` | `0x5574E764` | `AoWE.TAbility.fcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xE8` | `0x5574E814` | `AoWE.TAbility.fcGetDamageValue@23EDC2EF` | TAbility |
| `0xEC` | `0x5574E844` | `AoWE.TAbility.tcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xF0` | `0x5574E868` | `AoWE.TAbility.tcGetDamageValue@23EDC2EF` | TAbility |
| `0xF4` | `0x5574EF20` | `AoWE.TAbility.CombatObjectDestroyed@23EDC2EF` | TAbility |
| `0xF8` | `0x5574EF38` | `AoWE.TAbility.NewCombatTurn@23EDC2EF` | TAbility |
| `0xFC` | `0x5574EF3C` | `AoWE.TAbility.CombatDone@23EDC2EF` | TAbility |
| `0x100` | `0x5574E9D0` | `AoWE.TAbility.ListInfo@23EDC2EF` | TAbility |
| `0x104` | `0x5574E88C` | `AoWE.TAbility.GetCombatInfo@23EDC2EF` | TAbility |
| `0x108` | `0x5574E978` | `AoWE.TAbility.AbilityDataClass@23EDC2EF` | TAbility |

## TAbstractUnit  —  VMT `0x55710740`, instance `0x3C`, 110 slots, ends `0x1B8`

<details><summary>derivation notes</summary>

```
METHOD / GROUND TRUTH
AoWEPACK.dpl is a Delphi 3 runtime *package*: its .edata exports 10036 named symbols covering every method, so the export directory IS a complete symbol table. I parsed it directly out of "Modding Resources/AoWEPACK_original_backup.dpl" (the same pristine bytes Ghidra holds) and mapped VMT slot -> export name. Cross-checked 4 slots against Ghidra get_function_by_address (0x5577F524 SetOwner, 0x5577FD90 GetAttack, 0x5578091C Animate, 0x5574FC3C TAbilityOwner.GetAbAttack) - all 4 exact matches. No slot is a guess; every one of the 110 has a real RTTI symbol.

VMT EXTENT
VMT = 0x55710740, 110 slots, +0x000..+0x1B4 inclusive. Ends at +0x1B8: the dword there is 0x6241540D, which is not a pointer but the class-name ShortString itself (0x0D = len 13, then "TAb..") at 0x557108F8 - i.e. the name string sits immediately after the VMT. This is the same end-of-VMT signature as the TAoWHexagon case in the brief.

ANCESTOR CHAIN (via [VMT-0x18] -> classref ptr)
TAbstractUnit (VMT 0x55710740, inst 0x3C)
  -> TAbilityOwner (VMT 0x5570F588, inst 0x14, VMT 39 slots, ends +0x09C)
  -> TCustomAbilityList (VMT 0x5570F3DC, inst 0x10, VMT 23 slots, ends +0x05C)
  -> Engine.TEObject -- IMPORTED, lives in EngineP.dpl, NOT in this DLL.
TCustomAbilityList's vmtParent points at IAT slot 0x558FC92C = "EngineP.dpl!Engine..TEObject@BD8FE92F". A naive parent-walk therefore stops at TCustomAbilityList; the root is in another module.

THE 12 "UNNAMED" SLOTS ARE IMPORT THUNKS, NOT UNKNOWNS
Slots 0x00,0x04,0x0C,0x10,0x14,0x1C,0x24,0x34,0x38,0x3C,0x40,0x48 point into a thunk table at 0x557030xx. Each is `FF 25 <iat>` = jmp dword ptr [IAT], + an 8BC0 (mov eax,eax) pad. Ghidra has NO function defined at those addresses (get_function_by_address returns "No function found") - so a Ghidra-only walk would report them as nameless. Resolving the IAT gives the true owner: all 12 are Engine.TEObject methods in EngineP.dpl. Symbols below are given in "EngineP.dpl!Engine.TEObject.X@hash" form; the "dll!" prefix marks the imported/thunked ones.

DELPHI 3 NEGATIVE HEADER (empirically confirmed, differs from Delphi 4+)
 -0x40 vmtSelfPtr      = 0x55710740 (the VMT itself; also exported as classref "AoWE..TAbstractUnit@B010B7CB")
 -0x3C..-0x24          = 0 (IntfTable/AutoTable/InitTable/TypeInfo/FieldTable/MethodTable/DynamicTable all null)
 -0x20 vmtClassName    = 0x557108F8
 -0x1C vmtInstanceSize = 0x3C
 -0x18 vmtParent       = 0x5570F548
 -0x14 SafeCallException = 0x557010C8  VCL30.dpl!System.TObject.SafeCallException
 -0x10 DefaultHandler    = 0x557010D0  VCL30.dpl!System.TObject.DefaultHandler
 -0x0C NewInstance       = 0x55701098  VCL30.dpl!System.TObject.NewInstance
 -0x08 FreeInstance      = 0x557010A0  VCL30.dpl!System.TObject.FreeInstance
 -0x04 Destroy           = 0x5577EB6C  AoWE.TAbstractUnit.Destroy@23EDC2EF
IMPORTANT FOR HOOKING: Destroy is at VMT-0x04, a NEGATIVE offset - it is not in the positive slot table. Delphi 3 has no AfterConstruction/BeforeDestruction/Dispatch entries.

WHO INTRODUCED EACH SLOT (derived from the ancestors' own VMT lengths, which are exactly the boundaries)
  +0x000..+0x048 (19 slots) introduced by TEObject
  +0x04C..+0x058 ( 4 slots) introduced by TCustomAbilityList
  +0x05C..+0x098 (16 slots) introduced by TAbilityOwner
  +0x09C..+0x1B4 (71 slots) NEW virtuals introduced by TAbstractUnit
  = 110 total.

WHO IMPLEMENTS EACH SLOT (the "owner" field below)
  TAbstractUnit 81, TAbilityOwner 15, TEObject 12, TCustomAbilityList 2.
TAbstractUnit's 81 = 71 new + 10 OVERRIDES of inherited slots:
  overriding TEObject:      +0x08 SetOwner, +0x18 ReadWrite, +0x20 Create, +0x28 AddRef, +0x2C Release, +0x44 MsgProc
  overriding TAbilityOwner: +0x60 GetOwnerName, +0x8C GetAbilitySelectionTypes, +0x90 Changed, +0x98 RemoveAbility
Note TAbstractUnit does NOT override Clear (+0x30 stays TAbilityOwner.Clear), nor GetAbSet/GetAbCount (+0x4C/+0x54 stay TCustomAbilityList) - those two are the only slots still implemented by TCustomAbili
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x5577F524` | `AoWE.TAbstractUnit.SetOwner@23EDC2EF` | TAbstractUnit |
| `0x0C` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557820E4` | `AoWE.TAbstractUnit.ReadWrite@23EDC2EF` | TAbstractUnit |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5577EB28` | `AoWE.TAbstractUnit.Create@23EDC2EF` | TAbstractUnit |
| `0x24` | `0x55703094` | `EngineP.dpl!Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x2C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x30` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55781238` | `AoWE.TAbstractUnit.MsgProc@23EDC2EF` | TAbstractUnit |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x50` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x54` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x58` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x5C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x60` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x64` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x68` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x6C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x70` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x74` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x78` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x7C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x80` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x84` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x88` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x8C` | `0x5577ECC0` | `AoWE.TAbstractUnit.GetAbilitySelectionTypes@23EDC2EF` | TAbstractUnit |
| `0x90` | `0x55780FA8` | `AoWE.TAbstractUnit.Changed@23EDC2EF` | TAbstractUnit |
| `0x94` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x98` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x9C` | `0x5577FC64` | `AoWE.TAbstractUnit.GetUpkeep@23EDC2EF` | TAbstractUnit |
| `0xA0` | `0x5577FCC8` | `AoWE.TAbstractUnit.GetUnitLevel@23EDC2EF` | TAbstractUnit |
| `0xA4` | `0x5577EDDC` | `AoWE.TAbstractUnit.GetRace@23EDC2EF` | TAbstractUnit |
| `0xA8` | `0x5577FD8C` | `AoWE.TAbstractUnit.GetInherentAttack@23EDC2EF` | TAbstractUnit |
| `0xAC` | `0x5577FD94` | `AoWE.TAbstractUnit.GetInherentDefense@23EDC2EF` | TAbstractUnit |
| `0xB0` | `0x5577FD9C` | `AoWE.TAbstractUnit.GetInherentDamage@23EDC2EF` | TAbstractUnit |
| `0xB4` | `0x5577FDA4` | `AoWE.TAbstractUnit.GetInherentResistance@23EDC2EF` | TAbstractUnit |
| `0xB8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0xBC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0xC0` | `0x5577FD90` | `AoWE.TAbstractUnit.GetAttack@23EDC2EF` | TAbstractUnit |
| `0xC4` | `0x5577FD98` | `AoWE.TAbstractUnit.GetDefense@23EDC2EF` | TAbstractUnit |
| `0xC8` | `0x5577FDA0` | `AoWE.TAbstractUnit.GetDamage@23EDC2EF` | TAbstractUnit |
| `0xCC` | `0x5577FDA8` | `AoWE.TAbstractUnit.GetResistance@23EDC2EF` | TAbstractUnit |
| `0xD0` | `0x5577FDAC` | `AoWE.TAbstractUnit.GetHits@23EDC2EF` | TAbstractUnit |
| `0xD4` | `0x5577FDB0` | `AoWE.TAbstractUnit.GetMoves@23EDC2EF` | TAbstractUnit |
| `0xD8` | `0x5577FCD0` | `AoWE.TAbstractUnit.GetMovePoints@23EDC2EF` | TAbstractUnit |
| `0xDC` | `0x5577FCD4` | `AoWE.TAbstractUnit.SetMovePoints@23EDC2EF` | TAbstractUnit |
| `0xE0` | `0x5577FCD8` | `AoWE.TAbstractUnit.GetHitPoints@23EDC2EF` | TAbstractUnit |
| `0xE4` | `0x5577FCDC` | `AoWE.TAbstractUnit.SetHitPoints@23EDC2EF` | TAbstractUnit |
| `0xE8` | `0x5577FFD0` | `AoWE.TAbstractUnit.GetMoveTypes@23EDC2EF` | TAbstractUnit |
| `0xEC` | `0x5577FD54` | `AoWE.TAbstractUnit.GetImmunityTypes@23EDC2EF` | TAbstractUnit |
| `0xF0` | `0x5577FD74` | `AoWE.TAbstractUnit.GetProtectionTypes@23EDC2EF` | TAbstractUnit |
| `0xF4` | `0x5577FFE4` | `AoWE.TAbstractUnit.GetFace@23EDC2EF` | TAbstractUnit |
| `0xF8` | `0x5577FFE8` | `AoWE.TAbstractUnit.GetName@23EDC2EF` | TAbstractUnit |
| `0xFC` | `0x5577FC60` | `AoWE.TAbstractUnit.GetAlignment@23EDC2EF` | TAbstractUnit |
| `0x100` | `0x5577FFF4` | `AoWE.TAbstractUnit.GetPreviewImage@23EDC2EF` | TAbstractUnit |
| `0x104` | `0x5577FCCC` | `AoWE.TAbstractUnit.GetTransportCapacity@23EDC2EF` | TAbstractUnit |
| `0x108` | `0x5577FD40` | `AoWE.TAbstractUnit.GetTransporter@23EDC2EF` | TAbstractUnit |
| `0x10C` | `0x55780878` | `AoWE.TAbstractUnit.GetGender@23EDC2EF` | TAbstractUnit |
| `0x110` | `0x5577EBB4` | `AoWE.TAbstractUnit.GetBloodType@23EDC2EF` | TAbstractUnit |
| `0x114` | `0x5577FD88` | `AoWE.TAbstractUnit.GetUnitType@23EDC2EF` | TAbstractUnit |
| `0x118` | `0x5577FFF8` | `AoWE.TAbstractUnit.GetUnitGFXResourceIndex@23EDC2EF` | TAbstractUnit |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x5577EBB8` | `AoWE.TAbstractUnit.GetCampaignTransferPoints@23EDC2EF` | TAbstractUnit |
| `0x128` | `0x5577FDB8` | `AoWE.TAbstractUnit.GetCastingPointsMax@23EDC2EF` | TAbstractUnit |
| `0x12C` | `0x5577FDBC` | `AoWE.TAbstractUnit.GetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x130` | `0x5577FDC0` | `AoWE.TAbstractUnit.SetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x134` | `0x5577FDB4` | `AoWE.TAbstractUnit.GetPowerGeneration@23EDC2EF` | TAbstractUnit |
| `0x138` | `0x5578120C` | `AoWE.TAbstractUnit.NewDay@23EDC2EF` | TAbstractUnit |
| `0x13C` | `0x55780D4C` | `AoWE.TAbstractUnit.NewTurn@23EDC2EF` | TAbstractUnit |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5577F658` | `AoWE.TAbstractUnit.GetAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x148` | `0x5577F5E0` | `AoWE.TAbstractUnit.GetAbilityEnabled@23EDC2EF` | TAbstractUnit |
| `0x14C` | `0x5577F618` | `AoWE.TAbstractUnit.GetAbilitySet@23EDC2EF` | TAbstractUnit |
| `0x150` | `0x5577F630` | `AoWE.TAbstractUnit.GetAbilityName@23EDC2EF` | TAbstractUnit |
| `0x154` | `0x5577F67C` | `AoWE.TAbstractUnit.GetAbilityOwner@23EDC2EF` | TAbstractUnit |
| `0x158` | `0x5577F56C` | `AoWE.TAbstractUnit.GetAbilityCount@23EDC2EF` | TAbstractUnit |
| `0x15C` | `0x5577FBA0` | `AoWE.TAbstractUnit.GetExperience@23EDC2EF` | TAbstractUnit |
| `0x160` | `0x5577FBA4` | `AoWE.TAbstractUnit.SetExperience@23EDC2EF` | TAbstractUnit |
| `0x164` | `0x5577FBA8` | `AoWE.TAbstractUnit.GetNextLevelExperience@23EDC2EF` | TAbstractUnit |
| `0x168` | `0x5577FB98` | `AoWE.TAbstractUnit.GetDescription@23EDC2EF` | TAbstractUnit |
| `0x16C` | `0x5577F4A8` | `AoWE.TAbstractUnit.SetPlayer@23EDC2EF` | TAbstractUnit |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x5577F188` | `AoWE.TAbstractUnit.GetObtainValue@23EDC2EF` | TAbstractUnit |
| `0x178` | `0x5577F184` | `AoWE.TAbstractUnit.GetUnitSize@23EDC2EF` | TAbstractUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x5577FB9C` | `AoWE.TAbstractUnit.CanActivate@23EDC2EF` | TAbstractUnit |
| `0x184` | `0x5577FBAC` | `AoWE.TAbstractUnit.Activate@23EDC2EF` | TAbstractUnit |
| `0x188` | `0x5577FC20` | `AoWE.TAbstractUnit.Deactivate@23EDC2EF` | TAbstractUnit |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x557821AC` | `AoWE.TAbstractUnit.CanJoin@23EDC2EF` | TAbstractUnit |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55782364` | `AoWE.TAbstractUnit.OfferToJoin@23EDC2EF` | TAbstractUnit |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x557812EC` | `AoWE.TAbstractUnit.ShowEx@23EDC2EF` | TAbstractUnit |
| `0x1A8` | `0x5577FD3C` | `AoWE.TAbstractUnit.UnitKilled@23EDC2EF` | TAbstractUnit |
| `0x1AC` | `0x5578087C` | `AoWE.TAbstractUnit.Killed@23EDC2EF` | TAbstractUnit |
| `0x1B0` | `0x557808DC` | `AoWE.TAbstractUnit.Resurrect@23EDC2EF` | TAbstractUnit |
| `0x1B4` | `0x5578091C` | `AoWE.TAbstractUnit.Animate@23EDC2EF` | TAbstractUnit |

## TAoWHSMap  —  VMT `0x5570E874`, instance `0x41C`, 76 slots, ends `0x130`

<details><summary>derivation notes</summary>

```
DERIVED, NOT GUESSED. Source of truth = the DPL's own PE export + import tables, cross-checked against Ghidra (AoWEPACK_vanilla.dpl). All 76 slots resolved; ZERO slots have an unknown symbol.

== VMT LOCATION / IDENTITY ==
VMT = 0x5570E874 (CODE section; module preferred base 0x55700000, so file-relative RVA 0xE874 -> file offset 0xE274). Independently confirmed three ways:
 1. [VMT-0x20] = 0x5570E9C6 -> ShortString "\x09TAoWHSMap".
 2. [VMT-0x40] (vmtSelfPtr) = 0x5570E874, i.e. points at itself.
 3. The DPL EXPORTS the classref at that exact address as "AoWE..TAoWHSMap@2F9CE523" (Delphi's Unit..Class@hash form). Only one candidate VMT exists for this name.
Instance size [VMT-0x1C] = 0x41C (1052 bytes).

== WHERE THE VMT ENDS (hard boundary, not a guess) ==
Last valid slot is +0x12C. VMT+0x130 = 0x5570E9A4, which is exactly the pointer stored in [VMT-0x34] (vmtInitTable) — the class's RTTI managed-field table. Its first dword reads 0x0000000E (tkRecord in the Delphi-3 TTypeKind numbering), which is why the walk stops: it is data, not a code pointer. So the VMT occupies 0x5570E874..0x5570E9A4 = 0x130 bytes = 76 slots, then the init table (0x22 bytes), then the class-name ShortString at 0x5570E9C6.

== ANCESTRY (from [VMT-0x18], which is a PClass i.e. pointer-to-classref) ==
TAoWHSMap (AoWE, VMT 0x5570E874, instsize 0x41C)
  -> TAbstractAoWHSMap (AoWE, VMT 0x5570E37C, instsize 0xD8, Destroy 0x55772338)
     -> HSEngine.THSMap  [external: TAbstractAoWHSMap's vmtParent slot is IAT 0x558FC15C = HSEPack.dpl!"HSEngine..THSMap@EA8E2427", so the chain leaves this module here]
        -> ... Engine.TENode / Engine.TECustomNode / Engine.TEObject (EngineP.dpl) -> System.TObject (VCL30.dpl)
TAbstractAoWHSMap's own VMT ends at +0x118, so TAoWHSMap's slots +0x118..+0x12C (6 entries) are NEWLY INTRODUCED virtuals; every other TAoWHSMap-owned slot is an override.

== HOW INHERITED SLOTS WERE RESOLVED (important for readers) ==
Slots whose target lands in 0x55702400-0x55703300 are NOT functions in this module — they are 6-byte Delphi package import thunks "JMP dword ptr [IAT]". Verified in Ghidra: 0x55703074 = ff2524c78f55 -> JMP [0x558FC724]; 0x5570262C = ff2508bc8f55 -> JMP [0x558FBC08]. Ghidra reports "No function found" at these addresses (it never made functions in the thunk region), so the names above come from the PE import table, which is equally authoritative. Unit prefix tells you the module: Engine.* = EngineP.dpl, HSEngine.* = HSEPack.dpl, System.* = VCL30.dpl. Every one of the 40 non-export slots was confirmed to start with FF 25 and to hit a named IAT entry — none are unnamed ordinals.

== SLOT OWNERSHIP TALLY (76 total) ==
TAoWHSMap 23 | TAbstractAoWHSMap 13 | HSEngine.THSMap 14 (HSEPack.dpl) | Engine.TEObject 11 | Engine.TENode 8 | Engine.TECustomNode 7 (all EngineP.dpl).

== NEGATIVE HEADER (Delphi 3 layout, confirmed byte-for-byte against Ghidra at 0x5570E834) ==
 -0x40 vmtSelfPtr        = 0x5570E874  (export "AoWE..TAoWHSMap@2F9CE523")
 -0x3C vmtIntfTable      = 0
 -0x38 vmtAutoTable      = 0
 -0x34 vmtInitTable      = 0x5570E9A4  (tkRecord; 3 managed fields, all System.String — typeinfo via IAT 0x558FB72C = VCL30.dpl!"System.String@44481A84" — at instance offsets +0xE4, +0xE8, +0x178. Since the parent's instsize is 0xD8, all three are TAoWHSMap's own fields.)
 -0x30 vmtTypeInfo       = 0
 -0x2C vmtFieldTable     = 0
 -0x28 vmtMethodTable    = 0  (no published methods)
 -0x24 vmtDynamicTable   = 0  (NO dynamic/message methods on this class — relevant if you were hoping to hook a message handler here; message dispatch goes through MsgProc at +0x044 instead)
 -0x20 vmtClassName      = 0x5570E9C6 -> "TAoWHSMap"
 -0x1C vmtInstanceSize   = 0x41C
 -0x18 vmtParent         = 0x5570E33C -> [.] = 0x5570E37C (TAbstractAoWHSMap)
 -0x14 SafeCallException = 0x557010C8  thunk -> VCL30.dpl!System.TObject.SafeCallException@23EDC2EF
 -0x10 DefaultHandler    = 0x557010D0  thunk -> VCL30.dpl!System.TObject.DefaultHandler@23EDC2EF
 -0x0C NewInsta
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x55702534` | `HSEngine.THSMap.GetControlStyle@23EDC2EF` | THSMap |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55776D60` | `AoWE.TAoWHSMap.ReadWrite@23EDC2EF` | TAoWHSMap |
| `0x01C` | `0x557772A0` | `AoWE.TAoWHSMap.MainReadWrite@23EDC2EF` | TAoWHSMap |
| `0x020` | `0x557748A4` | `AoWE.TAoWHSMap.Create@23EDC2EF` | TAoWHSMap |
| `0x024` | `0x557773C4` | `AoWE.TAoWHSMap.ClassID@23EDC2EF` | TAoWHSMap |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570253C` | `HSEngine.THSMap.Clear@23EDC2EF` | THSMap |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x55703144` | `Engine.TECustomNode.Assign@23EDC2EF` | TECustomNode |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55778498` | `AoWE.TAoWHSMap.MsgProc@23EDC2EF` | TAoWHSMap |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x557031CC` | `Engine.TENode.GetChild@23EDC2EF` | TENode |
| `0x050` | `0x557031D4` | `Engine.TENode.SetChild@23EDC2EF` | TENode |
| `0x054` | `0x557031DC` | `Engine.TENode.GetCount@23EDC2EF` | TENode |
| `0x058` | `0x55703154` | `Engine.TECustomNode.ReadWriteChildren@23EDC2EF` | TECustomNode |
| `0x05C` | `0x5570316C` | `Engine.TECustomNode.SendToChild@23EDC2EF` | TECustomNode |
| `0x060` | `0x557031B4` | `Engine.TENode.DestroyAllChildren@23EDC2EF` | TENode |
| `0x064` | `0x5570314C` | `Engine.TECustomNode.QuickClear@23EDC2EF` | TECustomNode |
| `0x068` | `0x5577855C` | `AoWE.TAoWHSMap.SendMsg@23EDC2EF` | TAoWHSMap |
| `0x06C` | `0x557031EC` | `Engine.TENode.RemoveChild@23EDC2EF` | TENode |
| `0x070` | `0x557031F4` | `Engine.TENode.AddChild@23EDC2EF` | TENode |
| `0x074` | `0x5570319C` | `Engine.TECustomNode.DestroyChildren@23EDC2EF` | TECustomNode |
| `0x078` | `0x55703194` | `Engine.TECustomNode.FindChildInTree@23EDC2EF` | TECustomNode |
| `0x07C` | `0x557031FC` | `Engine.TENode.FindChild@23EDC2EF` | TENode |
| `0x080` | `0x55703184` | `Engine.TECustomNode.FindOwnedChild@23EDC2EF` | TECustomNode |
| `0x084` | `0x55703204` | `Engine.TENode.FindChildIndex@23EDC2EF` | TENode |
| `0x088` | `0x55775938` | `AoWE.TAoWHSMap.CreateMouse@23EDC2EF` | TAoWHSMap |
| `0x08C` | `0x557769DC` | `AoWE.TAoWHSMap.NotifyProgress@23EDC2EF` | TAoWHSMap |
| `0x090` | `0x55777590` | `AoWE.TAoWHSMap.InitializeNewMap@23EDC2EF` | TAoWHSMap |
| `0x094` | `0x557724EC` | `AoWE.TAbstractAoWHSMap.TriggerTerrainChangedEvent@23EDC2EF` | TAbstractAoWHSMap |
| `0x098` | `0x5570262C` | `HSEngine.THSMap.DrawStaticHS@23EDC2EF` | THSMap |
| `0x09C` | `0x55702644` | `HSEngine.THSMap.DrawDynamicHS@23EDC2EF` | THSMap |
| `0x0A0` | `0x55702634` | `HSEngine.THSMap.DrawStaticHSEx@23EDC2EF` | THSMap |
| `0x0A4` | `0x5570264C` | `HSEngine.THSMap.DrawDynamicHSEx@23EDC2EF` | THSMap |
| `0x0A8` | `0x557025C4` | `HSEngine.THSMap.FillLevelWithResource@23EDC2EF` | THSMap |
| `0x0AC` | `0x55777684` | `AoWE.TAoWHSMap.AddMapLevel@23EDC2EF` | TAoWHSMap |
| `0x0B0` | `0x55778000` | `AoWE.TAoWHSMap.Activate@23EDC2EF` | TAoWHSMap |
| `0x0B4` | `0x55702554` | `HSEngine.THSMap.Deactivate@23EDC2EF` | THSMap |
| `0x0B8` | `0x5570256C` | `HSEngine.THSMap.ViewLevel@23EDC2EF` | THSMap |
| `0x0BC` | `0x5570255C` | `HSEngine.THSMap.CenterViewTo@23EDC2EF` | THSMap |
| `0x0C0` | `0x55702564` | `HSEngine.THSMap.ChangeViewTo@23EDC2EF` | THSMap |
| `0x0C4` | `0x557025FC` | `HSEngine.THSMap.GetViewCenter@23EDC2EF` | THSMap |
| `0x0C8` | `0x55702574` | `HSEngine.THSMap.MakeVisible@23EDC2EF` | THSMap |
| `0x0CC` | `0x557776BC` | `AoWE.TAoWHSMap.CreateNewMap@23EDC2EF` | TAoWHSMap |
| `0x0D0` | `0x55778D84` | `AoWE.TAoWHSMap.ChangeTerrain@23EDC2EF` | TAoWHSMap |
| `0x0D4` | `0x55778DCC` | `AoWE.TAoWHSMap.ChangeTerrainEx@23EDC2EF` | TAoWHSMap |
| `0x0D8` | `0x55773544` | `AoWE.TAbstractAoWHSMap.UpdateStaticScene@23EDC2EF` | TAbstractAoWHSMap |
| `0x0DC` | `0x55773624` | `AoWE.TAbstractAoWHSMap.UpdateDynamicScene@23EDC2EF` | TAbstractAoWHSMap |
| `0x0E0` | `0x5570263C` | `HSEngine.THSMap.DrawStaticScene@23EDC2EF` | THSMap |
| `0x0E4` | `0x55778A60` | `AoWE.TAoWHSMap.DrawDynamicScene@23EDC2EF` | TAoWHSMap |
| `0x0E8` | `0x55777CE8` | `AoWE.TAoWHSMap.NewFrame@23EDC2EF` | TAoWHSMap |
| `0x0EC` | `0x557732F4` | `AoWE.TAbstractAoWHSMap.ShowBackHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F0` | `0x5577338C` | `AoWE.TAbstractAoWHSMap.ShowFrontHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F4` | `0x55773424` | `AoWE.TAbstractAoWHSMap.UpdateHexagonSelector@23EDC2EF` | TAbstractAoWHSMap |
| `0x0F8` | `0x55775948` | `AoWE.TAoWHSMap.SetSeatedPlayer@23EDC2EF` | TAoWHSMap |
| `0x0FC` | `0x55772A80` | `AoWE.TAbstractAoWHSMap.SetCurrentPlayer@23EDC2EF` | TAbstractAoWHSMap |
| `0x100` | `0x557723C0` | `AoWE.TAbstractAoWHSMap.SetFogEnabled@23EDC2EF` | TAbstractAoWHSMap |
| `0x104` | `0x557723D4` | `AoWE.TAbstractAoWHSMap.SetExplorationEnabled@23EDC2EF` | TAbstractAoWHSMap |
| `0x108` | `0x55773770` | `AoWE.TAbstractAoWHSMap.DropHeroItem@23EDC2EF` | TAbstractAoWHSMap |
| `0x10C` | `0x557737A8` | `AoWE.TAbstractAoWHSMap.GetHeroItemsOnGround@23EDC2EF` | TAbstractAoWHSMap |
| `0x110` | `0x557729B4` | `AoWE.TAbstractAoWHSMap.ShowMessage@23EDC2EF` | TAbstractAoWHSMap |
| `0x114` | `0x557728F0` | `AoWE.TAbstractAoWHSMap.ShowWarning@23EDC2EF` | TAbstractAoWHSMap |
| `0x118` | `0x557763D4` | `AoWE.TAoWHSMap.TriggerCombatEvent@23EDC2EF` | TAoWHSMap |
| `0x11C` | `0x557763E0` | `AoWE.TAoWHSMap.TriggerGameTerminatedEvent@23EDC2EF` | TAoWHSMap |
| `0x120` | `0x55776684` | `AoWE.TAoWHSMap.TriggerPlayerTerminatedEvent@23EDC2EF` | TAoWHSMap |
| `0x124` | `0x55777D68` | `AoWE.TAoWHSMap.StartNewMap@23EDC2EF` | TAoWHSMap |
| `0x128` | `0x55777F10` | `AoWE.TAoWHSMap.StartLoadedMap@23EDC2EF` | TAoWHSMap |
| `0x12C` | `0x55776624` | `AoWE.TAoWHSMap.TriggerExecuteEventLog@23EDC2EF` | TAoWHSMap |

## TAoWHexagon  —  VMT `0x5579A1D0`, instance `0x14`, 73 slots, ends `0x124`

<details><summary>derivation notes</summary>

```
DERIVATION. Class-name ShortString 0x0B "TAoWHexagon" at VA 5579A2F4; the dword pointing at it is at 5579A1B0, so VMT = 5579A1B0+0x20 = 5579A1D0. [VMT-0x20]=5579A2F4 (name), [VMT-0x1C]=0x14 (instance size), [VMT-0x18]=558FCD30 which is an IAT slot importing HSEPack.dpl!"Hexagon..THexagon@3C8222E0" -> parent class is THexagon. Exactly one VMT candidate exists for this name.

VMT END. Last valid slot is +0x120. VMT_VA+0x124 = 5579A2F4, which is byte-identical to the class-name ShortString itself (0x0B 'T''A''o' = dword 6F41540B, then 78654857 'WHex', 6E6F6761 'agon'). So the VMT occupies 5579A1D0..5579A2F3 = 0x124 bytes = 73 slots, and the class-name string sits immediately after it. This is the exact case the task warned about.

MOST SLOTS ARE IMPORT THUNKS, NOT REAL FUNCTIONS. 69 of 73 targets are 6-byte `JMP dword ptr [IAT]` stubs in AoWEPACK's own thunk block (55701D44-55703104 and 55799448-55799458), padded with `MOV EAX,EAX`. Ghidra has no function at those addresses (get_function_by_address returns "No function found") — the symbols below were derived by decoding the FF 25 operand and looking the IAT VA up in AoWEPACK.dpl's import directory, which names the exporting package and the full Delphi RTTI symbol. target_va is what the VMT slot literally contains (the thunk), which is the address you would overwrite to hook a slot; the real code lives in HSEPack.dpl / EngineP.dpl. Only the 4 TAoWHexagon overrides are real local functions with Ghidra symbols.

ANCESTOR CHAIN (walked through HSEPack.dpl's own VMTs, since Ghidra only holds AoWEPACK):
  TEObject         (EngineP.dpl, unit Engine)   - imported, VMT not local
  -> THexagonSprite   (HSEPack.dpl, unit HSEngine)  VMT=55603694 instsize=0x08 vmtlen=0x108 (66 slots)
  -> TMapObject       (HSEPack.dpl, unit HSEngine)  VMT=55604190 instsize=0x10 vmtlen=0x11C (71 slots)
  -> TAbstractHexagon (HSEPack.dpl, unit HSEngine)  VMT=556047CC instsize=0x10 vmtlen=0x120 (72 slots)
  -> THexagon         (HSEPack.dpl, unit Hexagon)   VMT=55611B10 instsize=0x14 vmtlen=0x124 (73 slots)
  -> TAoWHexagon      (AoWEPACK.dpl, unit AoWHex)   VMT=5579A1D0 instsize=0x14 vmtlen=0x124 (73 slots)
NOTE the chain order is the OPPOSITE of what the slot layout suggests: THexagonSprite is the BASE and TMapObject derives from it, not vice versa. Do not infer chain order from which owner appears at low offsets.

Slot introduction: TEObject introduces 0x00-0x48; THexagonSprite extends to 0x104; TMapObject introduces 0x108-0x118; TAbstractHexagon introduces 0x11C; THexagon introduces 0x120. TAoWHexagon introduces NOTHING - same vmtlen 0x124 and same instance size 0x14 as THexagon, so it adds no virtual methods and no fields. It is a pure behaviour-override subclass.

TAoWHexagon's 4 overrides, with the base implementation each one replaces (read out of THexagon's VMT in HSEPack.dpl):
  +0x09C ChangeTerrain            overrides HSEngine.TAbstractHexagon.ChangeTerrain (5560A548)
  +0x0A0 TerrainChanged           overrides HSEngine.TAbstractHexagon.TerrainChanged (5560A618)
  +0x0A4 NeighbourTerrainChanged  overrides Hexagon.THexagon.NeighbourTerrainChanged (55611DAC)
  +0x120 UpdateTransition         overrides Hexagon.THexagon.UpdateTransition (55611DE8)
Corroboration: Ghidra's search for "TAoWHexagon" returns exactly these four functions and no others, so no virtual method was missed. Slot-by-slot, TAoWHexagon's VMT is identical to THexagon's except at these four offsets.

Owner tally: TMapObject 32, TEObject 17, THexagonSprite 10, TAbstractHexagon 7, TAoWHexagon 4, THexagon 3 = 73.

Beware +0x11C UpdateTransitions (plural, THexagon, the driver) vs +0x120 UpdateTransition (singular, TAoWHexagon, the per-edge worker) - adjacent slots, one letter apart.

Scripts used (scratchpad, throwaway; nothing in the project was written or modified, and no mutating Ghidra tool was called):
  ...\scratchpad\hexvmt.py, hexvmt2.py, aowhex_chain_probe.py, aowhex_hsepack_slots.py, aowhex_emit.py
Source bytes: Modding Resources\A
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557021F4` | `HSEngine.TMapObject.ReadWrite@23EDC2EF` | TMapObject |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55703064` | `Engine.TEObject.Create@23EDC2EF` | TEObject |
| `0x24` | `0x55799448` | `Hexagon.THexagon.ClassID@23EDC2EF` | THexagon |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557021B4` | `HSEngine.TMapObject.GetTerrain@23EDC2EF` | TMapObject |
| `0x50` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x557021CC` | `HSEngine.TMapObject.GetOverlay@23EDC2EF` | TMapObject |
| `0x5C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x557022FC` | `HSEngine.TAbstractHexagon.GetLevel@23EDC2EF` | TAbstractHexagon |
| `0x68` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702164` | `HSEngine.TMapObject.GetXhx@23EDC2EF` | TMapObject |
| `0x78` | `0x5570216C` | `HSEngine.TMapObject.GetYhx@23EDC2EF` | TMapObject |
| `0x7C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x55701DC4` | `HSEngine.THexagonSprite.GetXYL@23EDC2EF` | THexagonSprite |
| `0x84` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557022F4` | `HSEngine.TAbstractHexagon.GetShowPriority@23EDC2EF` | TAbstractHexagon |
| `0x90` | `0x55702214` | `HSEngine.TMapObject.Connect@23EDC2EF` | TMapObject |
| `0x94` | `0x5570221C` | `HSEngine.TMapObject.Disconnect@23EDC2EF` | TMapObject |
| `0x98` | `0x55701E24` | `HSEngine.THexagonSprite.CanChangeTerrain@23EDC2EF` | THexagonSprite |
| `0x9C` | `0x5579A89C` | `AoWHex.TAoWHexagon.ChangeTerrain@23EDC2EF` | TAoWHexagon |
| `0xA0` | `0x5579A94C` | `AoWHex.TAoWHexagon.TerrainChanged@23EDC2EF` | TAoWHexagon |
| `0xA4` | `0x5579A864` | `AoWHex.TAoWHexagon.NeighbourTerrainChanged@23EDC2EF` | TAoWHexagon |
| `0xA8` | `0x55799450` | `Hexagon.THexagon.Show@23EDC2EF` | THexagon |
| `0xAC` | `0x5570222C` | `HSEngine.TMapObject.PlaceOnMap@23EDC2EF` | TMapObject |
| `0xB0` | `0x55702234` | `HSEngine.TMapObject.RemoveFromMap@23EDC2EF` | TMapObject |
| `0xB4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55702224` | `HSEngine.TMapObject.Loaded@23EDC2EF` | TMapObject |
| `0xCC` | `0x5570233C` | `HSEngine.TAbstractHexagon.MapFieldMsgProc@23EDC2EF` | TAbstractHexagon |
| `0xD0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x55702314` | `HSEngine.TAbstractHexagon.Activate@23EDC2EF` | TAbstractHexagon |
| `0xE4` | `0x55702254` | `HSEngine.TMapObject.Deactivate@23EDC2EF` | TMapObject |
| `0xE8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55701D44` | `HSEngine.THexagonSprite.UpdateMapField@23EDC2EF` | THexagonSprite |
| `0xF0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557021A4` | `HSEngine.TMapObject.CanSelect@23EDC2EF` | TMapObject |
| `0xFC` | `0x557021E4` | `HSEngine.TMapObject.Select@23EDC2EF` | TMapObject |
| `0x100` | `0x557021EC` | `HSEngine.TMapObject.Unselect@23EDC2EF` | TMapObject |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x5570230C` | `HSEngine.TAbstractHexagon.SetResource@23EDC2EF` | TAbstractHexagon |
| `0x114` | `0x5570232C` | `HSEngine.TAbstractHexagon.CanPlace@23EDC2EF` | TAbstractHexagon |
| `0x118` | `0x55702334` | `HSEngine.TAbstractHexagon.PlaceHX@23EDC2EF` | TAbstractHexagon |
| `0x11C` | `0x55799458` | `Hexagon.THexagon.UpdateTransitions@23EDC2EF` | THexagon |
| `0x120` | `0x5579A9E0` | `AoWHex.TAoWHexagon.UpdateTransition@23EDC2EF` | TAoWHexagon |

## TArena  —  VMT `557D6240`, instance `0x30`, 124 slots, ends `0x1F0`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Source = "Modding Resources/AoWEPACK_original_backup.dpl" (pristine vanilla, byte-identical to the Ghidra image). Every slot symbol comes from the file's own tables, not from guessing: local targets resolved through AoWEPACK's export directory (10036 exported names / 10033 unique VAs), cross-module targets resolved through the import directory. 15 slots spread across the table (including the tightly packed 1-4 byte stubs at 5575F360/64/68/74, 5575EDE4, 5575E69C, 5575F4F4) were independently spot-checked with mcp__ghidra__get_function_by_address — all 15 matched the export-derived name exactly. No slot came back without a symbol; there are zero "" entries.
All VAs are at the preferred base 0x55700000. The DPL rebases at runtime (see the project's PIC rule). CODE section: VA 55701000..558E7A00, raw 0x400 -> file offset = VA - 0x55700C00. VMT file offset = 0xD5640.

WHERE THE VMT ENDS (unambiguous)
+0x1EC (AoWE.TStructure.CanRaze) is the last slot. The dword at +0x1F0 is 0x72415406, i.e. the bytes 06 'T' 'A' 'r' — the start of the ShortString "TArena" at 557D6430, which is exactly what vmtClassName (VMT-0x20) points at. The class-name string immediately follows the VMT, so the terminator is self-proving. 124 slots, 0x1F0 bytes.

VMT HEADER (negative offsets) — Delphi 3 layout, all values verified
  -0x40 vmtSelfPtr        557D6240  (points back at the VMT; this is how I enumerated all 893 VMTs in the DLL)
  -0x3C vmtIntfTable      0
  -0x38 vmtAutoTable      0
  -0x34 vmtInitTable      0
  -0x30 vmtTypeInfo       0
  -0x2C vmtFieldTable     0
  -0x28 vmtMethodTable    0
  -0x24 vmtDynamicTable   0        <-- TArena has NO dynamic methods
  -0x20 vmtClassName      557D6430 -> ShortString "TArena"
  -0x1C vmtInstanceSize   0x30
  -0x18 vmtParent         55713BD8 -> deref -> 55713C18 = TStructure VMT
  -0x14 vmtSafeCallException 557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  -0x10 vmtDefaultHandler    557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  -0x0C vmtNewInstance       55701098 -> VCL30.dpl!System.TObject.NewInstance
  -0x08 vmtFreeInstance      557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  -0x04 vmtDestroy           5575E5C8 -> AoWE.TStructure.Destroy  (TArena does NOT override Destroy)
Note vmtDestroy sits at -0x04, NOT at a positive slot — user-declared virtuals start at +0x00.

⚠ 50 OF THE 124 SLOTS ARE IMPORT THUNKS, NOT REAL FUNCTIONS
Every target in 0x55701000-0x557035FF is a 6-byte `FF 25 <IAT>` jump stub inside AoWEPACK, forwarding to another package. The target_va I report is the address actually stored in the VMT (the thunk), which is what a patcher reads/writes; the symbol is the ultimate function in the foreign DLL. Module per owner class:
  TEObject           -> EngineP.dpl   (15 slots)
  TMapObject         -> HSEPack.dpl   (20 slots)
  TMultiHexMO        -> HSEPack.dpl   (9 slots)
  THexagonSprite     -> HSEPack.dpl   (8 slots)
  TILTerrainMO       -> HSEPack.dpl   (2 slots)
  TFixedILTerrainMO  -> HSEPack.dpl   (1 slot)
  TStructure/TArena  -> AoWEPACK.dpl  (65 + 4 slots, real local code)
Consequence: those 50 methods cannot be hooked by patching the function body in AoWEPACK — only the VMT slot (or the thunk's 6 bytes, or HSEPack/EngineP itself). Ghidra has none of those modules, which is why get_function_by_address returns "No function found" for them.

⚠ `owner` = IMPLEMENTER, NOT DECLARER
The owner field is the class whose implementation currently occupies the slot. It is not necessarily the class that first declared the virtual. Clear example: +0x74/+0x78 hold TMultiHexMO.GetXhx/GetYhx interleaved among TMapObject slots — TMultiHexMO overrode a slot declared further up the chain. Do not infer declaration order from it.

ANCESTRY
TArena -> TStructure (AoWEPACK, unit AoWE, VMT 55713C18) -> [TFixedILTerrainMO / TILTerrainMO / TMultiHexMO / TMapObject / THexagonSprite, all HSEPack.dpl] -> TEObject (EngineP.dpl) -> TObject (VCL30.dpl).
The chain walk stops at TStruc
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `5575E658` | `AoWE.TStructure.ReadWrite@23EDC2EF` | TStructure |
| `0x1C` | `55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `5575E590` | `AoWE.TStructure.Create@23EDC2EF` | TStructure |
| `0x24` | `557D66E8` | `Arena.TArena.ClassID@23EDC2EF` | TArena |
| `0x28` | `5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `5575F898` | `AoWE.TStructure.MsgProc@23EDC2EF` | TStructure |
| `0x48` | `557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x50` | `557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x5C` | `557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `5570213C` | `HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x68` | `55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `55702394` | `HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x78` | `5570239C` | `HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x7C` | `55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `557023A4` | `HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x84` | `5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `557023AC` | `HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x90` | `557023C4` | `HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x94` | `557023CC` | `HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x98` | `5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x9C` | `557035AC` | `ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0xA0` | `5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0xA4` | `55701E3C` | `HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0xA8` | `5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0xAC` | `5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0xB0` | `5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0xB4` | `5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `55703574` | `ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0xCC` | `5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0xD0` | `55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `5575F6C0` | `AoWE.TStructure.Activate@23EDC2EF` | TStructure |
| `0xE4` | `5575F710` | `AoWE.TStructure.Deactivate@23EDC2EF` | TStructure |
| `0xE8` | `55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0xF0` | `5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `5575E994` | `AoWE.TStructure.CanSelect@23EDC2EF` | TStructure |
| `0xFC` | `5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `55702184` | `HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `55702424` | `HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `557023F4` | `HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `55702414` | `HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `5575E6A0` | `AoWE.TStructure.GetTerrainTypeImage@23EDC2EF` | TStructure |
| `0x130` | `5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `55703534` | `ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `557D6B68` | `Arena.TArena.CreateTE@23EDC2EF` | TArena |
| `0x164` | `5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `557D67D8` | `Arena.TArena.ExecuteTE@23EDC2EF` | TArena |
| `0x16C` | `5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `5575F338` | `AoWE.TStructure.NewDay@23EDC2EF` | TStructure |
| `0x178` | `5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `5575E878` | `AoWE.TStructure.Update@23EDC2EF` | TStructure |
| `0x1CC` | `5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `557D66F0` | `Arena.TArena.CanDblClick@23EDC2EF` | TArena |
| `0x1D4` | `5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |

## TCombatObject  —  VMT `0x557158EC`, instance `0x4C`, 77 slots, ends `0x134`

<details><summary>derivation notes</summary>

```
DERIVED, NOT GUESSED. Source: pristine vanilla AoWEPACK.dpl (Ghidra program AoWEPACK_vanilla.dpl, image base 0x55700000; cross-checked byte-for-byte against Modding Resources/AoWEPACK_original_backup.dpl). 77 slots, ALL resolved to real symbols - zero unknowns, zero "" entries.

VMT HEADER (negative offsets, Delphi 2/3 layout - confirmed empirically, NOT the Delphi 4+ layout):
  VMT-0x20 = 0x55715A20 -> ClassName ShortString
  VMT-0x1C = 0x0000004C -> InstanceSize (76 bytes)
  VMT-0x18 = 0x558FC92C -> Parent (PClass cell) = EngineP.dpl!Engine..TEObject@BD8FE92F
  VMT-0x14 = 0x557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  VMT-0x10 = 0x557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  VMT-0x0C = 0x55701098 -> VCL30.dpl!System.TObject.NewInstance
  VMT-0x08 = 0x557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  VMT-0x04 = 0x55726168 -> AoWE.TCombatObject.Destroy (destructor lives in the header, NOT in a positive slot)

WHY THE END IS CERTAIN (not a heuristic stop): the last slot is +0x130, and the dword at +0x134 is 0x6F43540D = the bytes 0D 54 43 6F, i.e. the ShortString <len 13>"TCombatObject" - the very string VMT-0x20 points at (0x557158EC + 0x134 = 0x55715A20, exactly the ClassName pointer value). The VMT is immediately followed by its own class-name string, then 8B C0 padding, then the next VMT at 0x55715A34. So vmt_end = 0x134 is closed by arithmetic, not by "the pointer stopped looking like code".

DIRECT PARENT IS Engine.TEObject, AND IT LIVES IN ANOTHER PACKAGE (EngineP.dpl). This is the single most important structural fact here: TCombatObject derives directly from TEObject (no intermediate class), and TEObject's VMT is exactly 0x4C bytes = 19 slots. Therefore slots +0x00..+0x48 are the TEObject slice and slots +0x4C..+0x130 (58 slots) are TCombatObject's own additions.

*** PATCHING TRAP - READ BEFORE HOOKING ANY INHERITED SLOT ***
Because TEObject is in EngineP.dpl, every INHERITED (non-overridden) slot does NOT point at real code in AoWEPACK.dpl. It points at an 8-byte IMPORT THUNK in AoWEPACK's thunk band at 0x55703064..0x5570310C, each of the form:
    FF 25 <abs IAT cell>    jmp dword ptr [cell]      (+ 2 bytes 8B C0 padding)
The target_va I report for those slots is the THUNK address inside AoWEPACK (what the VMT slot literally contains - that is what you compare/patch), not the final TEObject code, which is in EngineP.dpl and is not in this image at all. Thunk -> IAT cell mapping for the inherited slots:
  +0x000 0x55703074 -> [0x558FC724] ClassVersion      +0x004 0x557030DC -> [0x558FC6F0] GetControlStyle
  +0x008 0x557030E4 -> [0x558FC6EC] SetOwner          +0x00C 0x557030D4 -> [0x558FC6F4] GetEngine
  +0x010 0x557030AC -> [0x558FC708] GetLastMsg        +0x014 0x557030B4 -> [0x558FC704] SetLastMsg
  +0x01C 0x55703104 -> [0x558FC6DC] MainReadWrite     +0x024 0x55703094 -> [0x558FC714] ClassID
  +0x028 0x5570307C -> [0x558FC720] AddRef            +0x02C 0x55703084 -> [0x558FC71C] Release
  +0x030 0x5570308C -> [0x558FC718] Clear             +0x034 0x557030BC -> [0x558FC700] Compare
  +0x038 0x5570309C -> [0x558FC710] Editor            +0x03C 0x557030C4 -> [0x558FC6FC] Assign
  +0x040 0x557030A4 -> [0x558FC70C] TimerEvent        +0x044 0x557030F4 -> [0x558FC6E4] MsgProc
  +0x048 0x557030EC -> [0x558FC6E8] SetArrayOwner
Two further TEObject thunks exist but are NOT reachable through this VMT because TCombatObject overrides both: Create thunk 0x55703064 -> [0x558FC72C] (overridden at +0x20) and ReadWrite thunk 0x557030FC -> [0x558FC6E0] (overridden at +0x18). TEObject.Destroy thunk 0x5570306C -> [0x558FC728] is likewise overridden, in the header at VMT-0x04.

Ghidra had NO function defined at 11 of those 17 thunk addresses (0x55703074, 0x5570307C, 0x55703084, 0x55703094, 0x557030A4, 0x557030AC, 0x557030B4, 0x557030BC, 0x557030C4, 0x557030D4, 0x55703104) - get_function_by_address returns "No function found". Those names were recovered by parsing the PE import table directly (75 descriptors, 1444 IAT
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x557265C0` | `AoWE.TCombatObject.ReadWrite@23EDC2EF` | TCombatObject |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x55726118` | `AoWE.TCombatObject.Create@23EDC2EF` | TCombatObject |
| `0x024` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5572637C` | `AoWE.TCombatObject.GetTargetCVDV@23EDC2EF` | TCombatObject |
| `0x050` | `0x55726390` | `AoWE.TCombatObject.GetTargetWallCV@23EDC2EF` | TCombatObject |
| `0x054` | `0x557261AC` | `AoWE.TCombatObject.TargetsChanged@23EDC2EF` | TCombatObject |
| `0x058` | `0x55726394` | `AoWE.TCombatObject.GetTargetPriority@23EDC2EF` | TCombatObject |
| `0x05C` | `0x55726454` | `AoWE.TCombatObject.GetTargetStrength@23EDC2EF` | TCombatObject |
| `0x060` | `0x5572663C` | `AoWE.TCombatObject.GetEnabled@23EDC2EF` | TCombatObject |
| `0x064` | `0x557267A0` | `AoWE.TCombatObject.GetLocked@23EDC2EF` | TCombatObject |
| `0x068` | `0x557267A4` | `AoWE.TCombatObject.SetCombatPlayer@23EDC2EF` | TCombatObject |
| `0x06C` | `0x5572685C` | `AoWE.TCombatObject.GetAttack@23EDC2EF` | TCombatObject |
| `0x070` | `0x55726860` | `AoWE.TCombatObject.GetDefense@23EDC2EF` | TCombatObject |
| `0x074` | `0x55726864` | `AoWE.TCombatObject.GetResistance@23EDC2EF` | TCombatObject |
| `0x078` | `0x55726868` | `AoWE.TCombatObject.GetDamage@23EDC2EF` | TCombatObject |
| `0x07C` | `0x5572686C` | `AoWE.TCombatObject.GetImmunityTypes@23EDC2EF` | TCombatObject |
| `0x080` | `0x55726878` | `AoWE.TCombatObject.GetProtectionTypes@23EDC2EF` | TCombatObject |
| `0x084` | `0x55726888` | `AoWE.TCombatObject.GetHits@23EDC2EF` | TCombatObject |
| `0x088` | `0x55726890` | `AoWE.TCombatObject.GetHitPoints@23EDC2EF` | TCombatObject |
| `0x08C` | `0x5572688C` | `AoWE.TCombatObject.SetHitPoints@23EDC2EF` | TCombatObject |
| `0x090` | `0x557268CC` | `AoWE.TCombatObject.GetAlignment@23EDC2EF` | TCombatObject |
| `0x094` | `0x55726884` | `AoWE.TCombatObject.GetMoves@23EDC2EF` | TCombatObject |
| `0x098` | `0x55726894` | `AoWE.TCombatObject.GetExperience@23EDC2EF` | TCombatObject |
| `0x09C` | `0x55726898` | `AoWE.TCombatObject.SetExperience@23EDC2EF` | TCombatObject |
| `0x0A0` | `0x5572689C` | `AoWE.TCombatObject.GetLevel@23EDC2EF` | TCombatObject |
| `0x0A4` | `0x557265BC` | `AoWE.TCombatObject.GetVisibilityRange@23EDC2EF` | TCombatObject |
| `0x0A8` | `0x557268D4` | `AoWE.TCombatObject.GetAbilityEnabled@23EDC2EF` | TCombatObject |
| `0x0AC` | `0x557268D8` | `AoWE.TCombatObject.SetAbilityEnabled@23EDC2EF` | TCombatObject |
| `0x0B0` | `0x557268DC` | `AoWE.TCombatObject.GetAbilityLevel@23EDC2EF` | TCombatObject |
| `0x0B4` | `0x557268E0` | `AoWE.TCombatObject.GetAbilityCount@23EDC2EF` | TCombatObject |
| `0x0B8` | `0x557268D0` | `AoWE.TCombatObject.GetAbilityOwner@23EDC2EF` | TCombatObject |
| `0x0BC` | `0x55726708` | `AoWE.TCombatObject.Activate@23EDC2EF` | TCombatObject |
| `0x0C0` | `0x5572674C` | `AoWE.TCombatObject.Deactivate@23EDC2EF` | TCombatObject |
| `0x0C4` | `0x55726934` | `AoWE.TCombatObject.ObjectDestroyed@23EDC2EF` | TCombatObject |
| `0x0C8` | `0x5572653C` | `AoWE.TCombatObject.ObjectSideChanged@23EDC2EF` | TCombatObject |
| `0x0CC` | `0x55726790` | `AoWE.TCombatObject.Initialize@23EDC2EF` | TCombatObject |
| `0x0D0` | `0x55726794` | `AoWE.TCombatObject.Finalize@23EDC2EF` | TCombatObject |
| `0x0D4` | `0x557265B8` | `AoWE.TCombatObject.fcRoundDistance@23EDC2EF` | TCombatObject |
| `0x0D8` | `0x557265AC` | `AoWE.TCombatObject.fcExecute@23EDC2EF` | TCombatObject |
| `0x0DC` | `0x557265B0` | `AoWE.TCombatObject.fcBehindWall@23EDC2EF` | TCombatObject |
| `0x0E0` | `0x557265B4` | `AoWE.TCombatObject.fcWallInBetween@23EDC2EF` | TCombatObject |
| `0x0E4` | `0x5572695C` | `AoWE.TCombatObject.SupportCombatMode@23EDC2EF` | TCombatObject |
| `0x0E8` | `0x55726630` | `AoWE.TCombatObject.WallCombatFeatures@23EDC2EF` | TCombatObject |
| `0x0EC` | `0x5572679C` | `AoWE.TCombatObject.PlaySFX@23EDC2EF` | TCombatObject |
| `0x0F0` | `0x557266B4` | `AoWE.TCombatObject.NewTurn@23EDC2EF` | TCombatObject |
| `0x0F4` | `0x557266D0` | `AoWE.TCombatObject.NewRound@23EDC2EF` | TCombatObject |
| `0x0F8` | `0x557266D4` | `AoWE.TCombatObject.CombatDone@23EDC2EF` | TCombatObject |
| `0x0FC` | `0x55726D40` | `AoWE.TCombatObject.Show@23EDC2EF` | TCombatObject |
| `0x100` | `0x55726D48` | `AoWE.TCombatObject.ShowAttackAnimation@23EDC2EF` | TCombatObject |
| `0x104` | `0x55726D54` | `AoWE.TCombatObject.ShowHitAnimation@23EDC2EF` | TCombatObject |
| `0x108` | `0x55726B1C` | `AoWE.TCombatObject.DoDamage@23EDC2EF` | TCombatObject |
| `0x10C` | `0x55726960` | `AoWE.TCombatObject.GetOptimalDamageType@23EDC2EF` | TCombatObject |
| `0x110` | `0x557269F0` | `AoWE.TCombatObject.ExecuteDamageRole@23EDC2EF` | TCombatObject |
| `0x114` | `0x55726A6C` | `AoWE.TCombatObject.ExecuteDamageRoleEx@23EDC2EF` | TCombatObject |
| `0x118` | `0x55726B10` | `AoWE.TCombatObject.ExecuteDamageEffectsRole@23EDC2EF` | TCombatObject |
| `0x11C` | `0x55726C24` | `AoWE.TCombatObject.Surrender@23EDC2EF` | TCombatObject |
| `0x120` | `0x55726BA4` | `AoWE.TCombatObject.DestroyObject@23EDC2EF` | TCombatObject |
| `0x124` | `0x55726C58` | `AoWE.TCombatObject.ExecuteDamage@23EDC2EF` | TCombatObject |
| `0x128` | `0x55726B04` | `AoWE.TCombatObject.ExecuteDamageEffects@23EDC2EF` | TCombatObject |
| `0x12C` | `0x557266D8` | `AoWE.TCombatObject.TurnDone@23EDC2EF` | TCombatObject |
| `0x130` | `0x557268A0` | `AoWE.TCombatObject.IDStr@23EDC2EF` | TCombatObject |

## TCombatUnit  —  VMT `0x55715A94`, instance `0x5C`, 79 slots, ends `0x13C`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Every symbol is ground truth from two independent sources that agreed on all of them:
(a) the DPL's own PE export directory (10036 exported names, parsed from
    "Modding Resources/AoWEPACK_original_backup.dpl"), and
(b) Ghidra's RTTI-derived function symbols, spot-checked on 8 addresses (557261AC, 557265B8,
    55725204, 5572653C, 557267A4, 55726960, 55726B1C, 55726C58, 557266D8) — all matched exactly.
Ghidra's in-memory VMT bytes at 55715A94 are byte-identical to the backup file.

Throwaway scripts (in the scratchpad, NOT in the project):
  vmt_walk_combatunit.py — locate VMT + naive slot walk
  vmt_resolve.py         — export+import symbol resolution; reusable for ANY class:
                           `python vmt_resolve.py TWhatever`
  vmt_extra.py           — negative header, parent chain, TCombatObject-vs-TCombatUnit diff

WHERE THE VMT ENDS — 0x13C, unambiguous
The dword at VMT+0x13C is 0x6F43540B, not a code pointer: the bytes are
`0B 54 43 6F 6D 62 61 74 55 6E 69 74` = the ShortString "TCombatUnit". That is exactly the string
[VMT-0x20] points at (0x55715BD0 == 0x55715A94 + 0x13C) — Delphi placed the class-name string
immediately after the last slot. Last real slot is +0x138. 79 slots total.

INSTANCE SIZE 0x5C (92). Parent TCombatObject is 0x4C, so TCombatUnit adds 0x10 bytes of fields.
Descendant TFastCombatUnit is 0x64.

VMT HEADER (negative offsets) — Delphi 3 layout, vmtSelfPtr at -0x40:
  -0x40 55715A94 vmtSelfPtr (exported as `AoWE..TCombatUnit@B2B5938D`)
  -0x3C 00000000 vmtIntfTable      -0x38 00000000 vmtAutoTable
  -0x34 00000000 vmtInitTable      -0x30 00000000 vmtTypeInfo
  -0x2C 00000000 vmtFieldTable     -0x28 00000000 vmtMethodTable
  -0x24 00000000 vmtDynamicTable  <-- NULL: TCombatUnit has NO dynamic/message-method table, so
                                     every dispatchable method is in the positive VMT.
  -0x20 55715BD0 vmtClassName -> "TCombatUnit"
  -0x1C 0000005C vmtInstanceSize
  -0x18 557158AC vmtParent (pointer TO the classref; deref -> 557158EC = TCombatObject VMT)
  -0x14 557010C8 vmtSafeCallException (thunk -> VCL30.dpl!System.TObject.SafeCallException)
  -0x10 557010D0 vmtDefaultHandler    (thunk -> VCL30.dpl!System.TObject.DefaultHandler)
  -0x0C 55701098 vmtNewInstance       (thunk -> VCL30.dpl!System.TObject.NewInstance)
  -0x08 557010A0 vmtFreeInstance      (thunk -> VCL30.dpl!System.TObject.FreeInstance)
  -0x04 55724A6C vmtDestroy = AoWE.TCombatUnit.Destroy@23EDC2EF  <-- destructor lives HERE, not in
                                     the positive table. Easy to miss.

ANCESTRY
  TCombatUnit      VMT=55715A94 instsize=0x5C vmtlen=0x13C (79 slots)
   -> TCombatObject VMT=557158EC instsize=0x4C vmtlen=0x134 (77 slots)
   -> Engine.TEObject — the chain LEAVES AoWEPACK here. TCombatObject's [VMT-0x18] is 558FC92C, an
      .idata slot importing `EngineP.dpl!Engine..TEObject@BD8FE92F`. TEObject's VMT is not in this
      module, so TEObject-owned slots cannot be walked further from this file.

THE 16 "TEObject" SLOTS ARE IMPORT THUNKS, NOT FUNCTION BODIES
Slots +0x00,04,08,0C,10,14,1C,28,2C,30,34,38,3C,40,44,48 point at 6-byte stubs in the 0x55703xxx
block: `FF 25 <abs>` = `jmp dword ptr [IAT]`, padded to 8 bytes with `8B C0`. Verified:
55703074 = FF 25 24 C7 8F 55 -> [558FC724] -> EngineP.dpl!Engine.TEObject.ClassVersion.
The symbol reported for these is the *imported* RTTI symbol from the import directory — real, not a
guess — but Ghidra has no function at those addresses ("No function found for 0x55703074"), so
get_function_by_address returns nothing there. target_va is the thunk inside AoWEPACK; the code
lives in EngineP.dpl. To hook one, patch the VMT slot, never the shared thunk.

OWNERSHIP SUMMARY (79 slots)
  50 owned/overridden by TCombatUnit
  13 inherited unchanged from TCombatObject: +0x054 TargetsChanged, +0x068 SetCombatPlayer,
     +0x0C8 ObjectSideChanged, +0x0D4 fcRoundDistance, +0x0D8 fcExecute, +0x0DC fcBehindWall,
     +0x0E0 fcWallInBe
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55725204` | `AoWE.TCombatUnit.ReadWrite@23EDC2EF` | TCombatUnit |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55724A28` | `AoWE.TCombatUnit.Create@23EDC2EF` | TCombatUnit |
| `0x24` | `0x55724A9C` | `AoWE.TCombatUnit.ClassID@23EDC2EF` | TCombatUnit |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x557252E8` | `AoWE.TCombatUnit.GetTargetCVDV@23EDC2EF` | TCombatUnit |
| `0x50` | `0x55725438` | `AoWE.TCombatUnit.GetTargetWallCV@23EDC2EF` | TCombatUnit |
| `0x54` | `0x557261AC` | `AoWE.TCombatObject.TargetsChanged@23EDC2EF` | TCombatObject |
| `0x58` | `0x5572582C` | `AoWE.TCombatUnit.GetTargetPriority@23EDC2EF` | TCombatUnit |
| `0x5C` | `0x55725850` | `AoWE.TCombatUnit.GetTargetStrength@23EDC2EF` | TCombatUnit |
| `0x60` | `0x55724B70` | `AoWE.TCombatUnit.GetEnabled@23EDC2EF` | TCombatUnit |
| `0x64` | `0x55724BA4` | `AoWE.TCombatUnit.GetLocked@23EDC2EF` | TCombatUnit |
| `0x68` | `0x557267A4` | `AoWE.TCombatObject.SetCombatPlayer@23EDC2EF` | TCombatObject |
| `0x6C` | `0x55725490` | `AoWE.TCombatUnit.GetAttack@23EDC2EF` | TCombatUnit |
| `0x70` | `0x5572549C` | `AoWE.TCombatUnit.GetDefense@23EDC2EF` | TCombatUnit |
| `0x74` | `0x557254A8` | `AoWE.TCombatUnit.GetResistance@23EDC2EF` | TCombatUnit |
| `0x78` | `0x557254B4` | `AoWE.TCombatUnit.GetDamage@23EDC2EF` | TCombatUnit |
| `0x7C` | `0x557254C0` | `AoWE.TCombatUnit.GetImmunityTypes@23EDC2EF` | TCombatUnit |
| `0x80` | `0x557254E0` | `AoWE.TCombatUnit.GetProtectionTypes@23EDC2EF` | TCombatUnit |
| `0x84` | `0x5572504C` | `AoWE.TCombatUnit.GetHits@23EDC2EF` | TCombatUnit |
| `0x88` | `0x55725064` | `AoWE.TCombatUnit.GetHitPoints@23EDC2EF` | TCombatUnit |
| `0x8C` | `0x5572507C` | `AoWE.TCombatUnit.SetHitPoints@23EDC2EF` | TCombatUnit |
| `0x90` | `0x55724FF4` | `AoWE.TCombatUnit.GetAlignment@23EDC2EF` | TCombatUnit |
| `0x94` | `0x55724FE0` | `AoWE.TCombatUnit.GetMoves@23EDC2EF` | TCombatUnit |
| `0x98` | `0x557254F8` | `AoWE.TCombatUnit.GetExperience@23EDC2EF` | TCombatUnit |
| `0x9C` | `0x55725504` | `AoWE.TCombatUnit.SetExperience@23EDC2EF` | TCombatUnit |
| `0xA0` | `0x55725510` | `AoWE.TCombatUnit.GetLevel@23EDC2EF` | TCombatUnit |
| `0xA4` | `0x55724AD0` | `AoWE.TCombatUnit.GetVisibilityRange@23EDC2EF` | TCombatUnit |
| `0xA8` | `0x55725004` | `AoWE.TCombatUnit.GetAbilityEnabled@23EDC2EF` | TCombatUnit | ⚠ nil-GUARDED |
| `0xAC` | `0x5572501C` | `AoWE.TCombatUnit.SetAbilityEnabled@23EDC2EF` | TCombatUnit |
| `0xB0` | `0x55725028` | `AoWE.TCombatUnit.GetAbilityLevel@23EDC2EF` | TCombatUnit | ⚠ **NOT** nil-guarded |
| `0xB4` | `0x55725034` | `AoWE.TCombatUnit.GetAbilityCount@23EDC2EF` | TCombatUnit | ⚠ nil-guarded |
| `0xB8` | `0x55725000` | `AoWE.TCombatUnit.GetAbilityOwner@23EDC2EF` | TCombatUnit |
| `0xBC` | `0x55724CD0` | `AoWE.TCombatUnit.Activate@23EDC2EF` | TCombatUnit |
| `0xC0` | `0x55724CF4` | `AoWE.TCombatUnit.Deactivate@23EDC2EF` | TCombatUnit |
| `0xC4` | `0x55725284` | `AoWE.TCombatUnit.ObjectDestroyed@23EDC2EF` | TCombatUnit |
| `0xC8` | `0x5572653C` | `AoWE.TCombatObject.ObjectSideChanged@23EDC2EF` | TCombatObject |
| `0xCC` | `0x55724D10` | `AoWE.TCombatUnit.Initialize@23EDC2EF` | TCombatUnit |
| `0xD0` | `0x55724D44` | `AoWE.TCombatUnit.Finalize@23EDC2EF` | TCombatUnit |
| `0xD4` | `0x557265B8` | `AoWE.TCombatObject.fcRoundDistance@23EDC2EF` | TCombatObject |
| `0xD8` | `0x557265AC` | `AoWE.TCombatObject.fcExecute@23EDC2EF` | TCombatObject |
| `0xDC` | `0x557265B0` | `AoWE.TCombatObject.fcBehindWall@23EDC2EF` | TCombatObject |
| `0xE0` | `0x557265B4` | `AoWE.TCombatObject.fcWallInBetween@23EDC2EF` | TCombatObject |
| `0xE4` | `0x55725638` | `AoWE.TCombatUnit.SupportCombatMode@23EDC2EF` | TCombatUnit |
| `0xE8` | `0x55724C14` | `AoWE.TCombatUnit.WallCombatFeatures@23EDC2EF` | TCombatUnit |
| `0xEC` | `0x55724F2C` | `AoWE.TCombatUnit.PlaySFX@23EDC2EF` | TCombatUnit |
| `0xF0` | `0x55724B28` | `AoWE.TCombatUnit.NewTurn@23EDC2EF` | TCombatUnit |
| `0xF4` | `0x55724B4C` | `AoWE.TCombatUnit.NewRound@23EDC2EF` | TCombatUnit |
| `0xF8` | `0x55724B54` | `AoWE.TCombatUnit.CombatDone@23EDC2EF` | TCombatUnit |
| `0xFC` | `0x5572591C` | `AoWE.TCombatUnit.Show@23EDC2EF` | TCombatUnit |
| `0x100` | `0x557259C4` | `AoWE.TCombatUnit.ShowAttackAnimation@23EDC2EF` | TCombatUnit |
| `0x104` | `0x55725A18` | `AoWE.TCombatUnit.ShowHitAnimation@23EDC2EF` | TCombatUnit |
| `0x108` | `0x55726B1C` | `AoWE.TCombatObject.DoDamage@23EDC2EF` | TCombatObject |
| `0x10C` | `0x55726960` | `AoWE.TCombatObject.GetOptimalDamageType@23EDC2EF` | TCombatObject |
| `0x110` | `0x557269F0` | `AoWE.TCombatObject.ExecuteDamageRole@23EDC2EF` | TCombatObject |
| `0x114` | `0x55726A6C` | `AoWE.TCombatObject.ExecuteDamageRoleEx@23EDC2EF` | TCombatObject |
| `0x118` | `0x55724C3C` | `AoWE.TCombatUnit.ExecuteDamageEffectsRole@23EDC2EF` | TCombatUnit |
| `0x11C` | `0x557257B8` | `AoWE.TCombatUnit.Surrender@23EDC2EF` | TCombatUnit |
| `0x120` | `0x557256F0` | `AoWE.TCombatUnit.DestroyObject@23EDC2EF` | TCombatUnit |
| `0x124` | `0x55726C58` | `AoWE.TCombatObject.ExecuteDamage@23EDC2EF` | TCombatObject |
| `0x128` | `0x55724C1C` | `AoWE.TCombatUnit.ExecuteDamageEffects@23EDC2EF` | TCombatUnit |
| `0x12C` | `0x557266D8` | `AoWE.TCombatObject.TurnDone@23EDC2EF` | TCombatObject |
| `0x130` | `0x5572551C` | `AoWE.TCombatUnit.IDStr@23EDC2EF` | TCombatUnit |
| `0x134` | `0x55725194` | `AoWE.TCombatUnit.SetUnit@23EDC2EF` | TCombatUnit |
| `0x138` | `0x557256E4` | `AoWE.TCombatUnit.KillUnit@23EDC2EF` | TCombatUnit |

## TExplorationSite  —  VMT `0x557C1440`, instance `0x38`, 129 slots, ends `0x204`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
- Class lives in Delphi unit "ExploreS" (NOT "AoWE"). Full symbols are ExploreS.TExplorationSite.<Method>@23EDC2EF.
- VMT found via the RTTI recipe on Modding Resources/AoWEPACK_original_backup.dpl (same bytes Ghidra holds):
  [VMT-0x20]=0x557C1644 -> ShortString(0x10)"TExplorationSite"; [VMT-0x1C]=0x38 instance size;
  [VMT-0x18]=0x55713BD8 -> deref 0x55713C18 = TStructure's VMT.
- RTTI TTypeInfo record at 0x557C165C (kind byte 0x07 = tkClass, name "TExplorationSite", ClassType=0x557C1440, UnitName "ExploreS"). Only 2 occurrences of the class-name ShortString in the file: the VMT name string and this TypeInfo — so there is exactly ONE TExplorationSite VMT.

WHERE THE VMT ENDS (important: "points into CODE" does NOT bound it here — Delphi puts VMTs, class-name strings and TypeInfo all inside the CODE section)
- Last valid slot is +0x200. The class-name ShortString begins immediately at VMT+0x204 (= 0x557C1644), verified byte-exact against Ghidra read_memory at 0x557C1638:
  90 18 7C 55 | 20 1A 7C 55 | 5C 1E 7C 55 | 10 'TExplorationSite' | 8D 40 00
  i.e. slots +0x1F8/+0x1FC/+0x200 then the string. So first offset past the VMT = 0x204, 129 slots.

INHERITANCE (ancestor chain, from slot owners + parent classrefs)
  Engine.TEObject (EngineP.dpl)
    -> HSEngine.THexagonSprite (HSEPack.dpl)
      -> HSEngine.TMapObject
        -> HSEngine.TMultiHexMO
          -> ILTer.TILTerrainMO
            -> ILTer.TFixedILTerrainMO   <-- TStructure's parent, resolved from IAT cell 0x558FCA08 = "HSEPack.dpl!ILTer..TFixedILTerrainMO@DE482B1C"
              -> AoWE.TStructure (VMT 0x55713C18, instsize 0x30, 124 slots, ends at +0x1EC / first past end 0x1F0)
                -> ExploreS.TExplorationSite (VMT 0x557C1440, instsize 0x38, 129 slots)
- TExplorationSite adds 8 bytes of own fields (0x30..0x37) over TStructure's 0x30.
- Owner histogram over the 129 slots: TStructure 58, TMapObject 20, TExplorationSite 16, TEObject 15, TMultiHexMO 9, THexagonSprite 8, TILTerrainMO 2, TFixedILTerrainMO 1.

OVERRIDE vs NEW (diffed slot-by-slot against TStructure's VMT — this is derived, not guessed)
- 11 INHERITED slots that TExplorationSite OVERRIDES (TStructure's value -> TExplorationSite's):
  +0x018 ReadWrite   0x5575E658 -> 0x557C1F8C
  +0x020 Create      0x5575E590 -> 0x557C17CC
  +0x024 ClassID     0x5575E588 -> 0x557C183C
  +0x044 MsgProc     0x5575F898 -> 0x557C2118
  +0x0E0 Activate    0x5575F6C0 -> 0x557C20F0
  +0x0E4 Deactivate  0x5575F710 -> 0x557C2104
  +0x0F8 CanSelect   0x5575E994 -> 0x557C1D58
  +0x12C GetTerrainTypeImage 0x5575E6A0 -> 0x557C1848
  +0x168 ExecuteTE   0x5575E8CC -> 0x557C1D28
  +0x174 NewDay      0x5575F338 -> 0x557C20A4
  +0x1C8 Update      0x5575E878 -> 0x557C20D0
- 5 slots NEWLY DECLARED by TExplorationSite (past TStructure's VMT end of 0x1F0): +0x1F0 GetExplored, +0x1F4 SetupCombat, +0x1F8 ExecuteSearchDone, +0x1FC ExecuteSearch, +0x200 Search. These are the exploration-site search/combat entry points and exist on no ancestor.
- All other 113 slots are inherited unchanged; "owner" is the class that PROVIDES the implementation (the most-derived override in the chain), which is what the symbol records. It is not necessarily the class that *declared* the slot — e.g. +0x04C is TStructure.GetTerrain while +0x050/+0x054 are TMapObject.SetTerrain/GetTerrainCount, one declared trio with only the getter overridden.

SYMBOL SOURCES (every slot resolved; none unknown)
- 61 slots point at functions inside AoWEPACK.dpl and were resolved from its export table (10036 named exports). Cross-checked 9 of them against Ghidra get_function_by_address — 9/9 exact string match (e.g. 0x557C1F8C -> ExploreS.TExplorationSite.ReadWrite@23EDC2EF, 0x5575EC04 -> AoWE.TStructure.GetTerrain@23EDC2EF).
- 68 slots point at 8-byte-spaced cross-package import thunks in the 0x55701D00-0x557035B0 range, of the form "FF 25 <IAT>" + "8B C0" padding. Ghidra has NO function defined at these addresses (get_function_by_address returns "No fun
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `EngineP.dpl!Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `EngineP.dpl!Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `EngineP.dpl!Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `EngineP.dpl!Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `EngineP.dpl!Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557C1F8C` | `ExploreS.TExplorationSite.ReadWrite@23EDC2EF` | TExplorationSite |
| `0x1C` | `0x55703104` | `EngineP.dpl!Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x557C17CC` | `ExploreS.TExplorationSite.Create@23EDC2EF` | TExplorationSite |
| `0x24` | `0x557C183C` | `ExploreS.TExplorationSite.ClassID@23EDC2EF` | TExplorationSite |
| `0x28` | `0x5570307C` | `EngineP.dpl!Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `EngineP.dpl!Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `EngineP.dpl!Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `EngineP.dpl!Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `EngineP.dpl!Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `EngineP.dpl!Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `EngineP.dpl!Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557C2118` | `ExploreS.TExplorationSite.MsgProc@23EDC2EF` | TExplorationSite |
| `0x48` | `0x557030EC` | `EngineP.dpl!Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x50` | `0x557021BC` | `HSEPack.dpl!HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x54` | `0x557021C4` | `HSEPack.dpl!HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x58` | `0x5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x5C` | `0x557021D4` | `HSEPack.dpl!HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x60` | `0x557021DC` | `HSEPack.dpl!HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x64` | `0x5570213C` | `HSEPack.dpl!HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x68` | `0x55702134` | `HSEPack.dpl!HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x6C` | `0x5570214C` | `HSEPack.dpl!HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x70` | `0x557021AC` | `HSEPack.dpl!HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x74` | `0x55702394` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x78` | `0x5570239C` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x7C` | `0x55702174` | `HSEPack.dpl!HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x80` | `0x557023A4` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x84` | `0x5570215C` | `HSEPack.dpl!HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x88` | `0x55702154` | `HSEPack.dpl!HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x8C` | `0x557023AC` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x90` | `0x557023C4` | `HSEPack.dpl!HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x94` | `0x557023CC` | `HSEPack.dpl!HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x98` | `0x5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x9C` | `0x557035AC` | `HSEPack.dpl!ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0xA0` | `0x5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0xA4` | `0x55701E3C` | `HSEPack.dpl!HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0xA8` | `0x5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0xAC` | `0x5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0xB0` | `0x5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0xB4` | `0x5570225C` | `HSEPack.dpl!HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0xB8` | `0x55702264` | `HSEPack.dpl!HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0xBC` | `0x55701EC4` | `HSEPack.dpl!HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0xC0` | `0x557021FC` | `HSEPack.dpl!HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0xC4` | `0x5570223C` | `HSEPack.dpl!HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0xC8` | `0x55703574` | `HSEPack.dpl!ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0xCC` | `0x5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0xD0` | `0x55701D54` | `HSEPack.dpl!HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0xD4` | `0x55701D5C` | `HSEPack.dpl!HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0xD8` | `0x55701D64` | `HSEPack.dpl!HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0xDC` | `0x55701D8C` | `HSEPack.dpl!HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0xE0` | `0x557C20F0` | `ExploreS.TExplorationSite.Activate@23EDC2EF` | TExplorationSite |
| `0xE4` | `0x557C2104` | `ExploreS.TExplorationSite.Deactivate@23EDC2EF` | TExplorationSite |
| `0xE8` | `0x55701D9C` | `HSEPack.dpl!HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0xEC` | `0x55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0xF0` | `0x5570219C` | `HSEPack.dpl!HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0xF4` | `0x55701DA4` | `HSEPack.dpl!HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0xF8` | `0x557C1D58` | `ExploreS.TExplorationSite.CanSelect@23EDC2EF` | TExplorationSite |
| `0xFC` | `0x5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `0x5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `0x55702144` | `HSEPack.dpl!HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEPack.dpl!HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEPack.dpl!HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x55702184` | `HSEPack.dpl!HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `0x5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `0x5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `0x55702424` | `HSEPack.dpl!HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `0x557023F4` | `HSEPack.dpl!HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `0x55702414` | `HSEPack.dpl!HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `0x5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `0x557C1848` | `ExploreS.TExplorationSite.GetTerrainTypeImage@23EDC2EF` | TExplorationSite |
| `0x130` | `0x5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `0x55703534` | `HSEPack.dpl!ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `0x5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `0x5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `0x5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `0x5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `0x5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `0x5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `0x5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `0x5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `0x5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `0x5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `0x5575E88C` | `AoWE.TStructure.CreateTE@23EDC2EF` | TStructure |
| `0x164` | `0x5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `0x557C1D28` | `ExploreS.TExplorationSite.ExecuteTE@23EDC2EF` | TExplorationSite |
| `0x16C` | `0x5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `0x5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `0x557C20A4` | `ExploreS.TExplorationSite.NewDay@23EDC2EF` | TExplorationSite |
| `0x178` | `0x5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `0x5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `0x5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `0x5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `0x5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `0x5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `0x5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `0x5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `0x5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `0x5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `0x5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `0x5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `0x5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `0x5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `0x5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `0x5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `0x5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `0x5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `0x5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `0x5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `0x557C20D0` | `ExploreS.TExplorationSite.Update@23EDC2EF` | TExplorationSite |
| `0x1CC` | `0x5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `0x5575E990` | `AoWE.TStructure.CanDblClick@23EDC2EF` | TStructure |
| `0x1D4` | `0x5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `0x5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `0x5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `0x5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `0x5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `0x557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `0x5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |
| `0x1F0` | `0x557C1844` | `ExploreS.TExplorationSite.GetExplored@23EDC2EF` | TExplorationSite |
| `0x1F4` | `0x557C1960` | `ExploreS.TExplorationSite.SetupCombat@23EDC2EF` | TExplorationSite |
| `0x1F8` | `0x557C1890` | `ExploreS.TExplorationSite.ExecuteSearchDone@23EDC2EF` | TExplorationSite |
| `0x1FC` | `0x557C1A20` | `ExploreS.TExplorationSite.ExecuteSearch@23EDC2EF` | TExplorationSite |
| `0x200` | `0x557C1E5C` | `ExploreS.TExplorationSite.Search@23EDC2EF` | TExplorationSite |

## THero  —  VMT `0x55711FEC`, instance `0x9C`, 114 slots, ends `0x1C8`

<details><summary>derivation notes</summary>

```
MODULE: AoWEPACK.dpl (pristine vanilla, image base 0x55700000 — Ghidra program AoWEPACK_vanilla.dpl). All VAs are at the preferred base; the DPL rebases at runtime.

=== VMT BOUNDARY — CONFIRMED TWO INDEPENDENT WAYS ===
The VMT slot array is 0x000..0x1C4 inclusive = 114 slots; first offset past the end is +0x1C8 (VA 0x557121B4).
1. Heuristic: [VMT+0x1C8] = 0x0000000E, not a CODE pointer.
2. Structural proof: Delphi 3's vmtInitTable field at [VMT-0x34] holds 0x557121B4 — i.e. the compiler's own record of where the init table starts, which is exactly VMT+0x1C8. The 0x0E byte is tkRecord, the head of that init table (3 managed AnsiString fields at instance offsets 0x60, 0x64, 0x94; typeinfo 0x558FB72C). The init table runs 0x22 bytes and is followed at 0x557121D6 by the class-name ShortString "THero" (which is what [VMT-0x20] points at).

=== DELPHI 3 VMT HEADER (verified on THero, offsets relative to VMT) ===
 -0x40 vmtSelfPtr        = 0x55711FEC (== VMT, verified for all four classes in the chain)
 -0x3C vmtIntfTable      = 0
 -0x38 vmtAutoTable      = 0
 -0x34 vmtInitTable      = 0x557121B4   <-- the reliable end-of-VMT marker when non-zero
 -0x30 vmtTypeInfo       = 0
 -0x2C vmtFieldTable     = 0
 -0x28 vmtMethodTable    = 0
 -0x24 vmtDynamicTable   = 0
 -0x20 vmtClassName      = 0x557121D6 -> \x05"THero"
 -0x1C vmtInstanceSize   = 0x9C
 -0x18 vmtParent         = 0x55710700 (pointer TO the parent classref; [0x55710700] = 0x55710740 = TAbstractUnit VMT)
 -0x14 vmtSafeCallException = 0x557010C8
 -0x10 vmtDefaultHandler    = 0x557010D0
 -0x0C vmtNewInstance       = 0x55701098
 -0x08 vmtFreeInstance      = 0x557010A0
 -0x04 vmtDestroy           = 0x557868F4 = AoWE.THero.Destroy@23EDC2EF
NOTE: THero.Destroy is at VMT-0x04, i.e. in the header, NOT in the slot array below. Do not look for it among the 114 slots.

=== ANCESTOR CHAIN (derived, with per-class VMT length) ===
  Engine.TEObject (EngineP.dpl, EXTERNAL — parentref 0x558FC92C is an IAT slot importing "EngineP.dpl!Engine..TEObject@BD8FE92F")
    -> TCustomAbilityList  VMT=0x5570F3DC  instsize=0x10  vmt_len=0x5C  (23 slots)
    -> TAbilityOwner       VMT=0x5570F588  instsize=0x14  vmt_len=0x9C  (39 slots)
    -> TAbstractUnit       VMT=0x55710740  instsize=0x3C  vmt_len=0x1B8 (110 slots)
    -> THero               VMT=0x55711FEC  instsize=0x9C  vmt_len=0x1C8 (114 slots)
THero's parent is TAbstractUnit, NOT TUnit — TUnit is a sibling branch.
Ancestor VMT lengths were confirmed by a second marker: for all three ancestors vmtInitTable is 0 (no managed fields), but their class-name ShortString ([VMT-0x20]) sits at exactly VMT+vmt_len (delta 0), so the slot arrays end precisely there.

=== NEW VIRTUALS INTRODUCED BY THero ===
TAbstractUnit's VMT is 0x1B8 long, so slots +0x1B8..+0x1C4 (4 slots) are THero-introduced: GetNickname, SetNickname, SetHeroResourceIndex, EditDropMsg. Everything at +0x000..+0x1B4 is a slot inherited from the ancestor layout, either overridden by THero or left pointing at the ancestor's implementation.

=== OWNERSHIP TALLY (implementing class per slot) ===
  THero 69, TAbstractUnit 20, TAbilityOwner 14, TEObject 10, TCustomAbilityList 1.
The 45 non-THero slots are inherited implementations — hooking those addresses affects every descendant sharing them, not just heroes.

=== TEObject SLOTS ARE IMPORT THUNKS, NOT LOCAL CODE ===
The 10 slots whose targets lie in 0x55703064..0x55703104 are NOT functions in AoWEPACK.dpl. That range is a table of 8-byte stubs, each `mov eax,eax; jmp dword ptr [IAT]`, forwarding to EngineP.dpl. Ghidra has function symbols on only 3 of the 10 used here (Editor, GetControlStyle, SetArrayOwner) and reports "No function found" for the rest — the names below were recovered by parsing the PE import table and mapping each stub's IAT slot to its import name. Full stub table for reference:
  0x55703064 -> [0x558FC72C] Engine.TEObject.Create
  0x5570306C -> [0x558FC728] Engine.TEObject.Destroy
  0x55703074 -> [0x558FC724] Engine.TEObject.Cl
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x55786A80` | `AoWE.THero.SetOwner@23EDC2EF` | THero |
| `0x00C` | `0x55786B1C` | `AoWE.THero.GetEngine@23EDC2EF` | THero |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55788880` | `AoWE.THero.ReadWrite@23EDC2EF` | THero |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x55786848` | `AoWE.THero.Create@23EDC2EF` | THero |
| `0x024` | `0x55786C10` | `AoWE.THero.ClassID@23EDC2EF` | THero |
| `0x028` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x02C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x030` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55788C04` | `AoWE.THero.MsgProc@23EDC2EF` | THero |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x55788104` | `AoWE.THero.GetAbSet@23EDC2EF` | THero |
| `0x050` | `0x557880FC` | `AoWE.THero.SetAbSet@23EDC2EF` | THero |
| `0x054` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x058` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x05C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x060` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x064` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x068` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x06C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x070` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x074` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x078` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x07C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x080` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x084` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x088` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x08C` | `0x55786B10` | `AoWE.THero.GetAbilitySelectionTypes@23EDC2EF` | THero |
| `0x090` | `0x55786BDC` | `AoWE.THero.Changed@23EDC2EF` | THero |
| `0x094` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x098` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x09C` | `0x557872C0` | `AoWE.THero.GetUpkeep@23EDC2EF` | THero |
| `0x0A0` | `0x55786A7C` | `AoWE.THero.GetUnitLevel@23EDC2EF` | THero |
| `0x0A4` | `0x55786F9C` | `AoWE.THero.GetRace@23EDC2EF` | THero |
| `0x0A8` | `0x55788354` | `AoWE.THero.GetInherentAttack@23EDC2EF` | THero |
| `0x0AC` | `0x557883DC` | `AoWE.THero.GetInherentDefense@23EDC2EF` | THero |
| `0x0B0` | `0x55788478` | `AoWE.THero.GetInherentDamage@23EDC2EF` | THero |
| `0x0B4` | `0x55788500` | `AoWE.THero.GetInherentResistance@23EDC2EF` | THero |
| `0x0B8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0x0BC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x0C0` | `0x55788360` | `AoWE.THero.GetAttack@23EDC2EF` | THero |
| `0x0C4` | `0x557883E8` | `AoWE.THero.GetDefense@23EDC2EF` | THero |
| `0x0C8` | `0x55788484` | `AoWE.THero.GetDamage@23EDC2EF` | THero |
| `0x0CC` | `0x5578850C` | `AoWE.THero.GetResistance@23EDC2EF` | THero |
| `0x0D0` | `0x5578859C` | `AoWE.THero.GetHits@23EDC2EF` | THero |
| `0x0D4` | `0x557885C0` | `AoWE.THero.GetMoves@23EDC2EF` | THero |
| `0x0D8` | `0x55787018` | `AoWE.THero.GetMovePoints@23EDC2EF` | THero |
| `0x0DC` | `0x5578701C` | `AoWE.THero.SetMovePoints@23EDC2EF` | THero |
| `0x0E0` | `0x55787044` | `AoWE.THero.GetHitPoints@23EDC2EF` | THero |
| `0x0E4` | `0x55787048` | `AoWE.THero.SetHitPoints@23EDC2EF` | THero |
| `0x0E8` | `0x55786FB8` | `AoWE.THero.GetMoveTypes@23EDC2EF` | THero |
| `0x0EC` | `0x55786FD8` | `AoWE.THero.GetImmunityTypes@23EDC2EF` | THero |
| `0x0F0` | `0x55786FF8` | `AoWE.THero.GetProtectionTypes@23EDC2EF` | THero |
| `0x0F4` | `0x557887DC` | `AoWE.THero.GetFace@23EDC2EF` | THero |
| `0x0F8` | `0x55786FA4` | `AoWE.THero.GetName@23EDC2EF` | THero |
| `0x0FC` | `0x5578707C` | `AoWE.THero.GetAlignment@23EDC2EF` | THero |
| `0x100` | `0x55788680` | `AoWE.THero.GetPreviewImage@23EDC2EF` | THero |
| `0x104` | `0x5577FCCC` | `AoWE.TAbstractUnit.GetTransportCapacity@23EDC2EF` | TAbstractUnit |
| `0x108` | `0x5577FD40` | `AoWE.TAbstractUnit.GetTransporter@23EDC2EF` | TAbstractUnit |
| `0x10C` | `0x55786C34` | `AoWE.THero.GetGender@23EDC2EF` | THero |
| `0x110` | `0x5577EBB4` | `AoWE.TAbstractUnit.GetBloodType@23EDC2EF` | TAbstractUnit |
| `0x114` | `0x55786C38` | `AoWE.THero.GetUnitType@23EDC2EF` | THero |
| `0x118` | `0x557875BC` | `AoWE.THero.GetUnitGFXResourceIndex@23EDC2EF` | THero |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x55786970` | `AoWE.THero.GetCampaignTransferPoints@23EDC2EF` | THero |
| `0x128` | `0x55788614` | `AoWE.THero.GetCastingPointsMax@23EDC2EF` | THero |
| `0x12C` | `0x55788644` | `AoWE.THero.GetCastingPoints@23EDC2EF` | THero |
| `0x130` | `0x5578864C` | `AoWE.THero.SetCastingPoints@23EDC2EF` | THero |
| `0x134` | `0x557885E4` | `AoWE.THero.GetPowerGeneration@23EDC2EF` | THero |
| `0x138` | `0x55786C3C` | `AoWE.THero.NewDay@23EDC2EF` | THero |
| `0x13C` | `0x55787FCC` | `AoWE.THero.NewTurn@23EDC2EF` | THero |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5578831C` | `AoWE.THero.GetAbilityLevel@23EDC2EF` | THero |
| `0x148` | `0x5578827C` | `AoWE.THero.GetAbilityEnabled@23EDC2EF` | THero |
| `0x14C` | `0x557882AC` | `AoWE.THero.GetAbilitySet@23EDC2EF` | THero |
| `0x150` | `0x557882DC` | `AoWE.THero.GetAbilityName@23EDC2EF` | THero |
| `0x154` | `0x55788274` | `AoWE.THero.GetAbilityOwner@23EDC2EF` | THero |
| `0x158` | `0x55788114` | `AoWE.THero.GetAbilityCount@23EDC2EF` | THero |
| `0x15C` | `0x55787670` | `AoWE.THero.GetExperience@23EDC2EF` | THero |
| `0x160` | `0x55787674` | `AoWE.THero.SetExperience@23EDC2EF` | THero |
| `0x164` | `0x5578770C` | `AoWE.THero.GetNextLevelExperience@23EDC2EF` | THero |
| `0x168` | `0x55786C30` | `AoWE.THero.GetDescription@23EDC2EF` | THero |
| `0x16C` | `0x557872D0` | `AoWE.THero.SetPlayer@23EDC2EF` | THero |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x55786C18` | `AoWE.THero.GetObtainValue@23EDC2EF` | THero |
| `0x178` | `0x5577F184` | `AoWE.TAbstractUnit.GetUnitSize@23EDC2EF` | TAbstractUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x55787264` | `AoWE.THero.CanActivate@23EDC2EF` | THero |
| `0x184` | `0x557873E8` | `AoWE.THero.Activate@23EDC2EF` | THero |
| `0x188` | `0x5578754C` | `AoWE.THero.Deactivate@23EDC2EF` | THero |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x55786D7C` | `AoWE.THero.CanJoin@23EDC2EF` | THero |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55786EB4` | `AoWE.THero.OfferToJoin@23EDC2EF` | THero |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x55786B30` | `AoWE.THero.ShowEx@23EDC2EF` | THero |
| `0x1A8` | `0x5577FD3C` | `AoWE.TAbstractUnit.UnitKilled@23EDC2EF` | TAbstractUnit |
| `0x1AC` | `0x55787164` | `AoWE.THero.Killed@23EDC2EF` | THero |
| `0x1B0` | `0x55787224` | `AoWE.THero.Resurrect@23EDC2EF` | THero |
| `0x1B4` | `0x55787244` | `AoWE.THero.Animate@23EDC2EF` | THero |
| `0x1B8` | `0x55786AB0` | `AoWE.THero.GetNickname@23EDC2EF` | THero |
| `0x1BC` | `0x55786AC4` | `AoWE.THero.SetNickname@23EDC2EF` | THero |
| `0x1C0` | `0x55788840` | `AoWE.THero.SetHeroResourceIndex@23EDC2EF` | THero |
| `0x1C4` | `0x55788B40` | `AoWE.THero.EditDropMsg@23EDC2EF` | THero |

## TItem  —  VMT `0x5570FAFC`, instance `0x4C`, 45 slots, ends `0xB4`

<details><summary>derivation notes</summary>

```
COMPLETE — 45 slots, +0x00..+0x0B0, every one has a real RTTI symbol (zero unknowns). Class name ShortString "TItem" @0x5570FBD2; class-ref export AoWE..TItem@228E47F6 = the VMT address itself.

== HOW DERIVED / CONFIDENCE ==
Parsed Modding Resources/AoWEPACK_original_backup.dpl (same bytes Ghidra holds) and resolved every slot through the DPL's own export table (10036 named exports) plus its import table. Cross-checked against Ghidra (AoWEPACK_vanilla.dpl) with get_function_by_address on 5 sampled slots (0x20 Create, 0xA0 Use, 0x30 Clear, 0x8C GetAbilitySelectionTypes, 0xB0 Deactivate) and read_memory on the header + tail — all identical. Scripts: <scratchpad>/ad_titem_full.py, ad_titem_thunks.py, ad_titem_chain.py, ad_teobject.py; row dump in ad_titem_rows.json.

== ⚠ TRAP: vmtParent IS DOUBLE-INDIRECT ==
The recipe in the task brief says [VMT-0x18] -> parent classref. It is actually a POINTER TO a classref cell: parent = [[VMT-0x18]]. Reading it singly gives 0x5570F548, which is not a VMT and decodes as string bytes ("bili"), producing a bogus "chain". Correct read gives 0x5570F588 = TAbilityOwner. Same idiom as Delphi's TObject.ClassParent (MOV EAX,[EAX+vmtParent]; MOV EAX,[EAX]). Additionally, when the parent lives in another package the cell is an IAT entry, so in the on-disk image it holds a hint/name RVA (e.g. 0x002086EA), not an address — dereference it against the import table instead.

== FULL VMT HEADER LAYOUT (this Delphi build; differs from stock Delphi 3) ==
Empirically verified on TItem, TAbilityOwner, TCustomAbilityList and EngineP's TEObject:
  [VMT-0x40] vmtSelfPtr        = 0x5570FAFC (== VMT; a reliable "is this really a VMT?" test)
  [VMT-0x3C] vmtIntfTable      = 0
  [VMT-0x38] vmtAutoTable      = 0
  [VMT-0x34] vmtInitTable      = 0x5570FBB0
  [VMT-0x30] vmtTypeInfo       = 0
  [VMT-0x2C] vmtFieldTable     = 0
  [VMT-0x28] vmtMethodTable    = 0
  [VMT-0x24] vmtDynamicTable   = 0
  [VMT-0x20] vmtClassName      -> ShortString "TItem" @0x5570FBD2
  [VMT-0x1C] vmtInstanceSize   = 0x4C
  [VMT-0x18] vmtParent         -> cell holding 0x5570F588 (TAbilityOwner)   <-- double indirect
  [VMT-0x14] vmtSafeCallException = 0x557010C8 -> VCL30.dpl!System.TObject.SafeCallException
  [VMT-0x10] vmtDefaultHandler   = 0x557010D0 -> VCL30.dpl!System.TObject.DefaultHandler
  [VMT-0x0C] vmtNewInstance      = 0x55701098 -> VCL30.dpl!System.TObject.NewInstance
  [VMT-0x08] vmtFreeInstance     = 0x557010A0 -> VCL30.dpl!System.TObject.FreeInstance
  [VMT-0x04] vmtDestroy          = 0x55793E9C -> AoWE.TItem.Destroy@23EDC2EF
Note the header is 0x40 bytes, not stock D3's 0x4C: vmtAfterConstruction/vmtBeforeDestruction/vmtDispatch are absent (3 dwords fewer between vmtClassName and vmtDestroy).
⚠ TItem.Destroy is at VMT-0x04, NOT a positive slot — a VMT-slot hook table that only walks +0x00 upward will miss the destructor entirely.

== VMT END = +0xB4, PROVEN STRUCTURALLY ==
[VMT+0xB4] = 0x0000000E, not a code pointer. Better proof than the "not in CODE" heuristic: vmtInitTable ([VMT-0x34]) = 0x5570FBB0 = VMT+0xB4 exactly, i.e. the RTTI init-table record is laid out immediately after the last VMT slot, so the last slot is +0xB0. Bytes past the end: +0xB4=0000000E, +0xB8=00030000, +0xBC=B72C0000, +0xC0=0018558F.

== ANCESTOR CHAIN (derived) AND WHERE EACH SLOT IS INTRODUCED ==
  TItem              VMT 0x5570FAFC  instsize 0x4C  vmt_end 0xB4 (45 slots)
  TAbilityOwner      VMT 0x5570F588  instsize 0x14  vmt_end 0x9C (39 slots)
  TCustomAbilityList VMT 0x5570F3DC  instsize 0x10  vmt_end 0x5C (23 slots)
  TEObject           VMT 0x5550C188 in EngineP.dpl (base 0x55500000), instsize 0x8, vmt_end 0x4C (19 slots)
  System.TObject     (VCL30.dpl, external)
Introduction ranges follow the vmt_end boundaries exactly (19+4+16+6 = 45):
  +0x00..+0x48 (19 slots) introduced by TEObject
  +0x4C..+0x58 (4 slots)  introduced by TCustomAbilityList
  +0x5C..+0x98 (16 slots) introduced by TAbilityOwner
  +0x9C..+0xB0 (6 slots)  introduced by TItem   (Can
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x55793F18` | `AoWE.TItem.SetOwner@23EDC2EF` | TItem |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x557945C8` | `AoWE.TItem.ReadWrite@23EDC2EF` | TItem |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55793E48` | `AoWE.TItem.Create@23EDC2EF` | TItem |
| `0x24` | `0x5579437C` | `AoWE.TItem.ClassID@23EDC2EF` | TItem |
| `0x28` | `0x55793EF8` | `AoWE.TItem.AddRef@23EDC2EF` | TItem |
| `0x2C` | `0x55793F00` | `AoWE.TItem.Release@23EDC2EF` | TItem |
| `0x30` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55794878` | `AoWE.TItem.MsgProc@23EDC2EF` | TItem |
| `0x48` | `0x55794274` | `AoWE.TItem.SetArrayOwner@23EDC2EF` | TItem |
| `0x4C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x50` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x54` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x58` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x5C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x60` | `0x55794498` | `AoWE.TItem.GetOwnerName@23EDC2EF` | TItem |
| `0x64` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x68` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x6C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x70` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x74` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x78` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x7C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x80` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x84` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x88` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x8C` | `0x557944AC` | `AoWE.TItem.GetAbilitySelectionTypes@23EDC2EF` | TItem |
| `0x90` | `0x55794360` | `AoWE.TItem.Changed@23EDC2EF` | TItem |
| `0x94` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x98` | `0x5574F5EC` | `AoWE.TAbilityOwner.RemoveAbility@23EDC2EF` | TAbilityOwner |
| `0x9C` | `0x557940AC` | `AoWE.TItem.CanUse@23EDC2EF` | TItem |
| `0xA0` | `0x557941B4` | `AoWE.TItem.Use@23EDC2EF` | TItem |
| `0xA4` | `0x55793F68` | `AoWE.TItem.ExecuteUse@23EDC2EF` | TItem |
| `0xA8` | `0x5579452C` | `AoWE.TItem.Show@23EDC2EF` | TItem |
| `0xAC` | `0x55794308` | `AoWE.TItem.Activate@23EDC2EF` | TItem |
| `0xB0` | `0x55794344` | `AoWE.TItem.Deactivate@23EDC2EF` | TItem |

## TRangedAttackAbility  —  VMT `0x5571E8D4`, instance `0x30`, 72 slots, ends `0x120`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
Two independent sources agree byte-for-byte. (1) File parse of "Modding Resources/AoWEPACK_original_backup.dpl" (same bytes Ghidra holds) using the Delphi RTTI recipe. (2) Ghidra read_memory at 0x5571E8D4 length 304 returned an identical byte run. Symbols come from the DPL's own export table (.edata: 10036 exports, 10033 distinct VAs) — i.e. Delphi's published RTTI names, not inference. Four slots were cross-checked against mcp__ghidra__get_function_by_address (0x5576E5C4, 0x5576ECF0, 0x55764C70, 0x5574E814) and matched exactly.

VMT LOCATION
Class-name ShortString "\x14TRangedAttackAbility" at 0x5571E9F4; the dword pointing at it is at 0x5571E8B4, so VMT = 0x5571E8B4 + 0x20 = 0x5571E8D4. [VMT-0x1C] = 0x30 instance size, [VMT-0x18] = 0x5571D8F0 -> parent VMT 0x5571D930 (TAdjustableAbility).

WHERE THE VMT ENDS — 0x120, and it is unambiguous
Slot +0x11C (0x5576E6B0) is the last CODE pointer. The dword at +0x120 reads 0x61525414, which is not a code address: those bytes are 14 54 52 61 6E 67 65 64 41 74 74 61 63 6B 41 62 ... = the length-prefixed ShortString "\x14TRangedAttackAbility" itself, which sits immediately after the VMT at 0x5571E9F4 (= VMT + 0x120). Exactly the failure mode the brief warned about. So: 72 slots, 0x00..0x11C inclusive.

ANCESTRY (each link derived from [VMT-0x18], not assumed)
  TRangedAttackAbility  VMT=0x5571E8D4  instsize=0x30  72 slots (ends 0x120)
  TAdjustableAbility    VMT=0x5571D930  instsize=0x28  67 slots (ends 0x10C)
  TAbility              VMT=0x5570F254  instsize=0x24  67 slots (ends 0x10C)
  Engine.TEObject       (external — TAbility's parent classref 0x558FC92C lies in .idata, i.e. imported from EngineP.dpl, so the chain leaves this module here)

SLOT OWNERSHIP TALLY (72 total)
  Engine.TEObject ....... 17 slots (inherited, imported)
  TAbility .............. 37 slots (inherited)
  TAdjustableAbility ..... 1 slot  (inherited)
  TRangedAttackAbility .. 17 slots (12 overrides + 5 brand-new virtuals)

TEObject SLOTS ARE IMPORT THUNKS — IMPORTANT FOR PATCHING
The 17 TEObject slots do not hold EngineP.dpl addresses. Each holds a local AoWEPACK stub in the 0x55703074..0x55703104 block of the form "JMP dword ptr [<IAT slot>]" followed by "MOV EAX,EAX" padding (verified: 0x55703074 = FF 25 24 C7 8F 55 -> IAT 0x558FC724). Ghidra has no function defined at these addresses (get_function_by_address returns "No function found"), which is why they look nameless in a decompile — the name comes from the import table. target_va below is the thunk VA (what is actually stored in the VMT slot), which is the address that matters for a VMT-slot patch. IAT slots for reference: +0x000->0x558FC724, +0x004->0x558FC6F0, +0x008->0x558FC6EC, +0x00C->0x558FC6F4, +0x010->0x558FC708, +0x014->0x558FC704, +0x01C->0x558FC6DC, +0x024->0x558FC714, +0x028->0x558FC720, +0x02C->0x558FC71C, +0x030->0x558FC718, +0x034->0x558FC700, +0x038->0x558FC710, +0x03C->0x558FC6FC, +0x040->0x558FC70C, +0x044->0x558FC6E4, +0x048->0x558FC6E8.

WHAT TRangedAttackAbility ACTUALLY ADDS
Five new virtuals at the tail, past every ancestor's VMT end (0x10C) — the "RA" (ranged-attack) accessor block:
  +0x10C GetRangeRA, +0x110 GetDamageRA, +0x114 GetAttackRA, +0x118 GetAttackRepeatRA, +0x11C GetDamageTypesRA
These are tiny (GetRangeRA is 4 bytes, GetDamageTypesRA is 7) — plain field getters over the 8 bytes of instance data TRangedAttackAbility adds on top of TAdjustableAbility's 0x28.
Twelve overrides of inherited slots: +0x020 Create, +0x084 GetCombatMode, +0x088 GetWallCombatFeatures, +0x098 GetControlType, +0x09C fcValidRoundDistance, +0x0A0 fcPrefetchCombatCommands, +0x0A4 fcExecuteCombatCommand, +0x0D8 GetDamageValue, +0x0DC GetDamageValueEx, +0x0E0 GetOffensiveStrength, +0x0E4 fcGetDamageValueEx, +0x104 GetCombatInfo.

TAdjustableAbility IS NEARLY A NO-OP LAYER
It overrides exactly ONE slot versus TAbility — +0x054 GetAbilityType (0x5574EF1C -> 0x55764C70, a 4-byte stub) — and adds 4 bytes of instance data. Worth knowing
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x0` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x4` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x8` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0xC` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x5574F07C` | `AoWE.TAbility.ReadWrite@23EDC2EF` | TAbility |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x5576E5C4` | `AoWE.TRangedAttackAbility.Create@23EDC2EF` | TRangedAttackAbility |
| `0x24` | `0x55703094` | `Engine.TEObject.ClassID@23EDC2EF` | TEObject |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5574EF2C` | `AoWE.TAbility.Execute@23EDC2EF` | TAbility |
| `0x50` | `0x5574E9AC` | `AoWE.TAbility.GetHidden@23EDC2EF` | TAbility |
| `0x54` | `0x55764C70` | `AoWE.TAdjustableAbility.GetAbilityType@23EDC2EF` | TAdjustableAbility |
| `0x58` | `0x5574E97C` | `AoWE.TAbility.GetName@23EDC2EF` | TAbility |
| `0x5C` | `0x5574E990` | `AoWE.TAbility.GetAttack@23EDC2EF` | TAbility |
| `0x60` | `0x5574E994` | `AoWE.TAbility.GetDefense@23EDC2EF` | TAbility |
| `0x64` | `0x5574E998` | `AoWE.TAbility.GetResistance@23EDC2EF` | TAbility |
| `0x68` | `0x5574E99C` | `AoWE.TAbility.GetDamage@23EDC2EF` | TAbility |
| `0x6C` | `0x5574E9A0` | `AoWE.TAbility.GetMoveTypes@23EDC2EF` | TAbility |
| `0x70` | `0x5574E9B0` | `AoWE.TAbility.GetLevel@23EDC2EF` | TAbility |
| `0x74` | `0x5574EEF4` | `AoWE.TAbility.GetEnabled@23EDC2EF` | TAbility |
| `0x78` | `0x5574EF00` | `AoWE.TAbility.GetImmunityTypes@23EDC2EF` | TAbility |
| `0x7C` | `0x5574EF0C` | `AoWE.TAbility.GetProtectionTypes@23EDC2EF` | TAbility |
| `0x80` | `0x5574E958` | `AoWE.TAbility.GetSkillPoints@23EDC2EF` | TAbility |
| `0x84` | `0x5576E6B8` | `AoWE.TRangedAttackAbility.GetCombatMode@23EDC2EF` | TRangedAttackAbility |
| `0x88` | `0x5576E6D4` | `AoWE.TRangedAttackAbility.GetWallCombatFeatures@23EDC2EF` | TRangedAttackAbility |
| `0x8C` | `0x5574E704` | `AoWE.TAbility.GetSourceName@23EDC2EF` | TAbility |
| `0x90` | `0x5574E948` | `AoWE.TAbility.GetInherent@23EDC2EF` | TAbility |
| `0x94` | `0x5574E954` | `AoWE.TAbility.GetInherentLevel@23EDC2EF` | TAbility |
| `0x98` | `0x5576E604` | `AoWE.TRangedAttackAbility.GetControlType@23EDC2EF` | TRangedAttackAbility |
| `0x9C` | `0x5576ECF0` | `AoWE.TRangedAttackAbility.fcValidRoundDistance@23EDC2EF` | TRangedAttackAbility |
| `0xA0` | `0x5576EC10` | `AoWE.TRangedAttackAbility.fcPrefetchCombatCommands@23EDC2EF` | TRangedAttackAbility |
| `0xA4` | `0x5576EB70` | `AoWE.TRangedAttackAbility.fcExecuteCombatCommand@23EDC2EF` | TRangedAttackAbility |
| `0xA8` | `0x5574EF30` | `AoWE.TAbility.NewDay@23EDC2EF` | TAbility |
| `0xAC` | `0x5574EF34` | `AoWE.TAbility.NewTurn@23EDC2EF` | TAbility |
| `0xB0` | `0x5574EF40` | `AoWE.TAbility.CanActivate@23EDC2EF` | TAbility |
| `0xB4` | `0x5574EF68` | `AoWE.TAbility.Activate@23EDC2EF` | TAbility |
| `0xB8` | `0x5574EFDC` | `AoWE.TAbility.CanActivateCombat@23EDC2EF` | TAbility |
| `0xBC` | `0x5574F004` | `AoWE.TAbility.ActivateCombat@23EDC2EF` | TAbility |
| `0xC0` | `0x5574EF18` | `AoWE.TAbility.ListSpells@23EDC2EF` | TAbility |
| `0xC4` | `0x5574E8B8` | `AoWE.TAbility.CanExpand@23EDC2EF` | TAbility |
| `0xC8` | `0x5574E908` | `AoWE.TAbility.ExpandCost@23EDC2EF` | TAbility |
| `0xCC` | `0x5574E8F4` | `AoWE.TAbility.ExpandName@23EDC2EF` | TAbility |
| `0xD0` | `0x5574E90C` | `AoWE.TAbility.Expand@23EDC2EF` | TAbility |
| `0xD4` | `0x5574E91C` | `AoWE.TAbility.Remove@23EDC2EF` | TAbility |
| `0xD8` | `0x5576E764` | `AoWE.TRangedAttackAbility.GetDamageValue@23EDC2EF` | TRangedAttackAbility |
| `0xDC` | `0x5576E7FC` | `AoWE.TRangedAttackAbility.GetDamageValueEx@23EDC2EF` | TRangedAttackAbility |
| `0xE0` | `0x5576E704` | `AoWE.TRangedAttackAbility.GetOffensiveStrength@23EDC2EF` | TRangedAttackAbility |
| `0xE4` | `0x5576E8D4` | `AoWE.TRangedAttackAbility.fcGetDamageValueEx@23EDC2EF` | TRangedAttackAbility |
| `0xE8` | `0x5574E814` | `AoWE.TAbility.fcGetDamageValue@23EDC2EF` | TAbility |
| `0xEC` | `0x5574E844` | `AoWE.TAbility.tcGetDamageValueEx@23EDC2EF` | TAbility |
| `0xF0` | `0x5574E868` | `AoWE.TAbility.tcGetDamageValue@23EDC2EF` | TAbility |
| `0xF4` | `0x5574EF20` | `AoWE.TAbility.CombatObjectDestroyed@23EDC2EF` | TAbility |
| `0xF8` | `0x5574EF38` | `AoWE.TAbility.NewCombatTurn@23EDC2EF` | TAbility |
| `0xFC` | `0x5574EF3C` | `AoWE.TAbility.CombatDone@23EDC2EF` | TAbility |
| `0x100` | `0x5574E9D0` | `AoWE.TAbility.ListInfo@23EDC2EF` | TAbility |
| `0x104` | `0x5576EA8C` | `AoWE.TRangedAttackAbility.GetCombatInfo@23EDC2EF` | TRangedAttackAbility |
| `0x108` | `0x5574E978` | `AoWE.TAbility.AbilityDataClass@23EDC2EF` | TAbility |
| `0x10C` | `0x5576E610` | `AoWE.TRangedAttackAbility.GetRangeRA@23EDC2EF` | TRangedAttackAbility |
| `0x110` | `0x5576E614` | `AoWE.TRangedAttackAbility.GetDamageRA@23EDC2EF` | TRangedAttackAbility |
| `0x114` | `0x5576E65C` | `AoWE.TRangedAttackAbility.GetAttackRA@23EDC2EF` | TRangedAttackAbility |
| `0x118` | `0x5576E6AC` | `AoWE.TRangedAttackAbility.GetAttackRepeatRA@23EDC2EF` | TRangedAttackAbility |
| `0x11C` | `0x5576E6B0` | `AoWE.TRangedAttackAbility.GetDamageTypesRA@23EDC2EF` | TRangedAttackAbility |

## TStrikeCA  —  VMT `0x5571E344`, instance `0x1C`, 28 slots, ends `0x70`

<details><summary>derivation notes</summary>

```
ALL ADDRESSES ARE PREFERRED-BASE VAs (image base 0x55700000); the DPL rebases at runtime.

WHY vmt_end = 0x70 (hard proof, not a guess): the dword at VMT+0x70 is 0x5571E3B4, which is exactly the value of vmtClassName ([VMT-0x20]). Its bytes are 09 'TStrikeCA' — the class-name ShortString, which Delphi lays down immediately after the VMT. So the VMT is exactly 0x70 bytes = 28 virtual slots (+0x00..+0x6C). Nothing at or beyond +0x70 is a method pointer.

INHERITANCE CHAIN (derived by walking vmtParent = [VMT-0x18]):
  TStrikeCA       VMT=0x5571E344  instsize=0x1C  vmt_end=0x70  (28 slots)
  TDamageCA       VMT=0x557162F4  instsize=0x18  vmt_end=0x70  (28 slots)
  TSingleTargetCA VMT=0x557161CC  instsize=0x10  vmt_end=0x64  (25 slots)
  TCombatAction   VMT=0x557160B4  instsize=0x0C  vmt_end=0x64  (25 slots)
  Engine.TEObject -- NOT in this module; vmtParent is IAT slot 0x558FC92C = "Engine..TEObject@BD8FE92F" imported from EngineP.dpl. Its VMT is 0x4C long (19 slots) - measured from two direct TEObject descendants in AoWEPACK that add no virtuals of their own (TUnitProduction VMT=0x5570A0D0 and TProductionSettings VMT=0x5570A4B4, both vmt_end=0x4C).
  TObject         (VCL30.dpl)

DELPHI 2/3 VMT HEADER (confirmed: vmtSelfPtr at -0x40 equals the VMT address):
  -0x40 SelfPtr           = 0x5571E344
  -0x3C..-0x24            = 0 (IntfTable, AutoTable, InitTable, TypeInfo, FieldTable, MethodTable, DynamicTable all NULL -> TStrikeCA has NO published fields, NO RTTI type info, and NO dynamic/message methods)
  -0x20 ClassName         = 0x5571E3B4 -> "TStrikeCA"
  -0x1C InstanceSize      = 0x1C
  -0x18 Parent            = 0x557162B4 (classref cell holding TDamageCA's VMT 0x557162F4)
  -0x14 SafeCallException = 0x557010C8 thunk -> VCL30.dpl  System.TObject.SafeCallException@23EDC2EF
  -0x10 DefaultHandler    = 0x557010D0 thunk -> VCL30.dpl  System.TObject.DefaultHandler@23EDC2EF
  -0x0C NewInstance       = 0x55701098 thunk -> VCL30.dpl  System.TObject.NewInstance@23EDC2EF
  -0x08 FreeInstance      = 0x557010A0 thunk -> VCL30.dpl  System.TObject.FreeInstance@23EDC2EF
  -0x04 Destroy           = 0x5570306C thunk -> EngineP.dpl Engine.TEObject.Destroy@23EDC2EF  (NOT overridden anywhere in the chain)

IMPORT-THUNK MECHANISM (this is why Ghidra reports "No function found" for the 0x5570xxxx slot targets, and why get_function_by_address/decompile fail there): every slot whose owner is TEObject points at an 8-byte import stub in the thunk table at the start of CODE. Layout per entry: FF 25 <imm32 IAT ptr> followed by 8B C0 padding. E.g. 0x55703074 = "jmp dword ptr [0x558FC724]" and IAT 0x558FC724 = EngineP.dpl!Engine.TEObject.ClassVersion@23EDC2EF. The real code lives in EngineP.dpl, which is NOT present in this game directory (glob found no EngineP.dpl) and is NOT loaded in Ghidra. The symbols above come from the PE import table, which is ground truth. Do not try to decompile those addresses in Ghidra - read the thunk's imm32 and look up the IAT instead.

WHERE EACH SLOT IS INTRODUCED (vs merely overridden):
- +0x00..+0x48 (19 slots) are ALL introduced by Engine.TEObject; its VMT is 0x4C long. TEObject slot order, verified against direct descendants: ClassVersion, GetControlStyle, SetOwner, GetEngine, GetLastMsg, SetLastMsg, ReadWrite, MainReadWrite, Create, ClassID, AddRef, Release, Clear, Compare, Editor, Assign, TimerEvent, MsgProc, SetArrayOwner.
  Of these, 5 are overridden somewhere in TStrikeCA's chain: +0x18 ReadWrite (by TStrikeCA), +0x20 Create (by TCombatAction), +0x24 ClassID (by TStrikeCA), +0x28 AddRef and +0x2C Release (by TCombatAction). The other 14 still run TEObject's code.
  Note Engine.TEObject.Copy@23EDC2EF (IAT 0x558FC6F8) is imported but occupies no VMT slot - it is a non-virtual method.
- +0x4C..+0x60 (6 slots) are introduced by TCombatAction (its VMT grows from TEObject's 0x4C to 0x64): GetName, Execute, Play, ShowObject, ShowFieldObject, ShowFightingObjects.
- +0x64..+0x6C (3 slots) are introduced by TDamageCA (VMT gr
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x0C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55766714` | `AoWE.TStrikeCA.ReadWrite@23EDC2EF` | TStrikeCA |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x557298B4` | `AoWE.TCombatAction.Create@23EDC2EF` | TCombatAction |
| `0x24` | `0x5576670C` | `AoWE.TStrikeCA.ClassID@23EDC2EF` | TStrikeCA |
| `0x28` | `0x557298EC` | `AoWE.TCombatAction.AddRef@23EDC2EF` | TCombatAction |
| `0x2C` | `0x557298F4` | `AoWE.TCombatAction.Release@23EDC2EF` | TCombatAction |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x557030F4` | `Engine.TEObject.MsgProc@23EDC2EF` | TEObject |
| `0x48` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x4C` | `0x5572990C` | `AoWE.TCombatAction.GetName@23EDC2EF` | TCombatAction |
| `0x50` | `0x55766738` | `AoWE.TStrikeCA.Execute@23EDC2EF` | TStrikeCA |
| `0x54` | `0x55766860` | `AoWE.TStrikeCA.Play@23EDC2EF` | TStrikeCA |
| `0x58` | `0x55729E1C` | `AoWE.TDamageCA.ShowObject@23EDC2EF` | TDamageCA |
| `0x5C` | `0x55729A0C` | `AoWE.TSingleTargetCA.ShowFieldObject@23EDC2EF` | TSingleTargetCA |
| `0x60` | `0x55729B1C` | `AoWE.TSingleTargetCA.ShowFightingObjects@23EDC2EF` | TSingleTargetCA |
| `0x64` | `0x55729BE4` | `AoWE.TDamageCA.Setup@23EDC2EF` | TDamageCA |
| `0x68` | `0x557668B4` | `AoWE.TStrikeCA.Generate@23EDC2EF` | TStrikeCA |
| `0x6C` | `0x55729C98` | `AoWE.TDamageCA.GenerateEx@23EDC2EF` | TDamageCA |

## TStructure  —  VMT `0x55713C18`, instance `0x30`, 124 slots, ends `0x1F0`

<details><summary>derivation notes</summary>

```
UNIT/MODULE: AoWE unit, AoWEPACK.dpl (preferred base 0x55700000, which is also Ghidra's image base, so VAs below are directly usable in Ghidra). 124 slots (0x1F0/4), ALL resolved to real RTTI symbols — zero unknowns.

METHOD: symbols came from the DPL's own export table (10036 named exports) plus the import table, parsed from Modding Resources/AoWEPACK_original_backup.dpl (the same pristine bytes Ghidra holds). This is ground truth, not inference. Scripts left in the scratchpad: tstructure_vmt.py, exports.py, vmt_full.py, check.py, tstruct_chain.py.

*** THE INHERITED SLOTS ARE IMPORT THUNKS, NOT LOCAL FUNCTIONS ***
55 of the 124 slots point into 0x55701000-0x557035FF, the thunk block at the very start of CODE. Each is `FF 25 <abs32>` = `jmp dword ptr [IAT]` followed by `8B C0` padding (verified: 0x55703074 = ff2524c78f55 8bc0 -> IAT 0x558FC724). Ghidra returns "No function found" for these because it never made them functions — that is expected, not a gap. The IAT entry's import name IS the ancestor's full RTTI symbol, which is where every inherited symbol below comes from. Consequence for modding: to hook an inherited slot you are pointing at a 6-byte jump stub shared by every AoWEPACK class that inherits it — patching the stub hits ALL of them; patching the VMT slot hits only TStructure.

VMT HEADER (measured, all negative offsets read directly):
  -0x24  0x00000000   (empty table ptr)
  -0x20  0x55713E08   -> ShortString "TStructure" (len byte 0x0A)
  -0x1C  0x00000030   instance size = 48 bytes
  -0x18  0x558FCA08   vmtParent -> IAT slot, HSEPack.dpl ! ILTer..TFixedILTerrainMO@DE482B1C
  -0x14  0x557010C8   thunk -> VCL30.dpl ! System.TObject.SafeCallException
  -0x10  0x557010D0   thunk -> VCL30.dpl ! System.TObject.DefaultHandler
  -0x0C  0x55701098   thunk -> VCL30.dpl ! System.TObject.NewInstance
  -0x08  0x557010A0   thunk -> VCL30.dpl ! System.TObject.FreeInstance
  -0x04  0x5575E5C8   AoWE.TStructure.Destroy@23EDC2EF   <-- TStructure OVERRIDES Destroy; it is at -0x04, NOT in the positive slot range
No AfterConstruction/BeforeDestruction/Dispatch slots exist (Delphi 2-era layout), so do not assume the modern Delphi vmt* constants.

PROOF OF VMT END (0x1F0): [VMT-0x20] (the class-name pointer) equals VMT+0x1F0 exactly — the class-name ShortString is laid down immediately after the last slot. Bytes at VMT+0x1EC are `80 FB 75 55 | 0A 54 53 74 72 75 63 74 75 72 65` = last slot (CanRaze) then 0x0A "TStructure". So VMT+0x1F0 reads 0x7453540A, which is string data, not a code pointer. Last valid slot = +0x1EC.

ANCESTRY (derived by following vmtParent across packages, not guessed):
  System.TObject            vcl30.dpl      VMT 0x41301244  instsize 0x04
   -> Engine.TEObject       Enginep.dpl    VMT 0x5550C188  instsize 0x08
   -> HSEngine.THexagonSprite  HSEPack.dpl VMT 0x55603694  instsize 0x08   VMT ends +0x108
   -> HSEngine.TMapObject      HSEPack.dpl VMT 0x55604190  instsize 0x10   VMT ends +0x11C
   -> HSEngine.TMultiHexMO     HSEPack.dpl VMT 0x55604540  instsize 0x14   VMT ends +0x128
   -> ILTer.TILTerrainMO       HSEPack.dpl VMT 0x556181E8  instsize 0x1C   VMT ends +0x138
   -> ILTer.TFixedILTerrainMO  HSEPack.dpl VMT 0x55618484  instsize 0x1C   VMT ends +0x138  (adds no new virtuals, only overrides)
   -> AoWE.TStructure          AoWEPACK.dpl VMT 0x55713C18 instsize 0x30   VMT ends +0x1F0

*** KEY BOUNDARY: 0x138 ***
The direct parent TFixedILTerrainMO's VMT ends at +0x138. Therefore slots +0x000..+0x134 (78 slots) are the INHERITED slot range, and slots +0x138..+0x1EC (46 slots) are methods TStructure INTRODUCES. This is independently confirmed: every single slot from +0x138 upward carries an AoWE.TStructure symbol, and the last non-TStructure slot is exactly +0x134. Breakdown: 55 slots inherited-as-is + 23 TStructure overrides within +0x000..+0x134, + 46 new = 124. Owner histogram: TStructure 69, TMapObject 20, TEObject 15, TMultiHexMO 9, THexagonSprite 8, TILTerrainMO 2, TFixedILTerrainMO 1.

THE 23 OVERRIDDE
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x557030E4` | `Engine.TEObject.SetOwner@23EDC2EF` | TEObject |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x5575E658` | `AoWE.TStructure.ReadWrite@23EDC2EF` | TStructure |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x5575E590` | `AoWE.TStructure.Create@23EDC2EF` | TStructure |
| `0x024` | `0x5575E588` | `AoWE.TStructure.ClassID@23EDC2EF` | TStructure |
| `0x028` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x02C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x030` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x5575F898` | `AoWE.TStructure.MsgProc@23EDC2EF` | TStructure |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5575EC04` | `AoWE.TStructure.GetTerrain@23EDC2EF` | TStructure |
| `0x050` | `0x557021BC` | `HSEngine.TMapObject.SetTerrain@23EDC2EF` | TMapObject |
| `0x054` | `0x557021C4` | `HSEngine.TMapObject.GetTerrainCount@23EDC2EF` | TMapObject |
| `0x058` | `0x5575EBF0` | `AoWE.TStructure.GetOverlay@23EDC2EF` | TStructure |
| `0x05C` | `0x557021D4` | `HSEngine.TMapObject.SetOverlay@23EDC2EF` | TMapObject |
| `0x060` | `0x557021DC` | `HSEngine.TMapObject.GetOverlayCount@23EDC2EF` | TMapObject |
| `0x064` | `0x5570213C` | `HSEngine.TMapObject.GetLevel@23EDC2EF` | TMapObject |
| `0x068` | `0x55702134` | `HSEngine.TMapObject.SetVisible@23EDC2EF` | TMapObject |
| `0x06C` | `0x5570214C` | `HSEngine.TMapObject.GetVisible@23EDC2EF` | TMapObject |
| `0x070` | `0x557021AC` | `HSEngine.TMapObject.GetSelected@23EDC2EF` | TMapObject |
| `0x074` | `0x55702394` | `HSEngine.TMultiHexMO.GetXhx@23EDC2EF` | TMultiHexMO |
| `0x078` | `0x5570239C` | `HSEngine.TMultiHexMO.GetYhx@23EDC2EF` | TMultiHexMO |
| `0x07C` | `0x55702174` | `HSEngine.TMapObject.GetLhx@23EDC2EF` | TMapObject |
| `0x080` | `0x557023A4` | `HSEngine.TMultiHexMO.GetXYL@23EDC2EF` | TMultiHexMO |
| `0x084` | `0x5570215C` | `HSEngine.TMapObject.GetEditMode@23EDC2EF` | TMapObject |
| `0x088` | `0x55702154` | `HSEngine.TMapObject.SetEditMode@23EDC2EF` | TMapObject |
| `0x08C` | `0x557023AC` | `HSEngine.TMultiHexMO.GetShowPriority@23EDC2EF` | TMultiHexMO |
| `0x090` | `0x557023C4` | `HSEngine.TMultiHexMO.Connect@23EDC2EF` | TMultiHexMO |
| `0x094` | `0x557023CC` | `HSEngine.TMultiHexMO.Disconnect@23EDC2EF` | TMultiHexMO |
| `0x098` | `0x5575EC1C` | `AoWE.TStructure.CanChangeTerrain@23EDC2EF` | TStructure |
| `0x09C` | `0x557035AC` | `ILTer.TFixedILTerrainMO.ChangeTerrain@23EDC2EF` | TFixedILTerrainMO |
| `0x0A0` | `0x5575EC80` | `AoWE.TStructure.TerrainChanged@23EDC2EF` | TStructure |
| `0x0A4` | `0x55701E3C` | `HSEngine.THexagonSprite.NeighbourTerrainChanged@23EDC2EF` | THexagonSprite |
| `0x0A8` | `0x5575F958` | `AoWE.TStructure.Show@23EDC2EF` | TStructure |
| `0x0AC` | `0x5575E7C0` | `AoWE.TStructure.PlaceOnMap@23EDC2EF` | TStructure |
| `0x0B0` | `0x5575E7EC` | `AoWE.TStructure.RemoveFromMap@23EDC2EF` | TStructure |
| `0x0B4` | `0x5570225C` | `HSEngine.TMapObject.MainPlace@23EDC2EF` | TMapObject |
| `0x0B8` | `0x55702264` | `HSEngine.TMapObject.MainRemove@23EDC2EF` | TMapObject |
| `0x0BC` | `0x55701EC4` | `HSEngine.THexagonSprite.MainLoaded@23EDC2EF` | THexagonSprite |
| `0x0C0` | `0x557021FC` | `HSEngine.TMapObject.Place@23EDC2EF` | TMapObject |
| `0x0C4` | `0x5570223C` | `HSEngine.TMapObject.Remove@23EDC2EF` | TMapObject |
| `0x0C8` | `0x55703574` | `ILTer.TILTerrainMO.Loaded@23EDC2EF` | TILTerrainMO |
| `0x0CC` | `0x5575F730` | `AoWE.TStructure.MapFieldMsgProc@23EDC2EF` | TStructure |
| `0x0D0` | `0x55701D54` | `HSEngine.THexagonSprite.CanMoveOn@23EDC2EF` | THexagonSprite |
| `0x0D4` | `0x55701D5C` | `HSEngine.THexagonSprite.CanMoveOver@23EDC2EF` | THexagonSprite |
| `0x0D8` | `0x55701D64` | `HSEngine.THexagonSprite.MoveExclusive@23EDC2EF` | THexagonSprite |
| `0x0DC` | `0x55701D8C` | `HSEngine.THexagonSprite.Changed@23EDC2EF` | THexagonSprite |
| `0x0E0` | `0x5575F6C0` | `AoWE.TStructure.Activate@23EDC2EF` | TStructure |
| `0x0E4` | `0x5575F710` | `AoWE.TStructure.Deactivate@23EDC2EF` | TStructure |
| `0x0E8` | `0x55701D9C` | `HSEngine.THexagonSprite.ControlMode@23EDC2EF` | THexagonSprite |
| `0x0EC` | `0x55760444` | `AoWE.TStructure.UpdateMapField@23EDC2EF` | TStructure |
| `0x0F0` | `0x5570219C` | `HSEngine.TMapObject.MakeVisible@23EDC2EF` | TMapObject |
| `0x0F4` | `0x55701DA4` | `HSEngine.THexagonSprite.GetBaseHX@23EDC2EF` | THexagonSprite |
| `0x0F8` | `0x5575E994` | `AoWE.TStructure.CanSelect@23EDC2EF` | TStructure |
| `0x0FC` | `0x5575EA40` | `AoWE.TStructure.Select@23EDC2EF` | TStructure |
| `0x100` | `0x5575EA64` | `AoWE.TStructure.Unselect@23EDC2EF` | TStructure |
| `0x104` | `0x55702144` | `HSEngine.TMapObject.EditName@23EDC2EF` | TMapObject |
| `0x108` | `0x5570217C` | `HSEngine.TMapObject.GetResourceList@23EDC2EF` | TMapObject |
| `0x10C` | `0x55702194` | `HSEngine.TMapObject.LinkToResource@23EDC2EF` | TMapObject |
| `0x110` | `0x55702184` | `HSEngine.TMapObject.SetResource@23EDC2EF` | TMapObject |
| `0x114` | `0x5575ECC8` | `AoWE.TStructure.CanPlace@23EDC2EF` | TStructure |
| `0x118` | `0x5575ED10` | `AoWE.TStructure.PlaceHX@23EDC2EF` | TStructure |
| `0x11C` | `0x55702424` | `HSEngine.TMultiHexMO.SortMapFields@23EDC2EF` | TMultiHexMO |
| `0x120` | `0x557023F4` | `HSEngine.TMultiHexMO.CanPlaceOnHS@23EDC2EF` | TMultiHexMO |
| `0x124` | `0x55702414` | `HSEngine.TMultiHexMO.GetMostFrequentMapFieldTerrainType@23EDC2EF` | TMultiHexMO |
| `0x128` | `0x5575EC44` | `AoWE.TStructure.ValidTerrainType@23EDC2EF` | TStructure |
| `0x12C` | `0x5575E6A0` | `AoWE.TStructure.GetTerrainTypeImage@23EDC2EF` | TStructure |
| `0x130` | `0x5575E93C` | `AoWE.TStructure.ForceTerrainType@23EDC2EF` | TStructure |
| `0x134` | `0x55703534` | `ILTer.TILTerrainMO.GetValidTerrainType@23EDC2EF` | TILTerrainMO |
| `0x138` | `0x5575EB0C` | `AoWE.TStructure.GetTopBorderImage@23EDC2EF` | TStructure |
| `0x13C` | `0x5575EB58` | `AoWE.TStructure.GetMiddleBorderImage@23EDC2EF` | TStructure |
| `0x140` | `0x5575EBA4` | `AoWE.TStructure.GetBottomBorderImage@23EDC2EF` | TStructure |
| `0x144` | `0x5575E988` | `AoWE.TStructure.GetDescription@23EDC2EF` | TStructure |
| `0x148` | `0x5575E950` | `AoWE.TStructure.GetName@23EDC2EF` | TStructure |
| `0x14C` | `0x5575EDE8` | `AoWE.TStructure.SetRazed@23EDC2EF` | TStructure |
| `0x150` | `0x5575EDE4` | `AoWE.TStructure.GetRazed@23EDC2EF` | TStructure |
| `0x154` | `0x5575EDDC` | `AoWE.TStructure.GetRazeable@23EDC2EF` | TStructure |
| `0x158` | `0x5576023C` | `AoWE.TStructure.RazeEx@23EDC2EF` | TStructure |
| `0x15C` | `0x5575FE0C` | `AoWE.TStructure.SetupRazeDefenderAG@23EDC2EF` | TStructure |
| `0x160` | `0x5575E88C` | `AoWE.TStructure.CreateTE@23EDC2EF` | TStructure |
| `0x164` | `0x5575E89C` | `AoWE.TStructure.SetupTE@23EDC2EF` | TStructure |
| `0x168` | `0x5575E8CC` | `AoWE.TStructure.ExecuteTE@23EDC2EF` | TStructure |
| `0x16C` | `0x5575F378` | `AoWE.TStructure.GetDefenseRequirements@23EDC2EF` | TStructure |
| `0x170` | `0x5575F374` | `AoWE.TStructure.GetDefensePriority@23EDC2EF` | TStructure |
| `0x174` | `0x5575F338` | `AoWE.TStructure.NewDay@23EDC2EF` | TStructure |
| `0x178` | `0x5575F33C` | `AoWE.TStructure.NewTurn@23EDC2EF` | TStructure |
| `0x17C` | `0x5575F36C` | `AoWE.TStructure.SeatedPlayerChanged@23EDC2EF` | TStructure |
| `0x180` | `0x5575F360` | `AoWE.TStructure.ArmyPlaced@23EDC2EF` | TStructure |
| `0x184` | `0x5575F364` | `AoWE.TStructure.ArmyRemoved@23EDC2EF` | TStructure |
| `0x188` | `0x5575F368` | `AoWE.TStructure.ArmyChanged@23EDC2EF` | TStructure |
| `0x18C` | `0x5575EA18` | `AoWE.TStructure.PlaySelectSample@23EDC2EF` | TStructure |
| `0x190` | `0x5575E818` | `AoWE.TStructure.CreateShadow@23EDC2EF` | TStructure |
| `0x194` | `0x5575E850` | `AoWE.TStructure.DestroyShadow@23EDC2EF` | TStructure |
| `0x198` | `0x5575F908` | `AoWE.TStructure.ShowShadow@23EDC2EF` | TStructure |
| `0x19C` | `0x5575F010` | `AoWE.TStructure.BuildingDone@23EDC2EF` | TStructure |
| `0x1A0` | `0x5575EF08` | `AoWE.TStructure.ExecuteRebuild@23EDC2EF` | TStructure |
| `0x1A4` | `0x5575EFD8` | `AoWE.TStructure.ExecuteBuild@23EDC2EF` | TStructure |
| `0x1A8` | `0x5575FD1C` | `AoWE.TStructure.GenerateRazeDefenders@23EDC2EF` | TStructure |
| `0x1AC` | `0x5575FE84` | `AoWE.TStructure.PlaceRazeDefenders@23EDC2EF` | TStructure |
| `0x1B0` | `0x5575FFC8` | `AoWE.TStructure.ExecuteRaze@23EDC2EF` | TStructure |
| `0x1B4` | `0x5575E968` | `AoWE.TStructure.GetCurrentActivityText@23EDC2EF` | TStructure |
| `0x1B8` | `0x5575F4F4` | `AoWE.TStructure.ValidateMap@23EDC2EF` | TStructure |
| `0x1BC` | `0x5575F4F8` | `AoWE.TStructure.MainValidateMap@23EDC2EF` | TStructure |
| `0x1C0` | `0x5575E698` | `AoWE.TStructure.ExecuteAI@23EDC2EF` | TStructure |
| `0x1C4` | `0x5575E69C` | `AoWE.TStructure.UpdateAITarget@23EDC2EF` | TStructure |
| `0x1C8` | `0x5575E878` | `AoWE.TStructure.Update@23EDC2EF` | TStructure |
| `0x1CC` | `0x5575EDEC` | `AoWE.TStructure.VisibleForPlayer@23EDC2EF` | TStructure |
| `0x1D0` | `0x5575E990` | `AoWE.TStructure.CanDblClick@23EDC2EF` | TStructure |
| `0x1D4` | `0x5575F37C` | `AoWE.TStructure.ListUnits@23EDC2EF` | TStructure |
| `0x1D8` | `0x5575F434` | `AoWE.TStructure.ListArmies@23EDC2EF` | TStructure |
| `0x1DC` | `0x5575F18C` | `AoWE.TStructure.GetRebuildInfo@23EDC2EF` | TStructure |
| `0x1E0` | `0x5575F1A4` | `AoWE.TStructure.CanRebuild@23EDC2EF` | TStructure |
| `0x1E4` | `0x5575F26C` | `AoWE.TStructure.Rebuild@23EDC2EF` | TStructure |
| `0x1E8` | `0x557602F8` | `AoWE.TStructure.Raze@23EDC2EF` | TStructure |
| `0x1EC` | `0x5575FB80` | `AoWE.TStructure.CanRaze@23EDC2EF` | TStructure |

## TUnit  —  VMT `0x55710CAC`, instance `0x48`, 110 slots, ends `0x1B8`

<details><summary>derivation notes</summary>

```
DERIVATION / CONFIDENCE
- Preferred image base 0x55700000; CODE = 0x55701000..0x558E7A00. All VAs below are at the preferred base (the DPL rebases at runtime).
- VMT located by the RTTI recipe on Modding Resources/AoWEPACK_original_backup.dpl: ShortString `05 "TUnit"` at 0x55710E64; the only dword pointing at it is at 0x55710C8C, so VMT = 0x55710C8C + 0x20 = 0x55710CAC. Unique — no other candidate.
- Ghidra's bytes at 0x55710C8C match the file byte-for-byte (read_memory cross-check), so the file-derived table is the same data Ghidra holds.

VMT END (hard stop)
- The VMT ends at +0x1B8. The dword at 0x55710E64 (= VMT+0x1B8) is 0x6E555405, which is not a code pointer — it is literally the class-name ShortString `05 'T' 'U' 'n'...` that [VMT-0x20] points at. Confirmed by read_memory at 0x55710E60: `1c097855 0554556e 6974 8bc0 700e7155`. So the name string immediately follows the last slot, exactly the TAoWHexagon pattern. 110 slots, 0x1B8 bytes, every one resolved to a real symbol — zero unnamed slots.

VMT HEADER (this is NOT the Delphi 4+ layout — 16 dwords, 0x40 total)
  VMT-0x40 = 0x55710CAC  SelfPtr (equals the VMT — this pins the header size)
  VMT-0x3C .. -0x24      all zero (IntfTable/AutoTable/InitTable/TypeInfo/FieldTable/MethodTable/DynamicTable)
  VMT-0x20 = 0x55710E64  class-name ShortString
  VMT-0x1C = 0x00000048  instance size (72 bytes)
  VMT-0x18 = 0x55710700  parent classref -> 0x55710740 = TAbstractUnit VMT
  VMT-0x14 = 0x557010C8 | VMT-0x10 = 0x557010D0 | VMT-0x0C = 0x55701098 | VMT-0x08 = 0x557010A0
  VMT-0x04 = 0x5577EB6C  AoWE.TAbstractUnit.Destroy@23EDC2EF   (destructor, inherited)
  Only FIVE TObject virtuals sit below +0 (-0x14..-0x04), not eight — there is no SafeCallException / AfterConstruction / BeforeDestruction. Anyone hand-porting a Delphi 7 VMT constant table here will be off by 0xC.

ANCESTRY (derived by walking [VMT-0x18] parent classrefs)
  TEObject (external) -> TCustomAbilityList -> TAbilityOwner -> TAbstractUnit -> TUnit
  TCustomAbilityList  VMT 0x5570F3DC  instsize 0x10  vmtlen 0x05C (23 slots)
  TAbilityOwner       VMT 0x5570F588  instsize 0x14  vmtlen 0x09C (39 slots)
  TAbstractUnit       VMT 0x55710740  instsize 0x3C  vmtlen 0x1B8 (110 slots)
  TUnit               VMT 0x55710CAC  instsize 0x48  vmtlen 0x1B8 (110 slots)
- IMPORTANT: TAbstractUnit's VMT is ALSO 0x1B8 long. TUnit introduces NO new virtual methods at all — it only overrides 40 of the 110 inherited slots. Any new virtual added to TUnit must be added to TAbstractUnit's VMT too (both grow together), or the slot index will not match across the hierarchy.
- The chain terminates inside this module at TCustomAbilityList: its [VMT-0x18] parent classref is 0x558FC92C, an .idata IAT slot, i.e. its parent TEObject lives in another package.

THE 11 "TEObject" SLOTS ARE IMPORT THUNKS — READ THIS BEFORE HOOKING THEM
- Slots +0x000, +0x004, +0x00C, +0x010, +0x014, +0x01C, +0x034, +0x038, +0x03C, +0x040, +0x048 point into 0x557030xx, which is NOT local code: each is a 6-byte `JMP dword ptr [0x558FC6xx]` import thunk into **EngineP.dpl** (unit `Engine`, class `TEObject`). Patching one of these thunks would change behaviour for every class in AoWEPACK that inherits the method, not just TUnit — override the VMT slot instead.
- Ghidra returns "No function found" for 6 of these thunk addresses (0x55703074, 0x557030AC, 0x557030B4, 0x557030BC, 0x557030C4, 0x557030D4, 0x55703104) because they are undefined there. Their names in the table come from the PE import table, not from Ghidra. Method validated: for the 3 thunks Ghidra *does* name (0x5570309C Editor, 0x557030DC GetControlStyle, 0x557030EC SetArrayOwner) the import-table walk produced exactly the same symbols, and get_xrefs_to 0x558FC724 confirms the 0x55703074 -> IAT indirection.

WHY THE EXPORT TABLE ALONE IS NOT ENOUGH (trap for future VMT dumps)
- AoWEPACK.dpl's export directory has 10036 names but its lowest function RVA is 0x374C — nothing below 0x5570374C is exported. A VMT dump th
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x000` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x004` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x008` | `0x5577F524` | `AoWE.TAbstractUnit.SetOwner@23EDC2EF` | TAbstractUnit |
| `0x00C` | `0x557030D4` | `Engine.TEObject.GetEngine@23EDC2EF` | TEObject |
| `0x010` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x014` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x018` | `0x55782CEC` | `AoWE.TUnit.ReadWrite@23EDC2EF` | TUnit |
| `0x01C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x020` | `0x5577EB28` | `AoWE.TAbstractUnit.Create@23EDC2EF` | TAbstractUnit |
| `0x024` | `0x557826AC` | `AoWE.TUnit.ClassID@23EDC2EF` | TUnit |
| `0x028` | `0x5577EBC4` | `AoWE.TAbstractUnit.AddRef@23EDC2EF` | TAbstractUnit |
| `0x02C` | `0x5577EBCC` | `AoWE.TAbstractUnit.Release@23EDC2EF` | TAbstractUnit |
| `0x030` | `0x5574F11C` | `AoWE.TAbilityOwner.Clear@23EDC2EF` | TAbilityOwner |
| `0x034` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x038` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x03C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x040` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x044` | `0x55781238` | `AoWE.TAbstractUnit.MsgProc@23EDC2EF` | TAbstractUnit |
| `0x048` | `0x557030EC` | `Engine.TEObject.SetArrayOwner@23EDC2EF` | TEObject |
| `0x04C` | `0x5574E0E0` | `AoWE.TCustomAbilityList.GetAbSet@23EDC2EF` | TCustomAbilityList |
| `0x050` | `0x5574F308` | `AoWE.TAbilityOwner.SetAbSet@23EDC2EF` | TAbilityOwner |
| `0x054` | `0x5574E1B0` | `AoWE.TCustomAbilityList.GetAbCount@23EDC2EF` | TCustomAbilityList |
| `0x058` | `0x5574FF48` | `AoWE.TAbilityOwner.ListAbilitiesEx@23EDC2EF` | TAbilityOwner |
| `0x05C` | `0x5574F310` | `AoWE.TAbilityOwner.Execute@23EDC2EF` | TAbilityOwner |
| `0x060` | `0x5577F69C` | `AoWE.TAbstractUnit.GetOwnerName@23EDC2EF` | TAbstractUnit |
| `0x064` | `0x5574FC14` | `AoWE.TAbilityOwner.GetAbName@23EDC2EF` | TAbilityOwner |
| `0x068` | `0x5574FC3C` | `AoWE.TAbilityOwner.GetAbAttack@23EDC2EF` | TAbilityOwner |
| `0x06C` | `0x5574FC60` | `AoWE.TAbilityOwner.GetAbDefense@23EDC2EF` | TAbilityOwner |
| `0x070` | `0x5574FC84` | `AoWE.TAbilityOwner.GetAbResistance@23EDC2EF` | TAbilityOwner |
| `0x074` | `0x5574FCA8` | `AoWE.TAbilityOwner.GetAbDamage@23EDC2EF` | TAbilityOwner |
| `0x078` | `0x5574FCCC` | `AoWE.TAbilityOwner.GetAbMoveTypes@23EDC2EF` | TAbilityOwner |
| `0x07C` | `0x5574FCF4` | `AoWE.TAbilityOwner.GetAbProtectionTypes@23EDC2EF` | TAbilityOwner |
| `0x080` | `0x5574FD1C` | `AoWE.TAbilityOwner.GetAbImmunityTypes@23EDC2EF` | TAbilityOwner |
| `0x084` | `0x5574FD44` | `AoWE.TAbilityOwner.GetAbLevel@23EDC2EF` | TAbilityOwner |
| `0x088` | `0x5574FD68` | `AoWE.TAbilityOwner.GetAbEnabled@23EDC2EF` | TAbilityOwner |
| `0x08C` | `0x5577ECC0` | `AoWE.TAbstractUnit.GetAbilitySelectionTypes@23EDC2EF` | TAbstractUnit |
| `0x090` | `0x55782B34` | `AoWE.TUnit.Changed@23EDC2EF` | TUnit |
| `0x094` | `0x5574F5B4` | `AoWE.TAbilityOwner.ExpandAbility@23EDC2EF` | TAbilityOwner |
| `0x098` | `0x5577F6EC` | `AoWE.TAbstractUnit.RemoveAbility@23EDC2EF` | TAbstractUnit |
| `0x09C` | `0x5577FC64` | `AoWE.TAbstractUnit.GetUpkeep@23EDC2EF` | TAbstractUnit |
| `0x0A0` | `0x55782B8C` | `AoWE.TUnit.GetUnitLevel@23EDC2EF` | TUnit |
| `0x0A4` | `0x55782C90` | `AoWE.TUnit.GetRace@23EDC2EF` | TUnit |
| `0x0A8` | `0x557829D0` | `AoWE.TUnit.GetInherentAttack@23EDC2EF` | TUnit |
| `0x0AC` | `0x55782A24` | `AoWE.TUnit.GetInherentDefense@23EDC2EF` | TUnit |
| `0x0B0` | `0x55782A8C` | `AoWE.TUnit.GetInherentDamage@23EDC2EF` | TUnit |
| `0x0B4` | `0x55782AE0` | `AoWE.TUnit.GetInherentResistance@23EDC2EF` | TUnit |
| `0x0B8` | `0x5577F570` | `AoWE.TAbstractUnit.GetInherentAbility@23EDC2EF` | TAbstractUnit |
| `0x0BC` | `0x5577F5A8` | `AoWE.TAbstractUnit.GetInherentAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x0C0` | `0x557829EC` | `AoWE.TUnit.GetAttack@23EDC2EF` | TUnit |
| `0x0C4` | `0x55782A40` | `AoWE.TUnit.GetDefense@23EDC2EF` | TUnit |
| `0x0C8` | `0x55782AA8` | `AoWE.TUnit.GetDamage@23EDC2EF` | TUnit |
| `0x0CC` | `0x55782AE8` | `AoWE.TUnit.GetResistance@23EDC2EF` | TUnit |
| `0x0D0` | `0x55782B68` | `AoWE.TUnit.GetHits@23EDC2EF` | TUnit |
| `0x0D4` | `0x55782B84` | `AoWE.TUnit.GetMoves@23EDC2EF` | TUnit |
| `0x0D8` | `0x5578276C` | `AoWE.TUnit.GetMovePoints@23EDC2EF` | TUnit |
| `0x0DC` | `0x55782794` | `AoWE.TUnit.SetMovePoints@23EDC2EF` | TUnit |
| `0x0E0` | `0x557827C0` | `AoWE.TUnit.GetHitPoints@23EDC2EF` | TUnit |
| `0x0E4` | `0x557827C4` | `AoWE.TUnit.SetHitPoints@23EDC2EF` | TUnit |
| `0x0E8` | `0x5577FFD0` | `AoWE.TAbstractUnit.GetMoveTypes@23EDC2EF` | TAbstractUnit |
| `0x0EC` | `0x5577FD54` | `AoWE.TAbstractUnit.GetImmunityTypes@23EDC2EF` | TAbstractUnit |
| `0x0F0` | `0x5577FD74` | `AoWE.TAbstractUnit.GetProtectionTypes@23EDC2EF` | TAbstractUnit |
| `0x0F4` | `0x5578283C` | `AoWE.TUnit.GetFace@23EDC2EF` | TUnit |
| `0x0F8` | `0x557826B4` | `AoWE.TUnit.GetName@23EDC2EF` | TUnit |
| `0x0FC` | `0x55782770` | `AoWE.TUnit.GetAlignment@23EDC2EF` | TUnit |
| `0x100` | `0x55782B94` | `AoWE.TUnit.GetPreviewImage@23EDC2EF` | TUnit |
| `0x104` | `0x55782BA0` | `AoWE.TUnit.GetTransportCapacity@23EDC2EF` | TUnit |
| `0x108` | `0x55782BD0` | `AoWE.TUnit.GetTransporter@23EDC2EF` | TUnit |
| `0x10C` | `0x55782810` | `AoWE.TUnit.GetGender@23EDC2EF` | TUnit |
| `0x110` | `0x55782800` | `AoWE.TUnit.GetBloodType@23EDC2EF` | TUnit |
| `0x114` | `0x55782808` | `AoWE.TUnit.GetUnitType@23EDC2EF` | TUnit |
| `0x118` | `0x55782C54` | `AoWE.TUnit.GetUnitGFXResourceIndex@23EDC2EF` | TUnit |
| `0x11C` | `0x55781208` | `AoWE.TAbstractUnit.CanAddToList@23EDC2EF` | TAbstractUnit |
| `0x120` | `0x5577ECCC` | `AoWE.TAbstractUnit.GetWallCombatFeatures@23EDC2EF` | TAbstractUnit |
| `0x124` | `0x5577EBB8` | `AoWE.TAbstractUnit.GetCampaignTransferPoints@23EDC2EF` | TAbstractUnit |
| `0x128` | `0x5577FDB8` | `AoWE.TAbstractUnit.GetCastingPointsMax@23EDC2EF` | TAbstractUnit |
| `0x12C` | `0x5577FDBC` | `AoWE.TAbstractUnit.GetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x130` | `0x5577FDC0` | `AoWE.TAbstractUnit.SetCastingPoints@23EDC2EF` | TAbstractUnit |
| `0x134` | `0x5577FDB4` | `AoWE.TAbstractUnit.GetPowerGeneration@23EDC2EF` | TAbstractUnit |
| `0x138` | `0x55782C98` | `AoWE.TUnit.NewDay@23EDC2EF` | TUnit |
| `0x13C` | `0x55780D4C` | `AoWE.TAbstractUnit.NewTurn@23EDC2EF` | TAbstractUnit |
| `0x140` | `0x55780E28` | `AoWE.TAbstractUnit.NewTurnDone@23EDC2EF` | TAbstractUnit |
| `0x144` | `0x5577F658` | `AoWE.TAbstractUnit.GetAbilityLevel@23EDC2EF` | TAbstractUnit |
| `0x148` | `0x5577F5E0` | `AoWE.TAbstractUnit.GetAbilityEnabled@23EDC2EF` | TAbstractUnit |
| `0x14C` | `0x5577F618` | `AoWE.TAbstractUnit.GetAbilitySet@23EDC2EF` | TAbstractUnit |
| `0x150` | `0x5577F630` | `AoWE.TAbstractUnit.GetAbilityName@23EDC2EF` | TAbstractUnit |
| `0x154` | `0x5577F67C` | `AoWE.TAbstractUnit.GetAbilityOwner@23EDC2EF` | TAbstractUnit |
| `0x158` | `0x5577F56C` | `AoWE.TAbstractUnit.GetAbilityCount@23EDC2EF` | TAbstractUnit |
| `0x15C` | `0x557828AC` | `AoWE.TUnit.GetExperience@23EDC2EF` | TUnit |
| `0x160` | `0x557828B4` | `AoWE.TUnit.SetExperience@23EDC2EF` | TUnit |
| `0x164` | `0x55782920` | `AoWE.TUnit.GetNextLevelExperience@23EDC2EF` | TUnit |
| `0x168` | `0x55782918` | `AoWE.TUnit.GetDescription@23EDC2EF` | TUnit |
| `0x16C` | `0x5577F4A8` | `AoWE.TAbstractUnit.SetPlayer@23EDC2EF` | TAbstractUnit |
| `0x170` | `0x5577F4F4` | `AoWE.TAbstractUnit.GetIndependentRelation@23EDC2EF` | TAbstractUnit |
| `0x174` | `0x55782764` | `AoWE.TUnit.GetObtainValue@23EDC2EF` | TUnit |
| `0x178` | `0x557827F8` | `AoWE.TUnit.GetUnitSize@23EDC2EF` | TUnit |
| `0x17C` | `0x5577EED8` | `AoWE.TAbstractUnit.GetUnitMoraleValue@23EDC2EF` | TAbstractUnit |
| `0x180` | `0x5577FB9C` | `AoWE.TAbstractUnit.CanActivate@23EDC2EF` | TAbstractUnit |
| `0x184` | `0x55782C5C` | `AoWE.TUnit.Activate@23EDC2EF` | TUnit |
| `0x188` | `0x5577FC20` | `AoWE.TAbstractUnit.Deactivate@23EDC2EF` | TAbstractUnit |
| `0x18C` | `0x55780328` | `AoWE.TAbstractUnit.MovedTo@23EDC2EF` | TAbstractUnit |
| `0x190` | `0x557825B0` | `AoWE.TAbstractUnit.CanDisband@23EDC2EF` | TAbstractUnit |
| `0x194` | `0x557821AC` | `AoWE.TAbstractUnit.CanJoin@23EDC2EF` | TAbstractUnit |
| `0x198` | `0x55782324` | `AoWE.TAbstractUnit.JoinAmount@23EDC2EF` | TAbstractUnit |
| `0x19C` | `0x55782364` | `AoWE.TAbstractUnit.OfferToJoin@23EDC2EF` | TAbstractUnit |
| `0x1A0` | `0x55782440` | `AoWE.TAbstractUnit.GetJoinMessage@23EDC2EF` | TAbstractUnit |
| `0x1A4` | `0x557826C8` | `AoWE.TUnit.ShowEx@23EDC2EF` | TUnit |
| `0x1A8` | `0x55782838` | `AoWE.TUnit.UnitKilled@23EDC2EF` | TUnit |
| `0x1AC` | `0x55782818` | `AoWE.TUnit.Killed@23EDC2EF` | TUnit |
| `0x1B0` | `0x557808DC` | `AoWE.TAbstractUnit.Resurrect@23EDC2EF` | TAbstractUnit |
| `0x1B4` | `0x5578091C` | `AoWE.TAbstractUnit.Animate@23EDC2EF` | TAbstractUnit |

## TUnitResource  —  VMT `0x55710A64`, instance `0x54`, 29 slots, ends `0x74`

<details><summary>derivation notes</summary>

```
ALL 29 slots resolved, zero unknowns. Every VA is at the DPL's preferred base 0x55700000 (the .dpl rebases at runtime).

== HOW THIS WAS DERIVED ==
VMT located by the RTTI recipe against Modding Resources/AoWEPACK_original_backup.dpl (the pristine vanilla bytes Ghidra holds). Exactly ONE candidate matched "TUnitResource"; self-check passed: [VMT-0x40] (SelfPtr) = 0x55710A64 = the VMT itself.

*** IMPORTANT METHOD NOTE — Ghidra ALONE CANNOT DO THIS. *** 12 of the 29 slots point at 6-byte import thunks (FF 25 <IAT>) into EngineP.dpl, and Ghidra has NO function defined at several of them (get_function_by_address on 0x55703074, 0x55703384, 0x557030AC, 0x557030B4 all return "No function found"). Their true symbols come from the PE IMPORT table, not from Ghidra and not from the DPL export table. Resolution used here: local slots -> AoWEPACK.dpl export table (10036 named exports); thunk slots -> read the IAT VA out of the FF 25 operand, look it up in the import descriptors. Spot-checked 6 local symbols against Ghidra get_function_by_address; all matched exactly.

== END OF VMT ==
[VMT+0x74] = 0x0000000E, not a CODE pointer -> VMT body is 0x00..0x70 inclusive, 29 slots, ends at +0x74. Corroborated three ways: (a) [VMT-0x34] InitTable = 0x55710AD8 = exactly VMT+0x74, i.e. the next structure begins there; (b) the sibling TAbstractUnitResource VMT also ends at +0x74, where its bytes read 0x62415415 = 0x15 'TAb...' — the length byte of its own 21-char class-name ShortString; (c) TUnitResource introduces no new virtuals over its parent (see below), so 29 is the inherited count.

== ANCESTRY (fully derived, not assumed) ==
System.TObject (VCL30.dpl)
  -> Engine.TEObject      (EngineP.dpl, VMT 0x5550C188, instsize 0x08, 19 slots, ends +0x4C)
    -> Engine.TEResource  (EngineP.dpl, VMT 0x5550D6C0, instsize 0x18, 25 slots, ends +0x64)
      -> AoWE.TAbstractUnitResource (AoWEPACK.dpl, VMT 0x5571096C, instsize 0x1C, 29 slots, ends +0x74)
        -> AoWE.TUnitResource       (AoWEPACK.dpl, VMT 0x55710A64, instsize 0x54, 29 slots, ends +0x74)
TAbstractUnitResource's [VMT-0x18] parent ref is an IAT entry (0x558FC8EC -> EngineP.dpl!"Engine..TEResource@9052749E"), i.e. the parent class lives in another package. The two EngineP VMTs were dumped from <game dir>\Enginep.dpl by the same method to confirm the chain and the slot boundaries.

== WHICH CLASS INTRODUCES WHICH SLOT (from the ancestors' own VMT lengths) ==
  0x00..0x48 (19 slots) declared by Engine.TEObject
  0x4C..0x60 (6 slots)  declared by Engine.TEResource
  0x64..0x70 (4 slots)  declared by AoWE.TAbstractUnitResource
  TUnitResource declares NO new virtual methods — it only overrides.
Note slot 0x48 SetArrayOwner and slot 0x08 SetOwner are TEObject-declared slots that TEResource overrides; slot 0x4C GetCellImage / 0x54 ResourceEditName / 0x58 ResourceUserClassID / 0x5C CreateResourceUser are TEResource-declared slots that TAbstractUnitResource or TUnitResource override.

== THE 7 SLOTS TUnitResource OVERRIDES vs TAbstractUnitResource (these are the interesting hook points) ==
  +0x18 ReadWrite            0x55784DE4  (was 0x55784A48 TAbstractUnitResource.ReadWrite)
  +0x20 Create               0x55784C44  (was 0x55703064 thunk -> Engine.TEObject.Create)
  +0x24 ClassID              0x55784DA0  (was 0x55703374 thunk -> Engine.TEResource.ClassID)
  +0x58 ResourceUserClassID  0x55784D68  (was 0x557033AC thunk -> Engine.TEResource.ResourceUserClassID)
  +0x5C CreateResourceUser   0x55784D70  (was 0x557033B4 thunk -> Engine.TEResource.CreateResourceUser)
  +0x64 DropUnit             0x55784F70  (was 0x55784A6C TAbstractUnitResource.DropUnit)
  +0x70 GetObtainValue       0x55784D58  (was 0x557849F8 TAbstractUnitResource.GetObtainValue)

== NEGATIVE (TObject) VMT SLOTS — part of virtual dispatch, NOT in the 0x00.. body ==
This build uses the Delphi 3 header layout (SafeCallException/DefaultHandler/NewInstance/FreeInstance/Destroy only; the Delphi-4 AfterConstruction/BeforeDestruction/Dispatch entr
```

</details>

| slot | target | symbol | implemented by |
|---|---|---|---|
| `0x00` | `0x55703074` | `Engine.TEObject.ClassVersion@23EDC2EF` | TEObject |
| `0x04` | `0x557030DC` | `Engine.TEObject.GetControlStyle@23EDC2EF` | TEObject |
| `0x08` | `0x55703384` | `Engine.TEResource.SetOwner@23EDC2EF` | TEResource |
| `0x0C` | `0x557849F0` | `AoWE.TAbstractUnitResource.GetEngine@23EDC2EF` | TAbstractUnitResource |
| `0x10` | `0x557030AC` | `Engine.TEObject.GetLastMsg@23EDC2EF` | TEObject |
| `0x14` | `0x557030B4` | `Engine.TEObject.SetLastMsg@23EDC2EF` | TEObject |
| `0x18` | `0x55784DE4` | `AoWE.TUnitResource.ReadWrite@23EDC2EF` | TUnitResource |
| `0x1C` | `0x55703104` | `Engine.TEObject.MainReadWrite@23EDC2EF` | TEObject |
| `0x20` | `0x55784C44` | `AoWE.TUnitResource.Create@23EDC2EF` | TUnitResource |
| `0x24` | `0x55784DA0` | `AoWE.TUnitResource.ClassID@23EDC2EF` | TUnitResource |
| `0x28` | `0x5570307C` | `Engine.TEObject.AddRef@23EDC2EF` | TEObject |
| `0x2C` | `0x55703084` | `Engine.TEObject.Release@23EDC2EF` | TEObject |
| `0x30` | `0x5570308C` | `Engine.TEObject.Clear@23EDC2EF` | TEObject |
| `0x34` | `0x557030BC` | `Engine.TEObject.Compare@23EDC2EF` | TEObject |
| `0x38` | `0x5570309C` | `Engine.TEObject.Editor@23EDC2EF` | TEObject |
| `0x3C` | `0x557030C4` | `Engine.TEObject.Assign@23EDC2EF` | TEObject |
| `0x40` | `0x557030A4` | `Engine.TEObject.TimerEvent@23EDC2EF` | TEObject |
| `0x44` | `0x55784B0C` | `AoWE.TAbstractUnitResource.MsgProc@23EDC2EF` | TAbstractUnitResource |
| `0x48` | `0x5570338C` | `Engine.TEResource.SetArrayOwner@23EDC2EF` | TEResource |
| `0x4C` | `0x55784A3C` | `AoWE.TAbstractUnitResource.GetCellImage@23EDC2EF` | TAbstractUnitResource |
| `0x50` | `0x5570339C` | `Engine.TEResource.SetCellImage@23EDC2EF` | TEResource |
| `0x54` | `0x55784AE8` | `AoWE.TAbstractUnitResource.ResourceEditName@23EDC2EF` | TAbstractUnitResource |
| `0x58` | `0x55784D68` | `AoWE.TUnitResource.ResourceUserClassID@23EDC2EF` | TUnitResource |
| `0x5C` | `0x55784D70` | `AoWE.TUnitResource.CreateResourceUser@23EDC2EF` | TUnitResource |
| `0x60` | `0x55703394` | `Engine.TEResource.Draw@23EDC2EF` | TEResource |
| `0x64` | `0x55784F70` | `AoWE.TUnitResource.DropUnit@23EDC2EF` | TUnitResource |
| `0x68` | `0x55784A1C` | `AoWE.TAbstractUnitResource.GetPreviewImage@23EDC2EF` | TAbstractUnitResource |
| `0x6C` | `0x557849FC` | `AoWE.TAbstractUnitResource.GetFace@23EDC2EF` | TAbstractUnitResource |
| `0x70` | `0x55784D58` | `AoWE.TUnitResource.GetObtainValue@23EDC2EF` | TUnitResource |

