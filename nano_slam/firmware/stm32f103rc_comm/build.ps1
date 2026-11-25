param([ValidateSet('CommunicationOnly','DcBench','DcFourWheel','EncoderOnly')][string]$Mode = 'CommunicationOnly')
$ErrorActionPreference = 'Stop'
$packageRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$workspaceRoot = (Resolve-Path (Join-Path $packageRoot '..')).Path
$imageStem = if ($Mode -eq 'DcFourWheel') { 'stm32f103rc_dc_four' } elseif ($Mode -eq 'DcBench') { 'stm32f103rc_dc_bench' } elseif ($Mode -eq 'EncoderOnly') { 'stm32f103rc_encoder' } else { 'stm32f103rc_comm' }
$buildRoot = Join-Path $workspaceRoot ('artifacts\'+$imageStem)
$toolRoot = 'D:\Keil_v5\ARM\ARMCLANG\bin'
$deviceIncludes = 'D:\Keil_v5\ARM\PACK\Keil\STM32F1xx_DFP\2.4.1\Device\Include'
$coreIncludes = 'D:\Keil_v5\ARM\PACK\ARM\CMSIS\5.8.0\CMSIS\Core\Include'
$protocolRoot = Join-Path $packageRoot 'firmware\j1_protocol_demo'
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
$compiler = Join-Path $toolRoot 'armclang.exe'
$common = @('--target=arm-arm-none-eabi','-mcpu=cortex-m3','-mthumb','-Os','-g','-DSTM32F10X_HD','-D__MICROLIB','-I', $deviceIncludes,'-I',$coreIncludes,'-I',$protocolRoot)
if ($Mode -eq 'DcBench') { $common += '-DBOARD_DC_BENCH' }
if ($Mode -eq 'DcFourWheel') { $common += @('-DBOARD_DC_BENCH','-DBOARD_DC_FOUR') }
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
  mcu='STM32F103RCT6'; image=$(if ($Mode -eq 'DcFourWheel') {'dc_four_wheel'} elseif ($Mode -eq 'DcBench') {'dc_bench'} elseif ($Mode -eq 'EncoderOnly') {'encoder_only'} else {'communication_only'});
  motor_interface_bound=($Mode -in @('DcBench','DcFourWheel')); flash_base='0x08000000';
  image_bytes=(Get-Item -LiteralPath $binary).Length;
  sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLower();
  flashed=$false; max_pwm_permille=200; max_pwm_duration_ms=400; default_state='DISARMED'
  pwm_pair_supported=($Mode -eq 'DcBench')
  pwm_four_supported=($Mode -eq 'DcFourWheel'); independent_channels=$(if($Mode -eq 'DcFourWheel'){4}else{2});
  encoder_channels=$(if ($Mode -eq 'EncoderOnly') {4} else {0});
  board_profile=$(if($Mode -in @('DcFourWheel','EncoderOnly')){'original_board_four_pwm'}else{'two_channel_ros_board'})
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildRoot 'build_metadata.json') -Encoding utf8
Get-Item -LiteralPath $binary | Select-Object FullName,Length | Out-String | Write-Output
Write-Output "BUILD_ONLY: profile=$Mode, boot state DISARMED. Nothing flashed."
