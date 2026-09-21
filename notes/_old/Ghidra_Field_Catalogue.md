# AoWEPACK.dpl instance-field catalogue -- GENERATED from `re_tools/ghidra_fields.py`

Do not hand-edit; edit the script and re-run `--md`. VMT slots are NOT here -- they are fully derived in `Ghidra_VMT_Layouts.md`.

**An offset means nothing without its class.** Evidence: **M** measured by decompile 2026-08-03 · **D** doc-stated · **S** speculative.

## Cross-class aliases -- read before using any offset

| offset | means | |
|---|---|---|
| `+0x4C` | TCombatUnit strategic-unit ptr / TCombatWall packed byte / TCombatPredictorUnit signed HP / TCity WallType / TUnitResource gold / THero level cache | caused the 'Blt Error' bug -- twice |
| `+0x30` | TStructure: PAST THE END (instsize 0x30) / TExplorationSite defender strength / TArena mod flags / TCity owner | three siblings, one byte |
| `+0x10` | TAoWHexagon: 3 transition-image bytes / TAoWWaterHexagon: a pointer | sibling classes, different parents |
| `+0x40 stats` | TUnit resource stats at +0x29..+0x2E / THero resource stats at +0x24..+0x29 | 5 bytes apart; both reached via +0x40 |
| `+0x18 on a CA` | TStrikeCA effect flags / TCombatSpellCA spell id / ranged CA ability id |  |

## TAbility (AoWE unit, AoWEPACK.dpl; VMT @ 0x5570F254, class name ptr [VMT-0x20]=0x5570F372 "TAbility", instance size [VMT-0x1C] = 0x24, parent cell [VMT-0x18]=0x558FC92C -> imported Engine.TEObject)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `unknown_this_offset_is_not_introdu` | S | UNKNOWN. This offset is NOT introduced by TAbility and is never read or written by any TAbility method (all 54 TAbility.* functions were checked; ever |
| `+0x08` | - | `fname_the_ability_s_display_name_a` | M | FName - the ability's display name, as a reference-counted Delphi AnsiString. Returned verbatim by GetName and ExpandName; set in each concrete abilit |
| `+0x0C` | - | `fabilityid_the_ability_s_global_ab` | M | FAbilityID - the ability's global ability id (0..N). It is the index under which the singleton is stored in TAbilityControl's TList, the key every TAb |
| `+0x10` | - | `fdescription_a_tstringlist_holding` | M | FDescription - a TStringList holding the ability's description text lines. Created empty in the constructor, freed in the destructor, filled from the  |
| `+0x14` | - | `fexpandcost_the_point_cost_of_acqu` | M | FExpandCost - the point cost of acquiring this ability, returned unchanged by ExpandCost, and also returned by GetSkillPoints as the ability's skill-p |
| `+0x18` | - | `fsfx_the_ability_s_sound_effect_li` | M | FSFX - the ability's sound-effect library: the set of sounds played when the ability fires. Constructed empty, freed in the destructor, populated from |
| `+0x1C` | - | `fanimation_the_ability_s_image_seq` | M | FAnimation - the ability's image-sequence list (its on-screen effect animation, and the frames the ability draws over its target). Created against the |
| `+0x20` | - | `fselectiontypes_the_set_of_owner_c` | M | FSelectionTypes - the set of owner categories this ability may legitimately belong to / be selected for. Members (from the enum's own RTTI, ordinal =  |

## TAbstractUnit  (instance size `0x3C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `owner_pointer_to_the_engine_contai` | M | [introduced by Engine.TEObject(imported)] Owner - pointer to the Engine container/list object that currently holds this unit (a TUnitList / TArmy while on the map, nil when unowned). Set only  |
| `+0x08` | 4 | `pointer_to_a_heap_allocated_bit_ar` | M | [introduced by TCustomAbilityList] Pointer to a heap-allocated bit array holding the unit's ability set - one bit per ability id, bit i at byte i>>3, mask 1<<(i&7). Its companion length |
| `+0x0C` | 4 | `ability_bitset_width_bits` | M | DWORD, not a byte: the ability count in BITS. GetAbilitySet: `if id < unit+0xC` |
| `+0x10` | 4 | `ability_data_head` | D | linked list; next at data+0x08 (TAbilityOwner) |
| `+0x14` | 4 | `reference_count_initialised_to_1_i` | M | Reference count. Initialised to 1 in the constructor; AddRef increments, Release decrements and calls the destructor (VMT-0x04) when it reaches zero.  |
| `+0x18` | 4 | `unit_id` | D | network / FindUnit key; Create inits to -1 |
| `+0x1C` | 4 | `id_of_the_ai_group_taigroup_this_u` | M | ID of the AI group (TAIGroup) this unit belongs to; 0 = not in a group. This is the *persistent* handle - the live TAIGroup pointer is the separate fi |
| `+0x20` | 4 | `ai_group_link` | D |  |
| `+0x24` | 1 | `owner_player_index` | D |  |
| `+0x25` | 1 | `flags` | D | bit1 gates the morale/notify block in Changed() |
| `+0x26` | 1 | `morale_cache` | M | cached morale VALUE, SIGNED byte clamped to [-25, +125]. loyal >= 41 |
| `+0x38` | 1 | `legacy_ai_group_behaviour_code_the` | M | Legacy AI-group *behaviour* code (the small enum returned by TGroupControl.Behavior: 0 = none/base, 2 = Guard, 0x0A = Suicidal, 0x0B = Passive, 0x0D = |

## TAoWHSMap  (instance size `0x41C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0xA4` | 1 | `current_turn_player` | D |  |
| `+0xA5` | 1 | `seated_local_player` | M | passed to GameOver in TPlayerControl.NewDay |
| `+0xE4` | 4 | `ansistring_the_map_s_game_s_name_n` | M | AnsiString: the map's/game's NAME (not its filename). Initialised to 'noname' in the constructor, streamed under property id 0x19, and used as the bas |
| `+0xF4` | 4 | `owned_aowe_titemcontrol_instance_t` | M | Owned AoWE.TItemControl instance - the map-wide registry of all TItem objects (RegisterItem/UnRegisterItem, FindItem, GenerateItem(s), CreateUniqueID, |
| `+0xF8` | 4 | `owned_aowe_therocontrol_instance_t` | M | Owned AoWE.THeroControl instance - the map-wide hero registry (RegisterHero/UnRegisterHero, GetHero, FindID, ListDeadHeroes, ValidateLibraryHeroes, Ge |
| `+0xFC` | 4 | `owned_aowe_tunitcontrol_instance_t` | M | Owned AoWE.TUnitControl instance - the map-wide unit registry and units-changed notification hub. Streamed under property id 0x26. |
| `+0x100` | 4 | `owned_aowe_tstructurecontrol_insta` | M | Owned AoWE.TStructureControl instance - the map-wide structure registry (Register/Unregister, GetStructure, FindID, IndexOfID, CreateUniqueID). Stream |
| `+0x124` | 4 | `owned_aowe_ttutorialcontrol_instan` | M | Owned AoWE.TTutorialControl instance - shows tutorial hint messages and remembers which have already been shown. Streamed under property id 0x38, so t |
| `+0x128` | 4 | `owned_aowe_taiexecuter_instance_th` | M | Owned AoWE.TAIExecuter instance - the per-frame driver that runs AI players' turns. Runtime only, not streamed. |
| `+0x12C` | 4 | `owned_aowe_taiplayeractionmanager_` | M | Owned AoWE.TAIPlayerActionManager instance - the registry of AI player-action (AIPA) CLASSES, not of instances. The constructor registers 12: TEndTurn |
| `+0x130` | 4 | `owned_aowe_taigroupmanager_instanc` | M | Owned AoWE.TAIGroupManager instance - creates and owns the AI's army groups (CreateGroup, CreateUniqueID) and holds the registry of AI-group classes ( |
| `+0x134` | 4 | `owned_aowe_taowhsmapkeyboard_insta` | M | Owned AoWE.TAoWHSMapKeyboard instance - the strategic-map keyboard-input handler. Not streamed. Caveat: the class identity is certain (taken from the  |
| `+0x13A` | 1 | `session_mode` | M | connection/session enum: 0 = local (single/hotseat), 1 = network MP. Gates the day-1 Randomize -- 'scenario flag' was the wrong label |
| `+0x140` | 4 | `player_list` | M | TPlayerList |
| `+0x144` | 4 | `race_list` | M | TRaceList -- was recorded only as '(second list)' |
| `+0x158` | 4 | `turn_limit` | M | compared to the day counter; triggers GameOver |
| `+0x16C` | 1 | `turn_order_mode` | M | == 2 -> GenerateNewTurnOrder |
| `+0x170` | 4 | `owned_engine_tbytelist_holding_the` | M | Owned Engine.TByteList holding the TURN ORDER - the sequence of player indices for the current day. Element 0 is always player 0 (the independents); t |
| `+0x174` | 4 | `day_counter` | M | incremented by TPlayerControl.NewDay. NOT 'init state' |
| `+0x188` | 4 | `global_magic_control` | D |  |
| `+0x18C` | 4 | `owned_aowe_taowmapcampaignsettings` | M | Owned AoWE.TAoWMapCampaignSettings instance - the per-scenario campaign carry-over limits. A pure data record (only Create + ReadWrite exist): +0x08 b |
| `+0x19C` | 4 | `notify_event_list` | M |  |
| `+0x1AC` | 4 | `owned_engine_teventlist_the_seated` | M | Owned Engine.TEventList - the 'seated player changed' notify-event list. Registered handlers are fired (with the global AoWHSMap as argument) whenever |
| `+0x1CC` | 4 | `owned_eventlog_teventloglist_used_` | M | Owned EventLog.TEventLogList used as a DEFERRAL BUFFER for per-player event-log entries. While the lock counter at +0x1C8 is non-zero each copy of an  |
| `+0x1D4` | 4 | `owned_eventlog_texecuteeventlogcal` | M | Owned EventLog.TExecuteEventLogCallBackList - the FIFO queue of pending event-log PLAYBACK requests (each entry a 16-byte record: log object + callbac |
| `+0x22C` | 4 | `seed_constant` | M | written day 1 from RandSeed |
| `+0x230` | 4 | `seed_state` | M | MP-lockstep RNG state |
| `+0x239` | 1 | `the_turn_mode_player_control_style` | M | The TURN MODE (player-control style) of this game: 1 = sequential/turn-based (TTurnPlayerControl, or TPBEMPlayerControl when the session is play-by-em |
| `+0x23C` | 4 | `token_manager` | D |  |
| `+0x240` | 4 | `owned_networke_tplayercommunicator` | M | Owned NetworkE.TPlayerCommunicator instance - the network/session transport for player messages. Its +0x1C is the TPlayerCommunicationControl (nil in  |
| `+0x244` | 4 | `owned_aowe_tplayercontrol_instance` | M | Owned AoWE.TPlayerControl instance - the polymorphic turn-flow controller. Its concrete class is chosen from the turn mode at +0x239: TTurnPlayerContr |

## TAoWHexagon  (instance size `0x14`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `map_field` | D |  |
| `+0x08` | 4 | `resource` | D |  |
| `+0x0C` | - | `fstatus_tmapobjectstatus_a_1_byte_` | M | FStatus : TMapObjectStatus - a 1-byte Delphi SET of runtime state flags (RTTI-confirmed type name and member names). Bits: 0x01 moVisible; 0x02 moReso |
| `+0x10` | 3 | `transition_image_per_edge` | M | ⚠ 3 BYTES here. On TAoWWaterHexagon (a SIBLING class) +0x10 is a pointer |
| `+0x13` | 1 | `transition_flags` | D | bits 0-2 = edge n has an image |

## TAoWWaterHexagon  (instance size `0x20`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `pointer_to_the_tmapfield_this_hexa` | M | [introduced by Engine.TEObject(imported)] Pointer to the TMapField this hexagon sprite occupies (the owning map field). That record carries: +0x04 = TMapLevel*, +0x10 = X (byte), +0x11 = Y (by |
| `+0x08` | 4 | `pointer_to_the_hexagon_s_resource_` | M | Pointer to the hexagon's resource / art-definition object (the TAoWWaterHexagonResource, of the TIsometricHexagonResource / TMapObjectResource family) |
| `+0x10` | 4 | `dynamic_companion` | M | lazily created in UpdateTransitions |
| `+0x14` | 1 | `land_neighbour_mask` | M | bit d set when the neighbour in dir d+1 IS land -- UpdateTransitions sets it when the neighbour owns no TLowerIsometricHexagon (the WATER family: it is TAoWWaterHexagon's own parent classref 0x558FCD70) and no TBorderHexagon |
| `+0x15` | 1 | `differing_terrain_mask` | M | low 6 bits; top 2 preserved (&0xC0) = tile phase |
| `+0x18` | 1 | `frame_counter` | M | signed; negative = idle delay |
| `+0x19` | 1 | `animation_id` | M | rolled 20-39 / 50-58 |
| `+0x1A` | 6 | `shore_tint_per_dir` | M | 0x28 Snow neighbour, 0x50 Wasteland, else 0 |

## TArena  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `pointer_to_the_taowmapfield_this_s` | M | [introduced by Engine.TEObject(imported)] Pointer to the TAoWMapField this structure occupies - the map-object's back-link to its own tile on the strategic map. Not a TArena concept at all: it |
| `+0x30` | 1 | `mod_flags` | D | ⚠ INSTALLED ONLY -- bit0 EMPTY, bit1 SEEDED. Legal only because build_arena.py grows instsize 0x30 -> 0x38 |
| `+0x34` | 4 | `mod_roster_seed` | D | ⚠ INSTALLED ONLY |

## TCombatObject  (instance size `0x4C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `combat` | D | owning TCombat |
| `+0x0C` | 4 | `find_id` | D |  |
| `+0x10` | 4 | `engine_tquaditemlist_the_outgoing_` | M | Engine.TQuadItemList* - the OUTGOING target list: one 16-byte quad per enemy object this object can attack. Quad = (A=target TCombatObject*, B=CV, C=W |
| `+0x14` | 4 | `engine_tquaditemlist_the_incoming_` | M | Engine.TQuadItemList* - the INCOMING/reverse list: one quad per enemy object that has registered THIS object as its target. Same quad shape, A=attacke |
| `+0x18` | 4 | `integer_running_sum_of_quad_field_` | M | Integer - running SUM of quad field B (CV, the normalised combat value this object can deal) over ALL entries of the outgoing list 0x10. I.e. this obj |
| `+0x1C` | 4 | `integer_running_sum_of_quad_field_` | D | Integer - running SUM of quad field C (WallCV, the value returned by the virtual GetTargetWallCV, only non-zero when the combat has walls) over all en |
| `+0x20` | 4 | `integer_running_sum_of_quad_field_` | M | Integer - running SUM of quad field B (CV) over all entries of the INCOMING list 0x14, accumulated by the attacker when it registers this object. I.e. |
| `+0x24` | 4 | `integer_running_sum_of_quad_field_` | D | Integer - running SUM of quad field C (WallCV) over the INCOMING list 0x14; the wall counterpart of 0x20. !! It is incremented in AddTarget but NEVER  |
| `+0x28` | 4 | `integer_count_of_entries_in_the_ou` | D | Integer - COUNT of entries in the outgoing list 0x10 whose CV (quad B) is > 0, i.e. how many enemy objects this object can actually damage. Incremente |
| `+0x2C` | 4 | `integer_count_of_entries_in_the_ou` | D | Integer - COUNT of entries in the outgoing list 0x10 whose WallCV (quad C) is > 0. Wall counterpart of 0x28. Maintained correctly in both directions b |
| `+0x30` | 4 | `integer_count_of_entries_in_the_in` | M | Integer - COUNT of entries in the INCOMING list 0x14 whose CV (quad B) is > 0, i.e. how many enemies can actually damage this object. Zero means nothi |
| `+0x34` | 4 | `integer_count_of_entries_in_the_in` | D | Integer - COUNT of entries in the INCOMING list 0x14 whose WallCV (quad C) is > 0. Wall counterpart of 0x30. Maintained correctly in both directions b |
| `+0x38` | 4 | `integer_memoised_result_of_the_vir` | M | Integer - memoised result of the virtual GetTargetPriority: the AI score for 'how attractive is it for this object to act'. Computed as (N+2) * SUM ov |
| `+0x3C` | 1 | `boolean_delphi_byte_boolean_dirty_` | M | Boolean (Delphi Byte/Boolean) - DIRTY flag for the 0x38 priority cache. Set to 1 by TargetsChanged (called whenever any target edge is added or remove |
| `+0x40` | 4 | `integer_memoised_result_of_the_vir` | M | Integer - memoised result of the virtual GetTargetStrength: the AVERAGE of quad field D (DV, the raw maximum damage value against that target) over th |
| `+0x44` | 1 | `boolean_delphi_byte_boolean_dirty_` | M | Boolean (Delphi Byte/Boolean) - DIRTY flag for the 0x40 strength cache. Set to 1 by TargetsChanged; cleared to 0 at the end of GetTargetStrength. No p |
| `+0x45` | 1 | `player_side` | D | GetPlayer |
| `+0x46` | 1 | `grid_position` | M | packed party<<4 | slot_in_party, each nibble 0..7; 0x80 = wall sentinel. NOT a printable id -- that name came from TCombatUnit.IDStr merely IntToStr-ing it |
| `+0x47` | 1 | `state_flags` | D | alive iff (x & 0x09) == 0 |
| `+0x48` | 1 | `conquer_flags` | D | bit0 = conquer object |

## TCombatUnit  (instance size `0x5C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x4C` | 4 | `strategic_unit` | M | PTR:TAbstractUnit -- ⚠ a TAbstractUnit*, NOT a TUnit*: THero and TLeader live here too. TCombatUnit ONLY; GetAlignment forwards through it. TCombatWall+0x4C is a packed byte, TCombatPredictorUnit+0x4C is signed HP -- the alias behind the 'Blt Error' bug |
| `+0x50` | 4 | `pointer_to_the_tcombatparty_this_c` | M | Pointer to the TCombatParty this combat unit currently belongs to (the on-battlefield stack, index = field_0x46 >> 4). Non-owning cache, no AddRef/Rel |
| `+0x54` | 1 | `boolean_this_unit_is_aboard_the_ar` | M | Boolean: "this unit is aboard the army's transport" (embarked cargo, e.g. a land unit inside a boat in a water battle). Set to True exactly when the u |
| `+0x55` | 1 | `cached_wall_combat_features_bitmas` | M | Cached wall-combat-features bitmask -- what this unit can do to/against a besieged city wall this battle. Recomputed, not serialized. Value = TAbstrac |
| `+0x58` | 4 | `int32_index_of_the_tunitgfxresourc` | M | Int32 index of the TUnitGFXResource this combat unit currently holds a reference on; -1 (0xFFFFFFFF) means "none held". Pure refcount bookkeeping, not |

## TExplorationSite  (instance size `0x38`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x30` | 1 | `defender_strength` | D | 0 none, 1-3 fixed, 4 = editor 'Random' |
| `+0x34` | 4 | `defenders_army` | D |  |

## THero  (instance size `0x9C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x3C` | 4 | `face_resource_index_index_into_tfa` | M | Face resource index - index into TFaceResourceList selecting the hero's portrait. Seeded from heroResource[+0x30] when the map is in editor mode; over |
| `+0x40` | 4 | `resource` | M | ⚠ stat block is 5 bytes EARLIER than TUnit's |
| `+0x44` | 4 | `hero_resource_index_the_index_into` | M | Hero resource index - the index into THeroResourceList identifying which hero template/definition this hero instance is. 0xFFFFFFFF = unassigned. Reso |
| `+0x48` | 4 | `experience_points_the_hero_s_raw_x` | M | Experience points (the hero's raw XP total; level is derived from it, not stored - +0x4C only caches the last computed level). |
| `+0x4C` | 1 | `level_cache` | M | 1 BYTE, not 4. Pure cache of ExperienceToLevel(+0x48); the experience dword at +0x48 is authoritative |
| `+0x50` | 4 | `a_subtractive_offset_applied_to_th` | M | A subtractive offset applied to the hero's skill-point allowance - skill points that have been written off and can no longer be spent. Pool = level*10 |
| `+0x54` | 1 | `upgrade_pending` | D |  |
| `+0x55` | 1 | `flag_byte_bit_0_the_hero_is_dead_k` | M | Flag byte. Bit 0 = the hero is dead (killed but retained in THeroControl so it can be resurrected/recalled). No other bit of this byte is read or writ |
| `+0x58` | 4 | `death_timestamp_a_copy_of_the_owni` | M | Death timestamp: a copy of the owning player's turn counter (TPlayer+0x5C) taken at the moment the hero was killed. Used as a cooldown so the hero wil |
| `+0x5C` | 1 | `the_player_index_that_owned_the_he` | M | The player index that owned the hero at the moment it was killed (the player it "died under"). Paired with +0x58 to gate re-joining that same player,  |
| `+0x5D` | 1 | `transient_runtime_flag_byte_not_se` | M | Transient runtime flag byte - NOT serialized (absent from THero.ReadWrite's field list). Bit 0 = "currently copying this hero from a hero-library temp |
| `+0x60` | 4 | `custom_name` | D | AnsiString |
| `+0x64` | 4 | `nickname_epithet_a_delphi_long_str` | M | Nickname / epithet - a Delphi long string (AnsiString pointer), separate from the hero's name at +0x60. |
| `+0x68` | 1 | `race_id_signed_byte_1_no_race_mirr` | M | Race id (signed byte; -1 = no race). Mirrors the hero resource's race field but is stored per-instance so it survives independently of the resource. |
| `+0x69` | 1 | `gender_thero_stores_it_per_instanc` | M | Gender. THero stores it per-instance; the base class returns the constant 2 and TUnit reads it from the unit resource, so this is the hero-specific ov |
| `+0x6A` | 1 | `atk_bonus` | D |  |
| `+0x6B` | 1 | `def_bonus` | M | read by THero.GetDefense |
| `+0x6C` | 1 | `damage_bonus_purchased_with_skill_` | M | Damage bonus purchased with skill points (signed). Costs 10 skill points per point - the most expensive of the six upgradable stats - and is clamped s |
| `+0x6D` | 1 | `maxhp_bonus` | D |  |
| `+0x6E` | 1 | `maxmv_bonus` | D |  |
| `+0x6F` | 1 | `res_bonus` | D |  |
| `+0x70` | 4 | `items` | M | PTR:THeroItems; THero.GetDefense reads it |
| `+0x74` | 4 | `inventory` | D | THeroInventory, 8 backpack slots |
| `+0x78` | 1 | `persistent_boolean_that_hides_the_` | D | Persistent Boolean that hides the hero from the hero-browse grids. Both hero grids include a hero only if `(TAoWEngine[+0x30] & 2) != 0 || hero[+0x78] |
| `+0x79` | 1 | `move_points_cur` | D |  |
| `+0x7A` | 1 | `hit_points_cur` | D |  |
| `+0x7C` | 4 | `power_source` | D | not serialized |
| `+0x80` | 1 | `casting_points` | D | RW tag 0x0D |
| `+0x84` | 4 | `spell_in_progress` | D | tag 0x0E |
| `+0x88` | 4 | `casting_progress` | D | tag 0x1F |
| `+0x8C` | 4 | `mana_required` | D | tag 0x22 |
| `+0x90` | 4 | `library_hero_id` | M | tag 0x23, -1 = not a library hero; paired with the library set name at +0x94. THero.GetLibraryHero is `cmp [eax+0x90],-1; setnz al`. NOT a casting-ready event-log id -- no such field exists on THero |
| `+0x94` | 4 | `ansistring_the_name_of_the_hero_li` | M | AnsiString: the name of the hero library (the .hero library file/collection) this hero was defined in. Together with dwLibrary_hero_id at +0x90 it is  |
| `+0x98` | 1 | `boolean_this_hero_is_currently_reg` | M | Boolean: "this hero is currently registered in the map's THeroControl list". Guards the register/unregister pair against double entry. |

## TItem  (instance size `0x4C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `container` | D | set by TItem.SetOwner |
| `+0x08` | 4 | `pointer_to_the_heap_allocated_abil` | M | [introduced by TCustomAbilityList] Pointer to the heap-allocated ability BITSET buffer - one bit per ability id, byte-indexed [id>>3], bit (id&7). Allocated/resized by ReallocMem to (Ab |
| `+0x0C` | 4 | `abcount_the_capacity_of_the_abilit` | M | [introduced by TCustomAbilityList] AbCount - the CAPACITY of the ability bitset in bits, i.e. the number of ability-id slots covered (highest usable ability id + 1). It is NOT a populat |
| `+0x10` | 4 | `head_pointer_of_a_singly_linked_li` | M | [introduced by TAbilityOwner] Head pointer of a singly-linked list of TAbilityData objects (per-ability extra payload, e.g. TUnitEnchantmentAbilityData). Nodes are chained through  |
| `+0x14` | 4 | `item_id` | D | RW tag 0x11 |
| `+0x18` | 4 | `name` | D | tag 8 |
| `+0x1C` | 1 | `flags` | D | bit0 = activated |
| `+0x20` | 4 | `reference_count_initialised_to_1_o` | M | Reference count. Initialised to 1 on construction; AddRef/Release are the VMT+0x28/+0x2C slots and the object self-destructs when it reaches 0. Delibe |
| `+0x24` | 4 | `library_item_id_this_item_s_unique` | M | Library item ID - this item's unique id inside its item library (paired with the library name at 0x28). The sentinel -1 (0xFFFFFFFF) means 'not a libr |
| `+0x28` | 4 | `ansistring_delphi_long_string_hold` | M | AnsiString (Delphi long string) holding the NAME OF THE ITEM LIBRARY this item was instantiated from; combined with the library id at 0x24 to re-resol |
| `+0x2C` | 4 | `obtain_value` | D | tag 0x13; GetObtainValue = max(x,10) |
| `+0x30` | 4 | `unknown_provably_a_delphi_long_str` | S | UNKNOWN - provably a Delphi long string (AnsiString) belonging to the item's own definition data (stream property id 9, immediately after Name at id 8 |
| `+0x34` | 1 | `item_type` | D | TItemTypes enum, tag 0x0F |
| `+0x38` | 4 | `spell_id` | D | tag 0x14 |
| `+0x3C` | 4 | `ability_list` | D | TStringList, tag 0x12 |
| `+0x40` | 4 | `gfx_index` | D | tag 7 |
| `+0x44` | 1 | `unknown_enum` | M | 1 BYTE, not 2 (+0x45 is a proven distinct field). tag 0x10, meaning still unresolved |
| `+0x45` | 1 | `rarity` | D | tag 0x0A |
| `+0x46` | 1 | `atk_bonus` | D | tag 0x0B |
| `+0x47` | 1 | `def_bonus` | D | tag 0x0C |
| `+0x48` | 1 | `dam_bonus` | D | tag 0x0D  ⚠ note order: TItem is ATK,DEF,DAM,RES |
| `+0x49` | 1 | `res_bonus` | D | tag 0x0E   whereas TUnit caches are ATK,DEF,RES,DAM |
| `+0x4A` | 1 | `unused_padding` | M | free zero-init padding in the vanilla 0x4C allocation; NOT claimed in either binary. The 'mod claims it' note came from a design proposal that was never built |
| `+0x4B` | 1 | `unused_padding2` | M | as +0x4A -- unbuilt proposal, not a live field |

## TPlayer  (instance size `0xDC`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `update_lock_nesting_counter_beginu` | M | Update-lock nesting counter (BeginUpdate/EndUpdate depth). While non-zero every change-notification is suppressed; EndUpdate decrements and, at 0, fir |
| `+0x0C` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's GOLD changes. |
| `+0x10` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's per-turn INCOME changes. |
| `+0x14` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's UPKEEP changes. |
| `+0x18` | 4 | `engine_teventlist_subscriber_list_` | M | Engine.TEventList - subscriber list fired when the player's event LOGBOOK changes. |
| `+0x1C` | 4 | `aowe_tplayerstructurelist_a_techan` | M | AoWE.TPlayerStructureList (a TEChangeNotifyEventList, with [list+0x14] = back-pointer to this player) holding EVERY structure this player owns (cities |
| `+0x20` | 4 | `aowe_tplayerstructurelist_of_this_` | M | AoWE.TPlayerStructureList of this player's VICTORY / capture locations (the win-condition sites). Emptiness of the not-yet-captured subset ends the ga |
| `+0x24` | 4 | `aowe_tproductioncontrollist_the_pl` | M | AoWE.TProductionControlList - the player's list of active production controls (one per producing site/city queue). |
| `+0x28` | 4 | `aowe_tarmylist_techangenotifyevent` | M | AoWE.TArmyList (TEChangeNotifyEventList, [list+0x14] = this player) - every army the player owns. Its change event is TPlayer.ArmiesChanged; emptying  |
| `+0x2C` | 1 | `boolean_turn_ended_flag_for_this_p` | M | Boolean "turn ended" flag for this player. |
| `+0x34` | 4 | `unknown_a_classes_tstringlist_owne` | S | UNKNOWN. A Classes.TStringList owned by the player: constructed in Create, streamed as property id 0x28, freed in Destroy - and never read, written or |
| `+0x38` | 4 | `aowe_tdiplomaticrelationlist_a_tby` | D | AoWE.TDiplomaticRelationList (a TByteList indexed by player id, value = relation enum) holding an initial relation table that is consumed at map start |
| `+0x3C` | 4 | `aowe_tdiplomaticrelationlist_tbyte` | M | AoWE.TDiplomaticRelationList (TByteList, index = player id, value = relation enum) holding the map/setup-authored STARTING diplomatic relations. At ma |
| `+0x40` | 4 | `aowe_tplayerdiplomaticrelations_th` | M | AoWE.TPlayerDiplomaticRelations - the player's LIVE diplomacy object ([+8] = back-pointer to this player, [+0x0C] = TByteList of current relations per |
| `+0x44` | 1 | `player_status` | M | 1-BYTE tri-state: 0 = still playing, 1 = victory, 2 = defeated. Not a 4-byte bool |
| `+0x45` | 1 | `player_participation_state_0_not_i` | M | Player participation state: 0 = not in play yet (initial), 1 = active/in the game, 2 = removed/eliminated from the game. This is the "is this player a |
| `+0x48` | 4 | `busy_lock` | D |  |
| `+0x4C` | 4 | `ansistring_the_player_s_own_name_u` | M | AnsiString: the player's own name, used only when the player has NO leader hero (0xD4 == nil). When a leader exists the name lives on the hero (hero+0 |
| `+0x54` | 4 | `magic_control` | D | TPlayerMagicControl |
| `+0x58` | 4 | `an_owned_aowe_tleader_instance_tha` | D | An owned AoWE.TLeader instance that acts as the stand-in for the player's leader at stream slot 0x1E: TPlayer.ReadWrite writes/reads either this objec |
| `+0x60` | 4 | `aowe_tplayerstatistics_the_per_tur` | M | AoWE.TPlayerStatistics - the per-turn statistics object; [obj+8] is the TTurnInfo list of TTurnInfoItem records (gold, mana, structure count, total ar |
| `+0x64` | 4 | `aowe_tincomesourcelist_the_list_of` | M | AoWE.TIncomeSourceList - the list of objects that contribute gold income; [list+8] is the underlying TList. Summed each turn into the income total at  |
| `+0x68` | 4 | `unknown_a_third_aowe_tplayerstruct` | S | UNKNOWN. A third AoWE.TPlayerStructureList (TEChangeNotifyEventList) that is constructed in TPlayer.Create and freed in TPlayer.Destroy but is never a |
| `+0x70` | 4 | `base_day_for_hero_join_hero_emerge` | M | Base day for hero-join/hero-emerge timing: the game day from which the next hero offer is measured. GetIdealHeroJoinDay returns this + 5/10/15 dependi |
| `+0x80` | 4 | `aowe_therolist_the_heroes_currentl` | M | AoWE.THeroList - the heroes currently belonging to this player. |
| `+0x84` | 4 | `aowe_taigrouplist_the_ai_groups_ar` | M | AoWE.TAIGroupList - the AI groups (army task forces) owned by this player. |
| `+0x88` | 4 | `aowe_taiplayercontrol_this_player_` | M | AoWE.TAIPlayerControl - this player's AI controller object; [obj+8] is a back-pointer to the player. Streamed as an object at id 0x1C and forwarded ev |
| `+0x8C` | 4 | `aowe_taibudgetmanager_this_player_` | M | AoWE.TAIBudgetManager - this player's AI gold/mana budget manager; [obj+8] is a back-pointer to the player. Streamed as an object at id 0x33 and forwa |
| `+0x90` | 4 | `aowe_tdiplomaticactionlist_the_log` | M | AoWE.TDiplomaticActionList - the log of diplomatic actions involving this player, kept so the AI can find the last action of a given type and not repe |
| `+0x94` | 4 | `engine_tbitlist_indexed_by_player_` | M | Engine.TBitList indexed by player id - the AI's "valid attack targets" mask (bit set when the diplomatic relation to that player is 1, i.e. war). |
| `+0xA0` | 4 | `aowe_tpbemplayersettings_the_playe` | M | AoWE.TPBEMPlayerSettings - the player's play-by-email settings object ([+8] byte flag, [+0x0C] an AoWE.TEmailGame). |
| `+0xA5` | 1 | `race_id_of_the_player_index_into_t` | M | Race id of the player (index into the race tables; 0xFF = none/unset, the Create default). |
| `+0xA6` | 1 | `player_index` | D |  |
| `+0xA7` | 1 | `player_type` | D | PlayerType enum; 4 = independent. NOT a bare human/AI bool |
| `+0xAC` | 4 | `starting_gold_for_the_player_map_s` | M | Starting gold for the player (map/setup authored). Default 250 (0xFA); copied into dwGold (0xC4) when a new map starts. |
| `+0xB0` | 4 | `flat_base_gold_income_per_turn_the` | M | Flat base gold income per turn: the starting value of the income accumulator before the registered income sources are summed (result stored in 0xD0).  |
| `+0xC4` | 4 | `gold` | D |  |
| `+0xC8` | 4 | `cached_army_gold_upkeep_total_for_` | M | Cached ARMY (gold) upkeep total for the player - the summed per-unit upkeep of all its armies. |
| `+0xCC` | 4 | `cached_magic_mana_upkeep_total_for` | M | Cached MAGIC (mana) upkeep total for the player. |
| `+0xD0` | 4 | `cached_total_gold_income_per_turn_` | M | Cached total gold income per turn = base (0xB0) + sum of all registered income sources, then scaled/bonused by AI difficulty (bPlayer_type 2,3 multipl |
| `+0xD4` | 4 | `pointer_to_the_player_s_leader_uni` | M | Pointer to the player's LEADER unit (AoWE.TLeader / THero). Nil means no leader; the object supplies the player's name (hero+0x60), face, map location |
| `+0xD8` | 4 | `event_logbook` | D |  |

## TRangedAttackAbility  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x28` | 1 | `range_tier` | D | 0..3, NOT a hex count |
| `+0x29` | 1 | `base_ranged_damage` | M | GetDamageRA reads it |
| `+0x2A` | 1 | `base_ranged_attack` | D |  |
| `+0x2B` | 2 | `innate_damage_types` | D | DamageTypeBits |
| `+0x2D` | 1 | `attack_repeat_count_how_many_separ` | M | Attack-repeat count: how many separate ranged shots/strikes this ability fires per attack. Backing field for the virtual getter TRangedAttackAbility.G |

## TSpell  (instance size `0x34`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `name` | D | plain LStr value, no VMT call |
| `+0x0C` | 1 | `castcontexts_a_delphi_set_bit_flag` | M | CastContexts: a Delphi SET (bit flags) of the contexts in which this spell may be cast. Bit 1 (mask 0x02) = CASTABLE IN COMBAT -- this is directly pro |
| `+0x10` | 4 | `spell_id` | D |  |
| `+0x14` | 4 | `mana_cost` | D | RW id 0x0D |
| `+0x18` | 4 | `research_cost` | D | RW id 0x0F; Create defaults it to 1 |
| `+0x1C` | 4 | `mana_upkeep_per_turn` | M | RW id 0x0E -- MANA UPKEEP PER TURN, not a casting-point cost. Nothing spends casting points from this field |
| `+0x20` | 1 | `sphere` | D | MagicSphere enum, RW id 0x10 |
| `+0x21` | 1 | `research_tier` | D | ResearchTier enum, RW id 0x11 |
| `+0x22` | 1 | `category` | D | 2 = global enchantment |
| `+0x24` | 4 | `description` | D | TStringList, RW id 0x0A |
| `+0x28` | 4 | `sfx` | D | RW id 0x0B |
| `+0x2C` | 4 | `images` | D | TImageSequenceList, RW id 0x0C; seq 10 = book icon |
| `+0x30` | 4 | `ai_value` | D |  |

## TStrikeCA  (instance size `0x1C`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x08` | 4 | `reference_count_lifetime_refcount_` | M | [introduced by TCombatAction] Reference count (lifetime refcount). Initialised to 1 by the constructor; AddRef increments and returns the new count; Release decrements and, on reac |
| `+0x0C` | 1 | `flags` | D | bit0 = defensive/retaliation |
| `+0x0D` | 1 | `attacker_id` | D |  |
| `+0x0E` | 1 | `target_id` | D |  |
| `+0x10` | 1 | `rolled_damage` | D | 0 = MISS |
| `+0x11` | 2 | `effective_damage_types` | D | 0 => fully immune |
| `+0x13` | 2 | `effect_landings` | D |  |
| `+0x15` | 1 | `applied_damage` | D | written in Execute |
| `+0x18` | 4 | `effect_flags` | D | ⚠ TStrikeCA ONLY. TCombatSpellCA+0x18 is the SPELL ID; a ranged CA carries the ability id there |

## TStructure  (instance size `0x30`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x04` | 4 | `map_field` | D |  |
| `+0x08` | 4 | `resource` | D |  |
| `+0x0C` | 1 | `object_state_flag_set_delphi_set_b` | M | Object state flag set (Delphi set, byte-wide). Named bits, from sibling accessors that read the same offset: bit0 (0x01) = Visible, bit1 (0x02) = Edit |
| `+0x10` | - | `hex_x_coordinate_hx_x_of_the_objec` | M | Hex X coordinate (HX x) of the object on the map - signed byte. Feeds every hex-geometry call the class makes. |
| `+0x11` | - | `hex_y_coordinate_hx_y_of_the_objec` | M | Hex Y coordinate (HX y) of the object on the map - signed byte. Always used as the second argument alongside +0x10. |
| `+0x14` | 4 | `cached_image_index_for_the_object_` | M | Cached image INDEX for the object's current terrain type - i.e. the memoised result of the virtual GetTerrainTypeImage (VMT+0x12C) applied to the terr |
| `+0x18` | - | `terrain_type_the_object_currently_` | M | Terrain type the object currently sits on / renders for - signed byte (negative = none/invalid). Set from the terrain-changed notification and from th |
| `+0x1C` | 4 | `structure_id` | D |  |
| `+0x20` | 4 | `beginupdate_endupdate_nesting_coun` | M | BeginUpdate/EndUpdate nesting counter (signed int, 0 = not inside an update block). Suppresses the TAoWHSMap.StructureChanged repaint/notify while non |
| `+0x24` | 1 | `player_index_of_the_player_current` | M | Player index of the player currently building or rebuilding this structure; 0xFF = nobody (the 'not under construction' sentinel). GetBuilding is lite |
| `+0x25` | 1 | `turns_remaining_until_the_current_` | M | Turns remaining until the current build/rebuild finishes - a countdown byte. Decremented once per turn of the player held in +0x24; when it reaches 0  |
| `+0x28` | 4 | `pointer_to_this_structure_s_aowe_t` | M | Pointer to this structure's AoWE.TStructureShadow companion object (nil when it has none). The shadow is a separate hex sprite that back-references th |
| `+0x2C` | 1 | `cached_this_structure_is_currently` | M | Cached 'this structure is currently hidden by fog of war' boolean (1 = hidden). Recomputed by FogChanged: seeded from the map's global fog flag (map+0 |

## TUnit  (instance size `0x48`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x3C` | 1 | `experience` | D | GetRank recomputes from it |
| `+0x3D` | 1 | `move_points_cur` | D |  |
| `+0x3E` | 1 | `hit_points_cur` | D | signed |
| `+0x3F` | 1 | `unknown_no_semantic_a_dead_byte_it` | D | UNKNOWN / no semantic - a dead byte. It is never read, written, compared, LEA'd, or streamed anywhere in AoWEPACK.dpl. Structurally it is the 1-byte a |
| `+0x40` | 4 | `resource` | M | PTR:TUnitResource -- ⚠ THero+0x40 is a DIFFERENT layout |
| `+0x44` | 1 | `atk_modifier_cache` | M | GetAttack adds it |
| `+0x45` | 1 | `def_modifier_cache` | M | GetDefense adds it |
| `+0x46` | 1 | `res_modifier_cache` | M | GetResistance adds it |
| `+0x47` | 1 | `dam_modifier_cache` | D | by position; the other three are measured |
| `+0x7C` | - | `casting_cluster` | D | ⚠ MOD ONLY -- vanilla instsize is 0x48. build_spellcast.py grows the class; +0x7C..+0x93 mirror THero's cluster |

## TUnitResource  (instance size `0x54`)

| offset | sz | field | ev | note |
|---|---|---|---|---|
| `+0x18` | 4 | `gfx_index` | D |  |
| `+0x1C` | - | `the_unit_type_s_name_a_delphi_ansi` | M | The unit type's name - a Delphi AnsiString (long-string pointer). It is the base component of the displayed unit name: TUnitResource.GetUnitName assig |
| `+0x20` | 1 | `race` | D |  |
| `+0x21` | 1 | `unknown_it_is_a_1_byte_non_pointer` | S | UNKNOWN. It is a 1-byte, non-pointer, persisted field (stream property id 0x16) that no code anywhere in AoWEPACK.dpl ever reads or writes - it is onl |
| `+0x24` | 4 | `own_name` | M | AnsiString, pfs tag 0x0B -- the unit's OWN name ("Rider", "Priest"), NOT a display name |
| `+0x28` | 1 | `alignment_a_talignment_enum_byte_0` | M | Alignment - a TAlignment enum byte: 0=alPureGood, 1=alGood, 2=alPureNeutral, 3=alNeutral, 4=alEvil, 5=alPureEvil, 6=alNone. This is the unit's inheren |
| `+0x29` | 1 | `base_attack` | M | TUnit.GetAttack reads it |
| `+0x2A` | 1 | `base_defense` | M | TUnit.GetDefense reads it |
| `+0x2B` | 1 | `base_damage` | D |  |
| `+0x2C` | 1 | `base_hits` | D |  |
| `+0x2D` | 1 | `base_moves` | D |  |
| `+0x2E` | 1 | `base_resistance` | M | TUnit.GetResistance reads it |
| `+0x2F` | 1 | `level_tier` | D | GetUpkeep = +0x2F + 1 |
| `+0x30` | 1 | `unit_type` | D | pfs tag 0x15; see UnitType_PARTIAL enum |
| `+0x31` | 1 | `gender_a_tunitgender_enum_byte_0_u` | M | Gender - a TUnitGender enum byte: 0=ugMale, 1=ugFemale, 2=ugNeutral. |
| `+0x32` | 1 | `transport_capacity_MOD` | D | ⚠ INSTALLED ONLY -- moved here from +0x44 by build_copper_medal.py |
| `+0x38` | 4 | `ability_owner_rank0` | D | pfs tag 0x19 |
| `+0x3C` | 4 | `ability_owner_rank1` | D | vanilla: silver. INSTALLED: copper (tag 0x20) |
| `+0x40` | 4 | `ability_owner_rank2` | D | vanilla: gold. INSTALLED: silver (tag 0x1E) |
| `+0x44` | 1 | `transport_capacity_VANILLA` | M | 1 BYTE in vanilla (pfs tag 0x18); +0x45..+0x47 are padding -- which is exactly what let build_copper_medal.py reuse the dword. INSTALLED: gold ability owner (tag 0x1F) |
| `+0x48` | 4 | `description_list` | M | TStringList OBJECT POINTER, not an AnsiString -- reading it as a string is wrong. pfs tag 0x1A |
| `+0x4C` | 4 | `gold_cost` | D | pfs tag 0x1B |
| `+0x50` | 1 | `unit_size` | M | TUnit.GetUnitSize reads [[unit+0x40]+0x50] |
| `+0x51` | 1 | `blood_type_a_tbloodtype_enum_byte_` | M | Blood type - a TBloodType enum byte selecting the colour of the blood/gore effect the unit produces: 0=btNone, 1=btRed, 2=btBlue, 3=btGreen. Defaults  |
| `+0x52` | - | `not_a_field_trailing_alignment_pad` | D | Not a field - trailing alignment padding in the instance. The last real field is the 1-byte 0x51, so the declared layout ends at 0x52, and Delphi roun |

