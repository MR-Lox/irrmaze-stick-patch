-- Test automatique du patch dans MAME (stick standard branché à la place du trackball).
-- Usage :
--   mame irrmaze -edge joy -rompath <dossier avec le set patché> -video none -sound none
--        -nothrottle -skip_gameinfo -seconds_to_run 60 -autoboot_script test_mame.lua
-- Met un crédit, lance une partie, valide les écrans, puis actionne le stick en jeu
-- et affiche dx/dy ($10A7CE/$10A7D0) et les boutons ($10A7C6/$10A7C8) du jeu.
local scr = manager.machine.screens[":screen"]
local m = manager.machine.devices[":maincpu"].spaces["program"]
local ports = manager.machine.ioport.ports
local J1 = ports[":edge:joy:JOY1"].fields
local J2 = ports[":edge:joy:JOY2"].fields
local ev = {
  {600, 606, ports[":AUDIO_COIN"].fields["Coin 1"]},
  {800, 806, ports[":edge:joy:START"].fields["1 Player Start"]},
  {1000, 1006, J1["P1 A"]}, {1200, 1206, J1["P1 A"]}, {1400, 1406, J1["P1 A"]},
  {1600, 1606, J1["P1 A"]}, {1800, 1806, J1["P1 A"]}, {2000, 2006, J1["P1 A"]},
  {2600, 2660, J1["P1 Right"]},                          -- accélération 1 -> 3 px/frame
  {2700, 2740, J1["P1 Left"]}, {2700, 2740, J1["P1 C"]}, -- mode précision
  {2800, 2840, J1["P1 Up"]}, {2800, 2840, J1["P1 D"]},   -- mode rapide
  {2900, 2940, J2["P2 Down"]},                           -- stick J2
  {3000, 3003, J1["P1 A"]}, {3050, 3053, J1["P1 B"]},    -- boutons
}
local last = -1
emu.register_periodic(function()
  local f = scr:frame_number()
  if f == last then return end
  last = f
  for _, e in ipairs(ev) do
    if f == e[1] then e[3]:set_value(1) elseif f == e[2] then e[3]:clear_value() end
  end
  if f >= 2595 and f <= 3060 and f % 5 == 0 then
    print(string.format("frame %d  dx=%d dy=%d  bouton1=%d bouton2=%d", f,
      m:read_i16(0x10a7ce), m:read_i16(0x10a7d0), m:read_i16(0x10a7c6), m:read_i16(0x10a7c8)))
  end
  if f == 3070 then manager.machine:exit() end
end)
