"""Pilha de undo/redo por snapshot do dicionário de entidades do Document.

Simples e correto para o tamanho atual dos desenhos: cada snapshot é uma
cópia profunda de `document.entities`. Não é o mais eficiente para desenhos
enormes, mas evita ter que rastrear o "desfazer" de cada comando
individualmente.
"""

from __future__ import annotations

import copy

from newsicad.core.document import Document


# Cada snapshot é uma cópia profunda de TODO `document.entities` — sem um
# teto, uma sessão longa (centenas de comandos, cada um empilhando um
# snapshot inteiro) acumula memória sem limite, principalmente em desenhos
# grandes. 200 passos de undo já é bem mais do que o AutoCAD guarda por
# padrão (`UNDOCTRL`/`MAXACTVP` de sobra); o mais antigo é descartado
# silenciosamente quando o teto é atingido (bug real de auditoria,
# 2026-08-22 — pilha era ilimitada).
_MAX_UNDO_DEPTH = 200


class UndoStack:
    def __init__(self, document: Document) -> None:
        self.document = document
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

    def _snapshot(self) -> dict:
        return copy.deepcopy(self.document.entities)

    def push(self) -> None:
        """Chamado ANTES de um comando que pode alterar o desenho."""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > _MAX_UNDO_DEPTH:
            del self._undo_stack[0]
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        self.document.entities = self._undo_stack.pop()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        self.document.entities = self._redo_stack.pop()
        return True
