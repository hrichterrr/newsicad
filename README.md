# NewSIcad

CAD 2D desktop com interface e comandos no estilo AutoCAD (menu superior, linha de comando, aliases, entrada de coordenadas `x,y` / `@dx,dy` / `@dist<ang`, seleção de objetos, undo/redo), com File > Open/Save lendo `.dxf`/`.dwg` e gravando `.dxf`.

**Developed by HRichter**

## Status

Em desenvolvimento — marco atual: desenho + modificação (seleção, MOVE/COPY/ROTATE/MIRROR/SCALE/ERASE) + menu superior estilo AutoCAD + **blocos, referências externas e exportação PDF** + **anotação (texto, cotas, hachura, leader)** + **edição geométrica avançada (TRIM/EXTEND/OFFSET/FILLET/CHAMFER/JOIN/EXPLODE/STRETCH/DIVIDE/MEASURE) e OSNAP/POLAR reais**.

Implementado:
- Canvas escuro com grid adaptativo, crosshair, zoom (scroll) e pan (botão do meio)
- Linha de comando ancorada embaixo, com histórico, prompts estilo AutoCAD e navegação por ↑/↓
- Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension, Modify, Help) — itens ainda não implementados aparecem desabilitados com tooltip, não somem da interface
- Ribbon estilo AutoCAD (abas File/Home/Insert/Annotate/View, painéis com botões grandes de ícone geométrico desenhado programaticamente) logo abaixo do menu — dispara exatamente os mesmos comandos que digitar na linha de comando; os toggles GRID/ORTHO/SNAP do ribbon ficam sincronizados com os da barra de status
- File > Open... (Ctrl+O): abre `.dxf` ou `.dwg` existente, substituindo o desenho atual (zoom extents automático ao carregar; entidades de tipo não suportado são ignoradas com aviso, em vez de travar a abertura)
- File > Save (Ctrl+S) / Save As... (Ctrl+Shift+S): grava o desenho atual como `.dxf`. Gravação de `.dwg` ainda não está disponível — ver seção "Arquivos `.dwg`" abaixo
- Comandos de desenho: `LINE`(L), `CIRCLE`(C), `ARC`(A), `RECTANG`(REC), `PLINE`(PL), `ELLIPSE`(EL) — com preview ao vivo e dynamic input (distância/ângulo perto do cursor)
- Medição: `DIST`(DI)
- **Anotação (novo):**
  - `MTEXT`(T/MT) — texto simples/multilinha (entidade `Text`), inserido no ponto clicado e digitado na linha de comando; renderizado no canvas com a inversão de ângulo correta (não fica de cabeça pra baixo)
  - `DIMLINEAR`(DLI) / `DIMALIGNED`(DAL) / `DIMANGULAR`(DAN) / `DIMRADIUS`(DRA) / `DIMDIAMETER`(DDI) — cotas (entidade única `Dimension` com campo `kind`), com linhas de extensão, linha de cota, marcas de seta simplificadas (dois traços em ângulo) e o texto da medida calculado automaticamente a partir da geometria
  - `DIMSTYLE`(D/DS) — informativo por enquanto: confirma que só o estilo de cota padrão é suportado (sem estilos nomeados customizados)
  - `HATCH`(H) — hachura (entidade `Hatch`) por linhas diagonais paralelas dentro de um contorno; nesta versão só aceita uma `LWPolyline` fechada pré-existente como contorno (selecionar com clique) — detecção automática de contorno a partir de várias entidades é o comando `BOUNDARY`, ainda não implementado
  - `LEADER`(LE) — leader simplificado: reusa `LWPolyline` (linha poligonal) + `Text` (anotação na ponta) em vez de um tipo de entidade dedicado
  - Todos os tipos novos (`Text`, `Dimension`, `Hatch`) entram na seleção (clique/janela/crossing), em MOVE/COPY/ROTATE/SCALE/MIRROR, e sobrevivem a salvar/reabrir `.dxf` (round-trip coberto por teste automatizado — ver `tests/test_dxf_io.py`)
- Seleção de objetos: clique único, Shift+clique (alterna), e arrasto por janela (esquerda→direita, seleciona só o que está totalmente dentro) ou crossing (direita→esquerda, seleciona qualquer coisa que a janela toque) — igual ao AutoCAD
- Comandos de modificação: `ERASE`(E), `MOVE`(M), `COPY`(CO/CP), `ROTATE`(RO), `SCALE`(SC), `MIRROR`(MI)
- **OSNAP (F3) de verdade**: durante qualquer prompt de ponto, o cursor gruda no snap mais próximo dentro de uma tolerância em pixels, entre Endpoint (quadrado), Midpoint (triângulo), Center (círculo) e Intersection (X) — marcador visual verde desenhado em `CanvasView.drawForeground`. Endpoint/Midpoint cobrem Line e cada segmento de LWPolyline; Center cobre Circle/Arc/Ellipse; Intersection usa a nova geometria de interseção de `geometry_ops.py` (segmento×segmento e segmento×círculo/arco) entre pares de entidades próximas do cursor.
- **POLAR (F10) de verdade**: quando ativo (e ORTHO desativado — os dois são mutuamente exclusivos, ORTHO tem prioridade se ambos ligados), o cursor gruda no múltiplo de 15° mais próximo a partir do último ponto, dentro de uma tolerância angular de 3°. Funciona tanto no clique quanto no preview/dynamic input.
- **TRIM** (TR): seleciona cutting edges, depois clica no segmento a aparar — remove a porção do lado clicado até a interseção mais próxima. Suporta Line, Circle e Arc como objeto aparado (Circle vira Arc quando aparado); cutting edges podem ser Line/Circle/Arc/LWPolyline.
- **EXTEND** (EX): seleciona boundary edges, clica numa Line pra estendê-la até a borda mais próxima na direção do clique. Boundary edges podem ser Line/Circle/Arc/LWPolyline. (Só estende objetos Line nesta versão — ver limitações.)
- **OFFSET** (O): distância + clique no objeto + clique do lado — Line vira linha paralela, Circle/Arc mantêm centro com raio ±distância, LWPolyline desloca cada segmento e reconecta pelas retas suporte (aproximação razoável, não trata auto-interseção).
- **FILLET** (F): fluxo real do AutoCAD — primeiro prompt oferece `[Radius]`; sem raio definido, pede pra usar a opção antes de selecionar. Depois de definido, seleciona duas Lines e arredonda o canto com um arco tangente. (Line-Arc não implementado nesta versão.)
- **CHAMFER** (CHA): mesmo fluxo com sub-opção `[Distance]` (pede as duas distâncias), corta o canto entre duas Lines com uma reta.
- **JOIN** (J): funde 2+ Lines colineares e conectadas nas pontas (com tolerância) numa única Line.
- **EXPLODE** (X): quebra uma LWPolyline em Lines individuais, um Line por segmento.
- **STRETCH** (S): usa um prompt explícito de janela crossing (dois cantos, como o próprio AutoCAD faz pra STRETCH) — só move vértices de Line/LWPolyline que caem dentro da janela, mantendo os demais fixos.
- **DIVIDE** (DIV) / **MEASURE** (ME): dividem uma Line/Circle/Arc em N partes iguais (DIVIDE) ou por comprimento fixo (MEASURE); como o NewSIcad ainda não tem um tipo `POINT`, cada marcador de divisão é representado por um `Circle` bem pequeno (raio 0.05) — simplificação documentada.
- Painel de Propriedades (Ctrl+1) mostrando tipo/camada da seleção atual
- Undo/redo real (Ctrl+Z / Ctrl+Y, ou comando `U`/`UNDO` digitado) — pilha de snapshots do desenho
- Janela de histórico de comandos (F2), ajuda (F1)
- Entrada de coordenadas absoluta, relativa (`@dx,dy`), polar (`@dist<ang`) e distância direta (mover o mouse + digitar número)
- Toggles GRID / SNAP / ORTHO / OSNAP / POLAR / DYN funcionais na barra de status (F7 / F9 / F8 / F3 / F10 / F12); OTRACK ainda não afeta a captura de pontos
- Todos os atalhos do guia rápido do AutoCAD são reconhecidos como comandos (mesmo os ainda não implementados, que respondem com uma mensagem clara em vez de "comando desconhecido")
- **Blocos (`BLOCK`/`B`, `INSERT`/`I`)**: define um bloco a partir de entidades selecionadas (coordenadas gravadas relativas ao ponto base, entidades originais "consumidas" e substituídas por uma instância — igual ao AutoCAD) e insere instâncias (`BlockReference`, com escala/rotação) de blocos já definidos. Sobrevive a salvar/reabrir `.dxf` de verdade (bloco vira `BLOCK`/`INSERT` do DXF, testado com round-trip automatizado)
- **Block Editor (`BEDIT`/`BE`, `REFEDIT`)**: abre um mini-desenho à parte (mesmo canvas/interpretador/linha de comando da janela principal) com cópias das entidades da definição — todos os comandos normais funcionam lá dentro (LINE, ERASE, MOVE, outro BLOCK aninhado...). "Save" grava de volta na definição e atualiza todas as instâncias no desenho principal automaticamente. Ver limitações na seção "Blocos e referências" abaixo
- **Referências externas (`XREF`/`XR`, `EXTERNALREFERENCES`/`ER`)**: XREF anexa um `.dxf` externo como uma `BlockReference` marcada (`is_xref=True`); o painel EXTERNALREFERENCES lista as xrefs do desenho (nome + caminho) com um botão Reload que relê o arquivo. **Sem watch automático de arquivo** — ver limitações abaixo
- **Imagem raster (`IMAGEATTACH`/`IM`)**: insere `.png`/`.jpg`/`.bmp` como `ImageReference` (ponto de inserção + largura/altura), renderizada via `QGraphicsPixmapItem`. **Não é gravada em `.dxf`** — ver limitações
- **Exportar PDF (`PLOT`, `PUBLISH`, File > Print/Export PDF..., Ctrl+P)**: renderiza o desenho inteiro (não só o que está visível na tela) numa página PDF via `QPdfWriter`

- **Edição geométrica (`TRIM`/TR, `EXTEND`/EX, `OFFSET`/O, `FILLET`/F, `CHAMFER`/CHA, `JOIN`/J, `EXPLODE`/X, `STRETCH`/S, `DIVIDE`/DIV, `MEASURE`/ME)**: geometria real de interseção/corte (segmento-segmento, segmento-círculo, círculo-círculo) — `FILLET`/`CHAMFER` cobrem Line-Line (com sub-opção `[Radius]`/`[Distance]`), `EXTEND` estende até um alvo do tipo Line, `OFFSET` cobre Line/Circle/Arc/LWPolyline (polilinha via aproximação por interseção de linhas de apoio), `STRETCH` usa uma janela crossing explícita. `DIVIDE`/`MEASURE` marcam os pontos com pequenos `Circle` (ainda não existe um tipo `POINT` dedicado) — ver detalhes/limitações na seção "Edição geométrica" abaixo
- **OSNAP e POLAR reais**: `OSNAP` calcula Endpoint/Midpoint/Center/Intersection de verdade a partir das entidades próximas ao cursor (com prioridade sobre ORTHO/POLAR/grid-snap), `POLAR` trava em incrementos de 15°; ambos com marcador visual no canvas e toggle funcional (F3/F10)

Ainda não implementado (próximos marcos): `ALIGN`, `ARRAY`, `BOUNDARY`, `PEDIT` (edição de vértice de polilinha), `MATCHPROP`, `REGION`, `TABLE`, `STYLE`, `GEOMCONSTRAINT`, `DSETTINGS`, `DVIEW`, `DIM`/`DIMEDIT`/`DIMREASSOCIATE`, `OPTIONS`, Object Snap Tracking (`OTRACK`), `VIEWPORTS`/`VM` (decisão consciente de não implementar — ver abaixo), gravação de `.dwg` (ver nota abaixo). `TRIM` ainda não tem undo dentro do próprio comando (só o Ctrl+Z do desenho inteiro).

### Blocos e referências — simplificações documentadas

Esta seção existe pra ser honesta sobre o que é uma versão "de verdade" e o
que é uma versão reduzida, propositalmente, dentro do orçamento deste marco:

- **BEDIT/REFEDIT não distinguem instâncias**: o Block Editor escolhe o
  bloco a editar por NOME numa lista (`QInputDialog`), não clicando numa
  referência específica no desenho como o REFEDIT de verdade do AutoCAD
  (que edita "in place", destacando o resto do desenho). Como toda
  `BlockReference` do mesmo bloco compartilha a mesma definição, editar por
  nome já cobre o caso de uso principal (mudar a geometria do bloco em
  todas as instâncias de uma vez) — só não cobre "editar só esta instância
  sem afetar as outras" (que no AutoCAD de verdade exigiria um bloco novo).
- **Sem undo dentro do Block Editor**: o mini-editor não tem sua própria
  pilha de undo; Cancel descarta tudo, Save grava tudo. Não afeta o undo
  do desenho principal (que continua funcionando normalmente).
- **XREF sem "live link"**: diferente do AutoCAD, não há verificação
  automática se o arquivo `.dxf` referenciado mudou — "atualizar" significa
  clicar em Reload no painel EXTERNALREFERENCES manualmente. Além disso,
  ao salvar o desenho como `.dxf`, uma xref vira um `BLOCK`/`INSERT` comum
  (perde a marcação `is_xref`/o caminho do arquivo original) — reabrir
  esse `.dxf` não vai mais oferecer "Reload" pra esse bloco.
- **Imagem raster não sobrevive ao `.dxf`**: `ImageReference` é só um
  conceito do NewSIcad em memória; salvar como `.dxf` descarta silenciosamente
  qualquer imagem inserida (raster embutido em DXF é raro e complexo o
  suficiente pra ficar fora de escopo). Se o arquivo de imagem não existir
  ou não puder ser aberto, o canvas mostra um retângulo tracejado no lugar
  em vez de quebrar.
- **`VIEWPORTS`/`VM` foi deixado como planejado, de propósito**: um
  viewport de verdade vive numa layout de papel (paper space), conceito que
  o NewSIcad não tem — só existe um espaço de modelo único. Avaliamos uma
  versão simplificada ("janela congelada" mostrando uma vista/zoom
  diferente dentro do próprio modelo), mas decidimos não implementar: sem
  paper space por trás, isso seria só um gadget de zoom duplicado sem
  paralelo real no fluxo de trabalho do AutoCAD — preferimos não fingir uma
  funcionalidade capenga. Fica em `PLANNED_COMMANDS` (`newsicad/commands/registry.py`).
- **`PLOT`/`PUBLISH` não distinguem folhas**: como não há layouts/paper
  space, os dois comandos fazem exatamente a mesma coisa (uma única página
  PDF com o desenho inteiro) — no AutoCAD real, PUBLISH lida com múltiplas
  folhas/layouts, o que não existe aqui.
- **MIRROR de um `BlockReference`** espelha o ponto de inserção e inverte o
  ângulo de rotação, mas não inverte o CONTEÚDO do bloco (isso exigiria
  escala negativa por eixo, que o modelo atual de `BlockReference` — escala
  uniforme única — não representa).

### Nota técnica: gravação DXF de Dimension/Hatch

O `DIMENSION` do formato DXF é, ele mesmo, geometria *derivada/renderizada*
(um bloco anônimo calculado a partir dos pontos de origem) — não é
suficiente pra reconstruir com 100% de fidelidade qual "kind" e quais pontos
originais deram origem a ele (ex.: `aligned` e `linear` produzem o mesmo
`dimtype` na biblioteca `ezdxf` usada aqui). Por isso `newsicad/io/dxf_io.py`
grava tanto a geometria `DIMENSION`/`HATCH` padrão do DXF (pra abrir/visualizar
corretamente em qualquer outro programa CAD) quanto os campos exatos do
nosso modelo como *XDATA* (extended entity data) sob o AppID `NEWSICAD` — ao
reabrir um arquivo salvo pelo próprio NewSIcad, o XDATA é usado e o
round-trip é exato. Ao abrir um `.dxf` de outro programa (sem esse XDATA), o
NewSIcad faz um melhor-esforço decodificando a geometria padrão do
`DIMENSION` (cobre linear/aligned/radius/diameter; `angular` de arquivos
externos é ignorado, contado como entidade "skipped" no aviso pós-abertura).

### Edição geométrica — simplificações documentadas

- **FILLET/CHAMFER**: só Line-Line (Line-Arc é bônus não implementado). FILLET não suporta raio 0 (corte de canto sem arco) — exige um raio positivo via `[Radius]`.
- **EXTEND**: só estende objetos Line (Arc/Circle como alvo fica pra uma versão futura; podem ser usados como boundary edges normalmente).
- **TRIM**: `[Undo]` dentro do comando ainda não desfaz o último corte — use Ctrl+Z depois de terminar o comando.
- **OFFSET de LWPolyline**: aproximação por interseção das retas suporte de cada segmento deslocado; não trata perfeitamente polilinhas que colapsam ou auto-intersectam após o offset (falha com mensagem clara no log em vez de travar).
- **Hit-test de TRIM/EXTEND/OFFSET sem CanvasView** (ex.: uso programático/testes): cai num fallback de tolerância fixa (0.5 unidade de desenho) em `geometry_ops.nearest_entity` em vez da tolerância em pixels da UI real.
- **DIVIDE/MEASURE**: pontos de divisão representados por `Circle` de raio fixo (0.05), já que não existe um tipo `POINT` no NewSIcad ainda.

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
| TRIM | TR | Apara objetos até a aresta de corte mais próxima |
| EXTEND | EX | Estende uma Line até a borda mais próxima |
| OFFSET | O | Cria cópia paralela deslocada (distância + lado) |
| FILLET | F | Arredonda o canto entre duas Lines (opção `[Radius]`) |
| CHAMFER | CHA | Corta o canto entre duas Lines com uma reta (opção `[Distance]`) |
| JOIN | J | Funde Lines colineares e conectadas numa só |
| EXPLODE | X | Quebra uma LWPolyline em Lines individuais |
| STRETCH | S | Move vértices dentro de uma janela crossing |
| DIVIDE | DIV | Marca N pontos de divisão iguais (círculos pequenos) |
| MEASURE | ME | Marca pontos por comprimento fixo (círculos pequenos) |
| BLOCK | B | Define um bloco a partir de objetos selecionados (nome, ponto base, seleção) |
| INSERT | I | Insere uma instância de um bloco já definido (nome, ponto, escala, rotação) |
| BEDIT | BE | Abre o Block Editor para uma definição de bloco existente |
| REFEDIT | — | Mesma coisa que BEDIT nesta versão (ver limitações) |
| XREF | XR | Anexa um `.dxf` externo como referência (`BlockReference` marcada) |
| EXTERNALREFERENCES | ER | Abre o painel de xrefs (lista + Reload) |
| IMAGEATTACH | IM | Insere uma imagem raster (`.png`/`.jpg`/`.bmp`) |
| PLOT | — | Exporta o desenho inteiro para PDF |
| PUBLISH | — | Mesma coisa que PLOT nesta versão (sem layouts/paper space) |
| UNDO | U | Desfaz o último comando |
| MTEXT | T / MT | Texto simples/multilinha (ponto de inserção + texto digitado) |
| DIMLINEAR | DLI | Cota linear (2 pontos de origem + posição da linha de cota) |
| DIMALIGNED | DAL | Cota alinhada à direção entre os 2 pontos |
| DIMANGULAR | DAN | Cota de ângulo (vértice + 2 pontos + posição do arco) |
| DIMRADIUS | DRA | Cota de raio (seleciona círculo/arco + posição do texto) |
| DIMDIAMETER | DDI | Cota de diâmetro (seleciona círculo/arco + posição do texto) |
| DIMSTYLE | D / DS | Informa o estilo de cota atual (só o padrão, por enquanto) |
| HATCH | H | Hachura dentro de uma LWPolyline fechada selecionada |
| LEADER | LE | Linha poligonal + texto na ponta (leader simplificado) |

Convenções: Enter/Espaço confirma ou repete o último comando, Esc cancela, roda do mouse dá zoom, botão do meio faz pan, clique direito equivale a Enter. Nos comandos de modificação, clique seleciona um objeto (Shift+clique alterna), e arrastar numa área vazia seleciona por janela/crossing.

### Arquivo

| Atalho | Ação |
|---|---|
| Ctrl+O | Abre um desenho `.dxf` ou `.dwg` (File > Open...) |
| Ctrl+S | Salva no arquivo atual (`.dxf`; pede um caminho se ainda não houver um) |
| Ctrl+Shift+S | Salva como... (`.dxf`) |
| Ctrl+P | Exporta o desenho para PDF (`PLOT`/`PUBLISH`) |

## Estrutura

```
newsicad/
  core/        modelo de documento (Document.block_definitions), entidades (inclui BlockReference/ImageReference/Text/Dimension/Hatch), seleção, geometria (translate/rotate/mirror/scale/offset/fillet/chamfer/interseções + dimension_geometry), undo
  commands/    interpretador de comandos, parser de coordenadas, comandos de desenho/modificação (draw_commands.py/modify_commands.py), blocos (block_commands.py) e anotação (annotation_commands.py)
  ui/          canvas Qt (renderiza todos os tipos de entidade, OSNAP/POLAR reais), linha de comando, menu superior, ribbon, janela principal, Block Editor (block_editor_dialog.py), painel de xrefs (xref_panel.py)
  io/          leitura/gravação DXF (dxf_io.py, com blocos/INSERT/Text/Dimension/Hatch) e ponte de leitura DWG via LibreDWG (dwg_bridge.py)
tests/         testes automatizados (pytest) — incluindo testes de integração Qt (QTest) para seleção, arrasto, undo/redo, blocos/xref/imagem/PDF, anotação e OSNAP/POLAR
```

## Testes

```bash
# macOS
~/.venvs/newsicad/bin/python3 -m pytest

# Windows
.venv\Scripts\python -m pytest
```

180/180 testes passando (validado no macOS nesta versão, rodando a suíte completa após mesclar os três marcos mais recentes — blocos/referências/PDF, anotação, e edição geométrica/OSNAP/POLAR). O merge desses três marcos expôs um bug real de integração (não visível em nenhum dos três isoladamente): reabrir qualquer `.dxf` com uma cota contava a seta da cota como "entidade não suportada", porque o bloco auto-gerado pelo ezdxf para a seta (`_CLOSEDFILLED`) não caía no filtro de "bloco anônimo" (que só reconhecia nomes começando com `*`) — corrigido em `newsicad/io/dxf_io.py`. Essa validação específica ainda não foi refeita no Windows 11 (a última validação em Windows real, com 56/56 testes, foi antes desses três marcos).

Observação sobre `tests/test_dwg_bridge.py`: os testes que exercitam `dwg_to_document` de verdade dependem do binário `dwg2dxf` do LibreDWG (empacotado para macOS/Windows em `newsicad/resources/libredwg/`, ou disponível no PATH). Em ambientes sem nenhum dos dois (ex.: a maioria dos runners de CI em Linux), esses testes são pulados automaticamente (`pytest.skip`) em vez de falhar.

---

**NewSIcad** — Developed by HRichter
