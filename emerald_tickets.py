#!/usr/bin/env python3
"""
emerald_tickets.py — enable ticket events on a Pokemon Emerald save file (.sav).

Supported events:
  aurora    Aurora Ticket  -> Birth Island (Deoxys)
  mystic    Mystic Ticket  -> Navel Rock (Ho-Oh + Lugia)
  eon       Eon Ticket     -> Southern Island (Latios or Latias)
  oldseamap Old Sea Map    -> Faraway Island (Mew)

For each event it:
  * adds the key item to the Key Items pocket (quantity 1, correctly
    XOR-encrypted with the save's encryption key)
  * sets the "received" event flag (where the game defines one)
  * sets the ferry-destination flag so the Lilycove sailor lists the island

All offsets/constants are taken from the pret/pokeemerald decompilation:
  FLAG_RECEIVED_AURORA_TICKET       = 0x13A
  FLAG_RECEIVED_MYSTIC_TICKET       = 0x13B
  FLAG_RECEIVED_OLD_SEA_MAP         = 0x13C
  FLAG_ENABLE_SHIP_SOUTHERN_ISLAND  = 0x8B3   (SYSTEM_FLAGS 0x860 + 0x53)
  FLAG_ENABLE_SHIP_BIRTH_ISLAND     = 0x8D5
  FLAG_ENABLE_SHIP_FARAWAY_ISLAND   = 0x8D6
  FLAG_ENABLE_SHIP_NAVEL_ROCK       = 0x8E0
  FLAG_LANDMARK_SOUTHERN_ISLAND     = 0x8A9
  ITEM_EON_TICKET = 275, ITEM_MYSTIC_TICKET = 370,
  ITEM_AURORA_TICKET = 371, ITEM_OLD_SEA_MAP = 376
  SaveBlock1.bagPocket_KeyItems     @ 0x05D8 (30 slots of {u16 id, u16 qty})
  SaveBlock1.flags                  @ 0x1270
  SaveBlock2.encryptionKey          @ 0x00AC

Usage:
  python3 emerald_tickets.py SAVE.sav                  # all four -> SAVE.patched.sav
  python3 emerald_tickets.py SAVE.sav --aurora --mystic
  python3 emerald_tickets.py SAVE.sav --eon            # any combination works
  python3 emerald_tickets.py SAVE.sav -o out.sav       # choose output path
  python3 emerald_tickets.py SAVE.sav --in-place       # overwrite (writes .bak first)
  python3 emerald_tickets.py SAVE.sav --info           # inspect, change nothing
"""

import argparse
import struct
import sys

SECTOR_SIZE = 0x1000
SECTOR_DATA_SIZE = 3968
SECTOR_SIGNATURE = 0x08012025
SECTORS_PER_SLOT = 14

SIZEOF_SAVEBLOCK2 = 0x0F2C  # 3884
SIZEOF_SAVEBLOCK1 = 0x3D88  # 15752
SIZEOF_PKMN_STORAGE = 33744

CHECKSUM_SIZES = [SIZEOF_SAVEBLOCK2]
for chunk in range(4):
    CHECKSUM_SIZES.append(min(SIZEOF_SAVEBLOCK1 - chunk * SECTOR_DATA_SIZE, SECTOR_DATA_SIZE))
for chunk in range(9):
    CHECKSUM_SIZES.append(min(SIZEOF_PKMN_STORAGE - chunk * SECTOR_DATA_SIZE, SECTOR_DATA_SIZE))
assert len(CHECKSUM_SIZES) == SECTORS_PER_SLOT
assert CHECKSUM_SIZES[4] == 3848 and CHECKSUM_SIZES[13] == 2000

SB1_FLAGS_OFFSET = 0x1270
SB1_KEYITEMS_OFFSET = 0x05D8
KEYITEMS_SLOTS = 30
SB2_ENCRYPTION_KEY_OFFSET = 0x00AC

FLAG_RECEIVED_AURORA_TICKET = 0x13A
FLAG_RECEIVED_MYSTIC_TICKET = 0x13B
FLAG_RECEIVED_OLD_SEA_MAP = 0x13C
FLAG_LANDMARK_SOUTHERN_ISLAND = 0x8A9
FLAG_ENABLE_SHIP_SOUTHERN_ISLAND = 0x8B3
FLAG_ENABLE_SHIP_BIRTH_ISLAND = 0x8D5
FLAG_ENABLE_SHIP_FARAWAY_ISLAND = 0x8D6
FLAG_ENABLE_SHIP_NAVEL_ROCK = 0x8E0

ITEM_EON_TICKET = 275
ITEM_MYSTIC_TICKET = 370
ITEM_AURORA_TICKET = 371
ITEM_OLD_SEA_MAP = 376

TICKETS = {
    "aurora": {
        "label": "Aurora Ticket (Birth Island / Deoxys)",
        "item": ITEM_AURORA_TICKET,
        "flags": [FLAG_RECEIVED_AURORA_TICKET, FLAG_ENABLE_SHIP_BIRTH_ISLAND],
    },
    "mystic": {
        "label": "Mystic Ticket (Navel Rock / Ho-Oh + Lugia)",
        "item": ITEM_MYSTIC_TICKET,
        "flags": [FLAG_RECEIVED_MYSTIC_TICKET, FLAG_ENABLE_SHIP_NAVEL_ROCK],
    },
    "eon": {
        "label": "Eon Ticket (Southern Island / Latios or Latias)",
        "item": ITEM_EON_TICKET,
        # the Eon Ticket has no RECEIVED flag in Emerald; the sailor keys off
        # the item + ship flag. Landmark flag makes it visible on the map.
        "flags": [FLAG_ENABLE_SHIP_SOUTHERN_ISLAND, FLAG_LANDMARK_SOUTHERN_ISLAND],
    },
    "oldseamap": {
        "label": "Old Sea Map (Faraway Island / Mew)",
        "item": ITEM_OLD_SEA_MAP,
        "flags": [FLAG_RECEIVED_OLD_SEA_MAP, FLAG_ENABLE_SHIP_FARAWAY_ISLAND],
    },
}


def checksum(data: bytes, size: int) -> int:
    total = 0
    for (word,) in struct.iter_unpack("<I", data[:size]):
        total = (total + word) & 0xFFFFFFFF
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


class Sector:
    def __init__(self, buf: bytearray, file_offset: int):
        self.buf = buf
        self.off = file_offset

    @property
    def data(self) -> bytearray:
        return self.buf[self.off:self.off + SECTOR_DATA_SIZE]

    def read_data(self, rel: int, n: int) -> bytes:
        return bytes(self.buf[self.off + rel:self.off + rel + n])

    def write_data(self, rel: int, payload: bytes):
        self.buf[self.off + rel:self.off + rel + len(payload)] = payload

    @property
    def sec_id(self) -> int:
        return struct.unpack_from("<H", self.buf, self.off + 0xFF4)[0]

    @property
    def stored_checksum(self) -> int:
        return struct.unpack_from("<H", self.buf, self.off + 0xFF6)[0]

    @property
    def signature(self) -> int:
        return struct.unpack_from("<I", self.buf, self.off + 0xFF8)[0]

    @property
    def counter(self) -> int:
        return struct.unpack_from("<I", self.buf, self.off + 0xFFC)[0]

    def fix_checksum(self):
        c = checksum(self.data, CHECKSUM_SIZES[self.sec_id])
        struct.pack_into("<H", self.buf, self.off + 0xFF6, c)


class Slot:
    """One save slot: 14 rotated sectors."""

    def __init__(self, buf: bytearray, first_sector_index: int):
        self.sectors = [Sector(buf, (first_sector_index + i) * SECTOR_SIZE)
                        for i in range(SECTORS_PER_SLOT)]

    def valid(self) -> bool:
        ids = set()
        for s in self.sectors:
            if s.signature != SECTOR_SIGNATURE:
                return False
            if not (0 <= s.sec_id < SECTORS_PER_SLOT):
                return False
            ids.add(s.sec_id)
        return len(ids) == SECTORS_PER_SLOT

    @property
    def counter(self) -> int:
        return max(s.counter for s in self.sectors)

    def section(self, sec_id: int) -> Sector:
        for s in self.sectors:
            if s.sec_id == sec_id:
                return s
        raise KeyError(sec_id)

    def sb1_locate(self, sb1_off: int):
        return self.section(1 + sb1_off // SECTOR_DATA_SIZE), sb1_off % SECTOR_DATA_SIZE

    def sb1_read(self, sb1_off: int, n: int) -> bytes:
        out = b""
        while n:
            sec, rel = self.sb1_locate(sb1_off)
            take = min(n, SECTOR_DATA_SIZE - rel)
            out += sec.read_data(rel, take)
            sb1_off += take
            n -= take
        return out

    def sb1_write(self, sb1_off: int, payload: bytes):
        while payload:
            sec, rel = self.sb1_locate(sb1_off)
            take = min(len(payload), SECTOR_DATA_SIZE - rel)
            sec.write_data(rel, payload[:take])
            sb1_off += take
            payload = payload[take:]

    @property
    def encryption_key(self) -> int:
        raw = self.section(0).read_data(SB2_ENCRYPTION_KEY_OFFSET, 4)
        return struct.unpack("<I", raw)[0]

    def get_flag(self, flag: int) -> bool:
        byte = self.sb1_read(SB1_FLAGS_OFFSET + flag // 8, 1)[0]
        return bool(byte & (1 << (flag % 8)))

    def set_flag(self, flag: int):
        off = SB1_FLAGS_OFFSET + flag // 8
        byte = self.sb1_read(off, 1)[0]
        self.sb1_write(off, bytes([byte | (1 << (flag % 8))]))

    def key_items(self):
        raw = self.sb1_read(SB1_KEYITEMS_OFFSET, KEYITEMS_SLOTS * 4)
        key16 = self.encryption_key & 0xFFFF
        out = []
        for i in range(KEYITEMS_SLOTS):
            item, enc_qty = struct.unpack_from("<HH", raw, i * 4)
            out.append((item, enc_qty ^ key16 if item else 0))
        return out

    def add_key_item(self, item_id: int) -> str:
        items = self.key_items()
        if any(it == item_id for it, _ in items):
            return "already in bag"
        for i, (it, _) in enumerate(items):
            if it == 0:
                enc_qty = 1 ^ (self.encryption_key & 0xFFFF)
                self.sb1_write(SB1_KEYITEMS_OFFSET + i * 4,
                               struct.pack("<HH", item_id, enc_qty))
                return f"added (slot {i + 1})"
        return "POCKET FULL — not added"

    def fix_checksums(self):
        for s in self.sectors:
            s.fix_checksum()

    def game_code(self) -> int:
        # SaveBlock2 +0xAC: 0 in Ruby/Sapphire, 1 in FRLG,
        # the (random, nonzero) encryption key itself in Emerald.
        return struct.unpack("<I", self.section(0).read_data(0xAC, 4))[0]


def load_slots(buf: bytearray):
    slots = [s for s in (Slot(buf, 0), Slot(buf, 14)) if s.valid()]
    if not slots:
        sys.exit("error: no valid save slot found — is this a raw 128 KiB "
                 "Emerald .sav (not a savestate)?")
    return max(slots, key=lambda s: (s.counter + 1) & 0xFFFFFFFF)


def main():
    ap = argparse.ArgumentParser(description="Enable ticket events on an Emerald save.")
    ap.add_argument("save", help="path to the .sav file")
    for name in TICKETS:
        ap.add_argument(f"--{name}", action="store_true",
                        help=TICKETS[name]["label"] + " only")
    ap.add_argument("-o", "--output", help="output path (default: <save>.patched.sav)")
    ap.add_argument("--in-place", action="store_true", help="overwrite input (backs up to .bak)")
    ap.add_argument("--info", action="store_true", help="show current state and exit")
    ap.add_argument("--force", action="store_true", help="skip the Emerald game check")
    args = ap.parse_args()

    with open(args.save, "rb") as f:
        buf = bytearray(f.read())
    if len(buf) < 28 * SECTOR_SIZE:
        sys.exit(f"error: file is {len(buf)} bytes; expected at least 114688 "
                 "(a raw GBA flash save). Emulator savestates are not supported.")

    slot = load_slots(buf)

    code = slot.game_code()
    if code in (0, 1) and not args.force:
        guess = "Ruby/Sapphire" if code == 0 else "FireRed/LeafGreen"
        sys.exit(f"error: this save doesn't look like Emerald "
                 f"(game code field = 0x{code:08X}, likely {guess}). "
                 "Use --force to override.")

    wanted = [k for k in TICKETS if getattr(args, k)] or list(TICKETS)

    if args.info:
        print(f"active slot counter: {slot.counter}")
        for name, t in TICKETS.items():
            have_item = any(it == t["item"] for it, _ in slot.key_items())
            flags = {f"0x{f:03X}": slot.get_flag(f) for f in t["flags"]}
            print(f"\n{t['label']}\n  key item in bag: {have_item}\n  flags: {flags}")
        return

    print(f"patching active slot (counter {slot.counter})")
    for name in wanted:
        t = TICKETS[name]
        print(f"\n{t['label']}")
        print(f"  item: {slot.add_key_item(t['item'])}")
        for f in t["flags"]:
            state = "already set" if slot.get_flag(f) else "set"
            slot.set_flag(f)
            print(f"  flag 0x{f:03X}: {state}")

    slot.fix_checksums()

    if args.in_place:
        out = args.save
        with open(args.save + ".bak", "wb") as f:
            with open(args.save, "rb") as orig:
                f.write(orig.read())
        print(f"\nbackup written to {args.save}.bak")
    else:
        out = args.output or (args.save.rsplit(".", 1)[0] + ".patched.sav")
    with open(out, "wb") as f:
        f.write(buf)
    print(f"written: {out}")
    print("\nIn game: talk to the sailor at the Lilycove City harbor ferry "
          "terminal and pick your destination.")


if __name__ == "__main__":
    main()
