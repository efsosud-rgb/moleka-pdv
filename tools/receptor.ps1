& {
# MOLEKA PDV - RECEPTOR: espera você clicar em "Copiar" no script grande do chat, confere a sintaxe e executa.
# Cole UMA vez no PowerShell como administrador e pressione Enter.
$pasta = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moleka-Diagnostico'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
$limite = 300
Set-Clipboard -Value ' ' -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'AGORA: volte ao chat e clique em "Copiar" no bloco grande do comando. Não cole nada aqui.' -ForegroundColor Yellow
$texto = $null
for($s = 0; $s -lt $limite; $s++){
  Write-Progress -Activity 'Moleka PDV - aguardando o script' -Status "Clique em Copiar no bloco grande do chat ($($limite - $s) s restantes)" -PercentComplete ([int](100 * $s / $limite))
  $c = Get-Clipboard -Raw -ErrorAction SilentlyContinue
  if($c -and $c.Length -gt 3000 -and $c.TrimStart().StartsWith('& {') -and $c.Contains('# MOLEKA PDV') -and -not $c.Contains('# MOLEKA PDV - RECEPTOR')){ $texto = $c; break }
  Start-Sleep -Seconds 1
}
Write-Progress -Activity 'Moleka PDV - aguardando o script' -Completed
if(-not $texto){ Write-Host 'Não recebi o script em 5 minutos. Nada foi executado. Cole este comando de novo.' -ForegroundColor Red; return }
$arq = Join-Path $pasta ('recebido_' + (Get-Date -Format 'yyyy-MM-dd_HHmmss') + '.ps1')
$texto | Out-File -FilePath $arq -Encoding UTF8
$tokens = $null; $erros = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($texto, [ref]$tokens, [ref]$erros)
if($erros.Count){
  Write-Host "O script chegou com $($erros.Count) erro(s) de sintaxe. NADA foi executado. Cole estas linhas no chat:" -ForegroundColor Red
  $erros | Select-Object -First 5 | ForEach-Object { "linha $($_.Extent.StartLineNumber): $($_.Message)" }
  return
}
Write-Host "Script recebido ($($texto.Length) caracteres), salvo em $arq e conferido pelo PowerShell: 0 erros de sintaxe. Executando..." -ForegroundColor Green
& ([scriptblock]::Create($texto))
}
