# CardioIA — Fase 5
## IR ALÉM 1 — Extração de Informações Clínicas com IA Generativa

**Projeto:** CardioIA — Assistente Cardiológico Inteligente e Conversacional
**Notebook:** `ir-alem/extracao_clinica_ia_generativa.ipynb`
**Versão do schema:** 1.0.0

---

## 1. Motivação

O assistente conversacional entregue na Parte 1 opera por intenções e entidades: reconhece categorias previamente treinadas e roteia o diálogo conforme a classificação obtida. Esse modelo é previsível e auditável — propriedades decisivas em saúde — mas pressupõe mensagens curtas e centradas em um único tópico.

Relatos reais raramente se comportam assim. Uma frase espontânea combina múltiplas informações:

> *"Sinto dores no peito há dois dias, principalmente quando subo escadas, e minha pressão estava 14 por 9 na última medição."*

A mensagem carrega, simultaneamente, um sintoma, sua duração, o fator que o desencadeia e uma medida de pressão arterial. Modelar cada combinação possível como uma intenção distinta produziria uma explosão combinatória insustentável. É exatamente a lacuna que a IA Generativa preenche: um único modelo, orientado por prompting estruturado, extrai todos os campos de uma vez, sem que cada combinação precise ter sido antecipada no treinamento.

## 2. Arquitetura do módulo

```
Relato livre do paciente
          │
          ▼
  Montagem do prompt  ──►  papel + regras + schema + exemplos few-shot
          │
          ▼
   Motor de extração   ──►  (A) LLM via API   |   (B) extrator determinístico
          │
          ▼
  Parsing da resposta  ──►  isolamento e leitura do objeto JSON
          │
          ▼
  Validação de schema  ──►  tipos, obrigatoriedade, domínios permitidos
          │
          ▼
  Pós-processamento    ──►  regras de segurança clínica
          │
          ▼
     JSON estruturado
```

### 2.1 Dois motores, um contrato

O módulo opera em dois modos selecionáveis:

| Modo | Motor | Requer credenciais | Papel |
|------|-------|--------------------|-------|
| `llm` | Modelo de linguagem via API | Sim | Operação plena, com capacidade de generalização |
| `local` | Extrator determinístico | Não | Execução autônoma, gabarito de validação e contingência |

O modo `local` implementa **as mesmas regras declaradas no prompt**, porém em código explícito, com léxicos e expressões regulares. Sua existência cumpre três funções: permite executar o notebook completo no Google Colab sem credenciais, preservando a reprodutibilidade da avaliação; fornece um gabarito contra o qual auditar a saída do modelo generativo; e mantém o módulo operante caso a API esteja indisponível — situação tratada por fallback automático, registrado no campo `metadados.motor`.

O schema, o prompt e as rotinas de validação são idênticos nos dois modos. Muda apenas o mecanismo que produz o JSON.

## 3. Schema de saída

O schema é definido **antes** do prompt. Essa ordem não é detalhe de organização: é o que distingue prompting estruturado de uma solicitação livre ao modelo. O formato de saída passa a ser um contrato explícito, verificável, em vez de uma expectativa implícita.

### 3.1 Campos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sintomas` | array | Sintomas identificados, cada um com categoria, intensidade e fator desencadeante |
| `duracao` | object | Tempo de evolução: valor, unidade e trecho original do relato |
| `pressao_arterial` | object \| null | Sistólica, diastólica, unidade e classificação |
| `nivel_urgencia` | enum | `emergencia`, `alta`, `moderada` ou `baixa` |
| `sinais_de_alarme` | array | Achados que exigem avaliação imediata |
| `recomendacao` | string | Orientação ao paciente, sempre reforçando avaliação profissional |
| `confianca_extracao` | number | Grau de completude da informação extraída (0 a 1) |
| `metadados` | object | Motor utilizado, versão do schema e momento do processamento |

### 3.2 Vocabulário controlado

Todos os campos categóricos são restringidos por `enum`. As categorias de sintoma aceitas são `dor_toracica`, `dispneia`, `palpitacao`, `tontura`, `sincope`, `edema`, `fadiga`, `sudorese`, `nausea` e `outro`. A intensidade admite `leve`, `moderada`, `intensa` ou `null`. O fator desencadeante admite `esforco`, `repouso`, `emocional`, `postural` ou `null`.

Essa restrição resolve um problema concreto dos modelos generativos: sem vocabulário fechado, o mesmo sintoma pode ser rotulado como "dor torácica" em uma execução, "dor no peito" em outra e "desconforto precordial" em uma terceira. Com `enum`, o valor está dentro da lista ou a saída é rejeitada na validação.

### 3.3 Faixas de classificação da pressão arterial

| Faixa | Critério | Classificação |
|-------|----------|---------------|
| Abaixo de 90 × 60 | sistólica < 90 ou diastólica < 60 | `baixa` |
| Até 129 × 84 | — | `adequada` |
| 130 × 85 a 139 × 89 | — | `limitrofe` |
| A partir de 140 × 90 | — | `elevada` |
| A partir de 180 × 110 | — | `crise_hipertensiva` |

Medidas informadas em escala reduzida, de uso corrente na fala do paciente ("14 por 9"), são convertidas para mmHg pela multiplicação por dez quando o valor é inferior a 30.

## 4. Desenho do prompt

O prompt segue uma estrutura de quatro blocos, cada um com função específica na redução da variabilidade da resposta.

### 4.1 Papel e escopo

Define o que o modelo é — um componente de extração — e, sobretudo, o que ele **não** deve fazer: não formula diagnósticos ou hipóteses diagnósticas, não prescreve medicamentos, não interpreta exames e não infere informação ausente do relato. O bloco declara explicitamente que `nivel_urgencia` expressa prioridade de atendimento, nunca avaliação clínica.

A proibição é declarada antes das instruções de tarefa, e não ao final. Modelos de linguagem tendem a aderir com mais consistência a restrições estabelecidas no início do contexto.

### 4.2 Regras de extração

Sete regras numeradas cobrem: extração restrita ao explícito; preenchimento com `null` em vez de suposição; conversão da escala de pressão; faixas de classificação; critérios de definição da urgência; obrigatoriedade de reforço à avaliação profissional na recomendação; e semântica do campo de confiança.

A segunda regra é a mais importante do conjunto — é ela que ataca diretamente o risco de alucinação, ao transformar a ausência de informação em um valor válido e esperado, e não em uma lacuna que o modelo se sinta compelido a preencher.

### 4.3 Schema

O JSON Schema completo é apresentado no prompt. O modelo recebe o contrato antes de produzir a resposta, e não apenas uma descrição informal do formato desejado.

### 4.4 Exemplos few-shot

Dois exemplos completos demonstram o comportamento esperado. A escolha foi deliberada: o primeiro cobre um relato completo, com todos os campos preenchidos; o segundo cobre um relato **parcial**, sem medida de pressão e sem intensidade explícita, mostrando o uso correto de `null`.

Instruções descrevem o comportamento desejado; exemplos o demonstram. Para casos limítrofes — campos ausentes, informação vaga —, demonstrar é substancialmente mais eficaz do que descrever. Por isso os exemplos cobrem justamente essas situações, e não apenas o caso ideal.

## 5. Validação

A validação é aplicada igualmente aos dois motores. Saída de modelo generativo não é confiável por construção: precisa ser verificada antes de entrar no fluxo do sistema.

O validador primário usa a biblioteca `jsonschema` (Draft 7). Quando ela não está disponível, um validador interno de contingência verifica os campos obrigatórios, os domínios dos campos categóricos, os tipos das estruturas compostas e os limites numéricos. Qualquer erro interrompe o processamento com exceção `ErroValidacaoSchema` — nenhuma saída inválida chega aos módulos consumidores.

O parsing também é defensivo. A função `extrair_json_da_resposta` isola o objeto JSON mesmo quando o modelo o envolve em cercas de código, precede-o de texto explicativo ou insere vírgulas finais inválidas. Esses desvios são frequentes o bastante para serem tratados como comportamento esperado, e não como exceção.

## 6. Camada de segurança clínica

Aplicada após a extração, esta camada identifica achados que exigem avaliação imediata:

- dor torácica de forte intensidade;
- dor torácica em repouso ou desencadeada por esforço;
- dor com irradiação para braço ou mandíbula;
- dor torácica associada a sudorese fria;
- dispneia em repouso;
- episódio de síncope ou pré-síncope;
- pressão arterial em faixa de crise hipertensiva.

A presença de qualquer item crítico eleva `nivel_urgencia` a `emergencia`, independentemente do que o restante da extração indique.

A camada é conservadora por decisão de projeto, não por imprecisão. Os erros possíveis são assimétricos: um falso positivo gera uma ida desnecessária ao pronto-socorro; um falso negativo pode custar uma vida. Diante dessa assimetria, a regra é sinalizar na dúvida e assumir o custo do excesso de cautela.

## 7. Resultados

O notebook processa três relatos, escolhidos para exercitar situações distintas.

| Relato | Situação | O que testa |
|--------|----------|-------------|
| 01 | Dor torácica ao esforço, há 2 dias, PA 14 × 9 | Extração de múltiplos campos e conversão de escala |
| 02 | Dor intensa irradiada, sudorese, dispneia em repouso | Acionamento da regra de emergência |
| 03 | Cansaço e tontura postural, sem medidas | Preenchimento com `null` sem invenção de dados |

**Resultados obtidos:**

| Relato | Sintomas | Duração | PA | Urgência | Alarmes |
|--------|----------|---------|-----|----------|---------|
| 01 | `dor_toracica` (esforço) | 2 dias | 140 × 90 — `elevada` | `alta` | 1 |
| 02 | `dor_toracica`, `sudorese`, `dispneia` | 30 minutos | `null` | `emergencia` | 4 |
| 03 | `tontura` (postural), `fadiga` | não informada | `null` | `moderada` | 0 |

A bateria de verificação automatizada aplica sete asserções por relato — aderência ao schema, sintomas identificados, pressão extraída e classificada, duração, nível mínimo de urgência, presença ou ausência de sinais de alarme e reforço à avaliação profissional na recomendação. **As 21 verificações são aprovadas.**

O relato 03 é o mais revelador: o extrator registra `pressao_arterial: null` e `duracao.valor: null` em vez de estimar valores. É o comportamento desejado — a ausência de informação é preservada como ausência, não convertida em suposição.

## 8. Integração com o assistente conversacional

O módulo se acopla ao backend em dois pontos.

**Enriquecimento do turno.** Quando a mensagem do usuário ultrapassa um limiar de extensão — indicando relato denso, em vez de resposta curta —, o backend a submete ao extrator antes de responder, e o JSON resultante alimenta as variáveis de contexto do diálogo:

```python
if len(mensagem) > 120:
    extracao = extrair_informacoes_clinicas(mensagem)
    contexto["sintoma_principal"] = extracao["sintomas"][0]["categoria"]
    contexto["nivel_urgencia"]    = extracao["nivel_urgencia"]
    if extracao["nivel_urgencia"] == "emergencia":
        contexto["encaminhamento"] = "emergencia"
```

**Sumarização para o profissional.** No encaminhamento a atendimento humano, o JSON acompanha o protocolo, entregando um resumo estruturado do relato em vez da transcrição integral da conversa.

### 8.1 Complementaridade entre as abordagens

| Dimensão | Watson Assistant (Parte 1) | IA Generativa (este módulo) |
|----------|---------------------------|-----------------------------|
| Entrada esperada | Mensagens curtas e diretas | Relatos livres e extensos |
| Previsibilidade | Alta — fluxo determinístico | Média — saída exige validação |
| Cobertura | Limitada às intenções treinadas | Ampla, generaliza para o não previsto |
| Custo por chamada | Baixo | Mais elevado |
| Auditabilidade | Alta — nó acionado é rastreável | Menor — requer validação de schema |

A arquitetura preserva o Watson Assistant como camada de controle do fluxo, e aciona a IA Generativa apenas onde o ganho é real: na interpretação de texto livre que não caberia em um conjunto fechado de intenções. Não se trata de substituição de uma tecnologia pela outra, mas de alocação de cada uma onde suas propriedades são vantajosas.

## 9. Limitações

**Dependência da qualidade do prompt.** A saída é altamente sensível à redação das instruções. Alterações aparentemente inócuas — ordem das regras, presença ou ausência de um exemplo — modificam o comportamento. Por isso o prompt é versionado junto ao código, e qualquer mudança exige reexecução da bateria de verificação.

**Risco de alucinação.** Modelos generativos podem produzir informação plausível mas inexistente no relato. As mitigações adotadas são cumulativas: `temperature = 0`, reduzindo a variabilidade; instrução explícita proibindo inferência; `enum` restringindo campos categóricos; e validação obrigatória de toda saída. Nenhuma elimina o risco isoladamente — a robustez vem da combinação.

**Vieses linguísticos.** O desempenho varia com o registro e o vocabulário do paciente. Relatos com gírias regionais, baixa escolaridade ou erros de digitação tendem a produzir extrações menos completas. A implicação é de equidade: o sistema pode funcionar pior justamente para as populações com menor acesso a atendimento — risco que exige monitoramento ativo, não apenas registro em documentação.

**Ausência de dado clínico objetivo.** O módulo trabalha exclusivamente com o relatado. Não há exame físico, eletrocardiograma ou exame laboratorial. O campo `confianca_extracao` existe para tornar essa limitação explícita a quem consome a informação.

**Escopo restrito.** Sintomas fora do domínio cardiológico são classificados como `outro` ou ignorados. O módulo não substitui triagem clínica geral.

## 10. Considerações éticas

**Não é diagnóstico.** O campo `nivel_urgencia` sugere prioridade de atendimento, não avaliação clínica. Nenhum campo do schema comporta hipótese diagnóstica. A distinção não é formalidade: sistemas que organizam informação e sistemas que decidem sobre saúde estão sujeitos a regimes regulatórios e de responsabilidade distintos.

**Privacidade e proteção de dados.** Relatos de saúde são dados pessoais sensíveis sob a LGPD (Lei 13.709/2018, art. 5º, II), exigindo base legal específica para tratamento. Em uso real, seriam requisitos mínimos: consentimento informado e destacado, criptografia em trânsito e em repouso, política explícita de retenção e descarte, e registro de acesso auditável. O envio de dados a APIs de terceiros merece atenção adicional, por poder configurar transferência internacional, submetida aos artigos 33 a 36 da LGPD. Neste protótipo acadêmico, todos os relatos são fictícios.

**Supervisão humana obrigatória.** A saída estruturada é insumo para decisão profissional, nunca substituto dela. Todo encaminhamento classificado como `emergencia` ou `alta` deve ser revisto por profissional habilitado. A automação reduz esforço de organização — não transfere responsabilidade clínica.

**Transparência com o paciente.** O usuário deve saber que interage com um sistema automatizado, que ele não realiza diagnóstico e que pode solicitar atendimento humano a qualquer momento — princípio já implementado no fluxo conversacional da Parte 1.

**Responsabilidade sobre o erro.** Quando um sistema automatizado participa da priorização de atendimento, a cadeia de responsabilidade precisa estar definida antes do incidente, não depois. A rastreabilidade registrada em `metadados` — motor utilizado, versão do schema, momento do processamento — existe para tornar cada extração auditável.

## 11. Conclusão

O módulo demonstra a aplicação de IA Generativa com prompting estruturado para converter relatos clínicos livres em dados estruturados e validados.

O resultado principal é metodológico: a combinação de schema formal, prompting estruturado e validação obrigatória converte a saída de um modelo generativo — por natureza probabilística — em um artefato com garantias verificáveis. Essa conversão é condição necessária para qualquer uso em contexto de saúde, onde saída não verificada não é utilizável, por mais convincente que pareça.

---

*CardioIA — Fase 5 | Assistente Cardiológico Inteligente e Conversacional*
