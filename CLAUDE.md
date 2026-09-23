# NewSIcad

CAD 2D desktop estilo AutoCAD, uso interno da New SI. Python 3.12 + PySide6 + ezdxf.
Abre `.dxf`/`.dwg`, grava `.dxf`. Versão atual em `pyproject.toml`.

## Antes de qualquer coisa

- **Este é o repo bom: `C:\Users\Hamilton\dev\newsicad`.** Existe uma cópia no iCloud
  (`Documents\Cloude CODE`) com o `.git` corrompido e o código desatualizado — não trabalhe nela.
- **Não leia o `README.md` inteiro** (~124 KB). Ele é o changelog histórico do projeto.
  Consulte por seção (`grep -n "^#" README.md`) só quando precisar do histórico de uma decisão.
- Ignore ao explorar: `.venv_win/`, `dist/`, `build/`, `*.zip`. O código-fonte real são
  **43 arquivos** em `newsicad/` + 72 em `tests/`.

## Estrutura

```
newsicad/
  core/      Document, entidades, seleção, geometria, undo
  commands/  interpretador, parser de coordenadas, draw/modify/block/annotation/utility
  ui/        canvas Qt, ribbon, janela principal, abas de documento, painéis
  io/        dxf_io.py, dxf_annotations.py, dxf_fills.py, dwg_bridge.py, pdf_import.py
tools/       bench_perf.py (medição de desempenho)
```

Os quatro arquivos que concentram quase tudo: `ui/canvas.py` (3.1k linhas),
`ui/main_window.py` (1.8k), `commands/modify_commands.py` (1.5k), `io/dxf_io.py` (1.4k).

## Comandos

```powershell
.venv_win\Scripts\python -m newsicad.main          # rodar
.venv_win\Scripts\python -m pytest                 # testes (810 passando, offscreen)
.venv_win\Scripts\pyinstaller build_windows.spec   # build -> dist\NewSIcad\
```

O venv desta máquina é **`.venv_win`**, não `.venv` (o README está desatualizado nesse ponto).

Desempenho (janela real, não entra na suíte de testes):

```powershell
set QT_QPA_PLATFORM=windows
.venv_win\Scripts\python tools\bench_perf.py "<caminho>\NEWSI-CASA PAU BRASIL-R01.dxf"
```

## Regras do projeto

1. **Toda versão nova passa pela rotina da Casa Pau Brasil (`tools/bench_perf.py`) antes de
   build, Drive e anúncio.** Os tempos medidos vão no texto do anúncio. Regra permanente.
2. Release = build → zipar `dist\NewSIcad` inteira (não só o `.exe`) → pasta "02 - Técnico" do
   Drive → anúncio no grupo "NewSicad" do WhatsApp.
3. Commits e mensagens em português, no formato `vX.Y.Z — resumo em uma linha` quando for
   release; frase descritiva curta quando for trabalho intermediário. Tag = `vX.Y.Z`.
4. `cloudconvert_api_key.txt` e `.env` nunca vão pro git (já no `.gitignore`). No `.exe`
   distribuído a chave fica ao lado do executável, copiada à mão em cada máquina.
5. `.gitattributes` protege os binários do LibreDWG — não mexa sem motivo.

## Decisões já fechadas (não reinvestigar)

- **Gravação nativa de `.dwg` não existe e não vai existir.** O `dxf2dwg` do LibreDWG foi testado
  em 4 releases e gera handles duplicados (bug estrutural do parser, issue upstream aberto desde
  2020). ODA proíbe redistribuição no EULA; QCAD só no Professional; Aspose é licença paga.
  O caminho adotado é `File > Export DWG...` via CloudConvert (`io/dwg_export.py`).
- **Leitura de `.dwg`** é via binários do LibreDWG empacotados em `newsicad/resources/libredwg/`.
  A conversão nunca foi a causa de bug de renderização — isso já foi conferido contra um
  conversor comercial independente, bloco a bloco.
- **Blocos anônimos `*U...`** (blocos dinâmicos do AutoCAD) são carregados de propósito; só
  `*Model_Space`/`*Paper_Space`/`*D...`/`*X...` ficam de fora.
- **Hachura sólida não é WIPEOUT** — só `Hatch.wipeout` é. Regressão já corrigida uma vez.
- PyMuPDF é AGPL-3.0, aceitável por ser uso interno e não revendido. Se isso mudar, reavaliar.

## Em aberto

- Paper space (selo, legenda e tabelas das pranchas) é listado na abertura, mas não exibido.
- Atributos de bloco, tabelas e layout ao salvar seguem com pendências conhecidas.
