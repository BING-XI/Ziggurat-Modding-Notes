#!/usr/bin/env python
r"""
build_deved_multi_instance.py -- several editor windows may run at once.  AoWDevEd.exe (then
build_zigeditor.py --apply).  From Inioch's share8 catalogue, §2.4.

VANILLA
    The editor's startup creates the named file mapping "AOWED" (CreateFileMappingA, 0x42EDEF);
    when GetLastError is ERROR_ALREADY_EXISTS (0xB7) the `je 0x42EF96` at 0x42EE04 shows the
    "already running" message and quits.  The same name is used by every AoW1 editor build, so a
    running vanilla editor also blocks ours.

THE CHANGE
    The 6-byte je becomes six NOPs.  The mapping is still created (its handle is closed on exit
    as before); only the refusal goes.
    ⚠ That refusal was the only guard against two editors saving the same Release\*.pfs file or
    map: whichever saves last wins, silently.

Rolls: none.  No cave, no .reloc under the site.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
import zigexe
from exe_patch import run

SITE = 0x0042EE04
hooks = [(SITE, bytes.fromhex("0f848c010000"), bytes.fromhex("909090909090"))]

if __name__ == "__main__":
    run("build_deved_multi_instance", hooks, [], (SITE, SITE), targets=[zigexe.SRC_EDITOR])
