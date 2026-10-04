# Varredura da base — resultado, outubro de 2026

Varredura automática dos **218 projetos `.dwg` da base** (3,5 GB, 48 clientes,
anexos dos itens de projeto do monday), sem esperar relato da equipe. O
método e as armadilhas de medição estão em [VARREDURA.md](VARREDURA.md).

Duas perguntas, duas medições independentes:

| | ferramenta | cobre |
|---|---|---|
| o desenho chega inteiro? | `tools/auditoria_projeto.py` | 193 arquivos (os 25 maiores estouraram o limite de tempo **da auditoria**) |
| está lento? | `tools/tempo_de_abertura.py` | 199 arquivos, incluindo os de 71 MB |

---

## 1. O desenho chega inteiro?

```
auditados: 187        SEM NENHUM ALERTA: 90 (48%)
cobertura:  mediana  99,5%
segmentos:  mediana 100,0%   pior 93,5%
```

**Nenhum arquivo deixa de ser lido.** Os 187 auditados abrem; os 6 que a
auditoria não concluiu estouraram o limite de tempo **dela** (ela mede os
dois lados do arquivo), e todos os 6 abrem no programa em ~6,5 min.

**Um único arquivo perde segmento de verdade** — `NEWSI-CARLA E RAYMOND_R04`,
93,5% —, e o que falta são hachuras de área zero vindas de importação de PDF
(camadas `PDF2_*`), que o AutoCAD também não desenha.

### O que o programa ainda não lê

| tipo | projetos | entidades | o que é |
|---|---|---|---|
| OLE2FRAME | 32 | 143 | objeto OLE colado (planilha, imagem de outro programa) |
| 3DSOLID | 10 | 372 | sólido 3D ACIS — fora de escopo de um editor 2D |
| HATCH | 19 | 111 | resíduo: contorno que o achatador não fecha |
| REGION | 14 | 92 | região ACIS, mesma família do 3DSOLID |
| INSERT | 13 | 74 | bloco de nome vazio (a etiqueta já é recuperada) |
| VIEWPORT | 17 | 17 | janela de prancha, não é desenho |
| MLINE | 5 | 18 | multilinha (parede de linha dupla) |

O mais espalhado é o **OLE2FRAME** (32 projetos); o mais incômodo em
potencial é a **MLINE**, que é parede.

---

## 2. Está lento?

Medido com 4 arquivos em paralelo numa máquina de 4 núcleos — um arquivo
sozinho tende a ser um pouco mais rápido.

| tamanho | arquivos | abrir (mediana) | pior | gravar (mediana) | pior |
|---|---|---|---|---|---|
| 0–2 MB | 56 | **5,0 s** | 11 s | 4,5 s | 47 s |
| 2–5 MB | 48 | 20,5 s | 44 s | 29 s | 116 s |
| 5–10 MB | 42 | 41,0 s | 59 s | 83 s | 175 s |
| 10–20 MB | 26 | 71,8 s | 140 s | 75 s | 319 s |
| 20–40 MB | 15 | 144,6 s | 265 s | 338 s | 647 s |
| 40–100 MB | 12 | **390 s** | 397 s | **1.048 s** | 1.097 s |

- mediana geral de abertura: **26,5 s**; 30% abrem em menos de 10 s; **22%
  passam de 1 minuto**
- **gravar custa 2,2× o que custa abrir** (somando a base: 54 min
  convertendo, 144 min lendo, **428 min gravando**)

### Onde está o custo — não é o número de entidades

Os cinco arquivos mais lentos são do mesmo cliente e têm **1.229 a 1.260
entidades no model space — e 1.800 a 1.880 definições de bloco**. Abrem em
6,6 min e gravam em 17,5 min.

> O gargalo dos projetos grandes é a **tabela de blocos**, não o desenho.
> É onde uma otimização teria efeito real, e é a próxima frente natural.

---

## 3. O que a varredura consertou

Treze defeitos, todos achados medindo e nenhum relatado pela equipe.

### Arquivo que não abria

| defeito | alcance |
|---|---|
| `.dwg` com acento no nome | 4 arquivos (NFD do iCloud); um com 66.166 entidades |
| POLYLINE sem SEQEND | 6 arquivos de 2 clientes |
| Ordem de desenho corrompida | Casa Sanchez `PV1_R07` |
| Falha ao limpar o temporário | derrubava a abertura depois de ela dar certo |

### Desenho que sumia

| defeito | alcance medido |
|---|---|
| **IMAGE (imagem raster)** | **19% dos arquivos**, 221 imagens; três plantas de luminotécnico foram de 73,6% / 83,9% / 89,5% para **100%** de cobertura |
| **Tipo de linha e espessura** | 6 de 7 projetos da amostra; Casa Sapucaia: **9.179 de 9.179** tracejados preservados |
| **ATTDEF solto** | **413 etiquetas de circuito** do Fernando Labes |
| 3DFACE do arquivo base | 72 no `BASE_XREF_LEE` do Joe Lee |
| Etiqueta de INSERT órfão | 19 etiquetas de corte da Patrícia e Fábio |
| Acento partido no meio dos bytes | nota de projeto do Joe Lee |

### O que estava errado era o alarme, não o desenho

| | antes | agora |
|---|---|---|
| aviso de abertura do Carla e Raymond | 2.146 entidades "perdidas" | **1** |
| aviso de abertura do Escritório H&M | 1.080 | **0** |

Eram SOLID e HATCH de **área zero** (contorno A→B→A, de importação de PDF).
Recusá-los está certo; contá-los como perda não estava.

### E o pior de todos

**O nosso saneador de DXF corrompia o arquivo do cliente, e o programa
adivinhava o resto.** O `splitlines()` do Python quebra linha em oito
caracteres que o DXF não usa — entre eles o byte `0x85`, que é parte do
símbolo de **diâmetro** (`∅`) em UTF-8. O saneador perdia a contagem
código/valor e colava linhas boas: **208 mesclagens indevidas** num arquivo
da Casa Sanchez, criando tags inválidas. O estrago ficava invisível porque a
leitura tolerante do ezdxf **chutava** os valores.

Depois do conserto, no mesmo arquivo: 208 → 1 mesclagem, arquivo saneado
idêntico ao original, e o ezdxf lê as 76.017 entidades sem recuperação.

---

## 4. O que fica aberto

- **Gravação dos projetos grandes** — 17,5 min num arquivo de 71 MB, com o
  custo na tabela de blocos. É a maior frente restante.
- **OLE2FRAME** em 32 projetos; dava para desenhar ao menos a moldura.
- **MLINE** (parede de linha dupla) em 5 projetos.
- **REGION / 3DSOLID** — ACIS, fora do escopo de um editor 2D
  (ver [ESCOPO.md](ESCOPO.md)).
- **ACAD_TABLE** continua sumindo, com os blocos `*T…` prontos no arquivo.
- Texto de cota sobrescrito; EXPLODE não explode bloco; "arquivo modificado"
  fica ligado para sempre depois de mexer em camada.

---

## 5. Sobre confiar nestes números

Doze vezes um número grande apontou para um defeito que não existia, e
reportar qualquer um deles teria custado mais confiança do que o defeito
custaria. Os doze estão listados em [VARREDURA.md](VARREDURA.md). Os dois
que mais ensinaram:

- **"O programa leva 25 minutos para abrir seis arquivos."** Cronometrando
  etapa por etapa: 9,6 s e 15,8 s. Os 25 minutos eram da ferramenta de
  auditoria.
- **"A legenda explodiu: 22 etiquetas fora do lugar."** Era um arquivo de
  legenda **100% íntegro**; a âncora de um TEXT centralizado é o ponto 11,
  não o 10.

Por isso toda cobertura neste documento vem acompanhada da razão de
segmentos, e todo alerta grande foi conferido num caso concreto antes de
virar linha de relatório.
