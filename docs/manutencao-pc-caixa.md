# Registro de manutenção — PC do caixa (Moleka Sorvetes)

Tudo o que foi mudado no PC do caixa, com a evidência e o caminho de volta. Atualizar a cada intervenção.

## 10/11/2026 — otimização de desempenho

**Arquivos no PC** (`Área de Trabalho\Moleka-Diagnostico\`): `estado_antes_2026-11-10_1146.json` (configurações originais), `DESFAZER_otimizacao.ps1` (2965 bytes, 5 etapas: volta tudo ao estado original), `CLAUDE.md` (tarefa da sessão local do Claude Code), `verificar_etapas_1a9.ps1` e `verificacao_etapas_1a9_<data>.csv` (verificação).

**Ponto de restauração do Windows:** nº 55, "Antes da otimizacao Moleka PDV", criado em 10/11/2026 11:47:12.

**Verificação** feita pelo Claude Code rodando no próprio PC (como administrador), às ~12:30, só leitura — 20 de 20 itens OK:

| Mudança | Valor aplicado (verificado) | O DESFAZER volta para |
|---|---|---|
| Plano de energia | "Moleka PDV (caixa)" (`6d6f6c65-6b61-5044-5600-000000000001`) | plano Equilibrado (e apaga o plano Moleka) |
| Suspender / hibernar / desligar disco (tomada) | nunca / nunca / nunca | os valores do Equilibrado |
| Desligar tela (tomada) | 15 min | os valores do Equilibrado |
| Economia de energia do USB (tomada / bateria) | desligada / desligada | os valores do Equilibrado |
| Inicialização rápida (`HiberbootEnabled`) | 0 | 1 |
| Windows Search (`WSearch`) | parado e desativado | automático com atraso |
| Edge `StartupBoostEnabled` / `BackgroundModeEnabled` (política) | 0 / 0 | políticas removidas |
| Chrome `BackgroundModeEnabled` (política; Chrome instalado) | 0 | política removida |
| Defender `EnableLowCpuPriority` / `ScanAvgCPULoadFactor` | True / 30 | prioridade normal / 50 |
| Animação de minimizar/maximizar | desligada | padrão do Windows (religada) |
| `TaskbarAnimations` | 0 | 0 (já era 0 antes) |
| `EnableTransparency` | 0 | transparência ligada |
| `VisualFXSetting` | 3 (personalizado) | sem valor (padrão; o diagnóstico inicial mostrou vazio) |

**Incidente:** o script `tools/otimizar-pc.ps1` (versão anterior a `8805c06`) perdeu o próprio relatório por colisão de variáveis (`$S`/`$s`; o PowerShell não diferencia maiúsculas). As mudanças 1 a 9 foram aplicadas; a coleta 10 a 17 não. Corrigido no repositório; a coleta foi refeita pela sessão local do Claude Code.

**Observação:** a tela do PC mostra a marca d'água "Ativar o Windows" — Windows não ativado (a confirmar pela sessão local, sem expor a chave).

**Pendente nesta data:** coleta complementar, perguntas ao responsável (sistema atual, AnyDesk, forma de desligar), ajustes restantes aprovados, teste da impressora Elgin i9 e do leitor de código de barras, `/logout` do Claude Code e saída do claude.ai no navegador do PC.
