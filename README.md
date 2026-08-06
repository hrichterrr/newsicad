# NewSIcad

CAD 2D desktop com interface e comandos no estilo AutoCAD (menu superior, linha de comando, aliases, entrada de coordenadas `x,y` / `@dx,dy` / `@dist<ang`, seleção de objetos, undo/redo), com File > Open/Save lendo `.dxf`/`.dwg` e gravando `.dxf`.

**Developed by HRichter**

## Status

Em desenvolvimento — marco atual: desenho + modificação (seleção, MOVE/COPY/ROTATE/MIRROR/SCALE/ERASE) + menu superior estilo AutoCAD.

Implementado:
- Canvas escuro com grid adaptativo, crosshair, zoom (scroll) e pan (botão do meio)
- Linha de comando ancorada embaixo, com histórico, prompts estilo AutoCAD e navegação por ↑/↓
- Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension, Modify, Help) — itens ainda não implementados aparecem desabilitados com tooltip, não somem da interface
- Ribbon estilo AutoCAD (abas File/Home/Insert/Annotate/View, painéis com botões grandes de ícone geométrico desenhado programaticamente) logo abaixo do menu — dispara exatamente os mesmos comandos que digitar na linha de comando; os toggles GRID/ORTHO/SNAP do ribbon ficam sincronizados com os da barra de status
- File > Open... (Ctrl+O): abre `.dxf` ou `.dwg` existente, substituindo o desenho atual (zoom extents automático ao carregar; entidades de tipo não suportado são ignoradas com aviso, em vez de travar a abertura)
- File > Save (Ctrl+S) / Save As... (Ctrl+Shift+S): grava o desenho atual como `.dxf`. Gravação de `.dwg` ainda não está disponível — ver seção "Arquivos `.dwg`" abaixo
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

Ainda não implementado (próximos marcos): TRIM, EXTEND, OFFSET, FILLET, CHAMFER, EXPLODE, JOIN, STRETCH, MATCHPROP (precisam de geometria de interseção/corte), HATCH, BLOCK/INSERT/REGION (sistema de blocos), MTEXT, DIMLINEAR/DIMALIGNED/DIMANGULAR/DIMRADIUS + DIMSTYLE (subsistema de anotação), rastreamento POLAR e snap a objetos (OSNAP) reais, gravação de `.dwg` (ver nota abaixo).

## Instalação

### Windows (rodando sem instalar nada)

Não quer mexer com Python? Baixe o `.exe` já pronto (gerado com PyInstaller,
testado numa VM Windows 11 — Python 3.12, 56/56 testes passando): descompacte
o `.zip` e rode `NewSIcad.exe`. É preciso manter a pasta inteira junto (o exe
depende dos arquivos da subpasta `_internal`), não copiar só o `.exe` sozinho.

### Windows (a partir do código-fonte)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m newsicad.main
```

Se `py -3.12` não for reconhecido, instale primeiro com `py install 3.12`
(o instalador do Python vem da própria Microsoft Store / python.org).

### macOS

> **Importante:** o PySide6 tem um bug conhecido ao carregar plugins do Qt quando o caminho de instalação contém espaços. Como esta pasta do projeto fica dentro de `Cloude CODE` (que tem espaço no nome), crie o venv **fora** dela, em um caminho sem espaços — por exemplo `~/.venvs/newsicad`. (No Windows/Linux esse problema não existe.)

```bash
python3 -m venv ~/.venvs/newsicad
~/.venvs/newsicad/bin/pip install -r requirements.txt
```

### Arquivos `.dwg`

O NewSIcad abre arquivos `.dwg` via [LibreDWG](https://www.gnu.org/software/libredwg/) (projeto GNU, licença GPL, **sem restrição de uso comercial**), convertendo internamente para `.dxf` de forma transparente — o usuário só usa File > Open normalmente, sem rodar nada manualmente. Os binários do LibreDWG (`dwg2dxf`) já vêm empacotados para macOS e Windows em `newsicad/resources/libredwg/`; se não encontrados, o NewSIcad procura no PATH do sistema (`brew install libredwg` no macOS).

**Gravação de `.dwg` ainda não está disponível.** O gravador do LibreDWG (`dxf2dwg`) foi testado tanto na versão 0.13.3 (Homebrew) quanto na 0.14 (compilada localmente a partir do código-fonte) e se mostrou não confiável em ambas — mesmo com um documento totalmente vazio (nenhuma entidade), produz arquivos `.dwg` com handles duplicados que nem o próprio LibreDWG consegue reler direito (`ERROR: Duplicate handle ... already points to object ...` na escrita, seguido de `Invalid handle 0.` na releitura). Investigamos a causa e chegamos a testar um fix na função `dwg_next_handle()` do LibreDWG (que calculava incorretamente o maior handle já em uso), mas isolar e corrigir a causa raiz completa está fora do escopo deste projeto — é um bug conhecido e **ainda aberto** do próprio LibreDWG ([libredwg#192](https://github.com/LibreDWG/libredwg/issues/192), aberto desde 2020; ver também [libredwg#1356](https://github.com/LibreDWG/libredwg/issues/1356) para a mesma classe de bug em outra direção de conversão), não algo específico do NewSIcad. Os mantenedores do projeto também confirmam que o `dxf2dwg` "ainda é altamente experimental" ([libredwg#195](https://github.com/LibreDWG/libredwg/issues/195)). Por isso File > Save/Save As só grava `.dxf` por enquanto — arquivos `.dwg` abertos no NewSIcad devem ser salvos como `.dxf`, que qualquer versão do AutoCAD abre sem problema. Próximo passo realista, se isso voltar a ser prioridade: reportar o caso mínimo de reprodução ao upstream do LibreDWG, ou considerar o ODA File Converter (abaixo) para quem tiver licença paga.

Alternativa mais completa (não usada por padrão, por causa da licença):

- **[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)** — mais completo e confiável na conversão (leitura e gravação), mas **gratuito só para uso não-comercial**; uso comercial exige associação paga à Open Design Alliance. Opção para quem já é membro ODA ou usa só para fins não-comerciais e precisa de gravação `.dwg` real.

## Executando

**Windows:**
```powershell
.venv\Scripts\python -m newsicad.main
```

**macOS:**
```bash
cd newsicad  # esta pasta (contém o pacote newsicad/)
~/.venvs/newsicad/bin/python3 -m newsicad.main
```

## Gerando o `.exe` (Windows)

```powershell
.venv\Scripts\pip install -r requirements-build.txt
.venv\Scripts\pyinstaller build_windows.spec
```

O executável final fica em `dist\NewSIcad\NewSIcad.exe` — para distribuir,
zipe a pasta `dist\NewSIcad` inteira (não só o `.exe`).

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

### Arquivo

| Atalho | Ação |
|---|---|
| Ctrl+O | Abre um desenho `.dxf` ou `.dwg` (File > Open...) |
| Ctrl+S | Salva no arquivo atual (`.dxf`; pede um caminho se ainda não houver um) |
| Ctrl+Shift+S | Salva como... (`.dxf`) |

## Estrutura

```
newsicad/
  core/        modelo de documento, entidades, seleção, geometria (translate/rotate/mirror/scale), undo
  commands/    interpretador de comandos, parser de coordenadas, comandos de desenho e modificação
  ui/          canvas Qt, linha de comando, menu superior, janela principal
  io/          leitura/gravação DXF (dxf_io.py) e ponte de leitura DWG via LibreDWG (dwg_bridge.py)
tests/         testes automatizados (pytest) — incluindo testes de integração Qt (QTest) para seleção, arrasto e undo/redo
```

## Testes

```bash
# macOS
~/.venvs/newsicad/bin/python3 -m pytest

# Windows
.venv\Scripts\python -m pytest
```

69/69 testes passando (validado no macOS nesta versão, incluindo os testes novos de DXF/DWG/menu File). A versão anterior — sem File Open/Save — foi validada também no Windows 11/Python 3.12 com 56/56; essa validação específica no Windows ainda não foi refeita com os 13 testes novos.

Observação sobre `tests/test_dwg_bridge.py`: os testes que exercitam `dwg_to_document` de verdade dependem do binário `dwg2dxf` do LibreDWG (empacotado para macOS/Windows em `newsicad/resources/libredwg/`, ou disponível no PATH). Em ambientes sem nenhum dos dois (ex.: a maioria dos runners de CI em Linux), esses testes são pulados automaticamente (`pytest.skip`) em vez de falhar.

---

**NewSIcad** — Developed by HRichter
