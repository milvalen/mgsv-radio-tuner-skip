"""Install, patch and restore tests on a synthetic SQAR archive (built with GzsTool's write algorithm).

Run: python3 tests/test_tuner.py [path to a TppRadio.lua]
Without an argument it uses the stub in tests/fixtures. Needs luajit.
"""

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import luapatch  # noqa: E402
import qar  # noqa: E402
import tuner  # noqa: E402
from qar import M1, M2, M3, M4  # noqa: E402


def encrypt2(data, key):
    return qar.decrypt2(data, key)  # XOR stream, symmetric


def build_archive(path, files, flags=0x800):
    """files: list of (hash, bytes, compress, crypt_key|None). Port of QarFile.Write/QarEntry.Write."""
    shift = 12 if flags & 0x800 else 10
    align = 1 << shift
    out = bytearray(32 + 8 * len(files))
    out += b"\0" * ((-len(out)) % align)
    data_offset = len(out)
    sections = []
    for i, (h, raw, compress, key) in enumerate(files):
        start = len(out)
        sections.append((start >> shift) << 40 | (h & 0xFF) << 32 | (h >> 32) & 0xFFFFFFFFFF)
        payload = zlib.compress(raw, 9) if compress else raw
        if key is not None:
            payload = struct.pack("<II", qar.CRYPT_MAGIC1, key) + encrypt2(payload, key)
        md5 = hashlib.md5(payload).digest()
        usize = len(raw) if compress else len(payload)
        hdr = struct.pack("<QII4I", h ^ ((M1 << 32) | M1), usize ^ M2, len(payload) ^ M3,
                          *(a ^ b for a, b in zip(struct.unpack("<4I", md5), (M4, M1, M1, M2))))
        out += hdr + qar.decrypt1(payload, h & 0xFFFFFFFF)
        out += b"\0" * ((-len(out)) % align)
    struct.pack_into("<8I", out, 0, qar.QAR_MAGIC, flags ^ M1, len(files) ^ M2, M3,
                     (len(out) >> shift) ^ M4, data_offset ^ M1, 1 ^ M1, 0 ^ M2)
    for i, s in enumerate(sections):
        lo, hi = s & 0xFFFFFFFF, s >> 32
        lo ^= qar.SECTION_XOR[(i + (i * 8) // 5) % 4]
        hi ^= qar.SECTION_XOR[(i + (i * 8 + 4) // 5) % 4]
        struct.pack_into("<II", out, 32 + 8 * i, lo, hi)
    with open(path, "wb") as f:
        f.write(out)


def minify_module_name(src):
    # in the game the module has a short name instead of "this"
    return src.replace(b"local this={}", b"local e={}").replace(b"this.", b"e.").replace(
        b"return this", b"return e")


LUA_HARNESS = r"""
package.path = "%(dir)s/?.lua;" .. package.path
local t = 0
Time = {GetRawElapsedTimeSinceStartUp=function() return t end}
math.random = function(n) return _G.__rand or 1 end
local played = {}
local stub = setmetatable({}, {__index=function() return function() end end})
Fox={StrCode32=function(s) return s end}
GkEventTimerManager=stub
Tpp={IsTypeFunc=function(x) return type(x)=="function" end,IsTypeTable=function(x) return type(x)=="table" end,
     IsTypeString=function(x) return type(x)=="string" end,IsTypeNumber=function(x) return type(x)=="number" end,
     StrCode32Table=function(x) return x end}
TppDefine=setmetatable({}, {__index=function() return setmetatable({}, {__index=function(_,k) return k end}) end})
TppStory={}
TppRadioCommand=setmetatable({PlayDirectGroupTable=function(a) played[#played+1]=a.tableName end,
  IsRadioGroupMarkAsRead=function() return false end}, {__index=function() return function() end end})
mvars={rad_radioPlayOnceList={}}
local R = dofile("%(file)s")
local function play(l) R.Play(l) end
local function count() local n=#played; played={}; return n end
-- common 30%%, cooldown 45: the first one passes when random<=30
_G.__rand = 10; play("f1000_rtrg0130"); assert(count()==1, "common first")
t = 10; play("f1000_rtrg0120"); assert(count()==0, "cooldown blocks")
t = 60; _G.__rand = 90; play("f1000_rtrg0120"); assert(count()==0, "chance blocks")
t = 61; _G.__rand = 5; play("f1000_rtrg0120"); assert(count()==1, "after cooldown")
t = 62; play("s10010_mprg0010"); assert(count()==1, "story always")
t = 63; play({"s10020_rtrg0010","s10020_rtrg0020"}); assert(count()==0, "mission under cooldown")
t = 63; play("f1000_rtrg9999"); assert(count()==1, "allow label")
t = 200; play("f1000_rtrg0100"); assert(count()==0, "mute label")
t = 300; play("f8000_gmov0010"); assert(count()==1, "gameover")
t = 300; play("f1000_esrg0010"); assert(count()==1, "unknown kind passes")
print("LUA OK")
"""


def main():
    lua_src_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "fixtures", "TppRadioStub.lua")
    with open(lua_src_path, "rb") as f:
        radio = minify_module_name(f.read())
    tmp = tempfile.mkdtemp()
    try:
        game = os.path.join(tmp, "MGS_TPP")
        os.makedirs(os.path.join(game, "master", "0"))
        other = [(0x1111111111 + i, (b"-- other lua %d\n" % i) * 50, True, None) for i in range(5)]
        binary = [(0x2222222222, os.urandom(5000), False, None), (0x3333333333, os.urandom(3000), True, 0x1234)]
        data1 = os.path.join(game, "master", "data1.dat")
        build_archive(data1, other[:2] + [(0x0ABCDEF012345678, radio, True, 0xBEEF)] + other[2:] + binary)
        build_archive(os.path.join(game, "master", "0", "00.dat"), binary, flags=0)
        orig = open(data1, "rb").read()

        # reading: everything written reads back
        arc = qar.QarArchive(data1)
        with open(data1, "rb") as f:
            assert arc.read_entry(f, arc.entries[2]) == radio
            assert arc.read_entry(f, arc.entries[7]) == binary[1][1]

        cfg = tuner.load_config(os.path.join(tmp, "none.json"))
        cfg["mute_labels"] = ["f1000_rtrg0100"]
        cfg["allow_labels"] = ["f1000_rtrg9999"]
        tuner.apply(game, cfg, log=lambda s: None)
        arc = qar.QarArchive(data1)
        with open(data1, "rb") as f:
            patched = arc.read_entry(f, arc.entries[2])
            rest = other + binary  # all entries except #2 are untouched
            for i, e in enumerate(arc.entries):
                if i != 2:
                    assert arc.read_entry(f, e) == rest[i if i < 2 else i - 1][1], i
        assert luapatch.MARK_BEGIN in patched and patched.rstrip().endswith(b"return e")
        assert luapatch.strip_patch(patched) == radio

        # Lua: syntax and filter behaviour
        lua_file = os.path.join(tmp, "TppRadio.lua")
        open(lua_file, "wb").write(patched)
        harness = os.path.join(tmp, "harness.lua")
        open(harness, "w").write(LUA_HARNESS % {"dir": tmp, "file": lua_file})
        r = subprocess.run(["luajit", harness], capture_output=True, text=True)
        print(r.stdout.strip(), r.stderr.strip())
        assert r.returncode == 0

        # applying again does not grow the archive, restoring is byte for byte
        size1 = os.path.getsize(data1)
        tuner.apply(game, cfg, log=lambda s: None)
        assert os.path.getsize(data1) == size1
        tuner.restore(game, log=lambda s: None)
        assert open(data1, "rb").read() == orig
        assert not os.path.exists(os.path.join(game, tuner.STATE_NAME))
        print("ALL OK")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
