# CardioIA — Fase 5
## Assistente Cardiológico Inteligente e Conversacional

Protótipo funcional de assistente conversacional para atendimento inicial em cardiologia. O sistema interpreta mensagens em linguagem natural, organiza informações clínicas relatadas pelo paciente e apresenta orientações estruturadas, encaminhando para atendimento humano ou emergência conforme a gravidade identificada.

> **Aviso de escopo**
> Este é um protótipo acadêmico. O assistente **não realiza diagnóstico**, não prescreve medicamentos e não substitui a avaliação de um profissional de saúde. Em situação de emergência, ligue para o **SAMU (192)**.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura do repositório](#3-estrutura-do-repositório)
4. [Instalação e execução](#4-instalação-e-execução)
5. [Demonstração](#5-demonstração)
6. [Configuração do Watson Assistant](#6-configuração-do-watson-assistant)
7. [Modo de simulação local](#7-modo-de-simulação-local)
8. [API REST](#8-api-rest)
9. [Modelo conversacional](#9-modelo-conversacional)
10. [Testes](#10-testes)
11. [Interface](#11-interface)
12. [IR ALÉM — IA Generativa](#12-ir-além--ia-generativa)
13. [Limitações e considerações éticas](#13-limitações-e-considerações-éticas)
14. [Licença](#14-licença)

---

## 1. Visão geral

| Item | Descrição |
|------|-----------|
| **Domínio** | Atendimento inicial informativo em cardiologia |
| **Plataforma de diálogo** | IBM Watson Assistant (API v2) |
| **Backend** | Python 3.9+ · Flask · SQLite |
| **Frontend** | HTML, CSS e JavaScript puro (arquivo único, sem dependências) |
| **Modelo conversacional** | 14 intents · 7 entities · 32 dialog nodes |
| **Cobertura de testes** | 50 casos automatizados |

**Funcionalidades:**

- Reconhecimento de intenção e extração de entidades em português brasileiro
- Manutenção de contexto entre turnos da conversa
- Qualificação progressiva de sintomas (intensidade, duração, fator desencadeante)
- Extração e classificação automática de medidas de pressão arterial
- Detecção de sinais de alarme com escalonamento para emergência
- Digressão entre tópicos sem perda do fluxo
- Tratamento de exceção local e global
- Persistência do histórico e métricas agregadas de uso
- Operação com o serviço remoto ou com runtime local de diálogo

---

## 2. Arquitetura

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

O ponto central do desenho é que **o modelo conversacional é único**. O arquivo `skill-cardioia-export.json` é simultaneamente o artefato importado no IBM Watson Assistant e a especificação lida pelo runtime local. Ambos os caminhos devolvem à aplicação a mesma estrutura de resposta, o que torna a API e a interface indiferentes ao modo de operação em uso.

---

## 3. Estrutura do repositório

```
cardioia-fase5/
├── backend/
│   ├── app.py                          # Aplicação Flask e endpoints REST
│   ├── watson_client.py                # Integração com o Watson Assistant v2
│   ├── mock_dialog_engine.py           # Runtime local de diálogo
│   ├── database.py                     # Persistência em SQLite
│   ├── testes_fluxo.py                 # Suíte de validação (50 casos)
│   ├── requirements.txt                # Dependências
│   └── .env.example                    # Modelo de configuração
├── frontend/
│   └── index.html                      # Interface de chat (arquivo único)
├── watson-assistant/
│   └── skill-cardioia-export.json      # Skill exportado (importável)
├── ir-alem/
│   └── extracao_clinica_ia_generativa.ipynb
├── docs/
│   ├── relatorio-fluxo-conversacional.md
│   ├── roteiro-video-demonstracao.md
│   └── ir-alem-extracao-clinica.md
├── README.md
└── .gitignore
```

---

## 4. Instalação e execução

### Pré-requisitos

- Python 3.9 ou superior
- `pip`
- Navegador moderno

### Passo a passo

```bash
# 1. Clonar o repositório
git clone https://github.com/<usuario>/cardioia-fase5.git
cd cardioia-fase5

# 2. Criar e ativar o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Instalar as dependências
cd backend
pip install -r requirements.txt

# 4. Configurar o ambiente (opcional — veja a seção 6)
cp .env.example .env

# 5. Executar o servidor
python app.py
```

Saída esperada:

```
CardioIA iniciado | modo configurado=auto | modo ativo=mock
 * Running on http://127.0.0.1:5000
```

Acesse **http://localhost:5000** — o backend serve a interface diretamente, dispensando servidor adicional.

### Verificação rápida

```bash
curl http://localhost:5000/api/saude
```

---

## 5. Demonstração

Esta seção reúne evidências de funcionamento do assistente: transcrições de conversas reais produzidas pelo motor de diálogo e a saída integral da suíte de testes automatizados. Todos os trechos abaixo são saída direta do sistema — não foram editados manualmente.

### 5.1 Conversas de exemplo

**Escalonamento para emergência**

O relato de dor torácica é qualificado em dois turnos; a intensidade "forte" combinada à irradiação para o braço aciona a camada de segurança clínica e escala o atendimento.

> **Usuário:** estou sentindo dor no peito
>
> **CardioIA:** Entendi que você está sentindo desconforto no peito. Para organizar melhor essas informações, me diga: a dor é leve, moderada ou intensa?
>
> Se a dor for intensa, surgir em repouso, irradiar para o braço ou mandíbula, ou vier acompanhada de suor frio e falta de ar, procure atendimento de emergência imediatamente (SAMU 192).
>
> **Usuário:** é forte e está irradiando para o braço esquerdo
>
> **CardioIA:** Dor torácica de forte intensidade é considerada um sinal de alarme e exige avaliação imediata.
>
> Procure o pronto-socorro agora ou ligue para o SAMU (192). Não dirija e não aguarde a dor passar sozinha.
>
> Registrei esta ocorrência como prioridade alta no seu atendimento.

**Extração e classificação de pressão arterial**

A entidade de padrão reconhece a medida em notação corrente, converte para mmHg e classifica a faixa.

> **Usuário:** minha pressão está 14 por 9
>
> **CardioIA:** Recebi o valor de pressão arterial informado. Vou organizar essa informação para você.
>
> O valor informado está acima da faixa considerada usualmente normal (referência geral: abaixo de 140 x 90 mmHg em medida de consultório).
>
> Orientações gerais:
> - Repita a medida após 5 minutos de repouso, sentado e com o braço apoiado.
> - Registre as medidas por alguns dias, sempre no mesmo horário.
> - Reduza o consumo de sal, álcool e mantenha atividade física conforme orientação médica.
>
> Uma única medida elevada não define hipertensão: o diagnóstico depende de avaliação médica. Deseja informações sobre agendamento de consulta?

**Tratamento de exceção (mensagem fora do domínio)**

> **Usuário:** qual a previsão do tempo hoje
>
> **CardioIA:** Desculpe, não consegui compreender a sua mensagem. Eu fui treinado para ajudar com temas cardiológicos.
>
> Você pode tentar, por exemplo:
> - "estou com dor no peito"
> - "minha pressão está 14 por 9"
> - "tenho dúvida sobre meu remédio"
> - "quero agendar uma consulta"
>
> Se preferir, digite "falar com atendente" para ser transferido a um humano.

### 5.2 Saída da suíte de validação

Execução de `python testes_fluxo.py`, sem edição:

```
============================================================================
CardioIA - Fase 5 | Validacao do modelo conversacional
============================================================================
Skill......: CardioIA - Assistente Cardiologico Conversacional
Idioma.....: pt-br
Estrutura..: 14 intents | 7 entities | 32 dialog nodes

1. CLASSIFICACAO DE INTENCOES
----------------------------------------------------------------------------
  [OK]    oi bom dia                                     -> saudacao
  [OK]    estou com dor no peito                         -> relato_dor_peito
  [OK]    estou com falta de ar                          -> relato_falta_ar
  [OK]    meu coracao esta disparado                     -> relato_palpitacao
  [OK]    estou com tontura                               -> relato_tontura
  [OK]    qual o valor normal da pressao                 -> duvida_pressao_arterial
  [OK]    minha pressao esta 14 por 9                    -> informar_pressao
  [OK]    posso parar de tomar o remedio da pressao      -> duvida_medicacao
  [OK]    quero marcar uma consulta                      -> agendar_consulta
  [OK]    quero falar com um atendente                   -> falar_com_atendente
  ... (22 casos no total, todos aprovados)

2. ROTEAMENTO DE DIALOG NODES
----------------------------------------------------------------------------
  [OK]    Dor toracica leve                              -> node_dp_leve_moderada
  [OK]    Dor toracica intensa                           -> node_dp_intensa
  [OK]    Digressao para agendamento                     -> node_agendamento
  [OK]    Falta de ar ao esforco                         -> node_fa_esforco
  [OK]    Falta de ar em repouso                         -> node_fa_intensa
  [OK]    Palpitacao com sintoma associado               -> node_palp_associado
  [OK]    Tontura com sincope                            -> node_tontura_sincope
  [OK]    Sinal de alarme direto                         -> node_emergencia
  ... (17 casos no total, todos aprovados)

3. CLASSIFICACAO DA PRESSAO ARTERIAL
----------------------------------------------------------------------------
  [OK]    minha pressao esta 12 por 8                    -> adequada
  [OK]    medi 14 por 9 agora                            -> elevada
  [OK]    deu 180 por 110 no aparelho                    -> crise_hipertensiva
  [OK]    aferi 85 por 55                                -> baixa

4. REGRAS DE SEGURANCA (SINAIS DE ALARME)
----------------------------------------------------------------------------
  [OK]    dor no peito muito forte agora                 -> encaminhamento de urgencia
  [OK]    quase desmaiei hoje                            -> encaminhamento de urgencia
  [OK]    dor no peito com suor frio                     -> encaminhamento de urgencia
  [OK]    dor que irradia para o braco esquerdo          -> encaminhamento de urgencia
  [OK]    minha pressao deu 190 por 120                  -> encaminhamento de urgencia

5. INTEGRIDADE DAS RESPOSTAS
----------------------------------------------------------------------------
  [OK]    Todos os dialog nodes possuem texto de resposta
  [OK]    Orientacao de emergencia (SAMU 192) presente nos nos criticos

============================================================================
RESULTADO: 50/50 casos aprovados
============================================================================
```

A lista completa dos 50 casos está no código-fonte de `backend/testes_fluxo.py` e pode ser reproduzida a qualquer momento com o comando acima.

---

## 6. Configuração do Watson Assistant

### 6.1 Importar o skill

1. Acesse o **IBM Cloud** e abra sua instância do Watson Assistant.
2. Vá em **Assistants → Create assistant** e nomeie o assistente como `CardioIA`.
3. Em **Actions/Dialog skills → Add skill → Import skill**, envie o arquivo `watson-assistant/skill-cardioia-export.json`.
4. Aguarde a conclusão do treinamento (indicador de status no topo da tela).
5. Publique o assistente em **Preview → Publish**.

### 6.2 Obter as credenciais

| Credencial | Onde encontrar |
|------------|----------------|
| `WATSON_API_KEY` | IBM Cloud → Watson Assistant → **Manage → API Key** |
| `WATSON_SERVICE_URL` | IBM Cloud → Watson Assistant → **Manage → URL** |
| `WATSON_ASSISTANT_ID` | Assistente → **Settings → API details → Assistant ID** |

### 6.3 Configurar o backend

Edite `backend/.env`:

```env
ASSISTANT_MODE=watson
WATSON_API_KEY=sua-chave-aqui
WATSON_SERVICE_URL=https://api.us-south.assistant.watson.cloud.ibm.com/instances/...
WATSON_ASSISTANT_ID=seu-assistant-id-aqui
WATSON_API_VERSION=2021-06-14
```

Reinicie o servidor. O endpoint `/api/saude` deve passar a reportar `"modo_ativo": "watson"`.

> O arquivo `.env` contém credenciais e **não deve ser versionado** — já consta no `.gitignore`.

---

## 7. Modo de simulação local

O projeto funciona integralmente sem credenciais do Watson Assistant. O runtime local (`mock_dialog_engine.py`) interpreta o mesmo arquivo de skill e reproduz o comportamento do runtime oficial: classificação de intenção, reconhecimento de entidades, avaliação da árvore de nós, variáveis de contexto e nós de exceção.

| `ASSISTANT_MODE` | Comportamento |
|------------------|---------------|
| `auto` (padrão) | Tenta o Watson Assistant; recorre ao runtime local em caso de falha |
| `watson` | Exige o serviço remoto; retorna HTTP 503 se indisponível |
| `mock` | Usa exclusivamente o runtime local |

Essa arquitetura garante reprodutibilidade da avaliação e permite executar a suíte de testes em ambientes sem acesso à rede, sem simplificar o modelo conversacional — que permanece o mesmo nos dois casos.

---

## 8. API REST

### `POST /api/chat`

Processa uma mensagem do usuário.

**Requisição**

```json
{
  "message": "estou com dor no peito",
  "session_id": "uuid-opcional"
}
```

**Resposta — HTTP 200**

```json
{
  "session_id": "3f2a...",
  "resposta": "Entendi que você está sentindo desconforto no peito...",
  "intent": "relato_dor_peito",
  "confianca": 0.75,
  "entidades": [
    { "entity": "sintoma", "value": "dor_peito", "literal": "dor no peito" }
  ],
  "no_dialogo": "node_dor_peito",
  "emergencia": false,
  "origem": "mock",
  "contexto": {
    "sintoma_principal": "dor_peito",
    "etapa_atendimento": "coleta_sintoma"
  },
  "timestamp": "2026-03-15T14:22:08+00:00"
}
```

**Códigos de erro**

| Código | Situação |
|--------|----------|
| `400` | Campo `message` ausente ou vazio |
| `413` | Mensagem acima de 1.000 caracteres |
| `503` | Serviço de diálogo indisponível (modo `watson`) |
| `500` | Erro interno |

### `GET /api/historico/<session_id>`

Retorna o histórico persistido da sessão. Parâmetro opcional: `?limite=50` (máximo 200).

### `POST /api/sessao/reiniciar`

Encerra a sessão e limpa o contexto.

```json
{ "session_id": "3f2a...", "apagar_historico": false }
```

### `GET /api/metricas`

Métricas agregadas de uso.

```json
{
  "total_interacoes": 42,
  "total_sessoes": 7,
  "encaminhamentos_emergencia": 3,
  "total_fallbacks": 2,
  "taxa_fallback": 0.0476,
  "distribuicao_intents": [
    { "intent": "relato_dor_peito", "ocorrencias": 12, "confianca_media": 0.81 }
  ]
}
```

A **taxa de fallback** é o indicador mais relevante para evolução do modelo: aponta diretamente as lacunas de cobertura das intenções treinadas.

### `GET /api/saude`

Health check, incluindo o modo de operação ativo e o resumo do skill carregado.

---

## 9. Modelo conversacional

### 9.1 Intenções (14)

| Grupo | Intenções |
|-------|-----------|
| Abertura e encerramento | `saudacao`, `despedida`, `agradecimento` |
| Relato de sintomas | `relato_dor_peito`, `relato_falta_ar`, `relato_palpitacao`, `relato_tontura` |
| Pressão arterial | `duvida_pressao_arterial`, `informar_pressao` |
| Apoio ao tratamento | `duvida_medicacao`, `agendar_consulta` |
| Atendimento humano | `falar_com_atendente` |
| Acompanhamento | `confirmacao_sim`, `negacao_nao` |

Cada intenção reúne de 8 a 12 exemplos de treinamento. Oito *counterexamples* delimitam o domínio.

### 9.2 Entidades (7)

| Entidade | Tipo | Valores |
|----------|------|---------|
| `sintoma` | synonyms | 10 valores, incluindo os sinais de alarme `desmaio`, `suor_frio` e `irradiacao_braco` |
| `intensidade` | synonyms | `leve`, `moderada`, `intensa` |
| `duracao` | synonyms | `agora`, `horas`, `dias`, `semanas` |
| `fator_desencadeante` | synonyms | `esforco`, `repouso`, `emocional` |
| `classe_medicamento` | synonyms | anti-hipertensivo, betabloqueador, estatina, anticoagulante |
| `unidade_medida` | synonyms | `mmHg`, `bpm` |
| `pressao_arterial` | **patterns** | Captura medidas em qualquer notação (`14 por 9`, `140x90`, `150/95`) |

### 9.3 Fluxo de diálogo

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

A seleção de nó ocorre em três estágios: continuidade do fluxo em foco, digressão para outro tópico do domínio e, por último, exceção — local ao nó em foco, quando existir, ou global.

### 9.4 Classificação da pressão arterial

| Faixa | Classificação | Encaminhamento |
|-------|---------------|----------------|
| ≥ 180 × 110 | `crise_hipertensiva` | Emergência |
| ≥ 140 × 90 | `elevada` | Consulta eletiva |
| < 90 × 60 | `baixa` | Consulta eletiva |
| Demais | `adequada` | Acompanhamento |

Medidas em escala reduzida ("14 por 9") são convertidas automaticamente para mmHg.

---

## 10. Testes

```bash
cd backend
python testes_fluxo.py
```

| Bloco | Casos | Cobertura |
|-------|-------|-----------|
| Classificação de intenções | 22 | Acurácia sobre conjunto de validação |
| Roteamento de dialog nodes | 17 | Continuidade, digressão e exceções |
| Classificação da pressão arterial | 4 | Quatro faixas de referência |
| Regras de segurança clínica | 5 | Detecção de sinais de alarme |
| Integridade das respostas | 2 | Textos presentes e orientação de emergência |
| **Total** | **50** | |

O processo retorna código de saída `0` quando todos os casos passam, permitindo uso em integração contínua.

---

## 11. Interface

Arquivo único (`frontend/index.html`), sem dependências externas.

**Recursos:**

- Layout de chat com mensagens diferenciadas por autor
- Indicador de digitação durante o processamento
- Destaque visual para respostas com encaminhamento de urgência
- Exibição da intenção reconhecida em cada resposta
- Sugestões de mensagem para início rápido da conversa
- Indicador de status do serviço e do modo de operação ativo
- Botão de reinício da conversa
- Layout responsivo para desktop e dispositivos móveis
- Envio por `Enter`; quebra de linha por `Shift + Enter`

**Segurança:** o conteúdo das mensagens é inserido via `textContent`, prevenindo injeção de HTML.

A interface é servida pelo próprio backend em `http://localhost:5000`. Também pode ser aberta diretamente do sistema de arquivos — nesse caso, ela aponta para `http://localhost:5000` por padrão, e o CORS já está habilitado.

---

## 12. IR ALÉM — IA Generativa

O notebook `ir-alem/extracao_clinica_ia_generativa.ipynb` implementa a extração de informações clínicas a partir de relatos livres, convertendo texto não estruturado em JSON validado.

**Conteúdo:**

- JSON Schema formal com vocabulário controlado por `enum`
- Prompt estruturado em quatro blocos, com exemplos *few-shot*
- Dois motores intercambiáveis (LLM via API e determinístico local)
- Validação obrigatória de toda saída contra o schema
- Camada de segurança clínica para sinais de alarme
- Três relatos de demonstração com 21 verificações automatizadas
- Exportação em formato consumível pelos demais módulos

O notebook executa integralmente no Google Colab **sem credenciais**, por meio do motor determinístico local.

Documentação completa: [`docs/ir-alem-extracao-clinica.md`](docs/ir-alem-extracao-clinica.md).

---

## 13. Limitações e considerações éticas

**O assistente não emite diagnóstico.** As faixas de pressão arterial e os critérios de alarme são referências gerais de literatura, não parâmetros individualizados — a interpretação depende de idade, comorbidades, gestação e medicamentos em uso, informações que o sistema não coleta nem avalia.

**Orientações sobre medicamentos** limitam-se a princípios de segurança de uso. O sistema não ajusta doses, não indica nem suspende tratamentos.

**Detecção conservadora de sinais de alarme.** A camada de segurança sinaliza na dúvida. Os erros possíveis são assimétricos: um falso positivo gera uma ida desnecessária ao pronto-socorro; um falso negativo pode custar uma vida.

**Atendimento humano sempre disponível.** A intent `falar_com_atendente` é acessível em qualquer ponto do diálogo, e o encaminhamento é explícito sempre que a dúvida ultrapassa o escopo informativo.

**Proteção de dados.** Dados de saúde são pessoais sensíveis sob a LGPD (Lei 13.709/2018, art. 5º, II). Em uso real, seriam requisitos mínimos: base legal específica, consentimento destacado, criptografia em trânsito e em repouso, política de retenção definida e registro de acesso auditável. Neste protótipo, todas as interações são fictícias e o banco local não contém dados reais.

**Limitações técnicas.** O modelo cobre quatro sintomas cardiológicos e não substitui triagem clínica geral. O runtime local emprega classificação lexical, adequada à validação mas inferior ao modelo estatístico do serviço remoto diante de variações linguísticas não previstas. O desempenho tende a ser menor para relatos com vocabulário regional ou erros de digitação — limitação com implicação de equidade.

---

## 14. Licença

Projeto acadêmico desenvolvido para fins educacionais, no âmbito da disciplina de Processamento de Linguagem Natural, Chatbots & Virtual Agents.

Uso restrito a contexto acadêmico. **Não destinado a uso clínico real.**

---

*CardioIA — Fase 5 | Assistente Cardiológico Inteligente e Conversacional*
