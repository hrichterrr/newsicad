# Plano de otimização de contexto (Claude Code)

Uma etapa por vez, da que dá mais retorno para a que dá menos. Medir antes de passar para a próxima.

## Etapa 0 — Medir o "antes" (1 sessão normal)
- [ ] Trabalhar uma sessão típica sem mudar nada
- [ ] Rodar `/context` e `/cost` no fim e anotar abaixo

| Métrica | Antes | Depois |
|---|---|---|
| Total de contexto usado | | |
| Arquivos de memória (CLAUDE.md etc.) | | |
| MCPs | | |
| Ferramentas | | |
| Custo da sessão (`/cost`) | | |

## Etapa 1 — RTK (maior ganho, ~30 min)
Filtra e comprime a saída dos comandos de terminal antes de chegar ao contexto.

- [ ] Instalar a partir do repositório oficial (**não** usar `cargo install rtk`, que instala o Rust Type Kit):
  ```
  cargo install --git https://github.com/rtk-ai/rtk
  rtk gain
  ```
  Se `rtk gain` não existir, é o pacote errado.
- [ ] Ativar no Claude Code e reiniciar:
  ```
  rtk init -g
  rtk init --show
  ```
- [ ] Windows: preferir instalar no WSL (hooks funcionam nativamente); senão, `rtk.exe` numa pasta do PATH e usar pelo PowerShell/Terminal.

Limitação: vale só para comandos Bash; Read, Grep e Glob do Claude Code não passam pelo hook.

## Etapa 2 — Enxugar o CLAUDE.md de cada projeto (~1 h)
Regra: menos de 200 linhas, só o essencial; documentação longa vai para arquivos separados, lidos sob demanda.

- [x] newsicad — `CLAUDE.md` criado (~30 linhas, aponta para seções do README)
- [ ] Demais projetos: ________

## Etapa 3 — Hábitos de sessão (grátis, efeito imediato)
- [ ] `/clear` ao trocar de tarefa
- [ ] `/compact` nos pontos de parada, pedindo para preservar as decisões importantes no resumo
- [ ] Sonnet/Haiku para tarefa simples; Opus só para raciocínio pesado (vale também para subagentes)
- [ ] Pedidos com escopo fechado ("corrige a função X no arquivo Y" em vez de "revisa o módulo inteiro")

## Etapa 4 — Medir o "depois"
- [ ] Repetir uma sessão parecida com a da Etapa 0
- [ ] Preencher a coluna "Depois" da tabela
- [ ] Rodar `rtk gain` e anotar a economia acumulada: ________

Os percentuais do RTK medem a saída do terminal, não a fatura, e a contagem de tokens dele é aproximada. A comparação que vale é Etapa 0 × Etapa 4.

## Para depois
- [ ] Avaliar o context-mode (compressão da saída dos MCPs), se os MCPs ainda pesarem no `/context` depois do RTK.
