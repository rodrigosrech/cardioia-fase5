# CardioIA — Fase 5
## Relatório Técnico: Assistente Cardiológico Conversacional

**Projeto:** CardioIA — Assistente Cardiológico Inteligente e Conversacional
**Disciplina:** Processamento de Linguagem Natural, Chatbots & Virtual Agents (PCV)
**Repositório:** `cardioia-fase5`

---

### 1. Objetivo e escopo

Esta fase entrega um protótipo funcional de assistente conversacional para atendimento inicial em cardiologia. O sistema interpreta mensagens em linguagem natural, organiza informações clínicas relatadas pelo paciente e devolve orientações estruturadas, encaminhando para atendimento humano ou emergência conforme a gravidade identificada.

O escopo é deliberadamente restrito: o assistente **organiza informação**, não realiza diagnóstico, não prescreve medicamentos e não interpreta exames. Essa delimitação está inscrita na própria arquitetura — nenhum nó de diálogo produz hipótese diagnóstica, e o aviso de escopo é exibido na abertura de cada sessão e reiterado nos nós críticos.

### 2. Arquitetura da solução

```
┌──────────────────────┐     HTTP/JSON      ┌────────────────────────┐
│  Interface Web       │ ─────────────────► │  Backend Flask         │
│  (HTML/CSS/JS)       │ ◄───────────────── │  app.py                │
│  frontend/index.html │                    └───────────┬────────────┘
└──────────────────────┘                                │
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                         ┌──────────────────┐  ┌────────────────┐  ┌──────────────┐
                         │ watson_client.py │  │ mock_dialog_   │  │ database.py  │
                         │ IBM Watson       │  │ engine.py      │  │ SQLite       │
                         │ Assistant API v2 │  │ runtime local  │  │ conversas    │
                         └────────┬─────────┘  └───────┬────────┘  └──────────────┘
                                  │                    │
                                  └────────┬───────────┘
                                           ▼
                            ┌──────────────────────────────┐
                            │ skill-cardioia-export.json   │
                            │ intents · entities · nodes   │
                            └──────────────────────────────┘
```

O ponto central do desenho é que **o modelo conversacional é único**. O arquivo `skill-cardioia-export.json` — 14 intents, 7 entities e 32 dialog nodes — é simultaneamente o artefato importado no IBM Watson Assistant e a fonte lida pelo runtime local. Os dois caminhos de execução produzem respostas equivalentes porque interpretam a mesma especificação, e ambos devolvem à camada de aplicação um dicionário normalizado com os mesmos campos (`resposta`, `intent`, `entidades`, `contexto`, `no_acionado`, `emergencia`).

O modo de operação é controlado pela variável `ASSISTANT_MODE`: `watson` exige o serviço remoto, `mock` usa exclusivamente o runtime local e `auto` (padrão) tenta o Watson e degrada para o local em caso de indisponibilidade. Essa decisão de projeto garante que o protótipo permaneça demonstrável independentemente de credenciais ativas, sem que isso represente simplificação do modelo conversacional.

### 3. Modelagem do assistente

**Intenções (14).** Cobrem a abertura e o encerramento da conversa (`saudacao`, `despedida`, `agradecimento`), o relato dos quatro sintomas cardiológicos priorizados (`relato_dor_peito`, `relato_falta_ar`, `relato_palpitacao`, `relato_tontura`), a interação sobre pressão arterial em duas frentes distintas (`duvida_pressao_arterial` para questões conceituais e `informar_pressao` para valores aferidos), além de `duvida_medicacao`, `agendar_consulta`, `falar_com_atendente` e as respostas de acompanhamento `confirmacao_sim` e `negacao_nao`. Cada intenção reúne de 8 a 12 exemplos de treinamento em português brasileiro coloquial. Oito *counterexamples* delimitam o domínio, garantindo que perguntas fora do escopo caiam no fluxo de exceção em vez de forçarem uma classificação inadequada.

**Entidades (7).** Seis são do tipo *synonyms* — `sintoma` (10 valores, incluindo os sinais de alarme `desmaio`, `suor_frio` e `irradiacao_braco`), `intensidade`, `duracao`, `fator_desencadeante`, `classe_medicamento` e `unidade_medida`. A sétima, `pressao_arterial`, é do tipo *patterns* e captura medidas informadas em qualquer notação corrente (`14 por 9`, `140x90`, `150/95`), extraindo os valores sistólico e diastólico em grupos de captura.

**Nós de diálogo (32).** Organizam-se em uma árvore de dois níveis. No primeiro, os nós de tópico são avaliados em ordem de prioridade, com o nó de emergência posicionado logo após as boas-vindas — antes de qualquer nó de sintoma. No segundo nível, os nós filhos qualificam o relato: intensidade da dor torácica, fator desencadeante da dispneia, presença de sintomas associados às palpitações, ocorrência de síncope na tontura e classificação da faixa de pressão arterial.

### 4. Fluxo conversacional

A conversa percorre quatro etapas. A **abertura** aciona o nó `welcome`, que apresenta o assistente, declara o aviso de escopo e inicializa as variáveis de contexto. A **coleta** identifica o tópico pela intenção principal e registra em contexto o sintoma relatado. A **qualificação** aprofunda o relato por meio dos nós filhos, mantendo o nó pai em foco entre turnos — é o que permite interpretar a resposta isolada "é leve" como qualificação da dor torácica mencionada no turno anterior. O **desfecho** classifica o encaminhamento em `emergencia`, `consulta_eletiva`, `acompanhamento` ou `atendimento_humano`.

Exemplo do fluxo de dor torácica:

```
Usuário : "estou sentindo dor no peito"
          intent: relato_dor_peito | entity: @sintoma:dor_peito
          → node_dor_peito | $sintoma_principal = "dor_peito"
Sistema : pergunta a intensidade e antecipa os sinais de alarme

Usuário : "é forte e está irradiando para o braço"
          entities: @intensidade:intensa, @sintoma:irradiacao_braco
          → node_dp_intensa | $encaminhamento = "emergencia"
Sistema : orienta procura imediata do pronto-socorro (SAMU 192)
```

A seleção do nó a cada turno ocorre em três estágios de prioridade. Primeiro, verifica-se se a mensagem responde ao nó em foco por meio de uma condição específica — é a continuidade do fluxo. Se não houver correspondência específica, avaliam-se os nós de topo, permitindo **digressão**: o usuário que informa dor no peito e, no turno seguinte, pede para agendar consulta é atendido no nó de agendamento, não no nó de exceção do fluxo anterior. Apenas quando nenhum dos dois estágios resolve é que se aciona a exceção — local ao nó em foco, quando existir, ou global.

### 5. Tratamento de exceções

O tratamento opera em quatro camadas. Os **nós `anything_else` locais** atendem respostas incompreensíveis dentro de um fluxo específico, reapresentando as opções válidas ("leve, moderada ou intensa") em vez de devolver uma mensagem genérica. O **nó `anything_else` global** captura mensagens fora do domínio, oferece exemplos de uso e o caminho para atendimento humano; sua política de seleção é sequencial, de modo que a segunda falha consecutiva produz texto distinto da primeira, evitando a repetição que caracteriza conversas travadas.

No nível da aplicação, o backend valida a entrada (mensagem vazia retorna HTTP 400; acima de 1.000 caracteres, HTTP 413) e trata falhas de comunicação com o serviço remoto: sessão expirada é recriada automaticamente no turno seguinte, e indisponibilidade prolongada resulta em HTTP 503 com orientação ao usuário — ou em degradação silenciosa para o runtime local, conforme o modo configurado. Falhas de gravação no banco são registradas em log sem interromper o atendimento, decisão que prioriza a continuidade da conversa sobre a completude da auditoria.

A camada de segurança clínica é a mais crítica. Os sinais de alarme — dor torácica intensa, irradiação para braço ou mandíbula, sudorese fria, síncope, dispneia em repouso e pressão em faixa de crise hipertensiva — são avaliados **antes** dos nós de tópico. Essa camada é deliberadamente conservadora: diante da assimetria entre um encaminhamento desnecessário ao pronto-socorro e um sinal de alarme não identificado, o sistema sinaliza na dúvida.

### 6. Persistência e métricas

Cada turno é gravado na tabela `conversas` com sessão, timestamp, mensagem, resposta, intenção detectada, confiança, entidades, nó acionado, sinalizador de emergência e origem da resposta. Sobre esse registro, o endpoint `/api/metricas` calcula volume de interações, sessões distintas, encaminhamentos de urgência, distribuição de intenções e **taxa de fallback** — indicador que expõe diretamente as lacunas de cobertura do modelo e orienta o próximo ciclo de treinamento.

### 7. Validação

A suíte `backend/testes_fluxo.py` executa 50 casos sobre o runtime local, distribuídos em cinco blocos: acurácia de classificação (22 casos), roteamento de nós incluindo continuidade, digressão e exceções (17 casos), classificação das quatro faixas de pressão arterial (4 casos), regras de segurança clínica (5 casos) e integridade das respostas (2 casos). Todos os 50 casos são aprovados na versão entregue.

### 8. Limitações e considerações éticas

O assistente **não emite diagnóstico**. As faixas de pressão arterial e os critérios de alarme são referências gerais de literatura, não parâmetros individualizados — a interpretação depende de idade, comorbidades, gestação e uso de medicamentos, informações que o sistema não coleta nem avalia. As orientações sobre medicamentos limitam-se a princípios de segurança de uso, sem qualquer ajuste de dose ou indicação terapêutica.

O caminho para atendimento humano está disponível em todos os pontos do diálogo, e o encaminhamento é explícito sempre que a dúvida ultrapassa o escopo informativo. Dados de saúde são pessoais sensíveis sob a LGPD (Lei 13.709/2018, art. 5º, II): em uso real, o tratamento exigiria base legal específica, consentimento destacado, criptografia em trânsito e em repouso, política de retenção definida e registro de acesso auditável. Neste protótipo acadêmico, todas as interações são fictícias e o banco local não contém dados reais.

Do ponto de vista técnico, o modelo cobre quatro sintomas cardiológicos e não substitui triagem clínica geral; o runtime local emprega classificação lexical, adequada ao propósito de validação mas inferior ao modelo estatístico do serviço remoto em variações linguísticas não previstas; e o desempenho tende a ser menor para relatos com vocabulário regional ou erros de digitação — limitação com implicação de equidade, já que pode afetar mais justamente quem tem menor acesso a atendimento.

---

*CardioIA — Fase 5 | Assistente Cardiológico Inteligente e Conversacional*
