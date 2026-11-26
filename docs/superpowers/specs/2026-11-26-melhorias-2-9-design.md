# Melhorias 2.9–2.11: monitor do PC, consumo das IAs, aparelhos, acesso remoto

## Intenção
O usuário quer acompanhar o PC e o consumo das IAs pelo celular/tablet e fechar o que
faltou do plano antigo. Uso pessoal, simples, estilo iOS, sem dependências novas e sem
comportamentos que façam o antivírus desconfiar.

## Objetivos
1. **Monitor do PC** (2.9): CPU, memória, disco, rede, GPU (quando o Windows informar),
   temperaturas (só se o LibreHardwareMonitor estiver aberto com o servidor web ligado),
   gerenciador de tarefas (lista dos que mais consomem + encerrar com confirmação, só em
   aparelhos com permissão de "controle total").
2. **Consumo das IAs** (2.9): limite de 5 h e semanal (% usado, quanto falta, quando reinicia)
   como no app. Fontes:
   - Claude: via status line do Claude Code (`rate_limits.five_hour/seven_day.used_percentage/resets_at`,
     documentado). O Stream Deck instala, com consentimento no editor, um comando de status line
     que grava esse JSON em `Documentos\StreamDeck\ia\claude.json` e repassa para a status line
     que o usuário já tinha. Só atualiza enquanto o Claude Code está aberto: mostrar "atualizado há X".
     Quem usa só o app precisa abrir o Claude Code de vez em quando (o limite é da conta).
   - Codex: leitura dos registros de sessão (`~/.codex/sessions/**.jsonl`), campo de limites
     (primário/secundário) quando existir; leitura defensiva.
   - Grok: sem fonte conhecida; aparece como "indisponível" até haver uma (não inventar).
   - Reserva (C): quando não houver limites, mostrar tokens usados hoje contados dos registros locais.
3. **Aparelhos** (2.10): cada celular/tablet vira um aparelho com nome; por aparelho:
   layout próprio (páginas visíveis, grade própria) e permissões (páginas permitidas,
   "controle total" para ações sensíveis como encerrar processos/desligar).
4. **Acesso fora de casa** (2.11): guia Tailscale + QR com o endereço Tailscale na tela Conectar.
   **Assinatura de código**: publicação preparada para assinar se houver certificado (segredo no
   GitHub); sem certificado, segue como hoje.

## Não-objetivos / anti-objetivos
- Não guardar senhas/sessões das contas de IA nem usar endpoints não documentados.
- Não instalar drivers/serviços para temperatura.
- Encerrar processo nunca sem confirmação e nunca de aparelho sem permissão.

## Abordagens consideradas
- IA: (A) status line/registros locais — escolhida; (B) login web — recusada (risco, fragilidade);
  (C) contagem local — reserva.
- Métricas: PDH/ctypes (stdlib) — escolhida; psutil/WMI via PowerShell — recusadas (dependência,
  antivírus, lentidão).

## Decisões do construtor (deixadas em aberto)
Formato exato dos blocos/página do monitor, fórmulas de "quanto falta", detalhes de UI.
