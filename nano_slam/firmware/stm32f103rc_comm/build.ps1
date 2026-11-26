param(
  [ValidateSet('CommunicationOnly','DcBench','DcFourWheel','DcFourWheel30','EncoderOnly')][string]$Mode = 'CommunicationOnly',
  [switch]$OneSecond,
  [switch]$FiveSeconds,
  [switch]$PairedDrivers,
  [switch]$EncoderReadback,
  [switch]$AlignEncoderForward,
  [switch]$FortyPercent,
  [switch]$FiftyPercent,
  [switch]$SixtyPercent,
  [switch]$EightyPercent
)
$ErrorActionPreference = 'Stop'
if ($OneSecond -and $FiveSeconds) { throw 'Choose either -OneSecond or -FiveSeconds' }
if (($OneSecond -or $FiveSeconds) -and $Mode -ne 'DcFourWheel30') { throw 'Use extended duration with DcFourWheel30' }
if ($PairedDrivers -and -not $FiveSeconds) { throw 'Use -PairedDrivers with -FiveSeconds' }
if ($EncoderReadback -and -not $PairedDrivers) { throw 'Use -EncoderReadback with -PairedDrivers' }
if ($AlignEncoderForward -and -not $EncoderReadback) { throw 'Use -AlignEncoderForward with -EncoderReadback' }
$extendedDutyOptions = @($FortyPercent, $FiftyPercent, $SixtyPercent, $EightyPercent).Where({ $_ })
if ($extendedDutyOptions.Count -gt 1) { throw 'Choose one PWM duty option' }
if ($extendedDutyOptions.Count -and -not $AlignEncoderForward) { throw 'Use the higher duty with -AlignEncoderForward' }
$maxPwmDuty = if ($EightyPercent) { 800 } elseif ($SixtyPercent) { 600 } elseif ($FiftyPercent) { 500 } elseif ($FortyPercent) { 400 } elseif ($Mode -eq 'DcFourWheel30') { 300 } else { 200 }
$dutyPercent = [int]($maxPwmDuty / 10)
$maxPwmDuration = if ($FiveSeconds) { 5000 } elseif ($OneSecond) { 1000 } else { 400 }
$packageRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$workspaceRoot = (Resolve-Path (Join-Path $packageRoot '..')).Path
$fourWheel = $Mode -in @('DcFourWheel','DcFourWheel30')
$imageStem = if ($Mode -eq 'DcFourWheel30') { "stm32f103rc_dc_four_$dutyPercent" } elseif ($fourWheel) { 'stm32f103rc_dc_four' } elseif ($Mode -eq 'DcBench') { 'stm32f103rc_dc_bench' } elseif ($Mode -eq 'EncoderOnly') { 'stm32f103rc_encoder' } else { 'stm32f103rc_comm' }
if ($OneSecond) { $imageStem += '_1s' }
if ($FiveSeconds) { $imageStem += '_5s' }
if ($PairedDrivers) { $imageStem += '_paired' }
if ($EncoderReadback) { $imageStem += '_enc' }
if ($AlignEncoderForward) { $imageStem += '_forward' }
$buildRoot = Join-Path $workspaceRoot ('artifacts\'+$imageStem)
$toolRoot = 'D:\Keil_v5\ARM\ARMCLANG\bin'
$deviceIncludes = 'D:\Keil_v5\ARM\PACK\Keil\STM32F1xx_DFP\2.4.1\Device\Include'
$coreIncludes = 'D:\Keil_v5\ARM\PACK\ARM\CMSIS\5.8.0\CMSIS\Core\Include'
$protocolRoot = Join-Path $packageRoot 'firmware\j1_protocol_demo'
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$compiler = Join-Path $toolRoot 'armclang.exe'
$common = @('--target=arm-arm-none-eabi','-mcpu=cortex-m3','-mthumb','-Os','-g','-DSTM32F10X_HD','-D__MICROLIB','-I', $deviceIncludes,'-I',$coreIncludes,'-I',$protocolRoot)
if ($Mode -eq 'DcBench') { $common += '-DBOARD_DC_BENCH' }
if ($fourWheel) { $common += @('-DBOARD_DC_BENCH','-DBOARD_DC_FOUR') }
if ($Mode -eq 'DcFourWheel30') { $common += "-DJ1_PWM_FOUR_$dutyPercent" }
if ($OneSecond) { $common += '-DJ1_PWM_FOUR_1S' }
if ($FiveSeconds) { $common += '-DJ1_PWM_FOUR_5S' }
if ($PairedDrivers) { $common += '-DJ1_PWM_FOUR_PAIRED' }
if ($EncoderReadback) { $common += '-DBOARD_ENCODER_QUERY' }
if ($AlignEncoderForward) { $common += '-DBOARD_ENCODER_FORWARD' }
if ($Mode -eq 'EncoderOnly') { $common += @('-DBOARD_DC_FOUR','-DBOARD_ENCODER_ONLY') }
& $compiler @common -x assembler-with-cpp -c (Join-Path $PSScriptRoot 'startup.S') -o (Join-Path $buildRoot 'startup.o')
if ($LASTEXITCODE -ne 0) { throw 'Startup assembly failed' }
foreach ($source in @((Join-Path $PSScriptRoot 'main.cpp'),(Join-Path $protocolRoot 'j1_protocol.cpp'))) {
  $outputObject = Join-Path $buildRoot (([IO.Path]::GetFileNameWithoutExtension($source))+'.o')
  & $compiler @common -std=c++11 -fno-exceptions -fno-rtti -c $source -o $outputObject
  if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $source" }
}
$elf = Join-Path $buildRoot ($imageStem+'.elf')
$objects = @((Join-Path $buildRoot 'startup.o'),(Join-Path $buildRoot 'main.o'),(Join-Path $buildRoot 'j1_protocol.o'))
& (Join-Path $toolRoot 'armlink.exe') --cpu=Cortex-M3 --library_type=microlib --entry=Reset_Handler --scatter (Join-Path $PSScriptRoot 'memory.sct') --map --list (Join-Path $buildRoot 'firmware.map') -o $elf @objects
if ($LASTEXITCODE -ne 0) { throw 'Link failed' }
& (Join-Path $toolRoot 'fromelf.exe') --bin --output (Join-Path $buildRoot ($imageStem+'.bin')) $elf
if ($LASTEXITCODE -ne 0) { throw 'Binary export failed' }
& (Join-Path $toolRoot 'fromelf.exe') --i32combined --output (Join-Path $buildRoot ($imageStem+'.hex')) $elf
if ($LASTEXITCODE -ne 0) { throw 'HEX export failed' }
$binary = Join-Path $buildRoot ($imageStem+'.bin')
$metadata = @{
  mcu='STM32F103RCT6'; image=$(if ($FiveSeconds) {"dc_four_wheel_${dutyPercent}_5s"} elseif ($OneSecond) {'dc_four_wheel_30_1s'} elseif ($Mode -eq 'DcFourWheel30') {'dc_four_wheel_30'} elseif ($fourWheel) {'dc_four_wheel'} elseif ($Mode -eq 'DcBench') {'dc_bench'} elseif ($Mode -eq 'EncoderOnly') {'encoder_only'} else {'communication_only'});
  motor_interface_bound=($fourWheel -or $Mode -eq 'DcBench'); flash_base='0x08000000';
  image_bytes=(Get-Item -LiteralPath $binary).Length;
  sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLower();
  flashed=$false; max_pwm_permille=$maxPwmDuty; max_pwm_duration_ms=$maxPwmDuration; default_state='DISARMED'
  pwm_pair_supported=($Mode -eq 'DcBench')
  pwm_four_supported=$fourWheel; independent_channels=$(if($fourWheel){4}else{2});
  encoder_channels=$(if ($Mode -eq 'EncoderOnly' -or $EncoderReadback) {4} else {0});
  board_profile=$(if($fourWheel -or $Mode -eq 'EncoderOnly'){'original_board_four_pwm'}else{'two_channel_ros_board'})
}
if ($PairedDrivers) {
  $metadata.image += '_paired'
  $metadata.paired_drivers = $true
}
if ($EncoderReadback) {
  $metadata.image += '_enc'
  $metadata.encoder_query = $true
}
if ($AlignEncoderForward) {
  $metadata.image += '_forward'
  $metadata.encoder_forward_signs = @(1,-1,-1,1)
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildRoot 'build_metadata.json') -Encoding utf8
Get-Item -LiteralPath $binary | Select-Object FullName,Length | Out-String | Write-Output
Write-Output "BUILD_ONLY: profile=$Mode, boot state DISARMED. Nothing flashed."
