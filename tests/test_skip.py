"""Simulates the in-game mission skip, side op skip, watchdog and story check under LuaJIT.

The game's API is replaced with small stubs, so this checks our logic, not the game itself.
Run: python3 tests/test_skip.py
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import copy  # noqa: E402

import luapatch  # noqa: E402

PRELUDE = r"""
local t=0
Time={GetRawElapsedTimeSinceStartUp=function() return t end}
msgs={}
TppUiCommand={AnnounceLogView=function(s) msgs[#msgs+1]=s end}
PlayerVars={scannedButtonsDirect=0}
vars={missionCode=10086}; mvars={}; svars={}
gvars={str_missionOpenPermission={}}
TppDefine={MISSION_CLEAR_TYPE={ON_FOOT=1},SYS_MISSION_ID={AFGH_FREE=30010,MAFR_FREE=30020},
  QUEST_CLEAR_TYPE={CLEAR=1},MISSION_ENUM={["10240"]=40},ELAPSED_MISSION_EVENT={STORY_SEQUENCE=0}}
TppLocation={IsAfghan=function() return true end,IsMiddleAfrica=function() return false end}
cleared=nil; ended=0
TppMission={ReserveMissionClear=function(i) cleared=i; mvars.mis_isReserveMissionClear=true; svars.mis_isDefiniteMissionClear=true end,
  MissionGameEnd=function() ended=ended+1; mvars.mis_missionGameEndDelayTime=0 end}
updates=0
TppPlayer={Update=function() updates=updates+1 end}
quest=nil; quests={}
TppQuest={GetCurrentQuestName=function() return quest end,ClearWithSave=function(_,q) quests[#quests+1]=q end,
  IsNowOccurringElapsed=function() return true end,GetElapsedCount=function() return 0 end}
done={}; opened={}
TppStory={IsMissionCleard=function(c) return done[c] end,IsMissionOpen=function(c) return opened[c] end,
  MissionOpen=function(c) opened[c]=true end,GetCurrentStorySequence=function() return 99 end,
  IsNowOccurringElapsedMission=function() return false end,UpdateStorySequence=function() end}
TppMotherBaseManagement={CanOpenS10240=function() return false end}
TppUI={ShowAnnounceLog=function() end}
M={Init=function() end,OnReload=function() end,PlayCommon=function() end}
dofile(arg[1])
M.Init()
ALL=bit.bor(2^7,2^6,2^5)
function frame(dt) t=t+dt; TppPlayer.Update() end
function press(on) PlayerVars.scannedButtonsDirect=on and ALL or 0 end
function has(text) for _,m in ipairs(msgs) do if m:find(text,1,true) then return true end end return false end
"""

CASES = {
    "mission skip": r"""
frame(0.1); assert(not cleared)
press(true); frame(0.1); frame(1); assert(not cleared,"too early")
press(false); frame(0.1); press(true)
frame(0.1); frame(2.5); assert(not cleared,"release must reset")
frame(0.6); assert(cleared and cleared.nextMissionId==30010,"should clear")
assert(updates==7,"game update runs every frame: "..updates)
M.Init(); assert(TppPlayer.RadioTunerSkip)
""",
    "no skip in free roam without a side op": r"""
vars.missionCode=30010
press(true); frame(5); frame(5); assert(not cleared)
""",
    "nothing happens on FOB": r"""
vars.missionCode=50050; quest="mtbs_q99060"
frame(9); frame(9)
press(true); frame(5); frame(5); assert(not cleared and #quests==0 and not opened[10240])
assert(#msgs==0,"no messages on FOB: "..table.concat(msgs," | "))
""",
    "keys held after a skip do nothing more": r"""
vars.missionCode=30010; quest="quest_q20015"
press(true); frame(0.1); frame(3.1); assert(#quests==1)
msgs={}; frame(4); frame(4)
assert(not has("story check") and not has("not cleared"),table.concat(msgs," | "))
press(false); frame(0.1); press(true); frame(0.1); assert(has("story check"))
""",
    "no story check while a mission is ending": r"""
press(true); frame(0.1); frame(3.1); assert(cleared); press(false); frame(0.1)
msgs={}; press(true); frame(4); frame(4); assert(not has("story check") and not has("not cleared"))
""",
    "side op skip": r"""
vars.missionCode=30010; quest="quest_q20015"
press(true); frame(0.1); frame(1); assert(#quests==0)
frame(2.1); assert(quests[1]=="quest_q20015")
frame(0.1); frame(4); frame(4); assert(#quests==1,"no double clear")
M.Init(); press(false); frame(0.1); press(true)
frame(0.1); frame(3.1); assert(#quests==2,"can skip again after reload")
""",
    "watchdog ends a stuck mission": r"""
vars.missionCode=10140
press(true); frame(0.1); frame(3.1); assert(cleared); press(false)
frame(3); assert(ended==0,"too early")
frame(3.5); assert(ended==1,"must fire")
frame(10); assert(ended==1,"only once")
""",
    "watchdog leaves a normal mission alone": r"""
press(true); frame(0.1); frame(3.1); press(false)
mvars.mis_missionGameEndDelayTime=0
frame(10); assert(ended==0)
""",
    "story check": r"""
vars.missionCode=30050
local function check() msgs={}; press(true); frame(0.1); frame(3.1); frame(0.1); press(false); frame(0.1) end
for _,c in ipairs({10010,10020,10030,10036,10043,10033,10040,10041,10044,10054,10050,10070,10080,10086,10082,
  10090,10091,10195,10110,10121,10115,10120,10085,10200,10211,10081,10130,10140,10150,10151,10045,10093,10156,10171}) do done[c]=true end
check(); assert(has("not cleared: 10, 18"),"episode numbers: "..table.concat(msgs," | "))
done[10052]=true; done[10100]=true
check(); assert(has("43 locked"),table.concat(msgs," | "))
gvars.str_missionOpenPermission[40]=true
check(); assert(has("Mission 43 opened") and opened[10240])
check(); assert(has("Mission 43 is open"))
done[10240]=true
check(); assert(has("already cleared"))
""",
    "game API errors never reach the game loop": r"""
TppMission.ReserveMissionClear=function() error("boom") end
press(true); frame(0.1); frame(3.1); frame(1)
assert(updates==3)
""",
}


def main():
    cfg = copy.deepcopy(luapatch.DEFAULT_CONFIG)
    assert cfg["game_dir"] == "" and cfg["chance"]["story"] == 100, "public defaults must stay safe"
    tmp = tempfile.mkdtemp()
    code = os.path.join(tmp, "patch.lua")
    with open(code, "w", encoding="utf-8") as f:
        f.write(luapatch.build_filter("M", cfg))
    failed = 0
    for name, body in CASES.items():
        path = os.path.join(tmp, "case.lua")
        with open(path, "w", encoding="utf-8") as f:
            f.write(PRELUDE + body)
        r = subprocess.run(["luajit", path, code], capture_output=True, text=True)
        print(("ok    " if r.returncode == 0 else "FAIL  ") + name)
        if r.returncode:
            failed += 1
            print(r.stderr.strip())
    assert not failed, "%d case(s) failed" % failed
    print("ALL OK")


if __name__ == "__main__":
    main()
