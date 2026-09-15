# CardioIA — Fase 5
## Roteiro do Vídeo de Demonstração

**Duração total:** até 3 minutos
**Formato sugerido:** gravação de tela com narração em áudio
**Resolução mínima:** 1280 × 720

---

### Preparação antes de gravar

| Item | Ação |
|------|------|
| Backend | `cd backend && python app.py` — confirmar a mensagem `CardioIA iniciado` no terminal |
| Navegador | Abrir `http://localhost:5000` e verificar o indicador de status em verde |
| Estado limpo | Clicar em `↺` para iniciar a conversa do zero |
| Segunda aba | Deixar `http://localhost:5000/api/metricas` aberta, para o trecho final |
| Editor | Manter `watson-assistant/skill-cardioia-export.json` e `backend/app.py` abertos |
| Áudio | Testar o microfone e silenciar notificações do sistema |

---

## Bloco 1 — Contextualização (0:00 – 0:20)

**Tela:** interface do CardioIA aberta, mensagem de boas-vindas visível.

**Narração:**

> Este é o CardioIA, assistente cardiológico conversacional desenvolvido na Fase 5 do projeto. Ele realiza o atendimento inicial de pacientes com queixas cardiológicas, organizando as informações relatadas e encaminhando cada caso conforme a gravidade identificada. Antes de qualquer interação, o assistente declara seu escopo: ele não realiza diagnóstico e não substitui avaliação profissional.

**Ação em tela:** apontar o cursor para a faixa de aviso vermelha abaixo do cabeçalho.

---

## Bloco 2 — Demonstração do fluxo conversacional (0:20 – 1:30)

### 2.1 — Sintoma com qualificação e escalonamento (0:20 – 0:50)

**Digitar:** `Estou sentindo dor no peito`

**Narração:**

> O assistente reconhece a intenção de relato de dor torácica e a entidade correspondente. Em vez de responder genericamente, ele solicita a qualificação da intensidade — e já antecipa os sinais de alarme que exigiriam atendimento imediato.

**Ação:** destacar a etiqueta `intenção: relato_dor_peito` abaixo da resposta.

**Digitar:** `É forte e está irradindo para o braço esquerdo`

**Narração:**

> Aqui há dois elementos importantes. Primeiro, a continuidade de contexto: a resposta "é forte" só faz sentido porque o assistente mantém o nó anterior em foco. Segundo, a camada de segurança clínica: intensidade forte somada à irradiação para o braço configura sinal de alarme, e o atendimento é imediatamente escalonado para emergência.

**Ação:** destacar o balão vermelho e a etiqueta `encaminhamento de urgência`.

### 2.2 — Pressão arterial e extração de valores (0:50 – 1:10)

**Ação:** clicar em `↺` para reiniciar.

**Digitar:** `Minha pressão está 14 por 9`

**Narração:**

> O assistente extrai a medida por meio de uma entidade de padrão, converte a escala reduzida para milímetros de mercúrio — cento e quarenta por noventa — e classifica o valor na faixa de referência correspondente, devolvendo orientações de nova aferição e acompanhamento.

### 2.3 — Digressão e tratamento de exceção (1:10 – 1:30)

**Digitar:** `Quero agendar uma consulta`

**Narração:**

> O usuário muda de assunto e o assistente acompanha a mudança, sem se prender ao fluxo anterior.

**Digitar:** `Qual a previsão do tempo hoje`

**Narração:**

> Para mensagens fora do domínio, o fluxo de exceção esclarece o escopo, sugere formulações válidas e oferece o caminho para atendimento humano — disponível em qualquer ponto da conversa.

---

## Bloco 3 — Arquitetura da solução (1:30 – 2:20)

### 3.1 — Modelo conversacional (1:30 – 1:55)

**Tela:** editor com `skill-cardioia-export.json` aberto.

**Narração:**

> Todo o comportamento demonstrado vem deste arquivo: o skill exportado no padrão do IBM Watson Assistant, com quatorze intenções, sete entidades e trinta e dois nós de diálogo. As intenções cobrem sintomas, pressão arterial, medicação e agendamento. Entre as entidades, destaca-se a de padrão, que captura medidas de pressão em qualquer notação. Os nós de diálogo formam uma árvore de dois níveis, com o nó de emergência avaliado antes de qualquer nó de sintoma.

**Ação:** rolar mostrando as seções `intents`, `entities` e `dialog_nodes`.

### 3.2 — Backend e integração (1:55 – 2:20)

**Tela:** editor com `app.py` e `watson_client.py`.

**Narração:**

> O backend em Flask expõe o endpoint de chat, que recebe a mensagem, aciona o serviço de diálogo, mantém o contexto da sessão e persiste cada turno em SQLite. A integração ocorre com a API versão dois do Watson Assistant. O mesmo arquivo de skill alimenta um runtime local, o que permite executar e validar o projeto sem credenciais ativas — os dois caminhos devolvem exatamente a mesma estrutura de resposta à aplicação.

**Ação:** alternar para a aba `/api/metricas`.

**Narração (sobre as métricas):**

> Cada interação registrada alimenta as métricas do sistema: distribuição de intenções, encaminhamentos de urgência e taxa de fallback — indicador que aponta diretamente as lacunas de cobertura do modelo.

---

## Bloco 4 — Encerramento e considerações éticas (2:20 – 3:00)

**Tela:** terminal executando `python testes_fluxo.py`.

**Narração:**

> A validação do modelo conversacional é automatizada: cinquenta casos cobrem acurácia de classificação, roteamento de nós, continuidade de contexto, digressão, classificação de pressão arterial e regras de segurança clínica. Todos são aprovados nesta versão.

**Ação:** mostrar a linha `RESULTADO: 50/50 casos aprovados`.

**Tela:** retornar à interface do chat.

**Narração final:**

> Por fim, os limites do sistema. O CardioIA organiza informações relatadas; ele não diagnostica, não prescreve e não interpreta exames. As faixas de referência utilizadas são gerais, não individualizadas. A camada de detecção de sinais de alarme é deliberadamente conservadora, porque o custo de um alerta desnecessário é incomparavelmente menor que o de um sinal não identificado. E o encaminhamento para profissional humano permanece disponível em todos os pontos do diálogo. Esta é a Fase 5 do projeto CardioIA.

---

## Checklist de gravação

- [ ] Aviso de escopo visível no início do vídeo
- [ ] Pelo menos três intenções diferentes demonstradas
- [ ] Escalonamento para emergência demonstrado
- [ ] Tratamento de exceção demonstrado
- [ ] Arquivo de skill exibido
- [ ] Integração backend ↔ assistente explicada
- [ ] Suíte de testes executada em tela
- [ ] Considerações éticas mencionadas no encerramento
- [ ] Duração final dentro de 3 minutos
- [ ] Áudio audível e sem ruído de fundo

---

*CardioIA — Fase 5 | Assistente Cardiológico Inteligente e Conversacional*
