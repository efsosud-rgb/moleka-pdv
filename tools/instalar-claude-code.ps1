& {
# MOLEKA PDV - INSTALA O CLAUDE CODE NESTE PC com barra de progresso.
# Usa o instalador oficial da documentação (irm https://claude.ai/install.ps1 | iex), rodando em segundo plano.
$atv = 'Instalando o Claude Code (instalador oficial da Anthropic)'
$job = Start-Job -ScriptBlock {
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  Invoke-RestMethod -Uri 'https://claude.ai/install.ps1' | Invoke-Expression
}
$seg = 0
while($job.State -eq 'Running' -and $seg -lt 900){
  $seg++
  Write-Progress -Activity $atv -Status "baixando e instalando... $seg s (o instalador oficial não mostra andamento; pode levar alguns minutos)" -PercentComplete ([math]::Min(95, [int]($seg / 3)))
  Start-Sleep -Seconds 1
}
Write-Progress -Activity $atv -Completed
if($job.State -eq 'Running'){ Stop-Job $job; Write-Host 'ATENÇÃO: passou de 15 minutos e o instalador não terminou. Me mande esta mensagem.' -ForegroundColor Red }
Receive-Job $job -ErrorAction Continue
"Instalador terminou com estado: $($job.State)"
Remove-Job $job -Force
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$cmd = Get-Command claude -ErrorAction SilentlyContinue
if($cmd){
  Write-Host "OK: Claude Code instalado em $($cmd.Source)" -ForegroundColor Green
  & $cmd.Source --version
} else {
  Write-Host 'ATENÇÃO: o comando claude não foi encontrado. Me mande tudo o que apareceu acima.' -ForegroundColor Red
}
}
