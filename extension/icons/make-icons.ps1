<#
  The NexusPLM icon pack.

  Twenty-one icons come from the Word add-in's 80px originals. Eight more are drawn here, in the
  same language — rounded grey strokes, one stroke weight, a single teal accent for the action —
  because reusing an existing icon for a different command made a menu lie: Revise wore Reload's
  circle, Release wore Workflow's boxes, and three commands shared one picture.

  The grey and the teal are sampled from the existing art rather than typed in, so the drawn
  icons match it exactly. Everything is then resized to the three sizes LibreOffice uses.

    powershell -File extension\icons\make-icons.ps1
#>
param(
  [string]$WordIcons = "C:\Github\Nexus.PLM.Office.Addins\Nexus.PLM.Office.WordAddin\Icons",
  [string]$Out = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$src = Join-Path $Out "src"
New-Item -ItemType Directory -Force $src | Out-Null

# ── 1. the palette, sampled from CheckIn (grey document, teal arrow) ─────────
$sample = [System.Drawing.Bitmap]::FromFile((Join-Path $WordIcons "CheckIn-80x80.png"))
$counts = @{}
for ($y = 0; $y -lt $sample.Height; $y++) {
  for ($x = 0; $x -lt $sample.Width; $x++) {
    $c = $sample.GetPixel($x, $y)
    if ($c.A -lt 250) { continue }
    $k = "{0},{1},{2}" -f $c.R, $c.G, $c.B
    $counts[$k] = 1 + $counts[$k]
  }
}
$sample.Dispose()
$top = $counts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 6
# The most common opaque colour is the grey stroke; the most common one that is clearly
# blue-green is the teal accent.
$greyKey = ($top | Select-Object -First 1).Key
$tealKey = ($top | Where-Object { $p = $_.Key -split ","; [int]$p[2] -gt ([int]$p[0] + 40) } | Select-Object -First 1).Key
if (-not $tealKey) { $tealKey = "86,196,196" }
$g0 = $greyKey -split ","; $t0 = $tealKey -split ","
$Grey = [System.Drawing.Color]::FromArgb(255, [int]$g0[0], [int]$g0[1], [int]$g0[2])
$Teal = [System.Drawing.Color]::FromArgb(255, [int]$t0[0], [int]$t0[1], [int]$t0[2])
$Light = [System.Drawing.Color]::FromArgb(255, 242, 242, 242)
Write-Output ("palette: grey {0} teal {1}" -f $greyKey, $tealKey)

# ── 2. drawing helpers ───────────────────────────────────────────────────────
$Stroke = 7.0   # measured against the originals: their strokes are 7px at 80px

function New-Pen([System.Drawing.Color]$Color, [double]$Width = $Stroke) {
  $p = New-Object System.Drawing.Pen $Color, $Width
  $p.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
  $p.EndCap   = [System.Drawing.Drawing2D.LineCap]::Round
  $p.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
  return $p
}

function Rounded([double]$x, [double]$y, [double]$w, [double]$h, [double]$r) {
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $d = $r * 2
  $path.AddArc($x, $y, $d, $d, 180, 90)
  $path.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
  $path.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
  $path.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
  $path.CloseFigure()
  return $path
}

# A document outline as the pack draws it: a rounded rectangle, portrait.
function Draw-Doc($g, [System.Drawing.Color]$Color, [double]$x = 20, [double]$y = 6, [double]$w = 40, [double]$h = 68) {
  $pen = New-Pen $Color
  $g.DrawPath($pen, (Rounded $x $y $w $h 6))
  $pen.Dispose()
}

# A person as SignIn draws one: a head and a shoulder line.
function Draw-Person($g, [System.Drawing.Color]$Head, [System.Drawing.Color]$Body, [double]$cx = 34, [double]$cy = 24) {
  $pen = New-Pen $Head
  $g.DrawEllipse($pen, ($cx - 11), ($cy - 11), 22, 22)
  $pen.Dispose()
  $pen = New-Pen $Body
  # shoulders: an arc open at the bottom
  $g.DrawArc($pen, ($cx - 24), ($cy + 16), 48, 44, 180, 180)
  $pen.Dispose()
}

# A filled teal badge with a light glyph, the idiom MyWorkList uses for "add".
function Draw-Badge($g, [double]$cx, [double]$cy, [double]$r, [string]$Glyph) {
  $b = New-Object System.Drawing.SolidBrush $Teal
  $g.FillEllipse($b, ($cx - $r), ($cy - $r), ($r * 2), ($r * 2))
  $b.Dispose()
  $pen = New-Pen $Light 5.0
  switch ($Glyph) {
    "plus"  { $g.DrawLine($pen, ($cx - $r * 0.5), $cy, ($cx + $r * 0.5), $cy); $g.DrawLine($pen, $cx, ($cy - $r * 0.5), $cx, ($cy + $r * 0.5)) }
    "check" { $g.DrawLines($pen, [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF ($cx - $r * 0.55), $cy),
                (New-Object System.Drawing.PointF ($cx - $r * 0.15), ($cy + $r * 0.4)),
                (New-Object System.Drawing.PointF ($cx + $r * 0.6), ($cy - $r * 0.45)))) }
    "up"    { $g.DrawLine($pen, $cx, ($cy + $r * 0.5), $cx, ($cy - $r * 0.5))
              $g.DrawLine($pen, ($cx - $r * 0.45), ($cy - $r * 0.05), $cx, ($cy - $r * 0.5))
              $g.DrawLine($pen, ($cx + $r * 0.45), ($cy - $r * 0.05), $cx, ($cy - $r * 0.5)) }
    "cycle" { $g.DrawArc($pen, ($cx - $r * 0.55), ($cy - $r * 0.55), ($r * 1.1), ($r * 1.1), 300, 270)
              # arrowhead at the arc's end (top right)
              $ax = $cx + $r * 0.55 * [Math]::Cos(-60 * [Math]::PI / 180); $ay = $cy + $r * 0.55 * [Math]::Sin(-60 * [Math]::PI / 180)
              $g.DrawLine($pen, $ax, $ay, ($ax - $r * 0.45), $ay); $g.DrawLine($pen, $ax, $ay, $ax, ($ay + $r * 0.45)) }
  }
  $pen.Dispose()
}

function New-Icon([string]$Name, [scriptblock]$Draw) {
  $bmp = New-Object System.Drawing.Bitmap 80, 80
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.Clear([System.Drawing.Color]::Transparent)
  & $Draw $g
  $g.Dispose()
  $bmp.Save((Join-Path $src "$Name-80x80.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Write-Output "  drew $Name"
}

# ── 3. the eight new icons ───────────────────────────────────────────────────

# Release: a document, sealed — a teal badge with a check.
New-Icon "Release" {
  param($g)
  Draw-Doc $g $Grey
  Draw-Badge $g 58 58 15 "check"
}

# Revise: the next revision — a second document stepping forward from the first, with the pack's
# badge carrying an "up": the revision letter goes up one. (A teal edge on the front document was
# tried first and did not read; at 26px it was two grey documents.)
New-Icon "Revise" {
  param($g)
  Draw-Doc $g $Grey 10 4 40 60
  Draw-Doc $g $Grey 26 16 40 60
  Draw-Badge $g 62 62 15 "up"
}

# Change Ownership: a person handed on — the person, and a two-way arrow beside them.
New-Icon "ChangeOwner" {
  param($g)
  Draw-Person $g $Grey $Grey 28 24
  $pen = New-Pen $Teal
  $g.DrawLine($pen, 50, 46, 74, 46); $g.DrawLine($pen, 66, 38, 74, 46); $g.DrawLine($pen, 66, 54, 74, 46)
  $g.DrawLine($pen, 74, 64, 50, 64); $g.DrawLine($pen, 58, 56, 50, 64); $g.DrawLine($pen, 58, 72, 50, 64)
  $pen.Dispose()
}

# Refresh Values: the attribute list, re-read — Properties' rows with a cycle badge.
New-Icon "RefreshValues" {
  param($g)
  $pen = New-Pen $Grey
  foreach ($y in 16, 40, 64) { $g.DrawLine($pen, 10, $y, 50, $y) }
  $pen.Dispose()
  Draw-Badge $g 60 58 16 "cycle"
}

# Connection Status: reach — signal arcs from a teal point.
New-Icon "ConnectionStatus" {
  param($g)
  $pen = New-Pen $Grey
  foreach ($r in 22, 40, 58) { $g.DrawArc($pen, (14 - $r), (66 - $r), ($r * 2), ($r * 2), 270, 90) }
  $pen.Dispose()
  $b = New-Object System.Drawing.SolidBrush $Teal
  $g.FillEllipse($b, 6, 58, 16, 16); $b.Dispose()
}

# Account: the person alone, shoulders in the accent — Sign In and Sign Out add their arrows.
New-Icon "Account" {
  param($g)
  Draw-Person $g $Grey $Teal 40 26
}

# Values: a form — a label and a value box per row, the value in the accent.
New-Icon "Values" {
  param($g)
  $pen = New-Pen $Grey
  $b = New-Object System.Drawing.SolidBrush $Teal
  foreach ($y in 12, 36, 60) {
    $g.DrawLine($pen, 8, ($y + 5), 30, ($y + 5))
    $g.FillPath($b, (Rounded 40 $y 34 11 4))
  }
  $pen.Dispose(); $b.Dispose()
}

# New Workflow: the workflow's boxes, with the pack's "add" badge.
New-Icon "NewWorkflow" {
  param($g)
  $base = [System.Drawing.Image]::FromFile((Join-Path $WordIcons "Workflow-80x80.png"))
  $g.DrawImage($base, 0, 0, 80, 80); $base.Dispose()
  Draw-Badge $g 62 18 14 "plus"
}

# ── 4. the pack: the twenty-one originals plus the eight above, at every size ─
Get-ChildItem $WordIcons -Filter "*-80x80.png" | ForEach-Object {
  Copy-Item $_.FullName (Join-Path $src $_.Name) -Force
}
Get-ChildItem $Out -Filter "*_*.png" | Remove-Item -Force
$sizes = 16, 26, 50
$n = 0
foreach ($f in Get-ChildItem $src -Filter "*-80x80.png") {
  $name = $f.BaseName -replace "-80x80$", ""
  $img = [System.Drawing.Image]::FromFile($f.FullName)
  foreach ($size in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.DrawImage($img, 0, 0, $size, $size)
    $bmp.Save((Join-Path $Out ("{0}_{1}.png" -f $name, $size)), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
  }
  if ($name -eq "Nexus") {
    $bmp = New-Object System.Drawing.Bitmap 42, 42
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear([System.Drawing.Color]::Transparent); $g.DrawImage($img, 0, 0, 42, 42)
    $bmp.Save((Join-Path $Out "nexus-42.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
  }
  $img.Dispose(); $n++
}
Write-Output "pack: $n icons x $($sizes.Count) sizes"
