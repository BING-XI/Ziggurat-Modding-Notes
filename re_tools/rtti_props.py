#!/usr/bin/env python3
r"""List a Delphi class's OWN published properties, straight out of the VCL's RTTI.

WHY THIS EXISTS
  TReader rejects the ENTIRE form over one unknown property, so a generated DFM that
  sets a property the compiled class does not publish fails at load with
  "Error reading X.Prop: Property does not exist" and nothing else loads. That has cost
  this project two round trips -- ItemIndex (public but not published on Delphi 3's
  TComboBox) and PageSize (arrived in Delphi 4). Run this BEFORE adding a property to
  any DFM a build script emits.

      python rtti_props.py TScrollBar TComboBox
      python rtti_props.py TComboBox OnChange OnClick      # names after the class are
                                                           # asserted, exit 1 if missing

FORMAT (Delphi 3, tkClass = 7)
      <u8 kind><shortstring classname>
      ClassType:u32  ParentInfo:u32  PropCount:u16   <- PropCount INCLUDES ancestors
      UnitName:shortstring
      TPropData: <u16 count>                         <- declared or republished HERE
        per property: 26 bytes then <shortstring name>

  ⚠ 26, not 24: PropType/GetProc/SetProc/StoredProc (4x4) + Index + Default (2x4) +
  NameIndex (2). Getting it wrong makes every class look absent rather than misparsed.

  A class republished in a `published` section appears in that class's OWN TPropData, so
  `OnClick` shows up under TComboBox even though TControl introduced it -- which is
  exactly the question a DFM needs answered.
"""
import glob
import os
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TK_CLASS = 7


def published(data, cls):
    """Every parse of `cls` found in `data`, as (total_incl_ancestors, [names])."""
    tag = bytes([TK_CLASS, len(cls)]) + cls.encode('latin1')
    out = []
    at = -1
    while True:
        at = data.find(tag, at + 1)
        if at < 0:
            return out
        p = at + len(tag) + 8                     # ClassType, ParentInfo
        total = struct.unpack_from('<H', data, p)[0]
        p += 2
        p += 1 + data[p]                          # UnitName
        n = struct.unpack_from('<H', data, p)[0]
        p += 2
        if not (0 < n <= 400 and 0 < total <= 600):
            continue
        names = []
        for _ in range(n):
            p += 26
            ln = data[p] if p < len(data) else 0
            if ln == 0 or ln > 63 or p + 1 + ln > len(data):
                names = None
                break
            names.append(data[p + 1:p + 1 + ln].decode('latin1'))
            p += 1 + ln
        if names:
            out.append((total, names))


def find(cls, modules=None):
    """(module, total, names) for the first module that carries `cls`'s RTTI."""
    mods = modules or sorted(glob.glob(os.path.join(GAME, '*.dpl')) +
                             glob.glob(os.path.join(GAME, '*.exe')))
    for f in mods:
        hits = published(open(f, 'rb').read(), cls)
        if hits:
            return os.path.basename(f), hits[0][0], hits[0][1]
    return None, 0, []


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[0])
        print('usage: rtti_props.py <TClass> [PropToAssert ...]')
        return 2
    cls, want = sys.argv[1], sys.argv[2:]
    mod, total, names = find(cls)
    if not mod:
        print('%s: no RTTI found in any module under %s' % (cls, GAME))
        return 1
    print('%s  (%s): %d published here, %d including ancestors'
          % (cls, mod, len(names), total))
    print('  ' + ', '.join(names))
    bad = [w for w in want if w not in names]
    for w in want:
        print('  %-14s %s' % (w, 'yes' if w in names else 'NOT PUBLISHED'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
