"""Generates the Lua radio filter and mission skip and inserts them into TppRadio.lua."""

import re

MARK_BEGIN = b"--[[RADIO_TUNER_BEGIN]]"
MARK_END = b"--[[RADIO_TUNER_END]]"

# Markers used to find TppRadio.lua inside an archive (module function names are not
# minified because they are table fields).
SIGNATURES = (b"PlayDirectGroupTable", b"GetRadioNameAndRadioIDs", b"COMMON_RADIO_LIST")

# Category -> (UI name, hint, whether it counts towards the pause between lines)
CATEGORIES = {
    "common": ("Common comments",
               "Ocelot/Miller on routine events: extraction, wounds, suppressor, helicopter, "
               "markers, finds and so on (f..._rtrg labels)", True),
    "mission": ("Mission lines",
                "Reactions tied to a specific mission, sometimes with hints (s..._rtrg labels)", True),
    "story": ("Story radio",
              "Briefings and mission progress. Keep at 100%: muting can stall a mission (mprg/mirg/mapr)", False),
    "gameover": ("Game over radio",
                 "The line on the Game Over screen (gmov)", False),
}

DEFAULT_CONFIG = {
    "game_dir": "",
    "cooldown_sec": 45,
    "chance": {"common": 30, "mission": 100, "story": 100, "gameover": 100},
    "mute_labels": [],
    "allow_labels": [],
    # mission skip: hold V+R+E for skip_hold_sec seconds and the mission counts as cleared
    "skip_mission": True,
    "skip_hold_sec": 3,
}

SKIP_TEMPLATE = r"""
do
  local M=%(mod)s
  local HOLD=%(hold)s
  _G.RadioTunerSkipState=_G.RadioTunerSkipState or {}
  local S=_G.RadioTunerSkipState
  local function now()
    if Time and Time.GetRawElapsedTimeSinceStartUp then return Time.GetRawElapsedTimeSinceStartUp() end
    return os.clock()
  end
  local function say(text)
    pcall(function() TppUiCommand.AnnounceLogView(text) end)
  end
  local function mask(name,bitIndex)
    if PlayerPad and type(PlayerPad[name])=="number" then return PlayerPad[name] end
    return 2^bitIndex
  end
  local function inGame()
    if mvars.mis_missionStateIsNotInGame then return false end
    if mvars.mis_isReserveMissionClear or svars.mis_isDefiniteMissionClear or svars.mis_isDefiniteGameOver then
      return false
    end
    return true
  end
  local function currentQuest()
    if type(TppQuest)~="table" or type(TppQuest.GetCurrentQuestName)~="function" then return nil end
    local q=TppQuest.GetCurrentQuestName()
    if type(q)~="string" or q=="" or q==S.questDone then return nil end
    return q
  end
  -- what can be skipped now: "mission" (story 10xxx/11xxx), "quest" (side op in free roam) or nil
  local function canSkip()
    local code=vars.missionCode
    if type(code)~="number" or not inGame() then return nil end
    if code>=10000 and code<12000 then return "mission" end
    if code>=30000 and code<40000 and currentQuest() then return "quest" end
    return nil
  end
  local function skipMission()
    S.skipAt=now()
    local clear=TppDefine.MISSION_CLEAR_TYPE
    local free=TppDefine.SYS_MISSION_ID
    if TppLocation.IsAfghan() then
      TppMission.ReserveMissionClear{missionClearType=clear.ON_FOOT,nextMissionId=free.AFGH_FREE}
    elseif TppLocation.IsMiddleAfrica() then
      TppMission.ReserveMissionClear{missionClearType=clear.ON_FOOT,nextMissionId=free.MAFR_FREE}
    else
      TppMission.ReserveMissionClearOnRideOnHelicopter()
    end
  end
  local function skipQuest()
    local q=currentQuest()
    if not q then return end
    S.questDone=q
    TppQuest.ClearWithSave(TppDefine.QUEST_CLEAR_TYPE.CLEAR,q)
  end
  -- missions the game requires for episode 43 (TppStory.CanOpenS10240): code -> episode number
  local REQ43={{10010,0},{10020,1},{10030,2},{10036,3},{10043,4},{10033,5},{10040,6},{10041,7},{10044,8},
    {10054,9},{10052,10},{10050,11},{10070,12},{10080,13},{10086,14},{10082,15},{10090,16},{10091,17},
    {10100,18},{10195,19},{10110,20},{10121,21},{10115,22},{10120,23},{10085,24},{10200,25},{10211,26},
    {10081,27},{10130,28},{10140,29},{10150,30},{10151,31},{10045,32},{10093,35},{10156,38},{10171,41}}
  local function storyHelp()
    local missing={}
    for _,r in ipairs(REQ43) do
      if not TppStory.IsMissionCleard(r[1]) then missing[#missing+1]=(r[2]==0 and "prologue" or tostring(r[2])) end
    end
    if TppStory.IsMissionCleard(10240) then
      say("Mission 43 already cleared. Story seq "..tostring(TppStory.GetCurrentStorySequence()))
      return
    end
    if #missing>0 then
      say("For 43 not cleared: "..table.concat(missing,", "))
      return
    end
    local enum=TppDefine.MISSION_ENUM["10240"]
    local permitted=enum and gvars.str_missionOpenPermission[enum]
    if permitted then
      if TppStory.IsMissionOpen(10240) then
        say("Mission 43 is open: pick it in the mission list")
      else
        TppStory.MissionOpen(10240)
        pcall(function() TppUI.ShowAnnounceLog"missionListUpdate" end)
        say("Mission 43 opened: pick it in the mission list")
      end
      return
    end
    local mb=TppMotherBaseManagement.CanOpenS10240()
    local q=TppQuest.IsNowOccurringElapsed()
    local mis=TppStory.IsNowOccurringElapsedMission(TppDefine.ELAPSED_MISSION_EVENT.STORY_SEQUENCE)
    say("43 locked. MotherBase ok="..tostring(mb).." 3 sideops/1 mission done="..tostring(q or mis)..
      " (sideops left "..tostring(TppQuest.GetElapsedCount and TppQuest.GetElapsedCount() or "?")..")")
    if mb and (q or mis) then
      pcall(function() TppStory.UpdateStorySequence{updateTiming="OnSideOpsClear"} end)
      say("Story update requested: open the mission list / fly to ACC")
    end
  end
  local function banner()
    if S.announced then return end
    local t=now()
    if not S.firstSeen then S.firstSeen=t return end
    if t-S.firstSeen<8 then return end
    S.announced=true
    say("Radio Tuner: hold V+R+E 3 sec = skip mission / side op")
  end
  -- some missions wait for their own cutscene after the clear and never end by themselves, so end them here
  local function watchdog()
    if not S.skipAt then return end
    if mvars.mis_missionGameEndDelayTime~=nil or not svars.mis_isDefiniteMissionClear then
      if mvars.mis_missionGameEndDelayTime~=nil then S.skipAt=nil end
      return
    end
    if now()-S.skipAt<6 then return end
    S.skipAt=nil
    TppMission.MissionGameEnd{loadStartOnResult=false}
  end
  -- story missions, free roam and the helicopter only: never active on FOB or anywhere else
  local function supported(code)
    return type(code)=="number" and ((code>=10000 and code<12000) or (code>=30000 and code<50000))
  end
  local function check()
    local code=vars.missionCode
    if not supported(code) then
      S.holdStart=nil
      return
    end
    pcall(banner)
    pcall(watchdog)
    local m=bit.bor(mask("ZOOM_CHANGE",7),mask("RELOAD",6),mask("ACTION",5))
    if bit.band(PlayerVars.scannedButtonsDirect,m)~=m then
      S.holdStart=nil
      S.helpDone=nil
      S.waitRelease=nil
      return
    end
    if S.waitRelease then return end  -- keys still held after a skip
    local kind=canSkip()
    if not kind then
      if code<30000 or not inGame() then
        S.holdStart=nil
        return
      end
      local t=now()
      if not S.holdStart then
        S.holdStart=t
        say("Nothing to skip. Keep holding: story check")
      elseif t-S.holdStart>=HOLD and not S.helpDone then
        S.helpDone=true
        local ok,err=pcall(storyHelp)
        if not ok then say("Story check error: "..tostring(err)) end
      end
      return
    end
    S.helpDone=nil
    local t=now()
    if not S.holdStart then
      S.holdStart=t
      say("Skip "..(kind=="quest" and "side op" or "mission")..": keep holding V+R+E")
    elseif t-S.holdStart>=HOLD then
      S.holdStart=nil
      S.waitRelease=true
      if kind=="quest" then
        say("Side op skipped")
        skipQuest()
      else
        say("Mission skipped")
        skipMission()
      end
    end
  end
  local function wrapPlayerUpdate()
    if type(TppPlayer)~="table" or type(TppPlayer.Update)~="function" or TppPlayer.RadioTunerSkip then return end
    local orig=TppPlayer.Update
    TppPlayer.Update=function(...)
      pcall(check)
      return orig(...)
    end
    TppPlayer.RadioTunerSkip=true
  end
  for _,name in ipairs({"Init","OnReload"}) do
    local orig=M[name]
    if type(orig)=="function" then
      M[name]=function(...)
        S.firstSeen=nil
        S.announced=false
        S.questDone=nil
        S.skipAt=nil
        pcall(wrapPlayerUpdate)
        return orig(...)
      end
    end
  end
end
"""

LABEL_RE = re.compile(r"^[A-Za-z0-9_]+$")

LUA_TEMPLATE = r"""
%(begin)s
do
  local M=%(mod)s
  local chance={%(chance)s}
  local chatter={%(chatter)s}
  local cooldown=%(cooldown)s
  local mute={%(mute)s}
  local allow={%(allow)s}
  local lastChatter=-1e9
  local function now()
    if Time and Time.GetRawElapsedTimeSinceStartUp then
      return Time.GetRawElapsedTimeSinceStartUp()
    end
    return os.clock()
  end
  local function category(label)
    local kind=string.match(label,"^%%a%%d+_(%%a%%a%%a%%a)")
    if kind=="gmov" then return "gameover" end
    if kind=="mprg" or kind=="mirg" or kind=="mapr" then return "story" end
    if kind=="rtrg" then
      if string.sub(label,1,1)=="f" then return "common" end
      return "mission"
    end
    return nil
  end
  local function isAllowed(radioGroups)
    local label=radioGroups
    if type(label)=="table" then label=label[1] end
    if type(label)~="string" then return true end
    if allow[label] then return true end
    if mute[label] then return false end
    local cat=category(label)
    if cat==nil then return true end
    local c=chance[cat] or 100
    if c<=0 then return false end
    local t
    if chatter[cat] and cooldown>0 then
      t=now()
      if t-lastChatter<cooldown then return false end
    end
    if c<100 and math.random(100)>c then return false end
    if chatter[cat] then lastChatter=t or now() end
    return true
  end
  local origPlayCommon=M.PlayCommon
  M.PlayCommon=function(radioGroups,...)
    local ok,res=pcall(isAllowed,radioGroups)
    if ok and not res then return end
    return origPlayCommon(radioGroups,...)
  end
end
%(skip)s%(end)s
"""


class PatchError(Exception):
    pass


def is_tpp_radio(data):
    return all(s in data for s in SIGNATURES)


def strip_patch(data):
    """Removes a previously inserted filter, if any."""
    b = data.find(MARK_BEGIN)
    if b == -1:
        return data
    e = data.find(MARK_END, b)
    if e == -1:
        raise PatchError("damaged filter block in TppRadio.lua")
    stop = e + len(MARK_END)
    if data[stop:stop + 1] == b"\n":
        stop += 1
    return data[:b] + data[stop:]


def _lua_set(labels):
    out = []
    for lbl in labels:
        lbl = lbl.strip()
        if not lbl:
            continue
        if not LABEL_RE.match(lbl):
            raise PatchError("invalid radio label: %r" % lbl)
        out.append('["%s"]=true' % lbl)
    return ",".join(out)


def build_filter(module_name, cfg):
    chance_parts = []
    for cat in CATEGORIES:
        v = int(cfg["chance"].get(cat, 100))
        chance_parts.append("%s=%d" % (cat, max(0, min(100, v))))
    chatter = ",".join("%s=true" % c for c, (_, _, ch) in CATEGORIES.items() if ch)
    skip = ""
    if cfg.get("skip_mission"):
        hold = max(1.0, float(cfg.get("skip_hold_sec", 3)))
        skip = (SKIP_TEMPLATE % {"mod": module_name, "hold": "%g" % hold}).lstrip("\n")
    return LUA_TEMPLATE % {
        "skip": skip,
        "begin": MARK_BEGIN.decode(),
        "end": MARK_END.decode(),
        "mod": module_name,
        "chance": ",".join(chance_parts),
        "chatter": chatter,
        "cooldown": "%g" % max(0.0, float(cfg.get("cooldown_sec", 0))),
        "mute": _lua_set(cfg.get("mute_labels", [])),
        "allow": _lua_set(cfg.get("allow_labels", [])),
    }


_RETURN_RE = re.compile(rb"\breturn[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t;]*\s*\Z")


def apply_patch(original, cfg):
    """original: clean TppRadio.lua (bytes). Returns the patched one."""
    src = strip_patch(original)
    m = _RETURN_RE.search(src)
    if not m:
        raise PatchError("could not find 'return <module>' at the end of TppRadio.lua")
    mod = m.group(1).decode()
    code = build_filter(mod, cfg).encode()
    return src[:m.start()] + code.lstrip(b"\n") + src[m.start():]
