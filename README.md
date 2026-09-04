# NewSIcad

CAD 2D desktop com interface e comandos no estilo AutoCAD (menu superior, linha de comando, aliases, entrada de coordenadas `x,y` / `@dx,dy` / `@dist<ang`, seleção de objetos, undo/redo), com File > Open/Save lendo `.dxf`/`.dwg` e gravando `.dxf`.

**Developed by HRichter**

## Status

Em desenvolvimento — marco atual: desenho + modificação (seleção, MOVE/COPY/ROTATE/MIRROR/SCALE/ERASE) + menu superior estilo AutoCAD + **blocos, referências externas e exportação PDF** + **anotação (texto, cotas, hachura, leader)** + **edição geométrica avançada (TRIM/EXTEND/OFFSET/FILLET/CHAMFER/JOIN/EXPLODE/STRETCH/DIVIDE/MEASURE) e OSNAP/POLAR reais** + **POLYGON, ALIGN, ARRAY, MATCHPROP, SELECTSIMILAR, SPLINE, BOUNDARY, PEDIT e HATCHEDIT** (feedback do grupo de testers via WhatsApp) + **proteção contra perda de trabalho não salvo** + **MLINE, XLINE/RAY, BREAK/BREAK AT POINT, LENGTHEN, DONUT, um tipo `POINT` real e justificação de MTEXT** (marco B do plano de melhorias, 2026-08-22) + **redesign da interface: ribbon colorido por categoria, Quick Access Toolbar, abas de documento (vários desenhos abertos ao mesmo tempo), painel de Propriedades reorganizado em seções, tema escuro em todo diálogo/menu (não só no canvas), ícones do ribbon em resolução mais alta (nítidos em telas HiDPI), painel de Camadas redesenhado com cor de camada afetando o desenho de verdade, e REVCLOUD/WIPEOUT/LAYMCH/LAYISO/LAYUNISO/QSELECT/CENTERMARK/DIMBREAK/TABLE**, inspirado no print do AutoCAD 2019 que o Hamilton mandou e no catálogo de comandos do ribbon do AutoCAD estudado a partir daí (2026-08-22) — com `TABLE` isso fecha a lista original de comandos que a Rafaela pediu lá no início do projeto.

Implementado:
- Ícone do programa (janela, barra de tarefas, o próprio `.exe`) com o logo "N" dourado fornecido por Hamilton (`newsicad/resources/newsi_icon.ico`, aplicado em `newsicad/main.py` e em `build_windows.spec`)
- **Pickbox no crosshair** (quadradinho de seleção no centro da mira, igual ao AutoCAD) — `CanvasView.drawForeground`
- **Seleção por clique fora de um comando ativo** (bug real, o mais fundamental de todos os reportados pela Rafaela): antes, só era possível clicar pra selecionar uma entidade DURANTE o prompt "Select objects:" de um comando como ERASE/MOVE — clicar numa linha sem nenhum comando ativo não fazia nada. Agora clique esquerdo seleciona/alterna a entidade sob o cursor (ou inicia janela/crossing numa área vazia) a qualquer momento. Isso também é o que fazia Del/Backspace, SELECTSIMILAR-com-seleção-prévia e botão direito parecerem "não funcionar" — não existia nada selecionado pra eles agirem sobre
- **Menu de contexto no botão direito** (Move/Copy/Rotate/Erase/Select Similar/Properties): clicar com o botão direito sobre uma entidade (fora de um comando ativo) a seleciona, se ainda não estava, e abre um menu — clicar com o direito numa área vazia continua repetindo o último comando (comportamento existente, não mudou); durante um comando ativo, botão direito continua equivalendo a Enter (confirmar/terminar), sem mudança
- **3 bugs reais corrigidos (feedback do grupo de testers)**:
  - **TRIM cortando o lado errado perto de interseções**: o clique de "selecionar objeto a aparar" grudava no OSNAP igual um clique normal, apagando a informação de qual lado do corte foi clicado — OSNAP agora só se aplica a pontos que definem geometria nova, não a cliques que identificam uma entidade/lado já existente (TRIM/EXTEND/OFFSET/FILLET/CHAMFER)
  - **Ctrl+Z parecia não funcionar**: desfazia só o texto digitado na linha de comando (undo nativo do campo de texto), nunca o desenho — a linha de comando intercepta Ctrl+Z/Ctrl+Y agora e repassa pro Undo/Redo do desenho
  - **RECTANG parecia estar desenhando uma linha**: a prévia ao arrastar só mostrava uma linha reta até o cursor (a entidade final sempre foi um retângulo de verdade) — agora mostra o contorno do retângulo
  - **Del/Backspace não apagavam nada**: não existia nenhum atalho de teclado pra isso no app inteiro — agora apagam a seleção atual direto (undo funciona normalmente depois)
  - **SELECTSIMILAR (SIM) parecia não funcionar**: sempre limpava a seleção atual e pedia pra selecionar de novo do zero, quebrando o fluxo natural "clico no objeto, digito SIM" — agora usa a seleção já feita como referência quando ela existir
- **Import PDF (`IMPORTPDF`, Insert > Import PDF...)**: extrai a geometria vetorial (linhas, curvas de Bézier tesseladas, retângulos) e o texto de uma página do PDF como entidades reais (`Line`/`LWPolyline`/`Text`) — diferente do `IMAGEATTACH`, que só cola uma imagem raster de fundo. Usa PyMuPDF (`newsicad/io/pdf_import.py`); PDF em pontos (1/72") convertido pra mm, eixo Y invertido pra bater com a convenção do NewSIcad. Simplificação documentada: cada segmento vira uma entidade independente, não tenta reconstruir contornos conectados como uma LWPolyline única; texto rotacionado é importado na horizontal. **Nota de licença**: PyMuPDF é AGPL-3.0 — aceitável porque o NewSIcad é uso interno da New SI, não é revendido a terceiros; se isso mudar, reavaliar (trocar por pdfminer.six/pdfplumber, MIT, com extração de vetores mais limitada)
- Canvas escuro com grid adaptativo, crosshair estilo AutoCAD (span completo da tela, cursor do SO escondido — `CanvasView.drawForeground`), zoom (scroll) e pan (botão do meio)
- Linha de comando ancorada embaixo, com histórico, prompts estilo AutoCAD e navegação por ↑/↓
- Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension, Modify, Help) — itens ainda não implementados aparecem desabilitados com tooltip, não somem da interface
- **Quick Access Toolbar** (barra fina acima do ribbon, com o botão "N" dourado + New/Open/Save/Save As/Plot/Undo/Redo, a QAT padrão do AutoCAD): fica visível o tempo todo, não importa qual aba do ribbon está aberta — pedido direto do Hamilton a partir do print do AutoCAD 2019 ("principais comandos sempre no menu aparente"), mesma ideia da QAT de verdade ao lado do "A" vermelho
- **Ribbon no padrão do AutoCAD 2020 (redesenho de 2026-09-03)**: abas Home/Insert/Annotate/View/Manage/Output; a aba Home tem os dez painéis do AutoCAD na ordem dele (Draw, Modify, Annotation, Layers, Block, Properties, Groups, Utilities, Clipboard, View) com a mesma anatomia — botões grandes de 32 px com rótulo embaixo, pilhas de três botões pequenos de 16 px com rótulo ao lado, colunas só de ícone, split-buttons com flyout (Circle▾, Trim▾, Text▾, Dimension▾...), o título do painel abre um slide-out com os comandos secundários (Spline/Xline/Ray... em Draw, Extend/Chamfer/Break/Join... em Modify) e a setinha ↘ ("dialog box launcher") só onde existe mesmo um diálogo por trás. O painel Layers tem o combo de camada atual (lâmpada + cor + nome, sincronizado com o painel de Camadas) e botões de isolar/travar/ligar todas/renomear. Comandos que o AutoCAD tem e o NewSIcad ainda não (Groups, atributos de bloco, Freeze, Point Cloud, Action Recorder...) ficam no mesmo lugar, desabilitados com tooltip. **Ícones novos em SVG** (`newsicad/resources/icons/*.svg`, 162 símbolos, grade 24 px, traço 1,5 px, renderizados a 3x pelo `QSvgRenderer` em `newsicad/ui/icon_utils.py:svg_icon`) coloridos pela família do painel (laranja Draw, azul Modify, roxo Annotation/Block, cinza neutro no resto) com um acento branco — os mesmos ícones aparecem no menu clássico, no menu de contexto do canvas (agora na ordem do AutoCAD: Repeat, Clipboard, Isolate, Erase/Move/Copy/Scale/Rotate, Select Similar/Deselect All, Quick Select/Find/Properties) e nos toggles da barra de status (só ícone, azul quando ligado). A QAT ganhou Save As e Plot. A proposta visual aprovada pelo Hamilton está em `docs/design/ribbon-proposta-2026-09.html`; os toggles GRID/SNAP/ORTHO/POLAR/OSNAP/DYN da aba View continuam sincronizados com os da barra de status
- **Tema escuro em toda a interface, não só no canvas**: o menu clássico (File/Edit/...) e todo QDialog/QMessageBox (Units, Export PDF, confirmar descarte de alterações, Block Editor, painel de xrefs...) agora seguem a mesma paleta escura do resto do app — antes só o canvas/ribbon/docks eram escuros, e cada diálogo abria com o branco nativo do Windows, destoando bastante. Estilo global em `newsicad/main.py:APP_STYLE` (aplicado no `QApplication`) + `newsicad/ui/menu_bar.py:MENU_BAR_STYLE`
- **Abas de documento** (acima do canvas, uma por desenho aberto): vários desenhos independentes na mesma janela, cada um com seu próprio undo/redo, seleção e histórico de comandos na linha de comando — trocar de aba troca tudo isso junto. `File > New`/`Open...` sempre abrem numa aba nova (a aba atual nunca é descartada), então a confirmação "Salvar alterações?" só aparece mais ao fechar uma aba ou a janela inteira com trabalho não salvo — ver `newsicad/ui/document_session.py`. Aba com `*` no nome = não salva; fechar a última aba deixa uma em branco no lugar (nunca fica com zero abas). Um "+" no canto direito da barra de abas abre um desenho novo (mesma coisa que `Ctrl+N`/File > New/o botão New do ribbon/QAT); `Ctrl+W`/"Close Tab" fecha a aba atual
- File > Open... (Ctrl+O): abre `.dxf` ou `.dwg` numa aba nova (zoom extents automático ao carregar; entidades de tipo não suportado são ignoradas com aviso, em vez de travar a abertura)
- File > Save (Ctrl+S) / Save As... (Ctrl+Shift+S): grava o desenho da aba atual como `.dxf`. Gravação de `.dwg` ainda não está disponível — ver seção "Arquivos `.dwg`" abaixo
- **Painel de Propriedades (Ctrl+1) redesenhado**: em vez do texto corrido de antes, agora mostra a seleção em seções "Geral" (tipo/camada/cor) e "Geometria" (campos específicos do tipo — ex.: centro/raio de um Circle, início/fim/comprimento de uma Line), no mesmo estilo de faixas escuras do Properties do AutoCAD. Múltiplos objetos selecionados mostram contagem + camada (se uniforme) + tipos. Só leitura nesta versão — edição inline dos valores fica pra um marco futuro
- Comandos de desenho: `LINE`(L), `CIRCLE`(C), `ARC`(A), `RECTANG`(REC), `PLINE`(PL), `ELLIPSE`(EL) — com preview ao vivo e dynamic input (distância/ângulo perto do cursor)
- **POINT** (PO): cria um `PointEntity` real (não mais o `Circle` minúsculo que `DIVIDE`/`MEASURE` usavam como marcador — ambos foram migrados pra usar este tipo). Desenhado como uma cruz de tamanho constante em pixels de tela, estilo marcador de OSNAP; grava/lê como `POINT` de verdade no `.dxf`
- **XLINE**(XL) / **RAY**: linhas de construção infinitas — `XLINE` nas duas direções a partir de um ponto, `RAY` numa única direção; ambas aceitam vários "through points" em sequência a partir da mesma base, como no AutoCAD. Guardadas internamente como ponto+ângulo (semântica real de "infinita"), gravadas/lidas como `XLINE`/`RAY` de verdade no `.dxf`; o canvas desenha um segmento bem comprido só para renderização (excluído do cálculo de zoom-extents, senão "explodiria" o zoom de qualquer desenho que tenha uma)
- **MLINE**(ML): parede de linhas paralelas — pede a largura total e a sequência de pontos do eixo (igual a `PLINE`). Simplificação documentada: não é uma entidade `MLINE` de verdade com `MLSTYLE` (múltiplos elementos com offsets/cores próprias), e sim duas `LWPolyline` independentes deslocadas ± metade da largura (reaproveita a mesma função de `OFFSET` que já resolve os cantos/junções)
- **DONUT**(DO): anel preenchido — pede diâmetro interno/externo (com defaults <0.5>/<1.0>, Enter aceita) e aceita vários centros em sequência. É um `Circle` com um novo campo `inner_radius` (canvas desenha preenchimento even-odd entre os dois raios); limitação documentada: grava no `.dxf` como dois `CIRCLE` simples (externo/interno), sem o preenchimento — o anel fica visualmente reconhecível ao reabrir, mas sem fill
- **REVCLOUD**: nuvem de revisão — entrada por cliques (como PLINE), não por arrastar o mouse em modo livre; cada trecho entre dois pontos vira um `Arc` real estufado pra fora, fechando de volta no primeiro ponto
- **WIPEOUT**: área que oculta o que está atrás dela — implementado como um `Hatch` com `solid_fill=True` (reaproveita toda a infraestrutura de contorno/seleção que o Hatch já tinha) em vez de um tipo de entidade dedicado; desenhado por cima do resto (zValue alto) na cor de fundo do canvas; grava/lê como `HATCH` sólido de verdade no `.dxf` (`set_solid_fill`)
- **CENTERMARK** (DIMCENTER): marca cruzada no centro de um Circle/Arc clicado, repete até Enter
- **DIMBREAK**: interrompe a linha de cota (só Linear/Aligned) onde ela cruza os objetos selecionados — `Dimension` ganhou um campo `break_points`; limitação documentada: não é salvo no `.dxf` (perdido ao reabrir), diferente do resto do modelo de Dimension que tem round-trip exato via XDATA
- **TABLE** (TB): último item da lista original de comandos pedida pelo grupo de testers (Rafaela), implementado. Grade UNIFORME de células com texto (mesma largura de coluna e altura de linha pra todas — sem estilos nomeados, sem customização por coluna/linha, sem células mescladas). Depois de definir linhas/colunas/dimensões, entra num loop preenchendo célula por célula em ordem (Enter deixa em branco, `[eXit]` para o preenchimento a qualquer momento). Entidade `Table` própria (`core/entities.py`), renderizada como grade + texto por célula num `QGraphicsItemGroup` rotacionável (mesmo padrão de `BlockReference`). **Limitação de gravação**: não vira um `ACAD_TABLE` de verdade no `.dxf` (a API do ezdxf pra isso exige estilos de tabela nomeados, bem mais elaborado do que o modelo aqui) — grava como `LINE` (grade) + `TEXT` (cada célula não-vazia), mesmo espírito de simplificação do MLINE/DONUT: não volta como Table ao reabrir, mas o desenho continua reconhecível
- Medição: `DIST`(DI)
- **Anotação (novo):**
  - `MTEXT`(T/MT) — texto simples/multilinha (entidade `Text`), inserido no ponto clicado e digitado na linha de comando; renderizado no canvas com a inversão de ângulo correta (não fica de cabeça pra baixo). Sub-opção `[Justify]` escolhe qual dos 9 attachment points do MTEXT de verdade (`TL`/`TC`/`TR`/`ML`/`MC`/`MR`/`BL`/`BC`/`BR`, `TL` = padrão) fica ancorado no ponto clicado — gravado/lido como `attachment_point` (group code 71) real no `.dxf`
  - `DIMLINEAR`(DLI) / `DIMALIGNED`(DAL) / `DIMANGULAR`(DAN) / `DIMRADIUS`(DRA) / `DIMDIAMETER`(DDI) — cotas (entidade única `Dimension` com campo `kind`), com linhas de extensão, linha de cota, marcas de seta simplificadas (dois traços em ângulo) e o texto da medida calculado automaticamente a partir da geometria
  - `DIMSTYLE`(D/DS) — informativo por enquanto: confirma que só o estilo de cota padrão é suportado (sem estilos nomeados customizados)
  - `HATCH`(H) — hachura (entidade `Hatch`) por linhas diagonais paralelas dentro de um contorno; nesta versão só aceita uma `LWPolyline` fechada pré-existente como contorno (selecionar com clique) — pra gerar esse contorno automaticamente a partir de outras entidades (paredes soltas, círculo), use `BOUNDARY` primeiro (ver abaixo)
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
- **DIVIDE** (DIV) / **MEASURE** (ME): dividem uma Line/Circle/Arc em N partes iguais (DIVIDE) ou por comprimento fixo (MEASURE); cada marcador de divisão é um `PointEntity` real (comando `POINT`, ver acima) — antes do tipo `POINT` existir, cada marcador era um `Circle` bem pequeno (raio 0.05); histórico, não mais usado.
- Undo/redo real (Ctrl+Z / Ctrl+Y, ou comando `U`/`UNDO` digitado) — pilha de snapshots do desenho, independente por aba de documento
- Janela de histórico de comandos (F2), ajuda (F1)
- Entrada de coordenadas absoluta, relativa (`@dx,dy`), polar (`@dist<ang`) e distância direta (mover o mouse + digitar número)
- Toggles GRID / SNAP / ORTHO / OSNAP / POLAR / DYN funcionais na barra de status (F7 / F9 / F8 / F3 / F10 / F12); OTRACK ainda não afeta a captura de pontos
- Todos os atalhos do guia rápido do AutoCAD são reconhecidos como comandos (mesmo os ainda não implementados, que respondem com uma mensagem clara em vez de "comando desconhecido")
- **Blocos (`BLOCK`/`B`, `INSERT`/`I`)**: define um bloco a partir de entidades selecionadas (coordenadas gravadas relativas ao ponto base, entidades originais "consumidas" e substituídas por uma instância — igual ao AutoCAD) e insere instâncias (`BlockReference`, com escala/rotação) de blocos já definidos. Sobrevive a salvar/reabrir `.dxf` de verdade (bloco vira `BLOCK`/`INSERT` do DXF, testado com round-trip automatizado)
- **Block Editor (`BEDIT`/`BE`, `REFEDIT`)**: abre um mini-desenho à parte (mesmo canvas/interpretador/linha de comando da janela principal) com cópias das entidades da definição — todos os comandos normais funcionam lá dentro (LINE, ERASE, MOVE, outro BLOCK aninhado...). "Save" grava de volta na definição e atualiza todas as instâncias no desenho principal automaticamente. Ver limitações na seção "Blocos e referências" abaixo
- **Referências externas (`XREF`/`XR`, `EXTERNALREFERENCES`/`ER`)**: XREF anexa um `.dxf` externo como uma `BlockReference` marcada (`is_xref=True`); o painel EXTERNALREFERENCES lista as xrefs do desenho (nome + caminho) com um botão Reload que relê o arquivo. **Sem watch automático de arquivo** — ver limitações abaixo
- **Imagem raster (`IMAGEATTACH`/`IM`)**: insere `.png`/`.jpg`/`.bmp` como `ImageReference` (ponto de inserção + largura/altura), renderizada via `QGraphicsPixmapItem`. **Não é gravada em `.dxf`** — ver limitações
- **Exportar PDF (`PLOT`, `PUBLISH`, File > Print/Export PDF..., Ctrl+P)**: renderiza o desenho inteiro (não só o que está visível na tela) numa página PDF via `QPdfWriter`, perguntando antes o **tamanho da folha** (A4/A3/A2/A1/A0) e a **orientação** (automática — escolhe retrato ou paisagem pela proporção do desenho, igual a um PLOT com "Fit" — ou fixa em retrato/paisagem)
- **Painel de Camadas redesenhado (`LAYER`/`LA`, View > Layers..., aba View do ribbon)**: lista todas as camadas do desenho (vem tabificado com o painel Properties) com **botões-ícone de lâmpada/cadeado** (visibilidade/trava, em vez dos checkboxes de antes — mesmo visual do Layer Properties Manager do AutoCAD) e uma coluna de **cor** (swatch clicável, abre um seletor de cor), e duplo clique no nome define a **camada atual** (onde LINE/CIRCLE/ARC/MTEXT/cotas/BLOCK/INSERT novos são desenhados). Desligar a visibilidade tira a entidade do desenho de verdade (some da tela, do hit-test/seleção e do zoom extents/Export PDF), não só "esconde visualmente"; travar mantém visível mas bloqueia seleção. Botão "Nova camada..." cria uma camada vazia; clique direito numa camada (ou o comando `RENAME`/`REN`) renomeia
- **Cor por camada/entidade agora afeta o desenho de verdade** — antes disso, `Layer.color`/`Entity.color` existiam no modelo mas o canvas sempre desenhava tudo na mesma cor fixa (limitação documentada explicitamente no painel de camadas, que por isso nem oferecia editar cor). `CanvasView._effective_color` resolve a cor real de cada entidade (a própria, se não for ByLayer, senão a da camada) e é usada tanto na renderização quanto restaurada corretamente ao desselecionar — inclusive dentro de um `BlockReference`, onde cada entidade filha pode estar numa camada/cor diferente das outras
- **`LAYMCH`, `LAYISO`/`LAYUNISO`, `QSELECT`**: `LAYMCH` muda só a camada dos objetos de destino pra igualar a de um objeto de origem (`MATCHPROP` também copia cor); `LAYISO`/`LAYUNISO` escondem todas as camadas exceto as dos objetos selecionados e revertem o isolamento mais recente (estado de sessão, não salvo no `.dxf`); `QSELECT` é uma versão simplificada — filtra por tipo de entidade digitado (Line, Circle...), não pelo diálogo completo de propriedade+operador+valor do QSELECT de verdade
- **Comandos utilitários adicionados do guia oficial de atalhos do AutoCAD**: `AREA`(AA) soma área/perímetro de círculos e polilinhas fechadas selecionados; `ID` mostra as coordenadas de um ponto clicado; `DDEDIT`(ED) edita o conteúdo de um `Text` já colocado no desenho (só `Text` — cotas não têm campo de texto sobreposto no modelo, ver limitações); `PURGE`(PU) remove camadas e blocos não usados em lugar nenhum do desenho; `PAN` ganhou o alias de uma letra `P`
- **Clipboard do Windows (`COPYCLIP`/Ctrl+C, `CUTCLIP`/Ctrl+X, `PASTECLIP`/Ctrl+V)**: copia/recorta os objetos selecionados pro clipboard do sistema operacional (num MIME type próprio, `application/x-newsicad-entities`) e cola de volta na posição escolhida — funciona entre abas de documento diferentes e até entre duas instâncias do NewSIcad abertas ao mesmo tempo, no mesmo computador. Não gera nenhum formato de imagem/texto junto, então colar num Word/Excel depois de um Ctrl+C no NewSIcad não traz nada (e vice-versa)
- **CLIP/XCLIP (`CLIP`, `CLIPOFF`)**: recorta a área visível de um bloco, referência externa (XREF) ou imagem — dois cliques definem um retângulo, tudo fora dele deixa de aparecer. `CLIPOFF` remove o recorte. Só contorno retangular (o XCLIP de verdade também aceita polígono à mão livre); o contorno acompanha o objeto se ele for movido/rotacionado/escalado depois, mas hit-test/seleção/zoom-extents continuam considerando a geometria INTEIRA (não só a parte visível recortada) — ver limitações
- **FIELD**: insere um `Text` vinculado a um valor calculado (`Area`/`Length` de uma entidade selecionada, ou `Date` de hoje) em vez de digitado — o valor é recalculado a cada redesenho, então continua correto se a entidade referenciada for editada depois (mostra `#REF!` se ela for apagada). Sem o `Filename` do FIELD de verdade do AutoCAD (exigiria plumbing do caminho do arquivo até a camada de comandos, que hoje só conhece o `Document`) e sem os outros dezenas de tipos de campo do AutoCAD (nenhum análogo de propriedade de folha/bloco/objeto além de área/comprimento). O valor gravado no `.dxf` é só o último calculado — reabrir um `.dxf` não recupera o vínculo vivo, ele volta a ser texto estático (ver README, mesmo padrão de outras simplificações de round-trip)

- **Edição geométrica (`TRIM`/TR, `EXTEND`/EX, `OFFSET`/O, `FILLET`/F, `CHAMFER`/CHA, `JOIN`/J, `EXPLODE`/X, `STRETCH`/S, `DIVIDE`/DIV, `MEASURE`/ME)**: geometria real de interseção/corte (segmento-segmento, segmento-círculo, círculo-círculo) — `FILLET`/`CHAMFER` cobrem Line-Line (com sub-opção `[Radius]`/`[Distance]`), `EXTEND` estende até um alvo do tipo Line, `OFFSET` cobre Line/Circle/Arc/LWPolyline (polilinha via aproximação por interseção de linhas de apoio), `STRETCH` usa uma janela crossing explícita. `DIVIDE`/`MEASURE` marcam os pontos com `PointEntity` de verdade — ver detalhes/limitações na seção "Edição geométrica" abaixo
- **BREAK**(BR) / **Break at Point**: `BREAK` remove o trecho entre dois pontos clicados de uma Line/Arc/Circle (Circle vira Arc, igual ao TRIM); sub-opção `[First point]` permite reescolher o primeiro ponto depois de já ter clicado no objeto. "Break at Point" (menu Modify — sem alias curto, igual ao AutoCAD, que também não tem um pra este) divide Line/Arc em dois pedaços no mesmo ponto sem remover material (Circle não é um alvo válido)
- **LENGTHEN**(LEN): sub-opções `[DElta/Percent/Total]` (igual ao AutoCAD) alteram o comprimento de uma Line ou o arco (comprimento = raio × ângulo) de um Arc, a partir da ponta mais próxima do clique — a outra ponta fica fixa
- **OSNAP e POLAR reais**: `OSNAP` calcula Endpoint/Midpoint/Center/Intersection/Node(`PointEntity`)/Insert(ponto de inserção de `BlockReference`) de verdade a partir das entidades próximas ao cursor (com prioridade sobre ORTHO/POLAR/grid-snap), `POLAR` trava em incrementos de 15°; ambos com marcador visual no canvas e toggle funcional (F3/F10). Sem Perpendicular/Tangent/Nearest/Quadrant ainda, e sem diálogo pra ligar/desligar tipos individualmente (é tudo-ou-nada via F3) — falta `DSETTINGS`
- **POLYGON** (POL): polígono regular como LWPolyline fechada — número de lados, centro, opção `[Inscribed/Circumscribed]` e raio, igual ao POLYGON do AutoCAD
- **ALIGN** (AL): move + rotaciona (e, opcionalmente, escala) os objetos selecionados a partir de um par de pontos origem/destino — modo 2 pontos do ALIGN de verdade (o modo de 3 pontos/3D não se aplica a um CAD só 2D)
- **ARRAY** (AR): array retangular (linhas × colunas + espaçamento) ou polar (centro + número de itens + ângulo a preencher); cada cópia é uma entidade independente, sem edição associativa depois de criado
- **MATCHPROP** (MA): copia layer e cor de um objeto de origem para os objetos de destino selecionados (simplificação: só layer/cor, não estilos de texto/cota/hachura)
- **SELECTSIMILAR** (SIM): seleciona um objeto de referência e marca todos os outros do mesmo tipo no desenho (simplificação: compara só o tipo da entidade, não layer/cor/linetype como no AutoCAD)
- **SPLINE** (SP): curva suave por pontos de ajuste (entidade `Spline` dedicada), com opção `[Close]`. Não é uma NURBS de verdade (sem vetor de nós/pesos) — é uma curva interpolante por Catmull-Rom (`geometry_ops.catmull_rom_bezier`), que passa exatamente pelos pontos informados e é visualmente suave; gravada/lida como `SPLINE` de verdade no `.dxf` (com `fit_points`), abre corretamente em outros programas CAD
- **BOUNDARY** (BO): gera uma `LWPolyline` fechada a partir de um ponto clicado dentro de uma área. Cobre três casos: ponto dentro de uma `LWPolyline` já fechada (cópia independente), dentro de um `Circle` (aproximado como polígono de 64 lados) ou dentro de um laço fechado **simples** de `Line` soltas — ex.: paredes de um ambiente (ver `geometry_ops.trace_simple_line_loop`). **Não resolve laços com bifurcação/junção em T** (ex.: parede interna encostando numa externa) — nesse caso nenhum contorno é encontrado nesse trecho, em vez de arriscar gerar uma geometria errada
- **PEDIT** (PE): edição básica de uma `LWPolyline` já desenhada, em loop de opções `[Close/Open/Add vertex/Remove vertex/eXit]`. Sem o submenu completo de edição de vértice do AutoCAD de verdade (Next/Previous/Break/Tangent...), que dependeria de marcadores de vértice interativos no canvas — "Add vertex" sempre acrescenta no final da polilinha (não insere no meio), "Remove vertex" remove o vértice mais próximo do ponto clicado
- **HATCHEDIT** (HE): edita ângulo e espaçamento de uma hachura já desenhada — como o `HATCH` nunca expôs esses parâmetros (sempre usava os valores padrão), HATCHEDIT é o primeiro jeito de ajustá-los. Não reatribui o contorno (apague e refaça com HATCH/BOUNDARY pra isso)
- **Proteção contra perda de trabalho não salvo**: fechar a janela, `File > New` e `File > Open` agora perguntam "Salvar alterações em ...?" `[Save/Discard/Cancel]` quando há alterações não gravadas — antes, as três ações descartavam o desenho em silêncio (bug real reportado por um usuário). Detecção por snapshot profundo do documento (entidades/camadas/unidades/blocos) comparado ao estado do último save/load, não por sinalizar cada comando individualmente — cobre qualquer forma de alteração, incluindo as que mutam entidades diretamente (MOVE/ROTATE/etc.) sem passar pelos métodos de `Document`. Corrigido de brinde: `File > New` agora reseta o arquivo atual e a pilha de undo (antes, um "New" seguido de Ctrl+S podia sobrescrever silenciosamente o arquivo anterior)

Ainda não implementado (próximos marcos): `REGION`, `STYLE`, `GEOMCONSTRAINT`, `DSETTINGS`, `DVIEW`, `DIM`/`DIMEDIT`/`DIMREASSOCIATE`, `OPTIONS`, Object Snap Tracking (`OTRACK` — botão desativado na barra de status até ter uma implementação de verdade, ver limitações), gravação de `.dwg` (ver nota abaixo). `TRIM` ainda não tem undo dentro do próprio comando (só o Ctrl+Z do desenho inteiro).

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
- **`VIEWPORTS`/`VM` (Viewport Configuration)**: a decisão original deste
  projeto era não implementar (um viewport de verdade vive numa layout de
  papel/paper space, conceito que o NewSIcad não tem, e uma versão
  simplificada pareceria um gadget de zoom duplicado sem paralelo real no
  AutoCAD). Essa decisão foi **revertida** — hoje `VIEWPORTS`/`VM` (menu
  View, `MainWindow._show_vports_dialog`) divide a aba atual em 1/2/4
  viewports lado a lado (Single/Two: Vertical/Two: Horizontal/Four: Equal),
  cada uma com zoom/pan/grid/snap próprios — a "Viewport Configuration"
  clássica de espaço de modelo do AutoCAD (tiled viewports), não os
  viewports flutuantes de paper space (que o NewSIcad continua sem ter).
  Simplificação documentada: só a PRIMEIRA viewport (esquerda/topo) recebe
  clique/comando — as demais são só de referência visual, sincronizadas por
  timer (não em tempo real estrito).
- **`PLOT`/`PUBLISH` não distinguem folhas**: como não há layouts/paper
  space, os dois comandos fazem exatamente a mesma coisa (uma única página
  PDF com o desenho inteiro) — no AutoCAD real, PUBLISH lida com múltiplas
  folhas/layouts, o que não existe aqui.
- **Export PDF não tem escala real definida**: o desenho é sempre ajustado
  pra caber na folha escolhida ("Fit"), não numa escala técnica como 1:50 ou
  1:100 — o tamanho de folha (A4-A0) e a orientação são escolhidos antes de
  exportar, mas a escala do desenho dentro da folha não é controlável ainda.
- **MIRROR de um `BlockReference` agora é um espelhamento exato** (limitação
  antiga resolvida): `BlockReference` passou a modelar escala POR EIXO
  (`scale`/`scale_y`, inclusive negativa = espelhado) — necessário de
  qualquer forma pra ler blocos dinâmicos de `.dwg` reais (ver seção
  "Arquivos `.dwg`") — e o MIRROR usa a identidade
  refl(α)·rot(θ)·scale(sx,sy) = rot(2α−θ)·scale(sx,−sy) pra inverter o
  conteúdo do bloco de verdade, pra qualquer eixo de espelho.
- **CLIP/XCLIP não persiste no `.dxf`**: `clip_boundary` é um atributo só do
  NewSIcad (não existe campo equivalente simples no formato DXF sem entrar em
  `ACAD_FILTER`/`SPATIAL_FILTER`, fora de escopo aqui) — salvar e reabrir um
  desenho com um objeto recortado faz o recorte sumir (volta a mostrar o
  bloco/xref/imagem inteiro). Além disso, hit-test/seleção/zoom-extents usam
  sempre a geometria INTEIRA do objeto, não só a parte visível dentro do
  recorte — clicar numa área "cortada fora" ainda seleciona o objeto.

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

`HATCH` (desde 2026-09-01): o `Hatch` do NewSIcad guarda TODOS os contornos
(`boundary_paths`: externo + furos/ilhas, arestas curvas já achatadas em
polígonos) e é gravado com um anel por contorno (o 1º com flag *external*,
os demais *outermost*, preenchidos em regra even-odd); uma hachura sólida vai
como `HATCH` com `solid_fill` na cor da própria entidade; o comando `WIPEOUT`
(`Hatch.wipeout=True`) vai como entidade `WIPEOUT` de verdade — antes era uma
`HATCH` sólida na cor do fundo do canvas, que abria como um borrão cinza no
AutoCAD. O nome do padrão de origem (`pattern_name`, ex.: `AR-CONC`) é
regravado se o ezdxf o conhecer (senão `ANSI31`), mas o canvas desenha todo
padrão como linhas paralelas (`angle`/`spacing`) — fidelidade visual, não
exata. A cor `BYBLOCK` (cor 0 do DXF) é um sentinel próprio em
`Entity.color` (`core/entities.py:BYBLOCK`) e faz round-trip como cor 0.

### Textos, leaders, cotas e tabelas de arquivos externos (WP-B, 2026-09)

Segunda leva do relato "os textos não vieram / tabelas explodidas / planta explodida" dos testers, diagnosticada por experimento nas plantas reais da New SI (metros e milímetros). Cada parágrafo abaixo é uma causa-raiz distinta:

- **Texto invisível no Windows** (a principal): o canvas fazia `font.setPointSizeF(altura CAD)` — 0.18 m virava 0.18 pt, e no Windows uma fonte com menos de 1 px não pinta nada e mede 0x0 (84-88% dos textos das plantas em metros sumiam; em mm o hinting quebrava "LEG ENDA"). A plataforma `offscreen` da suíte e o macOS clampam em ~1 px e escalam, por isso nunca falhou em teste. Agora `Text` é um `QGraphicsPathItem` com os contornos de uma fonte de referência fixa (100 px) escalados por `altura / capHeight` (`newsicad/ui/canvas.py:text_layout`) — a tinta de um "H" tem exatamente a altura CAD em qualquer plataforma (razão medida 0.98-1.0 de h=2.5 até h=0.01), o piso `max(h, 0.1)` foi removido (h ≤ 1e-6 não desenha, como no AutoCAD), e seleção/bbox/zoom extents usam as métricas reais da fonte em vez de "0.6·h por caractere". A mesma receita vale pro texto das cotas e das células de `TABLE`. `tests/test_text_render.py` inclui um teste que roda num subprocesso com `QT_QPA_PLATFORM=windows` de verdade (pulado fora do Windows).
- **TEXT/ATTRIB no lugar errado**: o ponto 10 do TEXT é esquerda-*baseline* e, pra qualquer alinhamento diferente de LEFT, a âncora real é o ponto 11 (`align_point`) — o leitor usava sempre o 10 com justify "TL". Agora `get_placement()` do ezdxf mapeia halign/valign pra `Text.justify` (LEFT→BL, CENTER→BC, MIDDLE→MC, TOP_*→T?, …), e no NewSIcad a linha "B?" ancora a linha de base (convenção do TEXT do DXF; a diferença pro "bottom" do MTEXT, ~0.2·h, é aceita ao gravar tudo como MTEXT). Estilo, rotação e fator de largura do TEXT também passaram a ser lidos.
- **MTEXT girado ficava horizontal e parágrafos atravessavam a prancha**: o `dwg2dxf` grava a rotação do MTEXT só como `text_direction` (código 11), nunca como o 50 que o leitor olhava; e a largura da caixa (41) era ignorada. `Text` ganhou `width` (0 = sem quebra) e `line_spacing_factor`; o canvas quebra cada parágrafo por palavras nessa largura (`QFontMetricsF`) antes de justificar, e `save_dxf` grava os dois de volta.
- **MULTILEADER e LEADER eram descartados; cotas externas re-renderizadas com DIMSTYLE fixo** (texto 2.0/tick 0.6 em unidades do desenho — 20x maiores que a planta em metros, cobrindo tudo; overrides de texto perdidos; angulares descartadas). Novo módulo `newsicad/io/dxf_annotations.py`: essas anotações (e `ACAD_TABLE`) são importadas pela geometria PRONTA que o AutoCAD já gravou (`virtual_entities()` do ezdxf: linhas, textos, setas como hachura sólida, blocos), empacotada num bloco anônimo por anotação (`*ML_/*LD_/*D_/*T_<handle>`) com uma `BlockReference` em (0,0) na camada/cor da original — um objeto só, selecionável/movível/apagável como no AutoCAD. **Cota importada é estática** (não re-mede ao mover pontos): só uma `Dimension` gravada pelo próprio NewSIcad (XDATA `NEWSICAD`) volta como cota nativa. Ao gravar, esses blocos saem como anônimos `*U<n>` válidos e voltam iguais. O tamanho de texto/seta das cotas nativas (`Document.dim_style`) agora acompanha o arquivo — mediana da altura real das cotas importadas, senão `$DIMTXT·$DIMSCALE`/`$DIMASZ` — e é gravado no cabeçalho e como override das cotas salvas.
- **ACAD_TABLE**: o `dwg2dxf` 0.14 descarta a entidade (sobra um bloco `*T…` órfão — caso do arquivo JOAO E BRENDA); quando ela existe no `.dxf`, vira `BlockReference` como acima. A ponte `.dwg` passou a contar o aviso `Unhandled Class entity … ACAD_TABLE` do `dwg2dxf` e mostrá-lo no aviso de abertura ("descartada pelo dwg2dxf").
- **ATTRIB aninhado**: etiquetas de INSERT dentro de definição de bloco (225 na R04) não eram promovidas a `Text` — agora são, no espaço do bloco pai; texto com altura ≤ 1e-6 é descartado na leitura.
- **Fontes SHX**: `romans.shx`/`txt`/`simplex` (e o "Menlo" padrão) caíam na fonte padrão do Qt (Tahoma no Windows, 30-50% mais larga, invadindo células de legenda). `TextStyle` guarda `font_file` e `width`; o canvas substitui SHX/desconhecida por uma TTF instalada estreitada (`Arial` com `setStretch(85)`), mantém TTF quando existe e aplica o width do STYLE e o do TEXT via `setStretch`.

### Edição geométrica — simplificações documentadas

- **FILLET/CHAMFER**: só Line-Line (Line-Arc é bônus não implementado). FILLET não suporta raio 0 (corte de canto sem arco) — exige um raio positivo via `[Radius]`.
- **EXTEND**: só estende objetos Line (Arc/Circle como alvo fica pra uma versão futura; podem ser usados como boundary edges normalmente).
- **TRIM**: `[Undo]` dentro do comando ainda não desfaz o último corte — use Ctrl+Z depois de terminar o comando.
- **OFFSET de LWPolyline**: aproximação por interseção das retas suporte de cada segmento deslocado; não trata perfeitamente polilinhas que colapsam ou auto-intersectam após o offset (falha com mensagem clara no log em vez de travar).
- **Hit-test de TRIM/EXTEND/OFFSET sem CanvasView** (ex.: uso programático/testes): cai num fallback de tolerância fixa (0.5 unidade de desenho) em `geometry_ops.nearest_entity` em vez da tolerância em pixels da UI real.
- **DIVIDE/MEASURE**: pontos de divisão representados por `Circle` de raio fixo (0.05), já que não existe um tipo `POINT` no NewSIcad ainda.

### Camadas — simplificações documentadas

- **Sem cor por camada na tela**: `Layer.color` existe no modelo (grava/lê certinho de `.dxf`) mas o canvas nunca usou cor nenhuma pra desenhar entidades — é sempre um branco fixo (`ENTITY_COLOR`), então o painel de camadas não oferece editar cor: seria um controle que muda o dado sem nenhum efeito visível.
- **Apagar camada** ainda não tem UI — só criar (`Nova camada...`), renomear, ligar/desligar visibilidade, travar, definir qual é a atual, e `PURGE` (remove só camadas sem nenhuma entidade, não uma remoção forçada).
- Corrigido junto com o painel: `document.current_layer` (a camada onde entidades novas são desenhadas) **nunca funcionou de verdade** antes disso — nenhum comando de desenho passava `layer=` explicitamente ao criar a entidade, e como o valor padrão do dataclass `Entity.layer` é `"0"` (não vazio), o fallback de `Document.add_entity` pro current_layer nunca disparava. Toda entidade nova ia sempre para a camada "0", não importa o que estivesse selecionado como atual. Corrigido em `draw_commands.py`, `annotation_commands.py` e `block_commands.py` (`modify_commands.py` não precisou de mudança — COPY/TRIM/FILLET/etc. já preservavam corretamente a camada da entidade original, o que é o comportamento certo).
- **`AREA`(AA) não tem o modo "clicar pontos pra definir um polígono"** do AREA de verdade do AutoCAD — só soma a área de círculos e polilinhas fechadas já desenhados que forem selecionados (o caso de uso mais comum: contorno de um ambiente já desenhado como `PLINE` fechada).
- **`DDEDIT`(ED) só edita `Text`** (MTEXT/LEADER) — cotas (`Dimension`) não têm um campo de texto sobreposto no modelo do NewSIcad (o texto exibido é sempre calculado a partir da medição real geometricamente), então selecionar uma cota no ED não faz nada.

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

**Blocos dinâmicos do AutoCAD são suportados na leitura** (correção de 2026-08-28, o bug real da "planta explodida" reportado pelos testers): o AutoCAD materializa a representação de cada bloco dinâmico em blocos ANÔNIMOS `*U...`, e num `.dwg` real de arquiteto a maioria dos símbolos de infraestrutura (tomada, CFTV, som, rede...) vira um INSERT apontando pra um desses. O leitor de `.dxf` antigo descartava toda definição com nome começando em `*` — num arquivo real testado, 77% dos blocos do desenho renderizavam como grupos vazios. Diagnóstico importante documentado aqui pra não re-investigar no futuro: **a conversão `.dwg`→`.dxf` em si nunca foi o problema** — a saída do LibreDWG foi comparada bloco a bloco com a de um segundo conversor comercial independente (CloudConvert, engine `cadconverter` 8.10) no mesmo arquivo e as duas eram idênticas em escala de instância e geometria de definição; os avisos de "unstable class" que o `dwg2dxf` emite se referem a METADADOS dos blocos dinâmicos (`ACDB_BLOCKREPRESENTATION_DATA` etc., que nenhum conversor traduz), mas a geometria das representações está toda presente no `.dxf`. Junto com isso: `BlockReference` ganhou escala POR EIXO (`scale_y`, inclusive negativa = espelhado — blocos dinâmicos esticados/flipados precisam disso), ATTRIBs (etiquetas/valores preenchidos dos blocos) viram entidades `Text` na leitura (simplificação: sem vínculo com o bloco — mover o bloco depois não arrasta a etiqueta), e ATTDEF deixou de contar no aviso de "entidades não suportadas". Blocos internos `*Model_Space`/`*Paper_Space`/`*D...`(cotas)/`*X...`(hachuras) continuam fora, como antes.

**Desempenho em arquivos grandes** (mesma auditoria de 2026-08-28): o canvas reconstruía TODOS os itens gráficos da cena a cada passo de qualquer comando (num `.dwg` real com ~7 mil entidades → ~47 mil itens, isso custava 6-8s por clique), e repintava a viewport inteira a cada movimento do mouse. Agora `refresh_entities` é incremental — cada entidade tem uma "impressão digital" (repr + cor efetiva + conteúdo da definição do bloco) e só o que mudou é recriado (medido: ~0,65s por refresh no mesmo arquivo, ~10x mais rápido, e proporcionalmente menos em desenhos normais) — e o movimento do mouse só invalida as faixas do crosshair + uma caixa ao redor do cursor, não a viewport inteira.

**Preenchimentos, cores de bloco, ordem de desenho e geometria OCS** (auditoria de 2026-09-01 com oito `.dwg` reais da New SI — o relato dos testers era "ícones das legendas vieram brancos/vazios, o rack não veio, hachuras incompletas, planta explodida"). Tudo o que segue vive em `newsicad/io/dxf_fills.py` (auxiliares chamados por `dxf_io.py`) e nos ramos de Hatch/bloco/cor/ordem de `newsicad/ui/canvas.py`:

- **Hachura sólida não é mais WIPEOUT.** O canvas tratava QUALQUER `Hatch.solid_fill` como o comando WIPEOUT (pintado na cor do fundo, por cima de tudo) — o corpo de todo ícone da biblioteca (blocos cheios de `HATCH` sólidas coloridas) sumia e ainda cobria as linhas/textos do próprio bloco. Agora só `Hatch.wipeout` é WIPEOUT; uma hachura sólida é pintada na cor efetiva da entidade, na ordem normal de desenho.
- **`HATCH` com vários contornos e arestas curvas.** O leitor lia só o 1º contorno e só o `start` de cada aresta (que arestas de arco/elipse/spline não têm): hachuras com contorno só de arcos eram descartadas (69 numa planta, 167 no quadro de automação, 846 na instalação fina) e furos/ilhas eram preenchidos. Agora cada contorno é achatado pelo `ezdxf.path` (tolerância = extensão/200) e os furos ficam vazios (even-odd) tanto no sólido quanto nas linhas do padrão. SPLINE de contorno com vetor de nós inconsistente (o ezdxf recusa; 5 casos reais) cai nos pontos de controle em vez de perder a hachura.
- **`BYBLOCK` e camada "0" herdam do INSERT**, regra do AutoCAD que a biblioteca de símbolos usa em massa: cor 0 (BYBLOCK) era descartada e filho ByLayer na camada "0" saía na cor da camada 0 (branco). `CanvasView._effective_color(entity, inherited)` resolve — cor própria → ela; BYBLOCK → cor efetiva do INSERT; ByLayer na camada "0" → cor da camada do INSERT; ByLayer em outra camada → cor dela — e `_create_block_reference_item` propaga (cor, camada) do INSERT pros filhos e pros blocos aninhados; filho na camada "0" segue a visibilidade da camada do INSERT, filho em camada desligada não é desenhado.
- **`SOLID`/`TRACE` viram hachura sólida** na cor da entidade (169 `SOLID` num único `.dwg` de rack eram "não suportados"); **`WIPEOUT` do arquivo vira `Hatch(wipeout=True)`**.
- **Ordem de desenho.** O `.dxf` é percorrido em `entities_in_redraw_order()` (tabela SORTENTS do AutoCAD) e o canvas empilha os itens na ordem do dict do documento (`zValue` = posição × 1e-6, abaixo de qualquer camada de UI) — um WIPEOUT cobre só o que estava atrás dele quando foi criado, e o comando WIPEOUT continua por cima do que já existia porque entra no fim do documento.
- **Extrusão (OCS).** `ARC`/`CIRCLE`/`LWPOLYLINE`/`INSERT` com `extrusion` (0,0,-1) (é assim que o AutoCAD grava o que foi espelhado com MIRROR) eram lidos como se fossem WCS: 175 arcos de uma planta caíam em x≈-2600 e o zoom-extents abria o desenho a 9% da tela. Agora centro/pontos passam por `OCS.to_wcs`; arco espelhado troca início/fim; INSERT espelhado vira `xscale` negativa + rotação invertida (conferido contra `Insert.virtual_entities()` do ezdxf). Um `ELLIPSE` PARCIAL (arco de elipse — `start_param`/`end_param`, que o leitor antigo nem lia e fechava a elipse) é aproximado por uma `LWPolyline` achatada, porque a entidade `Ellipse` do NewSIcad não modela arco parcial — simplificação documentada.
- **Blocos com "_" no nome são carregados.** O filtro "qualquer nome começando com sublinhado" (pensado pros blocos de seta que o ezdxf cria pra cotas) derrubava blocos reais da biblioteca (`_PRANCHA_LEGENDA` = o selo da prancha, `_SIMBOLO_USB`); agora o filtro é o conjunto explícito `dxf_fills.EZDXF_ARROW_BLOCKS`. `BLOCK` com `base_point` ≠ 0 tem o ponto base subtraído dos filhos (inclusive INSERTs aninhados); `INSERT` sem nome conta como ignorado.
- **True color** (grupo 420) tem prioridade sobre o ACI na leitura. `HATCH` com padrão vinda de outro programa usa o ângulo/espaçamento da 1ª família de linhas gravada no arquivo; sem definição, `pattern_scale × 3,175 mm` convertido pra unidade do desenho (`$INSUNITS`: metros → 0,003175). No canvas o número de linhas por hachura é limitado a 2.000 (acima disso o espaçamento abre proporcionalmente) — um dos `.dwg` da auditoria tem 2.500 hachuras.

**Gravação nativa de `.dwg` (via LibreDWG) não está disponível.** O gravador do LibreDWG (`dxf2dwg`) foi testado em quatro releases — 0.13.3 (Homebrew), 0.14 (compilada localmente a partir do código-fonte), e o release oficial **0.14.1** (nightly [0.14.8492](https://github.com/LibreDWG/libredwg/releases/tag/0.14.8492), 25/07/2026) — e se mostrou não confiável em todas: produz arquivos `.dwg` com handles duplicados (`ERROR: Duplicate handle ... already points to object ...`) em todas as versões de destino testadas. Investigação de código (sem compilar) apontou a causa: `dwg_next_handle()` em `src/dwg.c` não calcula o maior handle já em uso corretamente, e o parser de passagem única do `dxf2dwg` monta handles sintéticos sem saber quais handles explícitos ainda vão aparecer mais adiante no `.dxf` — um bug estrutural do parser, não um ajuste pontual, consistente com o issue upstream ([libredwg#192](https://github.com/LibreDWG/libredwg/issues/192)) estar aberto desde 2020. Também foram descartadas as alternativas óbvias: **ODA File Converter** proíbe no próprio EULA ser empacotado dentro de outro software distribuído (redistribuição, não só uso comercial); **QCAD** (open source) não tem suporte a `.dwg` na edição livre, só no Professional pago; **Aspose.CAD** resolveria mas é uma licença paga recorrente.

**Exportação de `.dwg` via CloudConvert (`File > Export DWG...`)** — o caminho adotado. `newsicad/io/dwg_export.py` chama a API do [CloudConvert](https://cloudconvert.com) (upload do `.dxf` → conversão → download do `.dwg`), sem nenhum binário pra empacotar ou instalar — ao contrário da ODA, os termos do CloudConvert permitem esse uso embutido. Troca real, aceita conscientemente pelo uso interno/arquivo da New SI: precisa de internet no momento da exportação, e o desenho sai da máquina até o servidor deles. A versão de saída não é configurável (o engine `cadconverter` não expõe essa opção documentada) — testado empiricamente, produz `.dwg` assinatura `AC1018` (AutoCAD 2004), compatível com qualquer AutoCAD/BricsCAD atual.

Precisa de uma API key do CloudConvert (conta própria da New SI, `suporte@newsi.com.br`) configurada via variável de ambiente `NEWSICAD_CLOUDCONVERT_API_KEY` **ou** um arquivo `cloudconvert_api_key.txt` — na raiz do repo em modo desenvolvimento, ou ao lado do `NewSIcad.exe` no `.exe` distribuído (precisa ser copiado manualmente em cada máquina; nunca commitado no git, está no `.gitignore`). Tier gratuito: até 10 conversões/dia, 25MB/arquivo; acima disso é pré-pago (US$8/100 créditos, sem expirar).

File > Save/Save As continuam gravando só `.dxf` — a exportação `.dwg` é uma ação separada, sob demanda, não o formato nativo do NewSIcad.

**Cache de abertura e avisos do arquivo (v2.14.0).** Abrir um `.dwg` grande custa dezenas de segundos e quase tudo é o parser DXF puro-Python do ezdxf (medido: 24 s dos ~32 s da planta Casa Pau Brasil só no `ezdxf.readfile`; o DXF binário do `dwg2dxf -b` foi testado e ganha só 12%, não compensa). Como os testers reabrem o mesmo arquivo várias vezes, o `Document` já lido vai para um cache em `%LOCALAPPDATA%\NewSIcad\cache` (`newsicad/io/open_cache.py`, chave = caminho + tamanho + data do arquivo + versão do app, 20 entradas mais recentes) e a segunda abertura volta em poucos segundos; o cursor vira ampulheta enquanto lê. Na abertura, além do aviso de entidades não suportadas, a linha de comando agora lista os **layouts (pranchas em paper space) com conteúdo que o NewSIcad ainda não exibe** — selo, legenda e tabelas das pranchas da New SI moram lá — e as **XREFs não carregadas** (a base arquitetônica costuma ser uma referência externa a outro `.dwg` que não vem junto; foi o caso da planta Joe Lee, `BASE_XREF_LEE`). Exibir paper space fica para uma próxima versão.

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
| POLYGON | POL | Desenha polígono regular (lados, centro, inscrito/circunscrito, raio) |
| SPLINE | SP | Desenha curva suave por pontos de ajuste (opção `[Close]`) |
| BOUNDARY | BO | Gera uma LWPolyline fechada a partir de um ponto clicado dentro de uma área |
| POINT | PO | Cria um ponto real (`PointEntity`) |
| XLINE | XL | Linha de construção infinita nas duas direções |
| RAY | — | Linha de construção infinita numa única direção |
| MLINE | ML | Parede de duas LWPolyline paralelas (largura + eixo) |
| DONUT | DO | Anel preenchido (diâmetro interno/externo + centro) |
| REVCLOUD | — | Nuvem de revisão (arcos estufados entre pontos clicados) |
| WIPEOUT | — | Área que oculta o que está atrás dela |
| DIST | DI | Mede distância e ângulo entre 2 pontos |
| AREA | AA | Soma área/perímetro de círculos e polilinhas fechadas selecionados |
| ID | — | Mostra as coordenadas X/Y de um ponto clicado |
| ERASE | E | Apaga objetos selecionados |
| MOVE | M | Move objetos selecionados |
| COPY | CO / CP | Copia objetos selecionados |
| ROTATE | RO | Rotaciona objetos selecionados (ângulo digitado) |
| SCALE | SC | Escala objetos selecionados (fator digitado) |
| MIRROR | MI | Espelha objetos selecionados |
| ALIGN | AL | Alinha objetos por um par de pontos origem/destino (2 pontos, com escala opcional) |
| ARRAY | AR | Cria array retangular (linhas/colunas) ou polar (centro/itens/ângulo) |
| MATCHPROP | MA | Copia layer/cor de um objeto de origem para os destinos selecionados |
| SELECTSIMILAR | SIM | Seleciona todos os objetos do mesmo tipo do objeto de referência |
| QSELECT | — | Seleciona por tipo de entidade digitado (versão simplificada) |
| LAYMCH | — | Muda a camada dos destinos pra igualar a de um objeto de origem |
| LAYISO | — | Esconde toda camada exceto as dos objetos selecionados |
| LAYUNISO | — | Reverte o LAYISO mais recente |
| CENTERMARK | DIMCENTER | Marca cruzada no centro de um Circle/Arc |
| DIMBREAK | — | Interrompe a linha de cota onde cruza objetos selecionados |
| TABLE | TB | Grade uniforme de células com texto |
| FIELD | — | Texto vinculado a um valor ao vivo (`Area`/`Length`/`Date`) |
| COPYCLIP | — | Copia objetos selecionados pro clipboard do Windows (Ctrl+C) |
| CUTCLIP | — | Como COPYCLIP, mas apaga os objetos do desenho (Ctrl+X) |
| PASTECLIP | — | Cola do clipboard na posição escolhida (Ctrl+V) |
| CLIP | XCLIP | Recorta a área visível de um bloco/xref/imagem (contorno retangular) |
| CLIPOFF | — | Remove o contorno de recorte aplicado por CLIP |
| TRIM | TR | Apara objetos até a aresta de corte mais próxima |
| EXTEND | EX | Estende uma Line até a borda mais próxima |
| OFFSET | O | Cria cópia paralela deslocada (distância + lado) |
| FILLET | F | Arredonda o canto entre duas Lines (opção `[Radius]`) |
| CHAMFER | CHA | Corta o canto entre duas Lines com uma reta (opção `[Distance]`) |
| JOIN | J | Funde Lines colineares e conectadas numa só |
| EXPLODE | X | Quebra uma LWPolyline em Lines individuais |
| STRETCH | S | Move vértices dentro de uma janela crossing |
| BREAK | BR | Remove o trecho entre dois pontos clicados (opção `[First point]`) |
| BREAKATPOINT | — | Divide num ponto sem remover material (Line/Arc) |
| LENGTHEN | LEN | Altera comprimento (`[DElta/Percent/Total]`) a partir da ponta mais próxima |
| PEDIT | PE | Edita uma polilinha: `[Close/Open/Add vertex/Remove vertex/eXit]` |
| DIVIDE | DIV | Marca N pontos de divisão iguais (`PointEntity`) |
| MEASURE | ME | Marca pontos por comprimento fixo (`PointEntity`) |
| DDEDIT | ED | Edita o conteúdo de um `Text` (MTEXT/LEADER) já colocado no desenho |
| BLOCK | B | Define um bloco a partir de objetos selecionados (nome, ponto base, seleção) |
| INSERT | I | Insere uma instância de um bloco já definido (nome, ponto, escala, rotação) |
| BEDIT | BE | Abre o Block Editor para uma definição de bloco existente |
| REFEDIT | — | Mesma coisa que BEDIT nesta versão (ver limitações) |
| XREF | XR | Anexa um `.dxf` externo como referência (`BlockReference` marcada) |
| EXTERNALREFERENCES | ER | Abre o painel de xrefs (lista + Reload) |
| IMAGEATTACH | IM | Insere uma imagem raster (`.png`/`.jpg`/`.bmp`) |
| IMPORTPDF | — | Importa a geometria vetorial + texto de uma página de PDF como entidades reais |
| LAYER | LA | Abre o painel de camadas (visibilidade, trava, camada atual) |
| RENAME | REN | Renomeia a camada atual (ou clique direito numa camada no painel) |
| PURGE | PU | Remove camadas e blocos não usados em lugar nenhum do desenho |
| PLOT | — | Exporta o desenho inteiro para PDF (pergunta tamanho de folha e orientação) |
| PUBLISH | — | Mesma coisa que PLOT nesta versão (sem layouts/paper space) |
| UNDO | U | Desfaz o último comando |
| MTEXT | T / MT | Texto simples/multilinha (ponto de inserção + texto digitado, opção `[Justify]`) |
| DIMLINEAR | DLI | Cota linear (2 pontos de origem + posição da linha de cota) |
| DIMALIGNED | DAL | Cota alinhada à direção entre os 2 pontos |
| DIMANGULAR | DAN | Cota de ângulo (vértice + 2 pontos + posição do arco) |
| DIMRADIUS | DRA | Cota de raio (seleciona círculo/arco + posição do texto) |
| DIMDIAMETER | DDI | Cota de diâmetro (seleciona círculo/arco + posição do texto) |
| DIMSTYLE | D / DS | Informa o estilo de cota atual (só o padrão, por enquanto) |
| HATCH | H | Hachura dentro de uma LWPolyline fechada selecionada |
| HATCHEDIT | HE | Edita ângulo e espaçamento de uma hachura já desenhada |
| LEADER | LE | Linha poligonal + texto na ponta (leader simplificado) |

Convenções: Enter/Espaço confirma ou repete o último comando, Esc cancela, roda do mouse dá zoom, botão do meio faz pan, clique direito equivale a Enter. Nos comandos de modificação, clique seleciona um objeto (Shift+clique alterna), e arrastar numa área vazia seleciona por janela/crossing.

### Arquivo

| Atalho | Ação |
|---|---|
| Ctrl+N | Abre uma aba nova em branco (File > New) |
| Ctrl+O | Abre um desenho `.dxf` ou `.dwg` numa aba nova (File > Open...) |
| Ctrl+W | Fecha a aba atual (pergunta antes se houver alterações não salvas) |
| Ctrl+S | Salva no arquivo atual (`.dxf`; pede um caminho se ainda não houver um) |
| Ctrl+Shift+S | Salva como... (`.dxf`) |
| Ctrl+P | Exporta o desenho para PDF (`PLOT`/`PUBLISH`) |
| — | File > Export DWG... exporta o desenho pra `.dwg` via CloudConvert (precisa de internet e API key — ver seção "Arquivos `.dwg`") |

## Estrutura

```
newsicad/
  core/        modelo de documento (Document.block_definitions), entidades (inclui BlockReference/ImageReference/Text/Dimension/Hatch/Spline), seleção, geometria (translate/rotate/mirror/scale/offset/fillet/chamfer/interseções + dimension_geometry + catmull_rom_bezier + trace_simple_line_loop/point_in_polygon pro BOUNDARY), undo
  commands/    interpretador de comandos, parser de coordenadas, comandos de desenho/modificação (draw_commands.py/modify_commands.py), blocos (block_commands.py), anotação (annotation_commands.py) e utilitários (utility_commands.py — AREA/ID/DDEDIT/PURGE)
  ui/          canvas Qt (renderiza todos os tipos de entidade, OSNAP/POLAR reais, respeita visibilidade/trava de camada), linha de comando, menu superior, ribbon (+ Quick Access Toolbar), janela principal (main_window.py — abas de documento, cada uma uma DocumentSession independente em document_session.py), painel de Propriedades reorganizado em seções (properties_panel.py), Block Editor (block_editor_dialog.py), painel de xrefs (xref_panel.py), painel de camadas (layer_panel.py)
  io/          leitura/gravação DXF (dxf_io.py, com blocos/INSERT/Text/Dimension/Hatch; dxf_annotations.py — TEXT/ATTRIB/MTEXT com alinhamento e rotação reais, MULTILEADER/LEADER/DIMENSION externa/ACAD_TABLE como bloco anônimo), ponte de leitura DWG via LibreDWG (dwg_bridge.py) e importação de PDF vetorial via PyMuPDF (pdf_import.py)
tests/         testes automatizados (pytest) — incluindo testes de integração Qt (QTest) para seleção, arrasto, undo/redo, blocos/xref/imagem/PDF, anotação e OSNAP/POLAR
```

## Testes

```bash
# macOS
~/.venvs/newsicad/bin/python3 -m pytest

# Windows
.venv\Scripts\python -m pytest
```

578/578 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). **Marco 2.15.2 — programa de otimização, etapa 3: passo de comando barato** (2026-09-04). Medido com `tools/bench_perf.py` na planta NEWSI-CASA PAU BRASIL-R01 (43 mil entidades): (a) `compute_extents_rect` recalculava a bbox de cada entidade em Python, descendo em cada bloco — agora usa a união dos `sceneBoundingRect` dos itens visíveis (C++), com a visibilidade vinda do documento: **2,09 s → 0,18 s** (zoom extents e abertura); um desenho só com linhas horizontais (bbox de altura zero) deixa de ser recusado pelo `isEmpty()`; (b) o painel de camadas era reconstruído a cada passo de comando (6 widgets + 3 ícones por camada, 0,25 s com 72 camadas) — `_refresh_layer_dock_if_needed` só reconstrói quando revisão/quantidade/camada atual mudam; (c) o temporizador de 400 ms das panes de VPORTS só remonta a pane se `session.state_id()` mudou (antes: reconstrução perpétua da cena); (d) `Entity.__setattr__` carimba uma versão em toda atribuição de atributo, e `refresh_entities` passou a ter duas passadas — LEVE com comando ativo (identidade + versão + cor efetiva, sem `repr()`) e COMPLETA sem comando ativo (confere também o `repr()` guardado, rede de segurança para mutação de lista no lugar; PEDIT chama `touch()`): refresh dentro de um comando **0,66 s → 0,22 s**, `_after_interpreter_step` com comando ativo **0,88 s → 0,43 s** (o que sobra é a repintura da viewport). Testes novos em `tests/test_command_step_performance.py` e `tests/test_entity_version.py`. Restam as etapas 4 (abertura em thread com progresso; parser do ezdxf 29 s) e 5 (pintura: arrastar 62 ms e zoom 211 ms por evento nessa planta — nível de detalhe por zoom / GPU).

571/571 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). **Marco 2.15.1 — programa de otimização, etapas 1 e 2** (2026-09-04). Relato do Hamilton na planta pesada NEWSI-CASA PAU BRASIL-R01 (42.978 entidades, 72 camadas, 50.595 itens): clicar na lâmpada de uma camada congelou o programa até precisar matá-lo, e a operação normal engasgava. Medido antes de mexer (novo `tools/bench_perf.py`, que abre um arquivo pelo fluxo real do File > Open e cronometra abertura, passo de comando, undo, camadas e interação): **1 clique na lâmpada = 177,8 s**, cadeado > 600 s, e — o vilão escondido — `is_dirty()` fazia `deepcopy` de entidades + camadas + blocos e comparava tudo a **cada passo de comando** (10,1 s por clique dentro de LINE/MOVE/…), mais 9,5 s ao abrir (`mark_saved`) e 2,7 s de `deepcopy` no `undo_stack.push()` antes de cada comando. **Etapa 1:** `DocumentSession.is_dirty` compara um identificador de estado (token da pilha de undo + `Document.revision` + revisão dos blocos + unidades) em vez de copiar o documento; `UndoStack` guarda snapshots em `pickle` (10× mais rápido que `deepcopy`) com teto de memória (`_MAX_UNDO_BYTES`) além do teto de profundidade, e emite um token único por estado — voltar por undo ao ponto salvo fica "limpo" de novo, e o token não colide quando a pilha descarta os mais antigos. `Document.touch()` marca o que muda fora do undo (painel de camadas, LAYISO/LAYUNISO). **Etapa 2:** camada desligada vira `item.setVisible(False)` (nada é destruído nem recriado; o pré-filtro espacial do clique deixa de se desligar com camada oculta); a impressão digital de cada item deixa de carregar o estado de TODAS as camadas — entidade comum já leva a cor efetiva, e instância de bloco leva só as cores das camadas que a definição usa (`_definition_layer_names`, cacheado); o destaque de seleção é reaplicado só nos itens recriados; recriação em massa (cor de camada muito usada, bloco redefinido) roda com o índice espacial da cena desligado (`_REINDEX_THRESHOLD`), porque `removeItem` item a item numa cena de 50 mil itens custava 17× o custo de montar do zero. Resultado na Casa Pau Brasil: lâmpada **177,8 s → 0,28 s**, cadeado **> 600 s → 0,21 s**, cor de camada com 11.208 entidades **~178 s → 6,9 s**, `is_dirty` **10,1 s → 0,00 s**, `_after_interpreter_step` **10,5 s → 1,0 s**, `undo push` **2,5 s → 0,28 s**, abertura (sessão + cena + zoom) **32 s → 12 s**; Ana Beatriz sem regressão. Testes novos em `tests/test_document_revision.py` e `tests/test_layer_performance.py` (de comportamento, com volume). Ficam para as próximas etapas: `refresh_entities` ainda recalcula as impressões digitais de tudo a cada passo (0,58 s na planta pesada), `zoom_extents` percorre todas as entidades (2,0 s), a primeira abertura depende do parser do ezdxf (29 s) e a pintura de 50 mil itens no arrastar/zoom (61 ms / 217 ms por evento).

558/558 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11). **Marco 2.15.0** (2026-09-03): redesenho do menu superior no padrão do AutoCAD 2020, a partir da proposta visual em `docs/design/ribbon-proposta-2026-09.html` (mockup HTML aprovado pelo Hamilton antes de qualquer linha de Qt — o processo foi: pesquisa do ribbon do AutoCAD, duas prévias inline, escolha do estilo "B" de cor por família e do layout fiel ao AutoCAD, mockup completo, depois o port). Ribbon reescrito (`newsicad/ui/ribbon.py`: abas Home/Insert/Annotate/View/Manage/Output, painéis com botões grandes/pequenos/só-ícone, split-buttons com flyout, slide-out no título do painel, combo de camada atual no painel Layers), 162 ícones SVG novos (`newsicad/resources/icons/`, carregados por `icon_utils.svg_icon` via QSvgRenderer a 3x, coloridos pela família do painel) usados também no menu clássico, no menu de contexto do canvas (reordenado como o do AutoCAD) e nos toggles da barra de status (agora só ícone, azul quando ligado). Duas armadilhas do Qt registradas no código: `QToolButton.setMenu` não toma posse do QMenu (o flyout era coletado pelo Python e sumia) e `setParent` sem as window flags transforma o menu num widget-filho desenhado dentro do botão. Testes novos em `tests/test_ribbon.py` (ordem dos painéis, desabilitados com tooltip, combo de camada, flyouts, slide-out) e o do menu de contexto em `tests/test_canvas_selection.py`.

551/551 testes passando. **Marco 2.14.3** (2026-09-03): conserto de uma regressão introduzida pela própria 2.14.2. A fusão de geometria criava um item gráfico por segmento e só depois removia um a um do grupo, e cada `removeFromGroup` recalcula o grupo inteiro — numa planta com blocos grandes (NEWSI-CASA PAU BRASIL-R01, 110 mil segmentos dentro de definições de bloco) montar a cena passou de 17 s para **5 minutos**, com a janela parecendo travada. Agora o traçado é acumulado DURANTE a montagem (`_plain_geometry_path` + `merged_paths` em `_create_block_reference_item`) e o item por cor entra no grupo já pronto: a mesma planta monta em **10,7 s** (melhor que os 17 s originais) e a Ana Beatriz segue em 1,7 s. Lição registrada: medir sempre no arquivo PESADO, não só no que motivou a mudança.

551/551 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). **Marco 2.14.2** (2026-09-03): continuação do trabalho de fluidez, medindo com JANELA REAL (`QT_QPA_PLATFORM=windows`) e com a vista sempre reposta em `zoom_extents` antes de cada medição — a primeira rodada de medições foi descartada por viés: depois do teste de arrasto a vista ficava numa região vazia do desenho, o que fazia qualquer configuração parecer rápida. Com a metodologia corrigida, na planta NEWSI-ANA BEATRIZ-R01: (a) a geometria de cada instância de bloco passou a ser fundida num `QGraphicsPathItem` por cor efetiva (`_merge_geometry_children`) — a cena caiu de **21.378 para 2.473 itens**, arrastar de **22,8 ms para 8,2 ms** por evento e o zoom de **67 ms para 39 ms**; texto, hachura e imagem continuam itens próprios (a fusão perderia preenchimento) e a unidade de seleção continua sendo o bloco; (b) a roda do mouse acumula a rajada num único passo de zoom (`_ZOOM_COALESCE_MS`), então cinco cliques de roda dados juntos custam um repaint em vez de cinco; (c) `DontSavePainterState`/`DontAdjustForAntialiasing` e `SmartViewportUpdate` na view. Descartado nesta rodada, por honestidade de medição: desligar o antialiasing durante a interação parecia levar o zoom de 91 ms para 6 ms, mas o A/B controlado mostrou diferença de ~2 ms — a economia vinha do viés acima. O que ainda pesa e fica para depois: o zoom repinta a viewport inteira (~39 ms) porque a planta tem ~20 mil segmentos visíveis de verdade — sair disso pede nível de detalhe por zoom ou aceleração por GPU.

549/549 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). **Marco 2.14.1** (2026-09-03): desempenho de interação, a partir do relato "abriu certinho, mas está lento demais" na planta NEWSI-ANA BEATRIZ-R01. Três gargalos medidos e corrigidos, sem mudar nada do que aparece na tela — (a) mover o mouse repintava duas faixas de borda a borda da viewport (herança de quando o crosshair era de tela cheia; hoje ele tem 5% por causa do pedido do Albert), obrigando o Qt a redesenhar todos os itens cruzados pela linha e pela coluna do cursor: **40,5 ms -> 5,3 ms por movimento**; (b) o clique de seleção testava a geometria de TODAS as entidades, descendo em cada bloco (uma planta de arquitetura tem centenas de instâncias de móveis com milhares de segmentos): agora o índice espacial da cena pré-filtra os candidatos — **860 ms -> 105 ms por clique**; (c) o destaque de seleção varria todos os itens do desenho a cada clique, agora toca só os que entraram/saíram da seleção. A hachura também virou um traçado único (um `drawPath` no lugar de milhares de `drawLine`) com chapa translúcida quando fica pequena demais na tela para o padrão ser distinguível. Testes novos em `tests/test_canvas_performance.py`. Continua pendente: o zoom repinta a viewport inteira (~95 ms por passo de roda) e a PRIMEIRA abertura de um arquivo grande ainda depende do parser do ezdxf (o cache resolve só a reabertura).

543/543 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). **Marco 2.14.0** (2026-09-02): resposta ao relato dos testers de 31/08 (ícones das legendas em branco, rack e textos sumindo, itens explodidos, hachuras incompletas, tabelas explodidas, lentidão), testado nas próprias plantas reportadas (NEWSI-ANA BEATRIZ-R01 e NEWSI-CASA PAU BRASIL-R01) mais seis .dwg reais da New SI. Duas frentes: preenchimentos/cores/ordem de desenho/OCS (`tests/test_fills_colors_ocs.py`, seção "Nota técnica: HATCH/WIPEOUT/BYBLOCK") e textos/leaders/cotas/tabelas (`tests/test_dxf_annotations.py`, `tests/test_text_render.py`), mais o cache de abertura e os avisos de layouts/xrefs (`tests/test_open_cache.py`). Resultado nas duas plantas do relato: 0 entidades ignoradas na Ana Beatriz (antes 50) e só 542 hachuras degeneradas (área zero) no Casa Pau Brasil (antes 1.825), zoom inicial correto (a Ana Beatriz abria com a planta ocupando 15% da vista por causa de blocos em OCS espelhado), textos visíveis no Windows.

539/539 testes passando (offscreen; validado no Windows 10 com Python 3.12, PySide6 6.11, ezdxf 1.4.4). WP-B (2026-09, seção "Textos, leaders, cotas e tabelas de arquivos externos"): testes novos em `tests/test_dxf_annotations.py` (alinhamento de TEXT/ATTRIB, rotação/largura de MTEXT, MULTILEADER/LEADER/DIMENSION/ACAD_TABLE como bloco anônimo, ATTRIB aninhado, STYLE SHX/width, DimStyle, aviso do dwg2dxf) e `tests/test_text_render.py` (altura da tinta = altura CAD de 2.5 a 0.01, baseline, quebra por largura, DimStyle no texto da cota, fallback SHX e um teste em subprocesso com `QT_QPA_PLATFORM=windows` — pulado fora do Windows).

313/313 testes passando (validado no Windows 11 com Python 3.12). Marco 2.5.1: nenhuma mudança de comportamento — reparo de um conflito de sincronização do iCloud que tinha deixado o projeto quebrado (6 arquivos renomeados com sufixo " 2" pelo iCloud, `newsicad/commands/utility_commands.py` chegou a ficar totalmente ausente do disco, impedindo até o app de abrir). Também investigado, sem conseguir reproduzir: "Del não tira a seleção dos itens" — testado via Ctrl+A+Delete e seleção por janela+Delete, ambos funcionaram corretamente.

313/313 testes passando. Marco 2.5.0: seleção por clique fora de comando ativo + menu de contexto no botão direito — a causa raiz real por trás de vários bugs reportados (Del, SELECTSIMILAR, "botão direito não seleciona"). Testes novos em `tests/test_canvas_selection.py`.

306/306 testes passando. Marco 2.4.0: Import PDF (extração vetorial real via PyMuPDF) — testes novos em `tests/test_pdf_import.py` e `tests/test_import_pdf_ui.py`.

291/291 testes passando. Marco 2.3.1: Del/Backspace apagando seleção e SELECTSIMILAR usando a seleção existente como referência — mais 2 bugs reais reportados pelo grupo de testers.

285/285 testes passando. Marco 2.3.0: pickbox no crosshair, ícone com o logo "N" dourado, e 3 bugs reais corrigidos (TRIM perto de interseções, Ctrl+Z com a linha de comando focada, preview do RECTANG) — testes novos em `tests/test_command_preview.py`, `tests/test_osnap_polar.py` e `tests/test_undo_shortcuts.py`.

280/280 testes passando (validado no Windows 11 com Python 3.12). Marco 2.2.0: `SPLINE`, `BOUNDARY`, `PEDIT`, `HATCHEDIT` (segunda leva do feedback do grupo de testers — só falta `TABLE` da lista original da Rafaela) e a proteção contra perda de trabalho não salvo (fechar/New/Open perguntando `[Save/Discard/Cancel]`), com testes novos em `tests/test_spline_boundary_pedit_hatchedit.py` e `tests/test_unsaved_changes.py`.

245/245 testes passavam na versão 2.1.0 (ambiente Windows recriado do zero: `.venv` anterior era de macOS e não funcionava aqui). Marco 2.1.0: `POLYGON`, `ALIGN`, `ARRAY` (retangular/polar), `MATCHPROP` e `SELECTSIMILAR`, a partir do feedback do grupo de testers (WhatsApp), com testes novos em `tests/test_new_commands.py`.

235/235 testes passavam na versão 2.0.0 (validado no macOS, rodando a suíte completa após mesclar os três marcos anteriores — blocos/referências/PDF, anotação, e edição geométrica/OSNAP/POLAR — mais correções de leitura de `.dwg` real, tamanho/orientação de folha no Export PDF, correções de layout do ribbon, o painel de camadas, e os comandos utilitários `AREA`/`ID`/`DDEDIT`/`PURGE`/`RENAME` incorporados do guia oficial de atalhos do AutoCAD). O merge dos três marcos expôs um bug real de integração (não visível em nenhum dos três isoladamente): reabrir qualquer `.dxf` com uma cota contava a seta da cota como "entidade não suportada", porque o bloco auto-gerado pelo ezdxf para a seta (`_CLOSEDFILLED`) não caía no filtro de "bloco anônimo" (que só reconhecia nomes começando com `*`) — corrigido em `newsicad/io/dxf_io.py`. Testando com 25 `.dwg` reais do usuário também apareceram e foram corrigidos: uma quebra de linha espúria que o `dwg2dxf` insere em MTEXT longos, um crash de decodificação UTF-8 em avisos do `dwg2dxf`, e um fallback de leitura tolerante (`ezdxf.recover`) pra arquivos com dano estrutural — foi de 12/25 pra 16/25 abrindo com desenho completo (ver `newsicad/io/dwg_bridge.py`). O painel de camadas revelou (e corrigiu) mais um bug real: `document.current_layer` nunca funcionava de verdade — toda entidade nova ia sempre pra camada "0" (ver seção "Camadas" acima).

Observação sobre `tests/test_dwg_bridge.py`: os testes que exercitam `dwg_to_document` de verdade dependem do binário `dwg2dxf` do LibreDWG (empacotado para macOS/Windows em `newsicad/resources/libredwg/`, ou disponível no PATH). Em ambientes sem nenhum dos dois (ex.: a maioria dos runners de CI em Linux), esses testes são pulados automaticamente (`pytest.skip`) em vez de falhar.

---

**NewSIcad** — Developed by HRichter
