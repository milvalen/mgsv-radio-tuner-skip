"""Reads and patches Fox Engine archives (.dat, SQAR format) from MGSV: TPP.

The format is ported from GzsTool (github.com/Atvaark/GzsTool). Only archive version 1
is supported, which is what MGSV: TPP uses.

A file is replaced without rebuilding the archive: new data is appended to the end and
only that entry's offset changes in the section table. The old data stays in place, so
restoring means putting back 8 table bytes and the header, then truncating the file.
"""

import hashlib
import struct
import zlib

QAR_MAGIC = 0x52415153  # "SQAR"
M1, M2, M3, M4 = 0x41441043, 0x11C22050, 0xD05608C3, 0x532C7319
SECTION_XOR = (M1, M2, M3, M4)
DECRYPT1_TABLE = (
    0xBB8ADEDB, 0x65229958, 0x08453206, 0x88121302,
    0x4C344955, 0x2C02F10C, 0x4887F823, 0xF3818583,
)
CRYPT_MAGIC1 = 0xA0F8EFE6
CRYPT_MAGIC2 = 0xE3F8EFE6
HEADER_SIZE = 32
ENTRY_HEADER_SIZE = 32
U32 = 0xFFFFFFFF


class QarError(Exception):
    pass


def _xor_bytes(data, keystream):
    n = len(data)
    return (int.from_bytes(data, "little") ^ int.from_bytes(keystream[:n], "little")).to_bytes(n, "little")


def decrypt1(data, hash_low):
    """Encryption layer of all entries (symmetric, also used to encrypt). Position 0 = start of entry data."""
    blocks = (len(data) + 7) // 8
    ks = bytearray(blocks * 8)
    for i in range(blocks):
        idx = 2 * ((hash_low + (i * 8) // 11) % 4)
        struct.pack_into("<II", ks, i * 8, DECRYPT1_TABLE[idx], DECRYPT1_TABLE[idx + 1])
    return _xor_bytes(bytes(data), ks)


def decrypt2(data, key):
    """Extra encryption of some files (read only; our own data is written without it)."""
    k = (278 * key) & U32
    block_key = (key | ((key ^ 25974) << 16)) & U32
    words = len(data) // 4
    ks = bytearray(len(data))  # the 0-3 byte tail is not encrypted -> zeros in the key
    for i in range(words):
        struct.pack_into("<I", ks, i * 4, block_key)
        block_key = (k + 48828125 * block_key) & U32
    return _xor_bytes(bytes(data), ks)


def _section_xor(i, raw, encrypt=False):
    lo, hi = struct.unpack("<II", raw)
    lo ^= SECTION_XOR[(i + (i * 8) // 5) % 4]
    hi ^= SECTION_XOR[(i + (i * 8 + 4) // 5) % 4]
    return lo, hi


class Entry:
    def __init__(self, index, section, offset):
        self.index = index
        self.section = section
        self.offset = offset
        self.hash = 0
        self.uncompressed_size = 0
        self.compressed_size = 0
        self.md5 = b""

    @property
    def hash_low(self):
        return self.hash & U32

    @property
    def compressed(self):
        return self.uncompressed_size != self.compressed_size


class QarArchive:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(HEADER_SIZE)
            if len(head) < HEADER_SIZE:
                raise QarError("file too short")
            vals = struct.unpack("<8I", head)
            if vals[0] != QAR_MAGIC:
                raise QarError("not an SQAR archive")
            self.flags = vals[1] ^ M1
            self.file_count = vals[2] ^ M2
            self.unknown_count = vals[3] ^ M3
            self.block_file_end = vals[4] ^ M4
            self.offset_first_file = vals[5] ^ M1
            self.version = vals[6] ^ M1
            if self.version != 1:
                raise QarError("archive version %d is not supported (expected 1)" % self.version)
            self.shift = 12 if self.flags & 0x800 else 10
            table = f.read(8 * self.file_count)
            if len(table) != 8 * self.file_count:
                raise QarError("truncated section table")
        self.entries = []
        for i in range(self.file_count):
            lo, hi = _section_xor(i, table[i * 8:i * 8 + 8])
            section = (hi << 32) | lo
            self.entries.append(Entry(i, section, (section >> 40) << self.shift))

    # --- reading ---

    def _read_entry_header(self, f, e):
        f.seek(e.offset)
        raw = f.read(ENTRY_HEADER_SIZE)
        if len(raw) != ENTRY_HEADER_SIZE:
            raise QarError("entry %d is past the end of the file" % e.index)
        v = struct.unpack("<8I", raw)
        e.hash = ((v[1] ^ M1) << 32) | (v[0] ^ M1)
        e.uncompressed_size = v[2] ^ M2
        e.compressed_size = v[3] ^ M3
        e.md5 = struct.pack("<4I", v[4] ^ M4, v[5] ^ M1, v[6] ^ M1, v[7] ^ M2)

    def read_entry(self, f, e, limit=None):
        """Returns the decrypted and decompressed entry data.

        limit: read only the start (for fast search); the result may then be shorter.
        """
        self._read_entry_header(f, e)
        size = e.compressed_size
        n = size if limit is None else min(size, limit)
        data = decrypt1(f.read(n), e.hash_low)
        if len(data) >= 8:
            magic, key = struct.unpack_from("<II", data)
            if magic in (CRYPT_MAGIC1, CRYPT_MAGIC2):
                hsize = 8 if magic == CRYPT_MAGIC1 else 16
                # Decrypt2 walks words from the stream start, cutting at limit keeps the prefix valid
                data = decrypt2(data[hsize:], key)
        if e.compressed:
            d = zlib.decompressobj()
            try:
                data = d.decompress(data)
            except zlib.error:
                if limit is None:
                    raise
                return b""
        return data

    def find_entries(self, predicate, probe=256):
        """Finds entries by content. predicate(prefix_bytes, full_reader) -> bool."""
        found = []
        with open(self.path, "rb") as f:
            for e in self.entries:
                try:
                    head = self.read_entry(f, e, limit=probe)
                except (QarError, zlib.error, struct.error):
                    continue
                if predicate(head, lambda: self.read_entry(f, e)):
                    found.append(e)
        return found

    # --- writing ---

    def _raw_section(self, f, index):
        f.seek(HEADER_SIZE + 8 * index)
        return f.read(8)

    def replace_entry(self, e, new_data):
        """Appends a new version of the entry to the archive and points the table at it.

        Returns a dict with the data needed to undo this (restore_entry).
        """
        payload = zlib.compress(new_data, 9) if e.compressed else bytes(new_data)
        if len(payload) == len(new_data) and e.compressed:
            # equal sizes would make the game treat the data as uncompressed
            payload = zlib.compress(new_data + b"\n", 9)
            new_data = new_data + b"\n"
        md5 = hashlib.md5(payload).digest()
        align = 1 << self.shift
        with open(self.path, "r+b") as f:
            f.seek(0, 2)
            orig_size = f.tell()
            start = (orig_size + align - 1) // align * align
            block = start >> self.shift
            if block >= (1 << 24):
                raise QarError("archive too large for the offset field")
            orig_section_raw = self._raw_section(f, e.index)
            f.seek(16)
            orig_end_raw = f.read(4)

            hdr = struct.pack(
                "<QII4I",
                e.hash ^ ((M1 << 32) | M1),
                len(new_data) ^ M2,
                len(payload) ^ M3,
                *(a ^ b for a, b in zip(struct.unpack("<4I", md5), (M4, M1, M1, M2)))
            )
            body = decrypt1(payload, e.hash_low)
            f.seek(orig_size)
            f.write(b"\0" * (start - orig_size))
            f.write(hdr)
            f.write(body)
            end = f.tell()
            end = (end + align - 1) // align * align
            f.write(b"\0" * (end - f.tell()))

            new_section = (block << 40) | (e.section & 0xFFFFFFFFFF)
            lo, hi = new_section & U32, new_section >> 32
            lo ^= SECTION_XOR[(e.index + (e.index * 8) // 5) % 4]
            hi ^= SECTION_XOR[(e.index + (e.index * 8 + 4) // 5) % 4]
            f.seek(HEADER_SIZE + 8 * e.index)
            f.write(struct.pack("<II", lo, hi))
            f.seek(16)
            f.write(struct.pack("<I", (end >> self.shift) ^ M4))
        return {
            "index": e.index,
            "orig_size": orig_size,
            "orig_section": orig_section_raw.hex(),
            "orig_block_end": orig_end_raw.hex(),
            "patched_size": end,
        }

    def restore_entry(self, info):
        with open(self.path, "r+b") as f:
            f.seek(0, 2)
            if f.tell() != info["patched_size"]:
                raise QarError("archive size changed after patching (game update?), cannot restore. "
                               "Use Steam: Verify integrity of game files")
            f.seek(HEADER_SIZE + 8 * info["index"])
            f.write(bytes.fromhex(info["orig_section"]))
            f.seek(16)
            f.write(bytes.fromhex(info["orig_block_end"]))
            f.truncate(info["orig_size"])
