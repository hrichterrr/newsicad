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

#: Foto da estrutura: (definições de bloco, todo o resto). São dois blobs
#: separados porque só o primeiro é caro — ver `UndoStack._blocks_cache`.
_Structure = tuple[bytes, bytes]

# Teto de profundidade: 200 passos já é bem mais do que o AutoCAD guarda por
# padrão. Teto de memória: com ~7 MB por snapshot numa planta pesada, 300 MB
# dão ~40 passos nela e os 200 completos em desenhos normais (bug real de
# auditoria, 2026-08-22 — a pilha era ilimitada).
_MAX_UNDO_DEPTH = 200
_MAX_UNDO_BYTES = 300 * 1024 * 1024


#: Campos do Document que NÃO são entidades e ainda assim fazem parte do
#: estado do desenho. Ficavam de fora do undo: redefinir um bloco por engano
#: era irreversível, e desfazer um PURGE devolvia as entidades sem devolver a
#: definição de bloco nem a camada, deixando INSERT órfão e entidade em camada
#: inexistente — um .dxf que o próprio `ezdxf.audit` reprova (auditoria de
#: 2026-09-07).
_STRUCTURE_FIELDS = (
    "block_definitions",
    "block_attdefs",
    "layers",
    "units",
    "text_styles",
    "current_text_style",
    "current_layer",
    "table_style",
    "mleader_style",
    "dim_style",
    "text_height",
    "annotation_scale",
    "fillet_radius",
    "isolated_layers",
)


class UndoStack:
    def __init__(self, document: Document) -> None:
        self.document = document
        # (snapshot das entidades, snapshot da estrutura, token desse estado)
        self._undo_stack: list[tuple[bytes, _Structure, int]] = []
        self._redo_stack: list[tuple[bytes, _Structure, int]] = []
        self._counter = 0
        self._current = 0
        #: (block_defs_revision -> bytes) da última foto das DEFINIÇÕES DE
        #: BLOCO. É a parte cara: 24 MB e ~1 s na planta NEWSI-CASA PAU
        #: BRASIL-R01 (244 blocos, 110 mil entidades dentro deles). Enquanto
        #: nenhum bloco for redefinido — o caso de longe mais comum — todos os
        #: passos compartilham o MESMO objeto de bytes.
        #:
        #: Ela fica separada do resto da estrutura (camadas, estilos,
        #: unidades) de propósito: o resto é pequeno e é fotografado a cada
        #: passo. Numa chave só, com `revision` junto, apagar uma camada ou
        #: rodar LAYISO — que mexem em `revision` — obrigava a refotografar os
        #: 24 MB de blocos, que não tinham mudado nada.
        self._blocks_cache: tuple[int, bytes] | None = None

    # ------------------------------------------------------------------ #
    # snapshots
    # ------------------------------------------------------------------ #
    def _snapshot(self) -> bytes:
        return pickle.dumps(self.document.entities, protocol=pickle.HIGHEST_PROTOCOL)

    def _structure_snapshot(self) -> _Structure:
        """Foto do que não é entidade: (definições de bloco, resto)."""
        key = self.document.block_defs_revision
        if self._blocks_cache is None or self._blocks_cache[0] != key:
            self._blocks_cache = (
                key,
                pickle.dumps(self.document.block_definitions, protocol=pickle.HIGHEST_PROTOCOL),
            )
        resto = {
            campo: getattr(self.document, campo)
            for campo in _STRUCTURE_FIELDS
            if campo != "block_definitions"
        }
        return (
            self._blocks_cache[1],
            pickle.dumps(resto, protocol=pickle.HIGHEST_PROTOCOL),
        )

    def _restore_structure(self, blob: _Structure) -> None:
        atual = self._structure_snapshot()
        if blob is atual or blob == atual:
            # Nada de estrutura mudou entre os dois estados — o caso de longe
            # mais comum. Sair aqui mantém `revision` intacta, e é ela que o
            # "arquivo modificado?" da aba compara para saber que um undo até
            # o ponto salvo voltou a deixar o desenho limpo.
            return
        blocos, resto = blob
        self.document.block_definitions = pickle.loads(blocos)
        for campo, valor in pickle.loads(resto).items():
            setattr(self.document, campo, valor)
        # As revisões só avançam: quem faz cache do CONTEÚDO (as impressões
        # digitais do canvas) compara esses números, e voltar o contador para
        # trás faria o cache achar que nada mudou.
        self.document.revision += 1
        self.document.block_defs_revision += 1
        self._blocks_cache = None

    def _restore(self, snapshot: bytes, structure: _Structure | None = None) -> None:
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
                continue
            # AVISA O CANVAS. `pickle.loads` monta o objeto direto no
            # __dict__, sem passar pelo __setattr__ — então a entidade
            # restaurada NÃO entrava no registro de alterados
            # (`entities.drain_dirty()`), e como o id dela já tinha item na
            # cena, ela também não contava como "nova". A passada incremental
            # não via nada para fazer: desfazer um MOVE devolvia a entidade
            # ao lugar certo no documento e deixava o DESENHO na posição
            # errada. Na tela parecia que o Ctrl+Z não fez nada, e o objeto
            # ficava impossível de selecionar — o clique procura onde o
            # documento diz que ele está, e ali não havia item nenhum
            # (relatado pelo Hamilton em 09/09/2026 movendo uma caixa de som
            # para fora da planta; vale para todo undo/redo de MOVE, ROTATE,
            # SCALE, STRETCH e mudança de propriedade — o de apagar e o de
            # criar sempre funcionaram, porque ali os ids somem ou aparecem).
            entity.touch()
        self.document.entities = restored
        if structure is not None:
            self._restore_structure(structure)

    def _trim(self) -> None:
        while len(self._undo_stack) > _MAX_UNDO_DEPTH:
            del self._undo_stack[0]
        # A foto dos blocos é compartilhada entre passos (mesmo objeto de
        # bytes), então conta uma vez só; o resto da estrutura é por passo.
        total = sum(len(s) for s, _, _ in self._undo_stack)
        total += sum({id(t[0]): len(t[0]) for _, t, _ in self._undo_stack}.values())
        total += sum(len(t[1]) for _, t, _ in self._undo_stack)
        while len(self._undo_stack) > 1 and total > _MAX_UNDO_BYTES:
            total -= len(self._undo_stack[0][0])
            del self._undo_stack[0]

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #
    def push(self) -> None:
        """Chamado ANTES de um comando que pode alterar o desenho."""
        self._undo_stack.append((self._snapshot(), self._structure_snapshot(), self._current))
        self._trim()
        self._redo_stack.clear()
        self._counter += 1
        self._current = self._counter

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        snapshot, structure, token = self._undo_stack.pop()
        self._redo_stack.append((self._snapshot(), self._structure_snapshot(), self._current))
        self._restore(snapshot, structure)
        self._current = token
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        snapshot, structure, token = self._redo_stack.pop()
        self._undo_stack.append((self._snapshot(), self._structure_snapshot(), self._current))
        self._restore(snapshot, structure)
        self._current = token
        return True

    def drop_last(self) -> None:
        """Descarta o passo empilhado por ultimo.

        Para quem empilha ANTES de uma operacao que ainda pode ser recusada
        no meio (renomear camada para um nome que ja existe, por exemplo):
        sem isto a operacao recusada deixaria para tras um Ctrl+Z que nao faz
        nada."""
        if not self._undo_stack:
            return
        _snapshot, _structure, token = self._undo_stack.pop()
        self._current = token

    def warm(self) -> None:
        """Tira a primeira foto das definições de bloco fora da hora do
        aperto. Ela custa ~1 s numa planta com centenas de blocos, e sem isto
        cai inteira no primeiro comando que altera o desenho — uma travada no
        primeiro clique de quem acabou de abrir o arquivo. Chamada pela
        abertura, enquanto o diálogo de progresso ainda está na tela."""
        self._structure_snapshot()

    def state_id(self) -> int:
        """Token do estado atual do desenho. Dois tokens iguais = o mesmo
        estado (undo/redo levam e trazem de volta ao mesmo token); um `push`
        cria um token novo, que nunca se repete. Usado pelo "modificado?" da
        sessão — nada aqui olha o conteúdo das entidades."""
        return self._current

    def memory_bytes(self) -> int:
        passos = self._undo_stack + self._redo_stack
        blocos_unicos = {id(t[0]): len(t[0]) for _, t, _ in passos}
        return (
            sum(len(s) for s, _, _ in passos)
            + sum(len(t[1]) for _, t, _ in passos)
            + sum(blocos_unicos.values())
        )
