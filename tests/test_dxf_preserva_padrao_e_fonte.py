"""Duas coisas que a gravação em .dxf trocava por conta própria: o nome de um
padrão de hachura vindo de biblioteca de terceiro (virava "ANSI31") e o nome
da fonte de um estilo de texto sem extensão (ganhava um ".ttf" que não existe)
— auditoria de 2026-09-07."""

from __future__ import annotations

import math

import ezdxf
import pytest

from newsicad.core.document import Document, TextStyle
from newsicad.core.entities import Hatch, Point
from newsicad.io.dxf_io import load_dxf, save_dxf


def test_padrao_de_terceiro_mantem_o_nome_e_ganha_definicao(tmp_path):
    doc = Document()
    doc.add_entity(
        Hatch(
            boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
            pattern_name="MINHA-HACHURA",
            angle=math.radians(30),
            spacing=2.0,
        )
    )
    caminho = tmp_path / "h.dxf"
    save_dxf(doc, caminho)

    lido = ezdxf.readfile(str(caminho))
    hatch = lido.modelspace().query("HATCH").first
    assert hatch.dxf.pattern_name == "MINHA-HACHURA"
    assert hatch.pattern is not None and len(hatch.pattern.lines) >= 1, (
        "sem definição de padrão o HATCH abre vazio no AutoCAD"
    )

    de_volta, _ = load_dxf(caminho)
    (h,) = [e for e in de_volta.all_entities() if isinstance(e, Hatch)]
    assert h.pattern_name == "MINHA-HACHURA"
    assert h.angle == pytest.approx(math.radians(30))
    assert h.spacing == pytest.approx(2.0)


def test_padrao_conhecido_continua_igual(tmp_path):
    doc = Document()
    doc.add_entity(
        Hatch(
            boundary_points=[Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4)],
            pattern_name="ANSI31",
            spacing=1.0,
        )
    )
    caminho = tmp_path / "a.dxf"
    save_dxf(doc, caminho)
    hatch = ezdxf.readfile(str(caminho)).modelspace().query("HATCH").first
    assert hatch.dxf.pattern_name == "ANSI31"


@pytest.mark.parametrize("fonte", ["txt", "romans.shx", "arial.ttf"])
def test_nome_da_fonte_sobrevive_a_ida_e_volta(tmp_path, fonte):
    origem = tmp_path / "origem.dxf"
    criado = ezdxf.new("R2018")
    criado.styles.add("MEUESTILO", font=fonte)
    criado.saveas(str(origem))

    doc, _ = load_dxf(origem)
    assert doc.text_styles["MEUESTILO"].font_file == fonte

    destino = tmp_path / "destino.dxf"
    save_dxf(doc, destino)
    regravado = ezdxf.readfile(str(destino))
    assert regravado.styles.get("MEUESTILO").dxf.font == fonte


def test_estilo_criado_no_newsicad_continua_ganhando_ttf(tmp_path):
    doc = Document()
    doc.text_styles["NOVO"] = TextStyle(name="NOVO", font_family="Menlo", height=2.5)
    caminho = tmp_path / "n.dxf"
    save_dxf(doc, caminho)
    assert ezdxf.readfile(str(caminho)).styles.get("NOVO").dxf.font == "Menlo.ttf"
