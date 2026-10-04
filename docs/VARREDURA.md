# Varredura da base — método e disciplina de medição

Desde 01/10/2026 os defeitos do NewSIcad são achados varrendo a base real de
projetos, não esperando o relato da equipe. Este documento registra **como**
a varredura mede e, principalmente, **como os números enganam** — porque
onze vezes um número grande apontou para um defeito que não existia, e
reportar qualquer um deles teria custado mais confiança do que o defeito
custaria.

## O que é a base

218 arquivos `.dwg`, 3,5 GB, de 48 clientes. Eles **não estão no Drive**:
são anexo de UPDATE nos itens de projeto dos boards de cliente do monday
("2.2 Pré-Projeto", "2.3/2.4 Projeto Aprovado", "2.1 Projetos Executivos").

## As ferramentas

| Ferramenta | Responde |
|---|---|
| `tools/varredura_base.py` | o que entra e o que se perde, por tipo de entidade |
| `tools/varredura_render.py` | apareceu alguma coisa na tela? (pega "abriu em branco") |
| `tools/auditoria_projeto.py` | os itens estão NO LUGAR CERTO? (a que importa) |
| `tools/relatorio_auditoria.py` | a fila de trabalho, ordenada por quantos projetos cada defeito atinge |

A auditoria compara, para **cada espaço de desenho** (Model e cada prancha):

- extensão total e extensão **por camada** (pega "a legenda explodiu");
- contagem de segmentos por camada (pega "sumiu linha");
- uma **grade de ocupação de 256×256** sobre a prancha, com mapa PNG do
  diff (vermelho = sumiu, azul = apareceu onde não devia);
- etiqueta por etiqueta, comparada por **conteúdo e âncora**;
- degradação de tipo (a cota voltou como cota, ou virou linha solta?).

Os dois lados são achatados pelo **mesmo** código, com a mesma tolerância —
comparação maçã com maçã, sem favorecer o nosso resultado.

## Como ler os números

**Cobertura sozinha NÃO é veredito.** Ela é normalizada pela extensão do
arquivo INTEIRO: duas formas cheias longe do desenho esticam a caixa de
medição e fazem o desenho real caber num canto da grade. O `BASE_XREF_LEE`
do Joe Lee aparecia com **4% de cobertura** tendo **4.323 dos 4.327
segmentos presentes**.

> Regra: cobertura só conta como perda quando a **razão de segmentos** cai
> junto. O relatório imprime as duas lado a lado e separa os casos em que
> elas discordam.

**Antes de chamar lentidão de defeito do produto, cronometre as etapas
separadas.** Seis arquivos da Ricardo e Gabriela estouravam o limite de
1.500 s da auditoria. O programa abre esses arquivos em **9,6 s e 15,8 s**:
a lentidão era do achatador da própria ferramenta.

**Número grande merece MAIS desconfiança, não menos.** Os dois maiores
"defeitos" que a varredura já produziu — 4.579 SOLID e 1.229 HATCH "não
lidos" — eram polígonos de área zero, que o AutoCAD também não desenha.

## Os onze falsos positivos do método

Registrados porque errar aqui é pior do que não medir: cada um teria virado
um relatório de defeito inexistente.

1. **Invisibilidade ignorada.** O `recursive_decompose` do ezdxf desenha
   variante inativa de bloco dinâmico. As dez molduras A0–A4 empilhadas no
   bloco de margem da New SI davam "34,5% de cobertura" num arquivo a 95,8%.
2. **Anotação não expandida do lado da referência.** LEADER/MULTILEADER/
   DIMENSION/ACAD_TABLE: como o NewSIcad materializa a seta e a linha de
   chamada, parecia que ele INVENTAVA geometria — 67 LEADER num layout do
   Joe Lee viraram 4.501 células de sobra inexistente.
3. **Texto achatado como caixa.** A nossa é sempre MTEXT e tem largura
   diferente: acusava geometria estranha em toda etiqueta. Texto saiu da
   comparação geométrica e virou comparação por conteúdo e posição.
4. **Herança de camada.** Conteúdo de bloco na camada "0" assume a camada do
   INSERT — regra do AutoCAD que o nosso importador aplica e o
   `virtual_entities` não. Dava "camada 0 fora do lugar, 44,9%".
5. **Âncora de texto errada.** Num TEXT centralizado a âncora é o ponto 11
   (`align_point`), não o 10. Acusava 22 etiquetas fora do lugar num arquivo
   de LEGENDA que está 100% íntegro — exatamente o sintoma "a legenda
   explodiu" que teria sido reportado.
6. **VIEWPORT filtrado pelo nome da camada**, que no padrão da New SI é
   `_NEWSI_VIEWPORTS`. Dava "96,6% — some desenho".
7. **Os 1.500 s** acima: lentidão da ferramenta, não do produto.
8. **Acento embaralhado no log.** A nota "ALTERAÇ??ES" parecia corrupção
   nossa; o registro da auditoria tinha ZERO substituto. O embaralhado era
   artefato do encadeamento de log — e o defeito de verdade estava no
   ORIGINAL, não no nosso (ver `remonta_acento`).
9. **Cobertura esticada pela caixa de medição** (o `BASE_XREF_LEE` acima).
10. **Preenchimento de área zero.** 4.579 SOLID e 1.229 HATCH com contorno
    A→B→A, vindos de importação de PDF. Recusá-los está certo; o defeito era
    contá-los no aviso de abertura.
11. **Exceção fora da guarda.** O ezdxf calcula o caminho da primitiva SOB
    DEMANDA, então a spline defeituosa do `dwg2dxf` estourava na linha do
    `is_empty`, fora do `try` que protegia a criação da lista. Três arquivos
    apareciam como "não abre" e abrem sem reclamar.

## Rodando

```bash
python tools/auditoria_projeto.py <pasta> --saida auditoria.json \
       --mapas mapas --trabalhadores 4 --tempo-limite 1800
python tools/relatorio_auditoria.py auditoria.json
```

A varredura é **retomável** (pula o que já está no JSON) e cada arquivo roda
num processo separado, porque travamento duro e estouro de memória
derrubavam a varredura inteira no arquivo 70 de 218.

**Ao mexer no importador, refaça a varredura inteira antes de usar os
números num relatório** — misturar registros de versões diferentes do
programa dá um retrato que não corresponde a nenhuma delas.
