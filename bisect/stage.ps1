# Stage a bisect test combination into the dadg_gen_battle_test scene folder.
# Usage:  .\stage.ps1 A|B|C|D|GEN
#   A   = all native battle_terrain_a files (sanity check, expect NO crash)
#   B   = native + generated navmesh.bin      (tests our navmesh)
#   C   = native + generated terrain.bin      (tests our terrain)
#   D   = native + generated scene.xscene     (tests our xscene)
#   GEN = all generated files (restore real state)
param([Parameter(Mandatory)][ValidateSet("A", "B", "C", "D", "GEN")][string]$Test)

$scene = "D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test"
$nat = Join-Path $PSScriptRoot "native"
$gen = Join-Path $PSScriptRoot "generated"

$base = if ($Test -eq "GEN") { $gen } else { $nat }
Copy-Item "$base\*" $scene -Force

switch ($Test) {
    "B" { Copy-Item "$gen\navmesh.bin" $scene -Force }
    "C" { Copy-Item "$gen\terrain.bin" $scene -Force }
    "D" { Copy-Item "$gen\scene.xscene" $scene -Force }
}

Write-Host "Staged test $Test into $scene"
Get-ChildItem $scene -File | ForEach-Object {
    $src = if ((Get-FileHash $_.FullName).Hash -eq (Get-FileHash (Join-Path $gen $_.Name) -ErrorAction SilentlyContinue).Hash) { "generated" } else { "native" }
    "{0,-16} {1,10}  {2}" -f $_.Name, $_.Length, $src
}
