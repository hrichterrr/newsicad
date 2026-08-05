# NewSIcad

CAD 2D desktop com interface e comandos no estilo AutoCAD (menu superior, linha de comando, aliases, entrada de coordenadas `x,y` / `@dx,dy` / `@dist<ang`, seleção de objetos, undo/redo), com suporte planejado a leitura/gravação de `.dxf` e `.dwg`.

**Developed by HRichter**

## Status

Em desenvolvimento — marco atual: desenho + modificação (seleção, MOVE/COPY/ROTATE/MIRROR/SCALE/ERASE) + menu superior estilo AutoCAD.

Implementado:
- Canvas escuro com grid adaptativo, crosshair, zoom (scroll) e pan (botão do meio)
- Linha de comando ancorada embaixo, com histórico, prompts estilo AutoCAD e navegação por ↑/↓
- Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension, Modify, Help) — itens ainda não implementados aparecem desabilitados com tooltip, não somem da interface
- Comandos de desenho: `LINE`(L), `CIRCLE`(C), `ARC`(A), `RECTANG`(REC), `PLINE`(PL), `ELLIPSE`(EL) — com preview ao vivo e dynamic input (distância/ângulo perto do cursor)
- Medição: `DIST`(DI)
- Seleção de objetos: clique único, Shift+clique (alterna), e arrasto por janela (esquerda→direita, seleciona só o que está totalmente dentro) ou crossing (direita→esquerda, seleciona qualquer coisa que a janela toque) — igual ao AutoCAD
- Comandos de modificação: `ERASE`(E), `MOVE`(M), `COPY`(CO/CP), `ROTATE`(RO), `SCALE`(SC), `MIRROR`(MI)
- Painel de Propriedades (Ctrl+1) mostrando tipo/camada da seleção atual
- Undo/redo real (Ctrl+Z / Ctrl+Y, ou comando `U`/`UNDO` digitado) — pilha de snapshots do desenho
- Janela de histórico de comandos (F2), ajuda (F1)
- Entrada de coordenadas absoluta, relativa (`@dx,dy`), polar (`@dist<ang`) e distância direta (mover o mouse + digitar número)
- Toggles GRID / SNAP / ORTHO / DYN funcionais na barra de status (F7 / F9 / F8 / F12); POLAR / OSNAP / OTRACK já aparecem na UI mas ainda não afetam a captura de pontos
- Todos os atalhos do guia rápido do AutoCAD são reconhecidos como comandos (mesmo os ainda não implementados, que respondem com uma mensagem clara em vez de "comando desconhecido")

Ainda não implementado (próximos marcos): TRIM, EXTEND, OFFSET, FILLET, CHAMFER, EXPLODE, JOIN, STRETCH, MATCHPROP (precisam de geometria de interseção/corte), HATCH, BLOCK/INSERT/REGION (sistema de blocos), MTEXT, DIMLINEAR/DIMALIGNED/DIMANGULAR/DIMRADIUS + DIMSTYLE (subsistema de anotação), rastreamento POLAR e snap a objetos (OSNAP) reais, leitura/gravação de `.dxf` e a ponte para `.dwg`.

## Instalação

> **Importante (macOS):** o PySide6 tem um bug conhecido ao carregar plugins do Qt quando o caminho de instalação contém espaços. Como esta pasta do projeto fica dentro de `Cloude CODE` (que tem espaço no nome), crie o venv **fora** dela, em um caminho sem espaços — por exemplo `~/.venvs/newsicad`. (No Windows/Linux esse problema não existe.)

```bash
python3 -m venv ~/.venvs/newsicad
~/.venvs/newsicad/bin/pip install -r requirements.txt
```

Para abrir/salvar arquivos `.dwg` (quando essa funcionalidade for implementada), será necessário instalar separadamente o **[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)** (gratuito) — o NewSIcad o usa como ponte para converter `.dwg` ↔ `.dxf`. Internamente o NewSIcad sempre trabalha em DXF.

## Executando

```bash
cd newsicad  # esta pasta (contém o pacote newsicad/)
~/.venvs/newsicad/bin/python3 -m newsicad.main
```

## Comandos disponíveis

| Comando | Alias | Descrição |
|---|---|---|
| LINE | L | Desenha linha(s) por sequência de pontos |
| CIRCLE | C | Desenha círculo (centro + raio) |
| ARC | A | Desenha arco (3 pontos) |
| RECTANG | REC | Desenha retângulo por dois cantos |
| PLINE | PL | Desenha polilinha (aceita Undo) |
| ELLIPSE | EL | Desenha elipse (centro, eixo maior, eixo menor) |
| DIST | DI | Mede distância e ângulo entre 2 pontos |
| ERASE | E | Apaga objetos selecionados |
| MOVE | M | Move objetos selecionados |
| COPY | CO / CP | Copia objetos selecionados |
| ROTATE | RO | Rotaciona objetos selecionados (ângulo digitado) |
| SCALE | SC | Escala objetos selecionados (fator digitado) |
| MIRROR | MI | Espelha objetos selecionados |
| UNDO | U | Desfaz o último comando |

Convenções: Enter/Espaço confirma ou repete o último comando, Esc cancela, roda do mouse dá zoom, botão do meio faz pan, clique direito equivale a Enter. Nos comandos de modificação, clique seleciona um objeto (Shift+clique alterna), e arrastar numa área vazia seleciona por janela/crossing.

## Estrutura

```
newsicad/
  core/        modelo de documento, entidades, seleção, geometria (translate/rotate/mirror/scale), undo
  commands/    interpretador de comandos, parser de coordenadas, comandos de desenho e modificação
  ui/          canvas Qt, linha de comando, menu superior, janela principal
  io/          leitura/gravação DXF e ponte DWG (planejado)
tests/         testes automatizados (pytest) — incluindo testes de integração Qt (QTest) para seleção, arrasto e undo/redo
```

## Testes

```bash
~/.venvs/newsicad/bin/python3 -m pytest
```

---

**NewSIcad** — Developed by HRichter
