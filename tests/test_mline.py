"""MLINE (multilinha): as linhas paralelas que o arquiteto usa como parede.

Achado da varredura da base em 04/10/2026. A entidade era descartada inteira:
18 MLINE em 5 arquivos de 2 clientes, e cada uma sumia da tela E do arquivo
entregue — o programa a contava como "não suportada" e seguia adiante.

    NEWSI-MARIANNE E GHREGORY-R01 e R02   6 MLINE cada, no bloco PAREDES
                                          (camada "Formato A3", escala 0,03)
    6644-FLE01/02/03 (Escritório H&M)     2 MLINE cada, no bloco da base
                                          elétrica (camada de multiduto,
                                          escala 0,1, três vértices)

Os dois casos têm em comum o que importa para a leitura: a MLINE mora DENTRO
de um bloco, o estilo vem do próprio arquivo (dois elementos de ±0,5 com cor
0 — "por bloco" — e tipo de linha por camada), e o `dwg2dxf` grava os
vértices já com a escala e a justificação aplicadas. O `virtual_entities()`
do ezdxf devolve exatamente as LINE que o AutoCAD desenha, e a leitura as
coloca no lugar da MLINE.

Duas decisões registradas, as duas medidas:

1. **Linhas soltas, não bloco anônimo** (como cota e chamada). O ponto de snap
   de um bloco é só o ponto de inserção: a parede embrulhada num bloco não
   oferecia canto nem meio — `_find_osnap_point` no canto devolvia `None` —, e
   quem marca a automação em cima da planta precisa encostar na parede. Solta,
   o mesmo ponto devolve "endpoint" (ver `test_parede_solta_oferece_snap_no_canto`).
   De quebra, o arquivo entregue leva as LINE direto, sem bloco `*U` — é o que
   o EXPLODE do AutoCAD daria — e é a mesma representação do comando MLINE do
   próprio programa, que também desenha a parede como linhas paralelas soltas.
2. **O contorno basta; a MLINE não é regravada como MLINE.** As 18 da base
   moram em blocos de base que o projetista não edita, e a geometria volta
   idêntica (ver `test_geometria_volta_identica_depois_de_salvar`). O que se
   perde é só poder editar a parede como multilinha no AutoCAD do cliente.
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import ezdxf
from ezdxf.audit import Auditor
from ezdxf.entities.mline import MLineStyle

from newsicad.core.entities import Arc, BlockReference, Hatch, Line, Point
from newsicad.io.dxf_io import load_dxf, save_dxf

#: As seis multilinhas de PAREDES no NEWSI-MARIANNE E GHREGORY-R01, medidas no
#: .dxf que o `dwg2dxf` gerou (linha de referência de cada uma, em metros).
PAREDES_DO_MARIANNE = [
    [(220.9556501679399, 135.0306349457002), (222.7552873813247, 135.0306349457002)],
    [(220.2462854750316, 139.0499743468661), (220.2462854750316, 139.7472622323016)],
    [(220.2462854750316, 140.1843051756061), (220.2462854750316, 141.8732349632999)],
    [(223.7662854750317, 133.2412895416952), (228.4462854750317, 133.2412895416954)],
    [(228.6862854750317, 133.2412895416954), (230.4062854750317, 133.2412895416961)],
    [(223.7256308790367, 133.3127950139421), (223.7256308790365, 134.6006349457001)],
]


def _estilo(doc, nome="STANDARD", elementos=((0.5, 0, "ByLayer"), (-0.5, 0, "ByLayer")), flags=0, fill=256):
    """O estilo do arquivo real: dois elementos de ±0,5, cor 0 (por bloco)."""
    estilo = doc.mline_styles.new(nome)
    estilo.dxf.flags = flags
    estilo.dxf.fill_color = fill
    for deslocamento, cor, tipo in elementos:
        estilo.elements.append(deslocamento, cor, tipo)
    return estilo


def _multilinha(layout, vertices, estilo, escala, justificacao=1, camada="Formato A3", **extra):
    m = layout.add_mline(vertices, dxfattribs={"style_name": estilo, "layer": camada, **extra})
    m.set_scale_factor(escala)
    m.set_justification(justificacao)
    return m


def _carrega(doc):
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "mline.dxf"
        doc.saveas(caminho)
        return load_dxf(caminho)


def _arquivo_marianne():
    """O bloco PAREDES do Marianne, com as seis multilinhas reais."""
    doc = ezdxf.new("R2010")
    doc.layers.add("Formato A3")
    _estilo(doc, "PAREDE")
    bloco = doc.blocks.new("PAREDES")
    for vertices in PAREDES_DO_MARIANNE:
        _multilinha(bloco, vertices, "PAREDE", escala=0.03, justificacao=1)
    doc.modelspace().add_blockref("PAREDES", (0, 0))
    return doc


def _soltas(entidades, tipo):
    return [e for e in entidades if isinstance(e, tipo)]


def test_as_seis_paredes_do_marianne_deixam_de_ser_descartadas():
    """Antes: `skipped.by_type == {'MLINE': 6}` e o bloco PAREDES abria sem
    nenhuma das seis paredes. Depois: nenhuma descartada e as 12 linhas que o
    AutoCAD desenha para elas (6 multilinhas × 2 elementos), soltas dentro
    do bloco, na camada da multilinha."""
    documento, skipped = _carrega(_arquivo_marianne())

    assert "MLINE" not in skipped.by_type
    assert int(skipped) == 0
    partes = documento.block_definitions["PAREDES"]
    linhas = _soltas(partes, Line)
    assert len(linhas) == 12
    assert len(partes) == 12, "só as linhas: nenhum bloco anônimo no meio"
    assert not any(isinstance(p, BlockReference) for p in partes)
    assert {linha.layer for linha in linhas} == {"Formato A3"}


def test_espessura_e_comprimento_das_paredes_batem_com_o_arquivo():
    """Cada parede mede 0,03 de espessura (escala 0,03 × ±0,5) e tem o
    comprimento da linha de referência — a justificação "zero" (1) deixa a
    referência no meio das duas linhas."""
    documento, _ = _carrega(_arquivo_marianne())
    linhas = _soltas(documento.block_definitions["PAREDES"], Line)

    assert len(linhas) == 2 * len(PAREDES_DO_MARIANNE) == 12
    for i, (a, b) in enumerate(PAREDES_DO_MARIANNE):
        par = linhas[2 * i : 2 * i + 2]
        comprimento = math.hypot(b[0] - a[0], b[1] - a[1])
        for linha in par:
            assert math.isclose(linha.start.distance_to(linha.end), comprimento, abs_tol=1e-9)
        meio_x = (par[0].start.x + par[1].start.x) / 2
        meio_y = (par[0].start.y + par[1].start.y) / 2
        assert math.isclose(meio_x, a[0], abs_tol=1e-9) and math.isclose(meio_y, a[1], abs_tol=1e-9)
        assert math.isclose(par[0].start.distance_to(par[1].start), 0.03, abs_tol=1e-9)


def test_cor_por_bloco_do_elemento_vira_a_cor_da_propria_multilinha():
    """O estilo do arquivo real tem cor 0 nos dois elementos. Para o elemento
    de uma multilinha isso é "a cor da PRÓPRIA multilinha" — não a do bloco
    onde ela mora. Solta, a linha herdaria o BYBLOCK do INSERT de fora (e
    sairia na cor do bloco PAREDES); tem que sair por camada, que é o que
    o AutoCAD desenha para uma MLINE sem cor própria."""
    documento, _ = _carrega(_arquivo_marianne())
    linhas = _soltas(documento.block_definitions["PAREDES"], Line)

    assert len(linhas) == 12
    assert all(linha.color is None for linha in linhas)


def test_multilinha_com_cor_propria_passa_a_cor_para_os_elementos_por_bloco():
    doc = ezdxf.new("R2010")
    _estilo(doc, "PAREDE")
    _multilinha(doc.modelspace(), [(0, 0), (6, 0)], "PAREDE", escala=0.2, camada="PAREDES", color=3)

    documento, _ = _carrega(doc)
    linhas = _soltas(documento.entities.values(), Line)

    assert len(linhas) == 2
    assert {linha.color for linha in linhas} == {"#00FF00"}


def test_multiduto_do_hm_tres_vertices_dentro_do_bloco_da_base():
    """O caso do Escritório H&M: três vértices, escala 0,1, justificação
    "topo" e a MLINE dentro do bloco da base elétrica (que o modelspace
    insere uma vez). Dois segmentos × dois elementos = 4 linhas, e a quina
    do meio é a esquadria que o AutoCAD calculou."""
    doc = ezdxf.new("R2010")
    doc.layers.add("BASE$0$_NBR-MULT-DUTO")
    _estilo(doc, "BASE$0$STANDARD", elementos=((0.5, 0, "BYLAYER"), (-0.5, 0, "BYLAYER")))
    bloco = doc.blocks.new("BASE-ELE")
    _multilinha(
        bloco, [(120.0, -1.0), (120.0, 12.0), (122.0, 14.0)], "BASE$0$STANDARD",
        escala=0.1, justificacao=0, camada="BASE$0$_NBR-MULT-DUTO",
    )
    doc.modelspace().add_blockref("BASE-ELE", (0, 0))

    documento, skipped = _carrega(doc)

    assert "MLINE" not in skipped.by_type
    linhas = _soltas(documento.block_definitions["BASE-ELE"], Line)
    assert len(linhas) == 4
    assert {linha.layer for linha in linhas} == {"BASE$0$_NBR-MULT-DUTO"}
    # a quina do meio é a esquadria: o segundo segmento começa onde o primeiro
    # termina, nas duas linhas
    inicios = {(round(l.start.x, 6), round(l.start.y, 6)) for l in linhas}
    fins = {(round(l.end.x, 6), round(l.end.y, 6)) for l in linhas}
    assert len(inicios & fins) == 2


def test_multilinha_solta_no_modelspace_e_na_prancha():
    """Fora de bloco também: no modelspace as linhas entram no desenho; na
    prancha (paper space) entram na prancha, não no modelspace."""
    doc = ezdxf.new("R2010")
    _estilo(doc, "PAREDE")
    _multilinha(doc.modelspace(), [(0, 0), (6, 0)], "PAREDE", escala=0.2, camada="PAREDES")
    prancha = doc.layout("Layout1")
    _multilinha(prancha, [(0, 0), (4, 0)], "PAREDE", escala=0.2, camada="PRANCHA")

    documento, skipped = _carrega(doc)

    assert "MLINE" not in skipped.by_type
    no_model = list(documento.entities.values())
    assert [(type(e).__name__, e.layer) for e in no_model] == [("Line", "PAREDES")] * 2
    na_prancha = list(documento.layouts["Layout1"].values())
    assert [(type(e).__name__, e.layer) for e in na_prancha] == [("Line", "PRANCHA")] * 2


def test_parede_solta_oferece_snap_no_canto():
    """O que decidiu "linhas soltas" em vez de bloco: o canto da parede e o
    meio de cada linha têm que servir de OSNAP. Embrulhada num bloco, a mesma
    parede devolvia `None` nos dois pontos — o único snap de um bloco é o
    ponto de inserção, que ficava em (0, 0), a quilômetros da parede."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from newsicad.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    doc = ezdxf.new("R2010")
    _estilo(doc, "PAREDE")
    _multilinha(doc.modelspace(), PAREDES_DO_MARIANNE[0], "PAREDE", escala=0.03, camada="PAREDES")
    documento, _ = _carrega(doc)

    janela = MainWindow()
    for entidade in documento.entities.values():
        janela.document.add_entity(entidade)
    janela.canvas.set_osnap_enabled(True)
    (x0, y0), (x1, _y1) = PAREDES_DO_MARIANNE[0]

    canto = janela.canvas._find_osnap_point(Point(x0, y0 + 0.015))
    meio = janela.canvas._find_osnap_point(Point((x0 + x1) / 2, y0 + 0.015))

    assert canto is not None and canto[1] == "endpoint"
    assert math.isclose(canto[0].x, x0, abs_tol=1e-9)
    assert math.isclose(canto[0].y, y0 + 0.015, abs_tol=1e-9)
    assert meio is not None and meio[1] == "midpoint"


def test_geometria_volta_identica_depois_de_salvar():
    """É isto que sustenta a decisão de não regravar como MLINE: ler e salvar
    devolve as mesmas linhas, nas mesmas coordenadas, direto no bloco PAREDES
    — sem bloco anônimo no meio — e o arquivo gravado passa na auditoria do
    ezdxf."""
    with tempfile.TemporaryDirectory() as tmp:
        origem = Path(tmp) / "origem.dxf"
        _arquivo_marianne().saveas(origem)
        documento, _ = load_dxf(origem)
        destino = Path(tmp) / "entregue.dxf"
        save_dxf(documento, destino)

        entregue = ezdxf.readfile(destino)
        auditor = Auditor(entregue)
        assert not auditor.errors and not auditor.fixes

        esperadas = []
        for mline in ezdxf.readfile(origem).blocks.get("PAREDES"):
            esperadas += [
                (round(v.dxf.start.x, 9), round(v.dxf.start.y, 9), round(v.dxf.end.x, 9), round(v.dxf.end.y, 9))
                for v in mline.virtual_entities()
            ]
        obtidas = []
        for entidade in entregue.blocks.get("PAREDES"):
            assert entidade.dxftype() == "LINE"
            obtidas.append((
                round(entidade.dxf.start.x, 9), round(entidade.dxf.start.y, 9),
                round(entidade.dxf.end.x, 9), round(entidade.dxf.end.y, 9),
            ))
        assert len(obtidas) == 12
        assert sorted(obtidas) == sorted(esperadas)
        assert not [b.name for b in entregue.blocks if b.name.startswith("*U")]


def test_tipo_de_linha_e_cor_do_elemento_do_estilo_sao_preservados():
    """Um estilo de parede com eixo tracejado: o elemento do meio é CENTER e
    vermelho. O tipo de linha e a cor são do ELEMENTO, não da MLINE, e se
    perdiam junto com a entidade."""
    doc = ezdxf.new("R2010", setup=True)
    _estilo(
        doc, "COM_EIXO",
        elementos=((1.0, 256, "BYLAYER"), (0.0, 1, "CENTER"), (-1.0, 256, "BYLAYER")),
    )
    _multilinha(doc.modelspace(), [(0, 0), (10, 0)], "COM_EIXO", escala=0.1, camada="PAREDES")

    documento, _ = _carrega(doc)

    linhas = _soltas(documento.entities.values(), Line)
    assert len(linhas) == 3
    por_tipo = sorted((linha.linetype, linha.color) for linha in linhas)
    assert por_tipo == [("", None), ("", None), ("CENTER", "#FF0000")]


def test_tampa_redonda_e_preenchimento_viram_arco_e_hachura_solida():
    """O estilo com tampa redonda desenha ARC e o preenchimento é uma HATCH
    que o ezdxf materializa sem `solid_fill` — tem que sair cheia, não como
    o padrão de linhas que `hatch_from_dxf` aproxima para hachura alheia."""
    doc = ezdxf.new("R2010", setup=True)
    _estilo(
        doc, "REDONDA", flags=MLineStyle.FILL | MLineStyle.START_ROUND | MLineStyle.END_ROUND, fill=5
    )
    _multilinha(doc.modelspace(), [(0, 0), (10, 0), (10, 8)], "REDONDA", escala=0.5, camada="PAREDES")

    documento, skipped = _carrega(doc)

    assert "MLINE" not in skipped.by_type
    partes = list(documento.entities.values())
    assert sum(isinstance(p, Arc) for p in partes) == 2
    cheias = [p for p in partes if isinstance(p, Hatch)]
    assert len(cheias) == 1 and cheias[0].solid_fill


def test_multilinha_que_o_ezdxf_nao_consegue_desenhar_continua_contando_como_perdida():
    """Se o estilo cita um tipo de linha que o arquivo não define, o ezdxf
    levanta na hora de materializar. Isso não pode derrubar a abertura do
    arquivo, e não pode sumir do aviso: a multilinha NÃO foi lida."""
    doc = ezdxf.new("R2010")  # sem os tipos de linha padrão: "CENTER" não existe
    _estilo(doc, "QUEBRADO", elementos=((0.5, 256, "CENTER"), (-0.5, 256, "BYLAYER")))
    mline = doc.modelspace().add_mline([(0, 0), (5, 0)], dxfattribs={"style_name": "QUEBRADO"})
    mline.set_scale_factor(0.1)

    documento, skipped = _carrega(doc)

    assert skipped.by_type.get("MLINE") == 1
    assert not documento.entities


def test_multilinha_sem_nada_a_desenhar_nao_entra_no_aviso_de_perda():
    """Um vértice só (ou vértices coincidentes): o AutoCAD não desenha nada,
    então não é entidade perdida — dizer ao projetista que o programa comeu
    uma multilinha que nem existe em tela é o falso alarme que a varredura
    já mostrou ser o pior ruído do aviso de abertura."""
    doc = ezdxf.new("R2010")
    _estilo(doc, "PAREDE")
    doc.modelspace().add_mline([(3, 3)], dxfattribs={"style_name": "PAREDE"})
    doc.modelspace().add_mline([(0, 0), (0, 0)], dxfattribs={"style_name": "PAREDE"})

    documento, skipped = _carrega(doc)

    assert int(skipped) == 0 and "MLINE" not in skipped.by_type
    assert not documento.entities
