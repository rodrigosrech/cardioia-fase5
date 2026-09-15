"""
testes_fluxo.py
===============

Suite de testes do modelo conversacional do CardioIA - Fase 5.

Os testes validam tres aspectos do assistente, sem exigir conexao com o
servico remoto:

    1. Classificacao de intencao (acuracia sobre um conjunto de validacao).
    2. Roteamento dos dialog nodes, incluindo continuidade de contexto,
       digressao entre topicos e acionamento dos nos de excecao.
    3. Regras de seguranca clinica (deteccao de sinais de alarme e
       classificacao das faixas de pressao arterial).

Execucao:

    cd backend
    python testes_fluxo.py

O processo retorna codigo de saida 0 quando todos os casos passam e 1 em caso
de falha, permitindo o uso em rotinas de integracao continua.

Autor: equipe CardioIA - Fase 5
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Tuple

from mock_dialog_engine import MockDialogEngine

# ---------------------------------------------------------------------------
# Conjuntos de validacao
# ---------------------------------------------------------------------------

#: (mensagem, intencao esperada)
CASOS_INTENT: List[Tuple[str, str]] = [
    ("oi bom dia", "saudacao"),
    ("ola preciso de ajuda", "saudacao"),
    ("estou com dor no peito", "relato_dor_peito"),
    ("sinto um aperto no peito ha dois dias", "relato_dor_peito"),
    ("estou com falta de ar", "relato_falta_ar"),
    ("fico ofegante ao caminhar", "relato_falta_ar"),
    ("meu coracao esta disparado", "relato_palpitacao"),
    ("sinto palpitacoes", "relato_palpitacao"),
    ("estou com tontura", "relato_tontura"),
    ("minha vista escurece", "relato_tontura"),
    ("qual o valor normal da pressao", "duvida_pressao_arterial"),
    ("como medir a pressao corretamente", "duvida_pressao_arterial"),
    ("minha pressao esta 14 por 9", "informar_pressao"),
    ("medi 12 por 8", "informar_pressao"),
    ("posso parar de tomar o remedio da pressao", "duvida_medicacao"),
    ("esqueci de tomar o losartana", "duvida_medicacao"),
    ("quero marcar uma consulta", "agendar_consulta"),
    ("quero falar com um atendente", "falar_com_atendente"),
    ("obrigado", "agradecimento"),
    ("tchau", "despedida"),
    ("sim", "confirmacao_sim"),
    ("nao", "negacao_nao"),
]

#: (descricao, sequencia de mensagens, dialog node esperado no ultimo turno)
CASOS_FLUXO: List[Tuple[str, List[str], str]] = [
    ("Dor toracica leve", ["estou sentindo dor no peito", "e leve"], "node_dp_leve_moderada"),
    ("Dor toracica intensa", ["dor no peito", "muito forte"], "node_dp_intensa"),
    ("Dor toracica - excecao local", ["estou com dor no peito", "nao sei dizer ao certo"], "node_dp_anything_else"),
    ("Digressao para agendamento", ["estou com dor no peito", "quero marcar uma consulta"], "node_agendamento"),
    ("Falta de ar ao esforco", ["estou com falta de ar", "so quando subo escada"], "node_fa_esforco"),
    ("Falta de ar em repouso", ["sinto falta de ar", "ate parado em repouso"], "node_fa_intensa"),
    ("Falta de ar - excecao local", ["estou com falta de ar", "sei la"], "node_fa_anything_else"),
    ("Palpitacao com sintoma associado", ["meu coracao esta disparado", "sim"], "node_palp_associado"),
    ("Palpitacao isolada", ["sinto palpitacoes", "nao"], "node_palp_isolado"),
    ("Tontura com sincope", ["estou com tontura", "sim"], "node_tontura_sincope"),
    ("Tontura sem sincope", ["sinto vertigem quando levanto", "nao"], "node_tontura_simples"),
    ("Sinal de alarme direto", ["dor no peito que vai para o braco esquerdo com suor frio"], "node_emergencia"),
    ("Duvida sobre pressao", ["qual o valor normal da pressao"], "node_duvida_pressao"),
    ("Duvida sobre medicacao", ["posso parar de tomar o remedio da pressao"], "node_medicacao"),
    ("Transferencia para humano", ["quero falar com um atendente"], "node_atendente"),
    ("Fallback global", ["quanto custa um carro novo"], "node_anything_else"),
    ("Encerramento", ["tchau"], "node_despedida"),
]

#: (mensagem, classificacao esperada da PA, indica emergencia)
CASOS_PRESSAO: List[Tuple[str, str, bool]] = [
    ("minha pressao esta 12 por 8", "adequada", False),
    ("medi 14 por 9 agora", "elevada", False),
    ("deu 180 por 110 no aparelho", "crise_hipertensiva", True),
    ("aferi 85 por 55", "baixa", False),
]

#: Mensagens que devem obrigatoriamente disparar encaminhamento de urgencia.
CASOS_EMERGENCIA: List[str] = [
    "dor no peito muito forte agora",
    "quase desmaiei hoje",
    "dor no peito com suor frio",
    "dor que irradia para o braco esquerdo",
    "minha pressao deu 190 por 120",
]


# ---------------------------------------------------------------------------
# Execucao dos testes
# ---------------------------------------------------------------------------

class Relatorio:
    """Acumula os resultados e imprime o resumo final."""

    def __init__(self) -> None:
        self.aprovados = 0
        self.falhas: List[str] = []

    def verificar(self, condicao: bool, descricao: str, detalhe: str = "") -> None:
        if condicao:
            self.aprovados += 1
            print(f"  [OK]    {descricao}")
        else:
            self.falhas.append(f"{descricao} | {detalhe}")
            print(f"  [FALHA] {descricao} | {detalhe}")

    @property
    def total(self) -> int:
        return self.aprovados + len(self.falhas)


def executar_conversa(engine: MockDialogEngine, mensagens: List[str]) -> Dict[str, Any]:
    """Executa uma conversa completa e devolve o resultado do ultimo turno."""
    contexto = engine.iniciar_conversa()["contexto"]
    resultado: Dict[str, Any] = {}
    for mensagem in mensagens:
        resultado = engine.processar(mensagem, contexto)
        contexto = resultado["contexto"]
    return resultado


def main() -> int:
    engine = MockDialogEngine()
    resumo = engine.resumo_skill()
    relatorio = Relatorio()

    print("=" * 76)
    print("CardioIA - Fase 5 | Validacao do modelo conversacional")
    print("=" * 76)
    print(f"Skill......: {resumo['nome']}")
    print(f"Idioma.....: {resumo['idioma']}")
    print(f"Estrutura..: {resumo['total_intents']} intents | "
          f"{resumo['total_entities']} entities | "
          f"{resumo['total_dialog_nodes']} dialog nodes")

    print("\n1. CLASSIFICACAO DE INTENCOES")
    print("-" * 76)
    for mensagem, esperado in CASOS_INTENT:
        obtido = engine.processar(mensagem, {"_conversa_iniciada": True})["intent"]
        relatorio.verificar(
            obtido == esperado,
            f"{mensagem[:44]:<46} -> {esperado}",
            f"obtido: {obtido}",
        )

    print("\n2. ROTEAMENTO DE DIALOG NODES")
    print("-" * 76)
    for descricao, mensagens, no_esperado in CASOS_FLUXO:
        resultado = executar_conversa(engine, mensagens)
        relatorio.verificar(
            resultado.get("no_acionado") == no_esperado,
            f"{descricao:<46} -> {no_esperado}",
            f"obtido: {resultado.get('no_acionado')}",
        )

    print("\n3. CLASSIFICACAO DA PRESSAO ARTERIAL")
    print("-" * 76)
    for mensagem, classificacao, emergencia in CASOS_PRESSAO:
        resultado = executar_conversa(engine, [mensagem])
        contexto = resultado["contexto"]
        relatorio.verificar(
            contexto.get("classificacao_pa") == classificacao
            and resultado["emergencia"] == emergencia,
            f"{mensagem[:44]:<46} -> {classificacao}",
            f"obtido: {contexto.get('classificacao_pa')} / emergencia={resultado['emergencia']}",
        )

    print("\n4. REGRAS DE SEGURANCA (SINAIS DE ALARME)")
    print("-" * 76)
    for mensagem in CASOS_EMERGENCIA:
        resultado = executar_conversa(engine, [mensagem])
        relatorio.verificar(
            resultado["emergencia"] is True,
            f"{mensagem[:44]:<46} -> encaminhamento de urgencia",
            f"obtido: emergencia={resultado['emergencia']}",
        )

    print("\n5. INTEGRIDADE DAS RESPOSTAS")
    print("-" * 76)
    nos_sem_texto = [
        no["dialog_node"]
        for no in engine.skill["dialog_nodes"]
        if not engine._extrair_texto(no, {}).strip()
    ]
    relatorio.verificar(
        not nos_sem_texto,
        "Todos os dialog nodes possuem texto de resposta",
        f"sem texto: {nos_sem_texto}",
    )

    referencias_samu = sum(
        1 for no in engine.skill["dialog_nodes"] if "192" in engine._extrair_texto(no, {})
    )
    relatorio.verificar(
        referencias_samu >= 5,
        "Orientacao de emergencia (SAMU 192) presente nos nos criticos",
        f"ocorrencias: {referencias_samu}",
    )

    print("\n" + "=" * 76)
    print(f"RESULTADO: {relatorio.aprovados}/{relatorio.total} casos aprovados")
    if relatorio.falhas:
        print(f"FALHAS ({len(relatorio.falhas)}):")
        for falha in relatorio.falhas:
            print(f"  - {falha}")
    print("=" * 76)

    return 0 if not relatorio.falhas else 1


if __name__ == "__main__":
    sys.exit(main())
