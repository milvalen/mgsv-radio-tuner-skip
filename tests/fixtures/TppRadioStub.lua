-- Minimal stand-in for the game's TppRadio.lua. Written for these tests, contains no game code.
-- It only has the names the patcher looks for (PlayDirectGroupTable, GetRadioNameAndRadioIDs,
-- COMMON_RADIO_LIST) and the functions the patch wraps.
local this={}
this.COMMON_RADIO_LIST={}
function this.GetRadioNameAndRadioIDs(radioGroups)
  if type(radioGroups)=="table" then return radioGroups[1],radioGroups end
  return radioGroups,{radioGroups}
end
function this.Play(radioGroups,info)
  this.PlayCommon(radioGroups)
end
function this.PlayCommon(radioGroups)
  local name,group=this.GetRadioNameAndRadioIDs(radioGroups)
  TppRadioCommand.PlayDirectGroupTable{tableName=name,groupName=group}
end
function this.Init() end
function this.OnReload() end
return this
