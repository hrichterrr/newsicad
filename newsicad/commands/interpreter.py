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
from newsicad.core.document import Document
from newsicad.core.entities import Point

# Sentinela enviada ao generator quando o usuário aperta Enter/Espaço sem digitar nada.
ENTER = object()

PromptKind = str  # "point" | "distance" | "text" | "keyword"


@dataclass
class Prompt:
    message: str
    kind: PromptKind = "point"
    options: list[str] = field(default_factory=list)


CommandFactory = Callable[[Document], Generator[Prompt, object, None]]


class CommandInterpreter:
    def __init__(self, document: Document, registry: dict[str, CommandFactory], aliases: dict[str, str]):
        self.document = document
        self.registry = registry
        self.aliases = aliases
        self.log: list[str] = []
        self.last_command_name: str | None = None
        self.last_point: Point | None = None
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
        self.log.append(f"Command: {command_text.strip().upper()}")
        factory = self.registry[name]
        self._generator = factory(self.document)
        self.last_command_name = name
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
        return self._advance(point)

    def submit_text(self, text: str, cursor_point: Point | None = None) -> Prompt | None:
        prompt = self._current_prompt
        if prompt is None:
            return None

        raw = text.strip()
        if raw == "":
            return self._advance(ENTER)

        option_match = next(
            (opt for opt in prompt.options if opt.upper() == raw.upper()), None
        )
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
                prompt = self._generator.send(value)
        except StopIteration:
            self._generator = None
            self._current_prompt = None
            return None
        self._current_prompt = prompt
        self.log.append(prompt.message)
        return prompt
