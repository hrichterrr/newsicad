"""Máquina de estados do prompt de comando, no estilo da linha de comando do AutoCAD.

Cada comando é uma função geradora que "yield"a um Prompt pedindo a próxima
entrada (ponto, distância, palavra-chave) e recebe de volta o valor já
resolvido via generator.send(). O CommandInterpreter dirige essa geração e
mantém o histórico exibido na janela de comando.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generator

from newsicad.commands.coord_parser import CoordParseError, parse_coordinate
from newsicad.commands.context import CommandContext
from newsicad.core.entities import Point

# Sentinela enviada ao generator quando o usuário aperta Enter/Espaço sem digitar nada.
ENTER = object()

PromptKind = str  # "point" | "distance" | "text" | "keyword" | "selection" | "info"


@dataclass
class Prompt:
    message: str
    kind: PromptKind = "point"
    options: list[str] = field(default_factory=list)
    # Para kind="point": indica se o canvas deve desenhar uma linha de "borracha"
    # ligando o último ponto até o cursor e aplicar OSNAP/ORTHO/POLAR de definição
    # de geometria. False para prompts que só *identificam* uma entidade já
    # existente na tela (ex.: "select the line to trim/extend/fillet"), onde esse
    # rubber-band não faz sentido e mais atrapalha do que ajuda.
    connect_to_last: bool = True
    # Para kind="point"/"distance": Enter é uma resposta VÁLIDA aqui (encerra
    # uma sequência de pontos, como o "Specify next point" da LINE/PLINE).
    # Sem isto, Enter num prompt que exige valor encerra o comando — ver
    # CommandInterpreter.submit_text.
    accepts_enter: bool = False


CommandFactory = Callable[[CommandContext], Generator[Prompt, object, None]]


def option_keyword(option: str) -> str:
    """Abreviação de uma opção de prompt, na convenção do AutoCAD: as LETRAS
    MAIÚSCULAS do nome ("Undo" -> U, "Close" -> C, "eXit" -> X, "DElta" ->
    DE, "Add vertex" -> A). Sem maiúscula nenhuma, cai na primeira letra."""
    caps = "".join(ch for ch in option if ch.isupper())
    return (caps or option[:1]).upper()


def match_option(raw: str, options: list[str], allow_prefix: bool = True) -> str | None:
    """Qual opção o usuário digitou, ou None.

    Aceita, nesta ordem: o nome inteiro, a abreviação em maiúsculas (ver
    `option_keyword`) e — só onde `allow_prefix` — um prefixo que combine
    com uma única opção. Num prompt que pede TEXTO livre (o conteúdo de uma
    célula de TABLE, por exemplo) o prefixo fica de fora: lá "e" é a letra
    que o usuário quer escrever, não o começo de "eXit". Até a
    2.15.10 só o nome INTEIRO valia: quem digitava "R" no [Radius] do FILLET
    ou "U" no [Undo] da LINE — o que o AutoCAD ensina e o próprio prompt
    sugere com a maiúscula — caía no parser de coordenada e levava um
    "valor inválido", com a opção parecendo não existir. É o que estava por
    trás de "Fillet não está funcionando" e de "não dá pra recuar a linha"
    no feedback do grupo do NewSicad (22/09/2026)."""
    if not options:
        return None
    alvo = raw.upper()
    for opt in options:
        if opt.upper() == alvo or option_keyword(opt) == alvo:
            return opt
    if not allow_prefix:
        return None
    prefixo = [opt for opt in options if opt.upper().startswith(alvo)]
    return prefixo[0] if len(prefixo) == 1 else None

#: Teto de linhas guardadas do histórico da linha de comando, e quanto se
#: descarta de uma vez quando ele estoura. O histórico crescia sem limite e
#: era REESCRITO INTEIRO na tela a cada passo de comando (ver
#: CommandLine.set_log): com 250 comandos já dados, uma LINE custava 208 ms
#: em vez de 21 ms, e com 2.500 comandos, 1,6 s — sem nenhuma relação com o
#: tamanho do desenho. É a causa do "o programa vai ficando pesado, tenho que
#: fechar e abrir" (auditoria de 07/09/2026 com as amostras da Autodesk).
_MAX_LINHAS_LOG = 5000
_DESCARTE_LOG = 1000


class CommandLog(list):
    """Histórico da linha de comando: uma lista com teto, que sabe quantas
    linhas já passaram por ela.

    `total` nunca diminui, mesmo quando as mais antigas são descartadas — é
    por ele que a tela sabe quantas linhas ainda não desenhou e acrescenta só
    essas, em vez de redesenhar o histórico inteiro."""

    def __init__(self, iterable=()) -> None:
        super().__init__(iterable)
        self.total = len(self)

    def append(self, item: str) -> None:
        super().append(item)
        self.total += 1
        if len(self) > _MAX_LINHAS_LOG:
            del self[:_DESCARTE_LOG]


class CommandInterpreter:
    def __init__(
        self,
        context: CommandContext,
        registry: dict[str, CommandFactory],
        aliases: dict[str, str],
    ):
        self.context = context
        self.registry = registry
        self.aliases = aliases
        self.log: list[str] = CommandLog()
        self.last_command_name: str | None = None
        self.last_point: Point | None = None
        #: Pontos já informados no comando ATUAL, na ordem. `last_point` é só
        #: o último; quem precisa dos anteriores — o preview do ARC, que
        #: desenha o arco de verdade passando pelos dois primeiros pontos e
        #: pelo cursor — lê daqui. Zerado a cada comando.
        self.command_points: list[Point] = []
        self._generator: Generator[Prompt, object, None] | None = None
        self._current_prompt: Prompt | None = None

    @property
    def active(self) -> bool:
        return self._generator is not None

    @property
    def current_prompt(self) -> Prompt | None:
        return self._current_prompt

    def resolve_command(self, text: str) -> str | None:
        return self.aliases.get(text.strip().upper())

    def start(self, command_text: str) -> Prompt | None:
        name = self.resolve_command(command_text)
        if name is None:
            self.log.append(f"Comando desconhecido: \"{command_text}\"")
            return None
        if name not in self.registry:
            self.log.append(
                f"{name}: comando reconhecido, ainda não implementado nesta versão do NewSIcad."
            )
            return None
        self.log.append(f"Command: {command_text.strip().upper()}")
        # Ver CommandContext.preselection_available.
        self.context.preselection_available = bool(self.context.selection.ids)
        factory = self.registry[name]
        self._generator = factory(self.context)
        self.last_command_name = name
        self.last_point = None
        self.command_points = []
        return self._advance(None)

    def start_generator(self, generator: Generator[Prompt, object, None]) -> Prompt | None:
        """Inicia um generator de comando já construído (parâmetros extras
        fechados via closure), sem passar pelo lookup normal de nome/registry.

        Usado por fluxos que precisam de uma etapa de UI própria antes dos
        prompts point/distance/text (ex.: XREF e IMAGEATTACH abrem um
        QFileDialog na MainWindow primeiro, e só depois alimentam este
        generator com o restante — ver newsicad/commands/block_commands.py)."""
        self._generator = generator
        self.context.preselection_available = bool(self.context.selection.ids)
        self.last_command_name = None
        self.last_point = None
        self.command_points = []
        return self._advance(None)

    def repeat_last(self) -> Prompt | None:
        if self.last_command_name is None:
            return None
        return self.start(self.last_command_name)

    def cancel(self) -> None:
        if self._generator is not None:
            self._generator.close()
        self._generator = None
        self._current_prompt = None
        self.log.append("*Cancel*")

    def submit_point(self, point: Point) -> Prompt | None:
        """Ponto vindo de um clique no canvas (não da linha de comando).

        Se o prompt atual espera uma distância (ex.: raio do CIRCLE), o clique
        é convertido na distância até o último ponto, em vez de enviar o
        Point bruto ao comando — igual ao comportamento do AutoCAD ao clicar
        na tela para definir um raio.
        """
        prompt = self._current_prompt
        if prompt is not None and prompt.kind == "distance" and self.last_point is not None:
            return self._advance(self.last_point.distance_to(point))
        if prompt is not None and prompt.kind in ("text", "keyword"):
            # Clique não é resposta pra prompt que pede PALAVRA. Mandar o
            # Point cru fazia o FIELD morrer com erro de Python na tela
            # ("'Point' object has no attribute 'upper'"), o MTEXT escrever
            # literalmente "Point(x=105, y=105)" na prancha, o INSERT
            # procurar um bloco com esse nome e a TABLE preencher célula com
            # o mesmo lixo — tudo em silêncio (auditoria de 07/09/2026 com as
            # amostras da Autodesk). É a irmã gêmea do "Enter em prompt de
            # ponto", corrigida na 2.15.9: mesmo engano de dedo, direção
            # contrária. O clique é ignorado e o prompt continua de pé.
            return prompt
        return self._advance(point)

    def submit_text(self, text: str, cursor_point: Point | None = None) -> Prompt | None:
        prompt = self._current_prompt
        if prompt is None:
            return None

        raw = text.strip()
        if raw == "":
            if (
                prompt.kind in ("point", "distance")
                and not prompt.accepts_enter
                and "<" not in prompt.message
            ):
                # Enter num prompt que EXIGE um valor encerra o comando, como
                # no AutoCAD ("Specify first point" + Enter sai do comando).
                # Antes o sentinela ENTER seguia para o gerador e virava valor
                # de campo: CIRCLE guardava um `object()` no raio, a entidade
                # entrava no desenho e a partir dali repintar, desfazer e
                # SALVAR estouravam — o usuário perdia tudo desde o último
                # save, sem conseguir nem apagar o objeto (auditoria de
                # 2026-09-07). Outros 13 comandos devolviam um erro interno de
                # Python na linha de comando. Prompt COM padrão no texto
                # (`<1>`, `<TL>`, `<2.50>`) continua aceitando Enter — é a
                # convenção que todo comando com valor default já usa.
                self.cancel()
                return None
            return self._advance(ENTER)

        option_match = match_option(raw, prompt.options, allow_prefix=prompt.kind != "text")
        if option_match is not None:
            return self._advance(option_match.upper())

        if prompt.kind == "point":
            try:
                value: object = parse_coordinate(raw, self.last_point, cursor_point)
            except CoordParseError as exc:
                self.log.append(str(exc))
                return prompt
        elif prompt.kind == "distance":
            try:
                value = float(raw)
            except ValueError:
                self.log.append(f"Valor numérico inválido: \"{raw}\"")
                return prompt
        elif prompt.kind == "keyword":
            # Se o prompt define `options`, só chegamos aqui quando `raw` NÃO
            # bateu com nenhuma delas (o match já teria retornado lá em cima)
            # — sem essa checagem, qualquer texto era aceito como se fosse
            # uma opção válida (bug real encontrado em auditoria: FIELD
            # aceitava um tipo inexistente e virava um campo `#REF!` pra
            # sempre). Prompt sem `options` definidas continua aceitando
            # qualquer palavra, como sempre.
            if prompt.options:
                self.log.append(
                    f"Opção inválida: \"{raw}\" — escolha uma de [{'/'.join(prompt.options)}]."
                )
                return prompt
            value = raw.upper()
        else:
            value = raw

        return self._advance(value)

    def _advance(self, value: object) -> Prompt | None:
        assert self._generator is not None
        try:
            if value is None:
                prompt = next(self._generator)
            else:
                if isinstance(value, Point):
                    self.last_point = value
                    self.command_points.append(value)
                prompt = self._generator.send(value)
        except StopIteration:
            self._generator = None
            self._current_prompt = None
            return None
        except Exception as exc:
            # Qualquer erro não previsto dentro do generator do comando (ex.:
            # geometria degenerada que a validação de entrada não pegou)
            # cancela SÓ o comando atual com uma mensagem clara, em vez de
            # deixar a exceção subir e travar o app inteiro — auditoria
            # encontrou vários comandos (ARC com pontos colineares, ARRAY/
            # DIVIDE/MEASURE com Enter em branco num prompt sem guarda)
            # crashando por essa falta de rede de segurança.
            self._generator = None
            self._current_prompt = None
            self.log.append(
                f"{self.last_command_name or 'Comando'}: erro inesperado ({exc}) — comando cancelado."
            )
            return None
        self._current_prompt = prompt
        self.log.append(prompt.message)
        if prompt.kind == "info":
            # mensagem informativa: loga e segue pro próximo yield sem esperar input
            return self._advance(None)
        return prompt
