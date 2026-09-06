"""Pilha de undo/redo por snapshot do dicionário de entidades do Document.

Cada snapshot é o `document.entities` serializado com `pickle` (protocolo
mais alto). Era `copy.deepcopy`: na planta NEWSI-CASA PAU BRASIL-R01 (43 mil
entidades) o deepcopy custava 2,7 s ANTES de cada comando que altera o
desenho, e 200 níveis de pilha seriam 200 cópias vivas de todas as entidades.
O pickle faz o mesmo trabalho em 0,27 s (o serializador é C), guarda ~7 MB
por snapshot nessa planta, e por ser bytes dá pra impor um teto de MEMÓRIA
(`_MAX_UNDO_BYTES`) além do teto de profundidade — o mais antigo cai quando
qualquer um dos dois estoura (medições de 2026-09-03).

A pilha também expõe `state_id()`: um token inteiro único por ESTADO do
desenho, sem olhar o conteúdo. Cada `push` cria um estado novo (token novo);
undo/redo devolvem o token do estado restaurado, então voltar por undo ao
ponto salvo dá o mesmo token de quando se salvou. Tokens nunca se repetem,
mesmo quando a pilha descarta os mais antigos — profundidade não serviria,
porque o descarte desloca todas as posições. É o que
`DocumentSession.is_dirty` compara com o estado gravado em disco, no lugar de
copiar e comparar o documento inteiro a cada passo de comando (10 s por
clique na mesma planta).
"""

from __future__ import annotations

import pickle

from newsicad.core.document import Document

# Teto de profundidade: 200 passos já é bem mais do que o AutoCAD guarda por
# padrão. Teto de memória: com ~7 MB por snapshot numa planta pesada, 300 MB
# dão ~40 passos nela e os 200 completos em desenhos normais (bug real de
# auditoria, 2026-08-22 — a pilha era ilimitada).
_MAX_UNDO_DEPTH = 200
_MAX_UNDO_BYTES = 300 * 1024 * 1024


class UndoStack:
    def __init__(self, document: Document) -> None:
        self.document = document
        # (snapshot do estado, token desse estado)
        self._undo_stack: list[tuple[bytes, int]] = []
        self._redo_stack: list[tuple[bytes, int]] = []
        self._counter = 0
        self._current = 0

    # ------------------------------------------------------------------ #
    # snapshots
    # ------------------------------------------------------------------ #
    def _snapshot(self) -> bytes:
        return pickle.dumps(self.document.entities, protocol=pickle.HIGHEST_PROTOCOL)

    def _restore(self, snapshot: bytes) -> None:
        """Volta ao snapshot PRESERVANDO os objetos atuais que não mudaram.

        `pickle.loads` devolve objetos novos para todas as entidades; o
        canvas identifica cada item gráfico pela identidade do objeto, então
        trocar todas de uma vez o obrigava a recriar a cena inteira em cima
        de uma cena cheia — 292 s num Ctrl+Z na planta NEWSI-CASA PAU
        BRASIL-R01 (43 mil entidades; 265 s só em QGraphicsScene.addItem,
        medição de 2026-09-05). Comparar cada entidade restaurada com a
        atual (== do dataclass, sem a versão) custa décimos de segundo e
        deixa só o que o undo de fato desfez para o canvas recriar."""
        restored = pickle.loads(snapshot)
        current = self.document.entities
        for key, entity in restored.items():
            old = current.get(key)
            if old is not None and old == entity:
                restored[key] = old
        self.document.entities = restored

    def _trim(self) -> None:
        while len(self._undo_stack) > _MAX_UNDO_DEPTH:
            del self._undo_stack[0]
        total = sum(len(s) for s, _ in self._undo_stack)
        while len(self._undo_stack) > 1 and total > _MAX_UNDO_BYTES:
            total -= len(self._undo_stack[0][0])
            del self._undo_stack[0]

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #
    def push(self) -> None:
        """Chamado ANTES de um comando que pode alterar o desenho."""
        self._undo_stack.append((self._snapshot(), self._current))
        self._trim()
        self._redo_stack.clear()
        self._counter += 1
        self._current = self._counter

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        snapshot, token = self._undo_stack.pop()
        self._redo_stack.append((self._snapshot(), self._current))
        self._restore(snapshot)
        self._current = token
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        snapshot, token = self._redo_stack.pop()
        self._undo_stack.append((self._snapshot(), self._current))
        self._restore(snapshot)
        self._current = token
        return True

    def state_id(self) -> int:
        """Token do estado atual do desenho. Dois tokens iguais = o mesmo
        estado (undo/redo levam e trazem de volta ao mesmo token); um `push`
        cria um token novo, que nunca se repete. Usado pelo "modificado?" da
        sessão — nada aqui olha o conteúdo das entidades."""
        return self._current

    def memory_bytes(self) -> int:
        return sum(len(s) for s, _ in self._undo_stack) + sum(len(s) for s, _ in self._redo_stack)
