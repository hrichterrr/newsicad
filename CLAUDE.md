# NewSIcad

CAD 2D desktop estilo AutoCAD (uso interno da New SI). Abre `.dxf`/`.dwg`, grava `.dxf`.
Stack: Python 3.12 + PySide6 (Qt) + ezdxf; PyMuPDF para PDF; LibreDWG para ler `.dwg`.

## Mapa do código
- `newsicad/core/` — Document, entidades, seleção, geometria (`geometry_ops.py`), undo
- `newsicad/commands/` — interpretador e comandos (draw/modify/annotation/block/utility/view)
- `newsicad/ui/` — canvas, ribbon, linha de comando, painéis, janela principal (abas = `DocumentSession`)
- `newsicad/io/` — DXF (`dxf_io.py`, `dxf_annotations.py`, `dxf_fills.py`), ponte DWG, PDF, cache de abertura
- `tests/` — pytest, com testes Qt em modo offscreen

## Regras
1. Rodar `python -m pytest` antes de commit (os testes Qt já definem `QT_QPA_PLATFORM=offscreen`).
2. Nova versão: atualizar **junto** `pyproject.toml` (`version`) e `newsicad/ui/main_window.py` (`APP_VERSION`); mensagem de commit no formato `vX.Y.Z — resumo`.
3. Simplificação ou limitação de round-trip DXF deve ficar documentada no README.
4. Nunca commitar `cloudconvert_api_key.txt` nem `.env`.
5. Pedidos com escopo fechado: ler só os arquivos envolvidos, não o módulo inteiro.

## Referências (ler só quando a tarefa pedir)
- `README.md` — é longo (~600 linhas); use a busca por seção em vez de ler inteiro:
  - "Blocos e referências", "Edição geométrica", "Camadas" — simplificações documentadas
  - "Arquivos `.dwg`" — leitura via LibreDWG, exportação via CloudConvert, cache de abertura
  - "Comandos disponíveis" — lista de comandos e aliases
  - "Testes" — changelog por marco de versão
- `docs/design/ribbon-proposta-2026-09.html` — proposta visual aprovada do ribbon
- `docs/plano-otimizacao-contexto.md` — plano de economia de contexto/tokens
