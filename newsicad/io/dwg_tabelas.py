"""ACAD_TABLE: a posição que o `dwg2dxf` não escreve, lida do .dwg.

O PROBLEMA. A tabela do cliente (quadro de legenda, lista de ambientes, carga
de circuitos) é uma entidade ACAD_TABLE — classe proprietária que o LibreDWG
não sabe traduzir: ele avisa "Unhandled Class entity ... ACAD_TABLE" e NÃO a
escreve no .dxf. O desenho dela, porém, ele escreve: é o bloco anônimo `*T…`
que o AutoCAD guarda ao lado, com as linhas, os fundos e os textos já
prontos. Resultado, antes deste módulo: a tabela sumia da tela e do arquivo
devolvido, e sobrava no .dxf um bloco "órfão" que ninguém insere.

POR QUE NÃO BASTAVA INSERIR O BLOCO. O bloco `*T…` é LOCAL: a geometria dele
começa em (0, 0) no canto superior esquerdo da tabela e desce em Y negativo
(medido: caixa de (0; -187,3) a (146,4; 0) no Carla e Raymond, de (0; -485,8)
a (148; 0) no Alejandro e Andrea). Quem diz onde a tabela fica é a entidade
ACAD_TABLE, exatamente a que o conversor jogou fora. Inserir em (0, 0) por
chute poria a tabela por cima da planta.

ONDE A POSIÇÃO ESTÁ. Não está no .dxf — nem no BLOCK (base em 0,0,0), nem no
aviso. O .dxf só guarda, no BLOCK_RECORD do bloco, o handle da entidade que o
insere (`102 {BLKREFS / 331 <handle>`). A posição está dentro do próprio
.dwg, e o único canal do `dwg2dxf` que a deixa sair é o log de rastreio
(`-v3`): para a entidade que não sabe traduzir ele despeja os bits crus, e o
prefixo deles é o de um bloco inserido — ponto de inserção, escala, rotação,
extrusão. Duas fontes independentes dentro do mesmo registro concordam bit a
bit nas 9 tabelas dos 6 arquivos até 10 MB da base: o ponto de inserção
decodificado e a translação da matriz do "proxy graphics" que o AutoCAD grava
junto da entidade.

CUSTO. O rastreio é caro: um .dwg de 3,6 MB vira 95 MB de texto e leva 6,0 s,
contra 2,5 s da conversão normal e 1,2 s da mínima. Por isso ele só roda DEPOIS
da conversão normal e só quando ela mesma avisou que descartou uma ACAD_TABLE,
e o texto é varrido em BYTES, procurando a marca do registro, sem quebrar em
linhas. Em arquivo grande o custo explode (ver `_TABELAS_MAX_BYTES` em
dwg_bridge.py), e lá a tabela continua perdida.

NADA DE CHUTE. Tudo aqui devolve "não sei" em vez de um palpite: registro sem
os campos, bits que não decodificam, extrusão que não é (0, 0, 1) — sinal de
que a leitura saiu do alinhamento. Uma tabela de posição desconhecida
continua sendo contada como perdida, como antes.
"""

from __future__ import annotations

import math
import re
import struct
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

#: Marca que o LibreDWG escreve para a entidade de classe que ele não traduz.
#: É o começo do registro que interessa (os campos vêm nas linhas seguintes,
#: até o `crc:` da entidade).
_MARCA_REGISTRO = b"Unhandled Class entity"
_FIM_DO_REGISTRO = b"\ncrc:"

#: O registro inteiro (marca + campos + hexa dos bits crus) tem uns 80 KB nas
#: tabelas medidas. Acima disto é lixo, não registro.
_MAX_REGISTRO = 16 * 1024 * 1024

#: Só os primeiros bytes do hexa importam (o resto é o conteúdo da tabela, que
#: já vem pronto no bloco `*T…`): ponto, flags de escala, escala, rotação e
#: extrusão cabem folgados em 64 bytes.
_BYTES_DO_PREFIXO = 64


@dataclass
class TabelaPerdida:
    """Uma ACAD_TABLE que o `dwg2dxf` descartou, com o que o .dwg diz dela."""

    #: Handle (hexa, maiúsculo) da entidade no .dwg — é a chave que o
    #: BLOCK_RECORD do `*T…` guarda em `{BLKREFS`.
    handle: str
    #: Handle do BLOCK_RECORD do espaço que contém a tabela (modelspace ou
    #: uma prancha; o ezdxf chama isso de `layout_key`) — ou "MODELO" /
    #: "PRANCHA" quando o .dwg não grava o dono (ver `_dono_da_tabela`).
    dono: str
    #: Handle da camada (o nome vem da tabela LAYER do .dxf).
    camada: str
    x: float
    y: float
    z: float = 0.0
    rotacao: float = 0.0
    escala: tuple[float, float, float] = (1.0, 1.0, 1.0)
    invisivel: bool = False
    #: Nome do bloco `*T…` que desenha a tabela. Preenchido por
    #: `blocos_das_tabelas`; vazio = não achei qual bloco é.
    bloco: str = ""
    #: Marcado por quem inseriu no desenho (`dxf_io`), para o chamador saber
    #: quantas tabelas deixaram de ser perda.
    inserida: bool = False

    @property
    def plana(self) -> bool:
        """Só translação: escala 1 e rotação 0. É o único caso MEDIDO (as 5
        tabelas dos 3 projetos menores da base). Escala e rotação são lidas
        pela especificação, mas ninguém confirmou que o AutoCAD NÃO gravou a
        rotação já embutida no bloco `*T…` — aplicar de novo giraria duas
        vezes. Fora do caso medido, quem usa não deve inserir."""
        return (
            all(abs(s - 1.0) < 1e-9 for s in self.escala)
            and abs(self.rotacao) < 1e-12
        )


# --------------------------------------------------------------------------- #
# Decodificação dos bits do DWG
# --------------------------------------------------------------------------- #
class _SemBits(Exception):
    pass


class _Bits:
    """Leitor de bits do DWG: o bit mais significativo de cada byte vem
    primeiro, e os `double` ficam em bytes little-endian dentro desse fluxo,
    sem alinhamento."""

    def __init__(self, dados: bytes) -> None:
        self.dados = dados
        self.pos = 0
        self.total = len(dados) * 8

    def ler(self, n: int) -> int:
        fim = self.pos + n
        if fim > self.total:
            raise _SemBits
        primeiro, ultimo = self.pos >> 3, (fim - 1) >> 3
        bloco = int.from_bytes(self.dados[primeiro : ultimo + 1], "big")
        sobra = (ultimo + 1) * 8 - fim
        self.pos = fim
        return (bloco >> sobra) & ((1 << n) - 1)

    def _bytes(self, n: int) -> bytes:
        return self.ler(8 * n).to_bytes(n, "big")

    def rd(self) -> float:
        """RD: double cru, 64 bits."""
        return struct.unpack("<d", self._bytes(8))[0]

    def bd(self) -> float:
        """BD: 2 bits de código — 00 double completo, 01 vale 1.0, 10 vale
        0.0. (11 não existe; chega aqui só se o alinhamento se perdeu.)"""
        codigo = self.ler(2)
        if codigo == 0:
            return self.rd()
        if codigo == 1:
            return 1.0
        if codigo == 2:
            return 0.0
        raise _SemBits

    def dd(self, padrao: float) -> float:
        """DD: double "com padrão" — 00 usa o padrão, 01 troca só os 4 bytes
        baixos, 10 troca os 4 baixos e 2 dos altos, 11 vem completo."""
        codigo = self.ler(2)
        if codigo == 0:
            return padrao
        cru = bytearray(struct.pack("<d", padrao))
        if codigo == 1:
            cru[0:4] = self._bytes(4)
        elif codigo == 2:
            cru[4:6] = self._bytes(2)
            cru[0:4] = self._bytes(4)
        else:
            return self.rd()
        return struct.unpack("<d", bytes(cru))[0]


def decodifica_insercao(hexa: str) -> tuple[float, float, float, float, tuple[float, float, float]] | None:
    """(x, y, z, rotação, escala) do prefixo de bloco inserido que abre os
    bits crus de uma ACAD_TABLE, ou None se não decodifica com sentido.

    Ordem, igual à do INSERT no formato R2000+: ponto de inserção (3BD),
    flags de escala (BB), escala, rotação (BD), extrusão (3BD). A extrusão é
    a trava de sanidade: toda tabela medida tem (0, 0, 1), e se a leitura
    anterior comeu bits a mais ou a menos ela sai lixo — melhor recusar a
    posição do que posicionar a tabela num lugar inventado."""
    try:
        dados = bytes.fromhex(hexa[: _BYTES_DO_PREFIXO * 2])
        bits = _Bits(dados)
        x, y, z = bits.bd(), bits.bd(), bits.bd()
        flags = bits.ler(2)
        if flags == 3:
            sx = sy = sz = 1.0
        elif flags == 1:
            sx = 1.0
            sy = bits.dd(1.0)
            sz = bits.dd(1.0)
        elif flags == 2:
            sx = bits.rd()
            sy = sz = sx
        else:
            sx = bits.rd()
            sy = bits.dd(sx)
            sz = bits.dd(sx)
        rotacao = bits.bd()
        ex, ey, ez = bits.bd(), bits.bd(), bits.bd()
    except (_SemBits, ValueError, struct.error):
        return None
    numeros = (x, y, z, sx, sy, sz, rotacao, ex, ey, ez)
    if not all(math.isfinite(n) for n in numeros):
        return None
    if abs(ex) > 1e-9 or abs(ey) > 1e-9 or abs(ez - 1.0) > 1e-9:
        return None
    return x, y, z, rotacao, (sx, sy, sz)


# --------------------------------------------------------------------------- #
# Leitura do log de rastreio
# --------------------------------------------------------------------------- #
_RE_HANDLE = re.compile(r"^handle: \d+\.\d+\.([0-9A-Fa-f]+)", re.MULTILINE)
_RE_DONO = re.compile(r"^ownerhandle: \([^)]*\) abs:([0-9A-Fa-f]+)", re.MULTILINE)
_RE_CAMADA = re.compile(r"^layer: \([^)]*\) abs:([0-9A-Fa-f]+)", re.MULTILINE)
_RE_INVISIVEL = re.compile(r"^invisible: (\d+)", re.MULTILINE)
_RE_MODO_DO_DONO = re.compile(r"^entmode: (\d+)", re.MULTILINE)
_RE_BITS = re.compile(r"^unknown_bits \[[^\]]*\]: ([0-9A-Fa-f]+)", re.MULTILINE)


def _dono_da_tabela(texto: str) -> str | None:
    """Quem contém a tabela: o handle do BLOCK_RECORD do espaço, ou
    "MODELO"/"PRANCHA".

    O .dwg só grava o `ownerhandle` quando a entidade vive num espaço que
    precisa ser apontado (`entmode` 0). Para as que vivem direto no
    modelspace (`entmode` 2) ou na prancha padrão (`entmode` 1) o campo nem
    existe — foi o que fez o primeiro protótipo deste leitor perder a tabela da
    JOÃO E BRENDA, a única da base nessa situação."""
    achou = _RE_DONO.search(texto)
    if achou:
        return achou.group(1).upper()
    modo = _RE_MODO_DO_DONO.search(texto)
    if modo:
        return {"2": "MODELO", "1": "PRANCHA"}.get(modo.group(1))
    return None


def le_registro_de_tabela(registro: bytes) -> TabelaPerdida | None:
    """Uma TabelaPerdida a partir do trecho do log que vai da marca
    "Unhandled Class entity" até o `crc:`, ou None se o trecho não é de uma
    ACAD_TABLE ou não traz tudo o que é preciso."""
    texto = registro.decode("latin-1")
    primeira_linha = texto.split("\n", 1)[0]
    if "ACAD_TABLE" not in primeira_linha:
        return None
    handle, camada, bits = (r.search(texto) for r in (_RE_HANDLE, _RE_CAMADA, _RE_BITS))
    if not (handle and camada and bits):
        return None
    dono = _dono_da_tabela(texto)
    if dono is None:
        return None
    prefixo = decodifica_insercao(bits.group(1))
    if prefixo is None:
        return None
    x, y, z, rotacao, escala = prefixo
    invisivel = _RE_INVISIVEL.search(texto)
    return TabelaPerdida(
        handle=handle.group(1).upper(),
        dono=dono,
        camada=camada.group(1).upper(),
        x=x,
        y=y,
        z=z,
        rotacao=rotacao,
        escala=escala,
        invisivel=bool(invisivel and int(invisivel.group(1))),
    )


class ExtratorDeTabelas:
    """Varre o log de rastreio — que tem centenas de MB — em pedaços de
    bytes, sem quebrar em linhas: `bytes.find` roda em C e procura a marca de
    registro; só o que vem depois dela é juntado e interpretado. O mesmo
    texto percorrido linha a linha em Python custaria dezenas de segundos
    num projeto grande.

    Alimentar em pedaços de qualquer tamanho dá o mesmo resultado (a marca e
    o `crc:` podem cair no meio de dois pedaços)."""

    def __init__(self) -> None:
        self.tabelas: list[TabelaPerdida] = []
        #: ACAD_TABLE que o log mostrou mas que não deu para ler.
        self.ilegiveis = 0
        self._buf = bytearray()
        self._capturando = False

    def alimenta(self, pedaco: bytes) -> None:
        self._buf += pedaco
        while True:
            if not self._capturando:
                i = self._buf.find(_MARCA_REGISTRO)
                if i < 0:
                    # Só o rabo pode ser o começo de uma marca cortada ao meio.
                    del self._buf[: max(0, len(self._buf) - len(_MARCA_REGISTRO) + 1)]
                    return
                del self._buf[:i]
                self._capturando = True
            fim = self._buf.find(_FIM_DO_REGISTRO)
            if fim < 0:
                if len(self._buf) > _MAX_REGISTRO:
                    self._buf.clear()
                    self._capturando = False
                return
            registro = bytes(self._buf[:fim])
            del self._buf[: fim + len(_FIM_DO_REGISTRO)]
            self._capturando = False
            if b"ACAD_TABLE" not in registro.split(b"\n", 1)[0]:
                continue
            tabela = le_registro_de_tabela(registro)
            if tabela is None:
                self.ilegiveis += 1
            else:
                self.tabelas.append(tabela)


def acha_tabelas_no_dwg(
    ferramenta: str,
    entrada: Path,
    saida_descartavel: Path,
    esperadas: int,
    limite_s: float,
) -> list[TabelaPerdida]:
    """Roda o `dwg2dxf` de novo, com rastreio, só para ler a posição das
    `esperadas` tabelas que a primeira conversão avisou ter descartado.

    `-m` (só o essencial) porque o .dxf desta volta é jogado fora — o que
    interessa é o log. Para assim que as `esperadas` apareceram (as tabelas
    ficam perto do fim do arquivo, então pouco se economiza, mas é de graça)
    e desiste no `limite_s`: devolve o que achou até lá, e o resto continua
    contado como perdido. Qualquer falha ao executar a ferramenta também vira
    lista vazia — recuperar a tabela é um bônus, nunca motivo para o arquivo
    não abrir."""
    extrator = ExtratorDeTabelas()
    try:
        processo = subprocess.Popen(
            [ferramenta, "-v3", "-m", "-o", str(saida_descartavel), "-y", str(entrada)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return []
    vigia = threading.Timer(limite_s, processo.kill)
    vigia.start()
    try:
        assert processo.stderr is not None
        while True:
            pedaco = processo.stderr.read(1 << 20)
            if not pedaco:
                break
            extrator.alimenta(pedaco)
            if len(extrator.tabelas) + extrator.ilegiveis >= esperadas:
                break
    finally:
        vigia.cancel()
        if processo.poll() is None:
            processo.kill()
        try:
            processo.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        if processo.stderr is not None:
            processo.stderr.close()
    return extrator.tabelas


# --------------------------------------------------------------------------- #
# Qual bloco `*T…` desenha cada tabela
# --------------------------------------------------------------------------- #
_RE_PRIMEIRO_REGISTRO = re.compile(rb"^[ \t]*0\r?\nBLOCK_RECORD\r?$", re.MULTILINE)


def blocos_das_tabelas(dxf: bytes) -> dict[str, str]:
    """handle da ACAD_TABLE -> nome do bloco `*T…` que a desenha.

    O `dwg2dxf` escreve o bloco e esquece a entidade, mas deixa a ponta
    solta no BLOCK_RECORD: `102 {BLKREFS` seguido de `331 <handle>` para
    cada entidade que insere aquele bloco. É por esse elo — e não por
    "todo `*T` que ninguém insere" — que a tabela é ligada ao bloco: o
    Alejandro e Andrea tem 4 blocos `*T` e só 2 tabelas vivas; os outros 2
    são restos de tabelas apagadas (sem BLKREFS) e inserir esses traria de
    volta uma tabela que o projetista tinha apagado.

    Só a tabela BLOCK_RECORD é lida (milhares de linhas), nunca o arquivo
    inteiro (milhões). Lida em pares código/valor, e não por regex solta,
    porque um VALOR pode ser igual a um código ("2", "331") e enganaria a
    busca."""
    achou = _RE_PRIMEIRO_REGISTRO.search(dxf)
    if achou is None:
        return {}
    fim = dxf.find(b"ENDTAB", achou.start())
    regiao = dxf[achou.start() : fim if fim >= 0 else len(dxf)].decode("latin-1")
    linhas = regiao.replace("\r\n", "\n").split("\n")
    resultado: dict[str, str] = {}
    nome: str | None = None
    nas_referencias = False
    for i in range(0, len(linhas) - 1, 2):
        codigo, valor = linhas[i].strip(), linhas[i + 1].strip()
        if codigo == "0":
            nome, nas_referencias = None, False
        elif codigo == "2" and nome is None:
            nome = valor
        elif codigo == "102":
            nas_referencias = valor == "{BLKREFS"
        elif codigo == "331" and nas_referencias and nome and nome.upper().startswith("*T"):
            resultado[valor.upper()] = nome
    return resultado
