# Escopo do NewSIcad

> Decisão do Hamilton em 01/10/2026, depois de medir as alternativas (ver o
> fim deste documento). Este arquivo manda: pedido que não couber aqui não
> vira trabalho sem que o escopo mude primeiro, por escrito.

## O que o NewSIcad é

**O editor de projetos da New SI.** Ele abre a planta do arquiteto, lança os
pontos dos nossos sistemas, mantém o padrão de prancha da casa e entrega o
arquivo para o cliente.

## O que o NewSIcad não é

**Um substituto geral do AutoCAD.** Não compete em modelagem, em comandos de
desenho avançado nem em personalização genérica — e não precisa competir,
porque ninguém na New SI desenha arquitetura: nós recebemos a arquitetura
pronta e marcamos a automação em cima dela.

Essa distinção é a correção de rumo. Perseguir "clone do AutoCAD" é perseguir
um alvo que não tem fim: a cada entrega aparecia um comando que falta, e a
sensação de "nunca fica redondo" vinha disso, não da qualidade do que estava
feito.

## Os três compromissos

Dentro deste escopo, três coisas precisam ser impecáveis. São as únicas em que
errar custa a confiança da equipe:

1. **Ler a planta do cliente sem perda.** O arquivo chega do arquiteto em
   `.dwg` e tem que aparecer como aparece no AutoCAD dele — blocos, textos,
   hachuras, cotas, chamadas, atributos, camadas. É aqui que doeu de verdade
   em 2026 (ver o histórico de 22/09 no README) e é aqui que a régua é mais
   alta.
2. **Lançar e editar os pontos New SI.** Inserir o símbolo do sistema, numerar
   a tag na nomenclatura da casa, montar a legenda, preencher o selo.
3. **Entregar.** PDF para a obra e `.dxf`/`.dwg` que abram certo no AutoCAD do
   cliente, sem perder nada do que ele mandou nem do que nós acrescentamos.

## O que está congelado

Os **72 comandos de desenho e edição** já implementados (LINE, ARC, TRIM,
OFFSET, FILLET, HATCH, DIM*, BLOCK, TABLE, LEADER...) cobrem o fluxo de
marcação. A lista para de crescer por padrão.

Comando novo de CAD genérico só entra quando **um projeto real travar sem
ele** — não porque o AutoCAD tem.

## Regra de decisão para pedido novo

Para quem recebe um pedido da equipe, a pergunta é uma só:

> **O pedido serve para marcar, revisar ou entregar um projeto da New SI?**
>
> - **Sim** → entra na fila normal.
> - **Não, é "o AutoCAD tem e aqui não"** → vai para a lista de espera e só
>   sobe se travar um projeto de verdade. Responder isso na hora, com o
>   motivo, em vez de prometer.

A segunda pergunta, para priorizar dentro do "sim":

> **É fidelidade de leitura do arquivo do cliente?** Se for, fura a fila.

## O roteiro daqui pra frente

O que o AutoCAD **não** dá para a New SI, e que justifica o NewSIcad existir:

- **Biblioteca de símbolos da casa integrada** — inserir ponto por sistema
  (áudio, vídeo, CFTV, rede, automação, infraestrutura) direto de um painel,
  com camada, cor, caixa, altura e cabo já certos pelo dicionário de símbolos.
- **Tag automática** na nomenclatura da New SI, numerando por ambiente e
  sistema em vez de o projetista digitar.
- **Legenda que se monta sozinha** a partir do que foi lançado na prancha —
  hoje é mantida à mão e desatualiza.
- **Selo, revisão e caderno por etapa** (PRÉ-PROJETO → PROJETO → PROJETO EX. →
  PROJETO APROVADO → INSTALAÇÃO FINA) no padrão da empresa.
- **Checklist do padrão antes de entregar** — conferir selo, revisão, arquivo
  de referência, nota e legenda, que hoje é conferência humana.

Nada disso existe em CAD nenhum do mercado, por melhor que seja. É aqui que o
software ganha de comprar licença.

## Por que não migramos de base

Em 01/10/2026 foram testados, com os arquivos reais da New SI, todos os
candidatos de código aberto:

| Candidato | Resultado |
|---|---|
| LibreCAD 2.2.1.5 | não abre o `.dwg`; com `.dxf`, nenhuma geometria |
| FreeCAD 1.1.4 | descarta HATCH, MULTILEADER, ATTRIB, ATTDEF, WIPEOUT; zero objetos de texto; 25–50 s para abrir |
| QCAD Community 3.33.1 | sem DWG na edição livre (é plugin pago) |
| ODA File Converter | empata com o LibreDWG que já usamos, e é mais lento |

Nenhum CAD de código aberto lê DWG nativamente — todos terceirizam para o
mesmo punhado de conversores. A pilha atual (LibreDWG + ezdxf + o importador
próprio) é, por medição, a melhor combinação disponível para estes arquivos.
Detalhe completo na memória do projeto (`newsicad-base-alternativas`).
