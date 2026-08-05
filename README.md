# NewSIcad

CAD 2D desktop com interface e comandos no estilo AutoCAD (linha de comando, aliases, entrada de coordenadas `x,y` / `@dx,dy` / `@dist<ang`, camadas), com suporte planejado a leitura/gravação de `.dxf` e `.dwg`.

**Developed by HRichter**

## Status

Em desenvolvimento — marco atual: esqueleto do app + comandos essenciais de desenho.

Implementado:
- Canvas escuro com grid adaptativo, crosshair, zoom (scroll) e pan (botão do meio)
- Linha de comando ancorada embaixo, com histórico, prompts estilo AutoCAD e navegação por ↑/↓
- Comandos `LINE` (L), `CIRCLE` (C), `ARC` (A), `RECTANGLE` (REC), `PLINE` (PL) com preview ao vivo e dynamic input (distância/ângulo perto do cursor)
- Entrada de coordenadas absoluta, relativa (`@dx,dy`), polar (`@dist<ang`) e distância direta (mover o mouse + digitar número)
- Toggles GRID / SNAP / ORTHO funcionais na barra de status (F7 / F9 / F8)

Ainda não implementado (próximos marcos): seleção + ERASE/MOVE/COPY/ROTATE/MIRROR, TRIM/EXTEND/OFFSET, camadas (comando LAYER), undo/redo, rastreamento POLAR e snap a objetos (OSNAP) — os toggles já aparecem na UI mas ainda não afetam a captura de pontos —, leitura/gravação de `.dxf` e a ponte para `.dwg`.

## Instalação

> **Importante (macOS):** o PySide6 tem um bug conhecido ao carregar plugins do Qt quando o caminho de instalação contém espaços. Como esta pasta do projeto fica dentro de `Cloude CODE` (que tem espaço no nome), crie o venv **fora** dela, em um caminho sem espaços — por exemplo `~/.venvs/newsicad`.

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
| RECTANGLE | REC | Desenha retângulo por dois cantos |
| PLINE | PL | Desenha polilinha (aceita Undo) |

Convenções: Enter/Espaço confirma ou repete o último comando, Esc cancela, roda do mouse dá zoom, botão do meio faz pan, clique direito equivale a Enter.

## Estrutura

```
newsicad/
  core/        modelo de documento e entidades geométricas
  commands/    interpretador de comandos e parser de coordenadas
  ui/          canvas Qt, linha de comando, janela principal
  io/          leitura/gravação DXF e ponte DWG (planejado)
tests/         testes automatizados (pytest)
```

## Testes

```bash
~/.venvs/newsicad/bin/python3 -m pytest
```

---

**NewSIcad** — Developed by HRichter
