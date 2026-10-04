"""IMAGE (imagem raster) — lida do .dxf e devolvida nele.

Achado da varredura da base. 19% dos arquivos auditados têm IMAGE, somando
221 imagens, e era tudo descartado: sumia da tela E do arquivo entregue ao
cliente. Os três casos mais graves eram plantas de luminotécnico, onde a
imagem é a planta de fundo do arquiteto:

    03.02-LUMINOTÉCNICO (Mauro e Marcia)   92 imagens   89,5% -> 100%
    MBB-LUM-PRE-001-TERR (Marco Belmonte)  69 imagens   73,6% -> 100%
    MBB-LUM-PRE-002-SUP  (Marco Belmonte)  29 imagens   83,9% -> 100%

O .dxf nunca carrega os pixels, só o CAMINHO — é assim no AutoCAD também.
O arquivo quase nunca vem junto com o .dwg do cliente; nesse caso o canvas
desenha a moldura tracejada no lugar certo (o que o AutoCAD faz) e a
gravação devolve a referência intacta, para a imagem reaparecer na máquina
de quem tem o arquivo.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf

from newsicad.core.entities import ImageReference
from newsicad.io.dxf_io import load_dxf, save_dxf


def _arquivo_com_imagens(destino: Path) -> Path:
    doc = ezdxf.new("R2010")
    fundo = doc.add_image_def(filename="C:/plantas/fundo_terreo.png", size_in_pixel=(1024, 768))
    doc.modelspace().add_image(
        fundo, insert=(10, 20), size_in_units=(50, 37.5), dxfattribs={"layer": "FUNDO"}
    )
    recorte = doc.add_image_def(filename="C:/plantas/detalhe.jpg", size_in_pixel=(400, 300))
    cortada = doc.modelspace().add_image(recorte, insert=(0, 0), size_in_units=(20, 15))
    cortada.set_boundary_path([(50, 40), (350, 40), (350, 260), (50, 260)])
    caminho = destino / "com_imagem.dxf"
    doc.saveas(caminho)
    return caminho


def test_le_posicao_tamanho_e_arquivo_da_imagem():
    with tempfile.TemporaryDirectory() as tmp:
        documento, descartadas = load_dxf(_arquivo_com_imagens(Path(tmp)))

    assert not dict(getattr(descartadas, "by_type", {})), "IMAGE não pode mais contar como perdida"
    imagens = [e for e in documento.entities.values() if isinstance(e, ImageReference)]
    assert len(imagens) == 2

    fundo = next(i for i in imagens if i.layer == "FUNDO")
    assert (fundo.insertion_point.x, fundo.insertion_point.y) == (10.0, 20.0)
    assert (fundo.width, fundo.height) == (50.0, 37.5)
    assert fundo.pixel_size == (1024, 768)
    assert fundo.path.name == "fundo_terreo.png"


def test_le_o_recorte_da_imagem_em_unidades_de_desenho():
    """O .dxf dá o contorno em PIXELS a partir do canto; o modelo quer
    unidades de desenho a partir do ponto de inserção."""
    with tempfile.TemporaryDirectory() as tmp:
        documento, _ = load_dxf(_arquivo_com_imagens(Path(tmp)))

    cortada = next(e for e in documento.entities.values()
                   if isinstance(e, ImageReference) and e.clip_boundary)
    # 400 px -> 20 unidades, então 1 px = 0,05 unidade. O meio pixel de
    # folga é do formato: o contorno de uma imagem INTEIRA vai de -0,5 a
    # tamanho-0,5, justamente para que a borda caia em 0 e no tamanho cheio.
    xs = [round(p.x, 4) for p in cortada.clip_boundary]
    ys = [round(p.y, 4) for p in cortada.clip_boundary]
    assert min(xs) == 2.525 and max(xs) == 17.525
    assert min(ys) == 2.025 and max(ys) == 13.025


def test_devolve_a_imagem_no_arquivo_entregue():
    """O compromisso com o cliente: ele reabre o que a gente entregou e a
    planta de fundo continua lá."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        documento, _ = load_dxf(_arquivo_com_imagens(tmp))
        entregue = tmp / "entregue.dxf"
        save_dxf(documento, entregue)
        relido = ezdxf.readfile(entregue)

        imagens = [e for e in relido.modelspace() if e.dxftype() == "IMAGE"]
        assert len(imagens) == 2

        fundo = next(i for i in imagens if i.dxf.layer == "FUNDO")
        assert (round(fundo.dxf.insert.x, 6), round(fundo.dxf.insert.y, 6)) == (10.0, 20.0)
        assert fundo.image_def.dxf.filename.endswith("fundo_terreo.png")
        assert (int(fundo.dxf.image_size.x), int(fundo.dxf.image_size.y)) == (1024, 768)
        largura = abs(fundo.dxf.image_size.x) * abs(fundo.dxf.u_pixel.x)
        assert round(largura, 6) == 50.0

        cortada = next(i for i in imagens if i.dxf.layer != "FUNDO")
        assert cortada.dxf.clipping == 1, "o recorte tem que sobreviver"


def test_imagem_sem_caminho_nao_vira_referencia_quebrada():
    """Sem caminho não há o que referenciar: melhor não gravar nada do que
    gravar uma IMAGE apontando para lugar nenhum."""
    from newsicad.core.document import Document
    from newsicad.core.entities import Point

    documento = Document()
    documento.add_entity(
        ImageReference(insertion_point=Point(0, 0), width=10, height=10, path=Path(""))
    )
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "sem_caminho.dxf"
        save_dxf(documento, caminho)
        relido = ezdxf.readfile(caminho)

    assert not [e for e in relido.modelspace() if e.dxftype() == "IMAGE"]
