"""
mock_dialog_engine.py
=====================

Motor de dialogo local do CardioIA.

Este modulo interpreta o MESMO arquivo de exportacao do skill utilizado pelo IBM
Watson Assistant (`watson-assistant/skill-cardioia-export.json`) e reproduz
localmente o comportamento essencial do runtime de dialogo:

    1. Classificacao de intencao (intent) por similaridade lexical com os
       exemplos de treinamento declarados no skill.
    2. Reconhecimento de entidades (entities) dos tipos `synonyms` e `patterns`.
    3. Avaliacao da arvore de `dialog_nodes`, respeitando a ordem definida pelos
       campos `parent` e `previous_sibling`.
    4. Manutencao de variaveis de contexto (`$variavel`) entre turnos da conversa.
    5. Tratamento de excecao por meio dos nos `anything_else`.

O objetivo do modo local e garantir que o protótipo permaneca demonstravel e
testavel sem depender de credenciais externas, mantendo total fidelidade ao
modelo conversacional projetado. Em producao, o mesmo JSON e importado no Watson
Assistant e o runtime oficial assume a execucao (ver `watson_client.py`).

Autor: equipe CardioIA - Fase 5
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constantes de configuracao do classificador
# ---------------------------------------------------------------------------

#: Confianca minima para que uma intencao seja considerada reconhecida.
LIMIAR_CONFIANCA_INTENT = 0.34

#: Peso atribuido a correspondencia exata de um exemplo de treinamento.
BONUS_CORRESPONDENCIA_EXATA = 0.45

#: Palavras sem valor discriminativo para a classificacao (stopwords pt-BR).
STOPWORDS = {
    "a", "as", "ao", "aos", "aquele", "aquela", "ate", "com", "como", "da",
    "das", "de", "do", "dos", "e", "em", "essa", "esse", "esta", "este", "eu",
    "foi", "ha", "isso", "ja", "la", "lhe", "mais", "mas", "me", "meu", "minha",
    "muito", "na", "nas", "no", "nos", "o", "os", "ou", "para", "pela", "pelo",
    "por", "que", "se", "sera", "seu", "so", "sua", "tambem", "te", "tem",
    "um", "uma", "voce", "vou",
}

#: Entidades de alarme que disparam encaminhamento imediato para emergencia.
SINAIS_DE_ALARME = {"desmaio", "suor_frio", "irradiacao_braco"}


# ---------------------------------------------------------------------------
# Funcoes utilitarias de normalizacao textual
# ---------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Converte para minusculas, remove acentuacao e pontuacao redundante.

    A normalizacao e aplicada tanto aos exemplos de treinamento quanto a entrada
    do usuario, tornando a comparacao insensivel a acentos e a maiusculas.
    """
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s/x]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def tokenizar(texto: str) -> List[str]:
    """Divide o texto normalizado em tokens relevantes.

    Alem da remocao de stopwords, valores numericos sao substituidos pelo token
    generico `<num>`. Sem essa normalizacao, medidas distintas ("12 por 8" e
    "14 por 9") seriam tratadas como termos diferentes, enfraquecendo a
    correspondencia com os exemplos de treinamento da intencao.
    """
    tokens = normalizar(texto).split()
    normalizados: List[str] = []
    for token in tokens:
        if token.isdigit():
            normalizados.append("<num>")
        elif token not in STOPWORDS and len(token) > 1:
            normalizados.append(token)
    return normalizados


# ---------------------------------------------------------------------------
# Classificador de intencoes
# ---------------------------------------------------------------------------

class ClassificadorIntent:
    """Classificador lexical baseado nos exemplos declarados no skill.

    A pontuacao combina tres sinais:
      * indice de Jaccard entre os tokens da mensagem e os do exemplo;
      * cobertura dos tokens do exemplo presentes na mensagem;
      * bonus para correspondencia textual exata ou por substring.

    Nao se trata de um modelo estatistico treinado: a finalidade e reproduzir de
    forma transparente e auditavel o comportamento esperado do skill em ambiente
    local, mantendo o mesmo conjunto de intencoes e exemplos.
    """

    def __init__(self, intents: List[Dict[str, Any]], counterexamples: List[Dict[str, Any]]):
        self._intents: Dict[str, List[List[str]]] = {}
        self._exemplos_literais: Dict[str, List[str]] = {}
        for intent in intents:
            nome = intent["intent"]
            exemplos = [e["text"] for e in intent.get("examples", [])]
            self._intents[nome] = [tokenizar(e) for e in exemplos]
            self._exemplos_literais[nome] = [normalizar(e) for e in exemplos]
        self._counterexamples = [normalizar(c["text"]) for c in counterexamples]

    def classificar(self, mensagem: str, top_n: int = 3) -> List[Dict[str, Any]]:
        """Retorna as `top_n` intencoes mais provaveis, ordenadas por confianca."""
        mensagem_norm = normalizar(mensagem)
        tokens_msg = set(tokenizar(mensagem))

        # Contraexemplos: mensagens claramente fora do dominio nao geram intent.
        for contra in self._counterexamples:
            if contra and (contra == mensagem_norm or self._similaridade_textual(contra, mensagem_norm) > 0.85):
                return []

        if not tokens_msg:
            return []

        resultados: List[Tuple[str, float]] = []
        for nome, listas_tokens in self._intents.items():
            melhor = 0.0
            for i, tokens_ex in enumerate(listas_tokens):
                if not tokens_ex:
                    continue
                conjunto_ex = set(tokens_ex)
                intersecao = tokens_msg & conjunto_ex
                if not intersecao:
                    continue
                jaccard = len(intersecao) / len(tokens_msg | conjunto_ex)
                cobertura = len(intersecao) / len(conjunto_ex)
                score = (0.45 * jaccard) + (0.55 * cobertura)

                exemplo_literal = self._exemplos_literais[nome][i]
                if exemplo_literal == mensagem_norm:
                    score += BONUS_CORRESPONDENCIA_EXATA
                elif exemplo_literal and exemplo_literal in mensagem_norm:
                    score += 0.20

                melhor = max(melhor, score)

            if melhor > 0:
                resultados.append((nome, min(round(melhor, 4), 1.0)))

        resultados.sort(key=lambda item: item[1], reverse=True)
        acima_do_limiar = [
            {"intent": nome, "confidence": score}
            for nome, score in resultados
            if score >= LIMIAR_CONFIANCA_INTENT
        ]
        return acima_do_limiar[:top_n]

    @staticmethod
    def _similaridade_textual(a: str, b: str) -> float:
        """Jaccard simples entre dois textos ja normalizados."""
        ta, tb = set(a.split()), set(b.split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Reconhecedor de entidades
# ---------------------------------------------------------------------------

class ReconhecedorEntidades:
    """Extrai entidades do tipo `synonyms` e `patterns` declaradas no skill."""

    def __init__(self, entities: List[Dict[str, Any]]):
        self._sinonimos: List[Tuple[str, str, str]] = []   # (entidade, valor, sinonimo_normalizado)
        self._padroes: List[Tuple[str, str, re.Pattern]] = []  # (entidade, valor, regex)

        for entidade in entities:
            nome_entidade = entidade["entity"]
            for valor in entidade.get("values", []):
                nome_valor = valor["value"]
                if valor.get("type") == "patterns":
                    for padrao in valor.get("patterns", []):
                        self._padroes.append(
                            (nome_entidade, nome_valor, re.compile(padrao, re.IGNORECASE))
                        )
                else:
                    termos = [nome_valor.replace("_", " ")] + valor.get("synonyms", [])
                    for termo in termos:
                        self._sinonimos.append((nome_entidade, nome_valor, normalizar(termo)))

        # Sinonimos mais longos primeiro evita que "dor" capture antes de "dor no peito".
        self._sinonimos.sort(key=lambda item: len(item[2]), reverse=True)

    def reconhecer(self, mensagem: str) -> List[Dict[str, Any]]:
        """Retorna a lista de entidades encontradas na mensagem do usuario."""
        mensagem_norm = normalizar(mensagem)
        encontradas: List[Dict[str, Any]] = []
        intervalos_ocupados: List[Tuple[int, int]] = []

        for nome_entidade, nome_valor, sinonimo in self._sinonimos:
            if not sinonimo:
                continue
            for match in re.finditer(r"(?<!\w)" + re.escape(sinonimo) + r"(?!\w)", mensagem_norm):
                intervalo = (match.start(), match.end())
                if self._sobrepoe(intervalo, intervalos_ocupados):
                    continue
                intervalos_ocupados.append(intervalo)
                encontradas.append({
                    "entity": nome_entidade,
                    "value": nome_valor,
                    "literal": match.group(0),
                    "location": list(intervalo),
                    "confidence": 1.0,
                })

        for nome_entidade, nome_valor, regex in self._padroes:
            for match in regex.finditer(mensagem_norm):
                encontradas.append({
                    "entity": nome_entidade,
                    "value": nome_valor,
                    "literal": match.group(0),
                    "location": [match.start(), match.end()],
                    "groups": list(match.groups()),
                    "confidence": 1.0,
                })

        return encontradas

    @staticmethod
    def _sobrepoe(intervalo: Tuple[int, int], ocupados: List[Tuple[int, int]]) -> bool:
        inicio, fim = intervalo
        return any(not (fim <= o_ini or inicio >= o_fim) for o_ini, o_fim in ocupados)


# ---------------------------------------------------------------------------
# Avaliador de condicoes dos dialog nodes
# ---------------------------------------------------------------------------

class AvaliadorCondicoes:
    """Avalia as expressoes declaradas no campo `conditions` dos dialog nodes.

    Subconjunto suportado (suficiente para o skill do CardioIA):
      * `welcome`, `conversation_start`, `anything_else`, `true`, `false`
      * `#intent`
      * `@entidade` e `@entidade:valor`
      * `$variavel`, `$variavel == "valor"`, `$variavel >= 140` (e demais
        operadores relacionais)
      * combinacoes com `&&` e `||` (E tem precedencia sobre OU)
    """

    OPERADORES = ["==", "!=", ">=", "<=", ">", "<"]

    def avaliar(
        self,
        condicao: Optional[str],
        intents: List[Dict[str, Any]],
        entidades: List[Dict[str, Any]],
        contexto: Dict[str, Any],
        turno_de_boas_vindas: bool,
        modo_anything_else: bool = False,
    ) -> bool:
        if condicao is None:
            return False

        condicao = condicao.strip()
        if not condicao:
            return False

        # Expressao OU no nivel mais externo.
        if "||" in condicao:
            return any(
                self.avaliar(parte, intents, entidades, contexto, turno_de_boas_vindas, modo_anything_else)
                for parte in condicao.split("||")
            )
        if "&&" in condicao:
            return all(
                self.avaliar(parte, intents, entidades, contexto, turno_de_boas_vindas, modo_anything_else)
                for parte in condicao.split("&&")
            )

        atomo = condicao.strip()

        if atomo in ("true", "irrelevant"):
            return True
        if atomo == "false":
            return False
        if atomo in ("welcome", "conversation_start"):
            # Assim como no runtime oficial, o no de boas-vindas so e acionado na
            # abertura da sessao (entrada vazia), nunca em uma mensagem do usuario.
            return turno_de_boas_vindas
        if atomo == "anything_else":
            return modo_anything_else

        if atomo.startswith("#"):
            # O roteamento considera apenas a intencao principal (maior confianca),
            # replicando o comportamento do runtime do Watson Assistant. As demais
            # intencoes retornadas ficam disponiveis apenas para analise e metricas.
            nome = atomo[1:].strip()
            return bool(intents) and intents[0]["intent"] == nome

        if atomo.startswith("@"):
            corpo = atomo[1:].strip()
            if ":" in corpo:
                nome_entidade, valor = [p.strip() for p in corpo.split(":", 1)]
                valor = valor.strip("'\"")
                return any(
                    e["entity"] == nome_entidade and e["value"] == valor for e in entidades
                )
            return any(e["entity"] == corpo for e in entidades)

        if atomo.startswith("$"):
            return self._avaliar_variavel(atomo, contexto)

        return False

    def _avaliar_variavel(self, atomo: str, contexto: Dict[str, Any]) -> bool:
        for operador in self.OPERADORES:
            if operador in atomo:
                esquerda, direita = atomo.split(operador, 1)
                nome = esquerda.strip().lstrip("$").strip()
                esperado = direita.strip().strip("'\"")
                atual = contexto.get(nome)
                return self._comparar(atual, operador, esperado)
        nome = atomo.lstrip("$").strip()
        valor = contexto.get(nome)
        return valor is not None and valor is not False and valor != ""

    @staticmethod
    def _comparar(atual: Any, operador: str, esperado: str) -> bool:
        if atual is None:
            return operador == "!="

        # Comparacao numerica quando ambos os lados forem conversiveis.
        try:
            atual_num = float(atual)
            esperado_num = float(esperado)
            comparacoes = {
                "==": atual_num == esperado_num,
                "!=": atual_num != esperado_num,
                ">=": atual_num >= esperado_num,
                "<=": atual_num <= esperado_num,
                ">": atual_num > esperado_num,
                "<": atual_num < esperado_num,
            }
            return comparacoes[operador]
        except (TypeError, ValueError):
            pass

        atual_str = str(atual).strip().lower()
        esperado_str = str(esperado).strip().lower()
        if operador == "==":
            return atual_str == esperado_str
        if operador == "!=":
            return atual_str != esperado_str
        return False


# ---------------------------------------------------------------------------
# Motor de dialogo
# ---------------------------------------------------------------------------

class MockDialogEngine:
    """Runtime local que executa o skill do CardioIA a partir do JSON exportado."""

    def __init__(self, caminho_skill: Optional[str] = None):
        caminho = Path(caminho_skill) if caminho_skill else self._caminho_padrao()
        if not caminho.exists():
            raise FileNotFoundError(
                f"Arquivo de skill nao encontrado em '{caminho}'. "
                "Verifique a variavel de ambiente SKILL_FILE."
            )

        with open(caminho, "r", encoding="utf-8") as arquivo:
            self.skill: Dict[str, Any] = json.load(arquivo)

        self.caminho_skill = str(caminho)
        self.classificador = ClassificadorIntent(
            self.skill.get("intents", []),
            self.skill.get("counterexamples", []),
        )
        self.reconhecedor = ReconhecedorEntidades(self.skill.get("entities", []))
        self.avaliador = AvaliadorCondicoes()

        self._nos_por_id: Dict[str, Dict[str, Any]] = {
            no["dialog_node"]: no for no in self.skill.get("dialog_nodes", [])
        }
        self._raizes = self._ordenar_irmaos(parent=None)

    # -- Infraestrutura da arvore de nos -----------------------------------

    @staticmethod
    def _caminho_padrao() -> Path:
        """Resolve o caminho padrao do skill relativo a raiz do repositorio."""
        return (
            Path(__file__).resolve().parent.parent
            / "watson-assistant"
            / "skill-cardioia-export.json"
        )

    def _ordenar_irmaos(self, parent: Optional[str]) -> List[Dict[str, Any]]:
        """Ordena os nos de um mesmo nivel seguindo a cadeia `previous_sibling`."""
        irmaos = [
            no for no in self.skill.get("dialog_nodes", [])
            if no.get("parent") == parent
        ]
        if not irmaos:
            return []

        por_anterior = {no.get("previous_sibling"): no for no in irmaos}
        ordenados: List[Dict[str, Any]] = []
        atual = por_anterior.get(None)
        visitados = set()

        while atual is not None and atual["dialog_node"] not in visitados:
            ordenados.append(atual)
            visitados.add(atual["dialog_node"])
            atual = por_anterior.get(atual["dialog_node"])

        # Garante que nenhum no seja perdido caso a cadeia esteja incompleta.
        for no in irmaos:
            if no["dialog_node"] not in visitados:
                ordenados.append(no)

        return ordenados

    # -- Execucao de um turno ---------------------------------------------

    def iniciar_conversa(self, contexto: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Abre a sessao acionando o no de boas-vindas.

        Equivale ao envio de uma entrada vazia ao runtime do Watson Assistant,
        procedimento padrao para obter a mensagem inicial do assistente.
        """
        return self.processar("", contexto, turno_de_boas_vindas=True)

    def processar(
        self,
        mensagem: str,
        contexto: Optional[Dict[str, Any]] = None,
        turno_de_boas_vindas: bool = False,
    ) -> Dict[str, Any]:
        """Executa um turno da conversa.

        Args:
            mensagem: texto enviado pelo usuario (vazio na abertura da sessao).
            contexto: variaveis de contexto acumuladas nos turnos anteriores.
            turno_de_boas_vindas: quando verdadeiro, aciona o no `welcome`.

        Returns:
            Dicionario no formato normalizado da aplicacao, contendo texto de
            resposta, intencao detectada, entidades, contexto atualizado, no
            acionado e sinalizador de emergencia.
        """
        contexto = dict(contexto or {})

        intents = self.classificador.classificar(mensagem)
        entidades = self.reconhecedor.reconhecer(mensagem)

        contexto = self._atualizar_contexto_automatico(contexto, entidades)

        no_selecionado, contexto = self._selecionar_no(
            intents, entidades, contexto, turno_de_boas_vindas
        )

        textos: List[str] = []
        no_atual = no_selecionado
        profundidade = 0

        # Suporte a `skip_user_input`: encadeia o no filho correspondente sem
        # exigir nova mensagem do usuario (usado na classificacao de pressao).
        while no_atual is not None and profundidade < 5:
            contexto = self._aplicar_contexto_do_no(no_atual, contexto)
            textos.append(self._extrair_texto(no_atual, contexto))

            comportamento = (no_atual.get("next_step") or {}).get("behavior")
            if comportamento == "skip_user_input":
                no_atual = self._avaliar_filhos(
                    no_atual["dialog_node"], intents, entidades, contexto,
                    turno_de_boas_vindas, permitir_anything_else=True,
                )
                profundidade += 1
            else:
                no_atual = None

        contexto["_conversa_iniciada"] = True
        contexto["_no_anterior"] = no_selecionado["dialog_node"] if no_selecionado else None

        # Um no so permanece "em foco" se possuir filhos aguardando resposta.
        contexto["_no_em_foco"] = (
            no_selecionado["dialog_node"]
            if no_selecionado
            and self._ordenar_irmaos(no_selecionado["dialog_node"])
            and (no_selecionado.get("next_step") or {}).get("behavior") != "skip_user_input"
            else None
        )

        emergencia = contexto.get("encaminhamento") == "emergencia" or any(
            e["entity"] == "sintoma" and e["value"] in SINAIS_DE_ALARME for e in entidades
        )

        return {
            "resposta": "\n\n".join(t for t in textos if t).strip(),
            "intent": intents[0]["intent"] if intents else None,
            "confianca": intents[0]["confidence"] if intents else 0.0,
            "intents": intents,
            "entidades": [
                {"entity": e["entity"], "value": e["value"], "literal": e["literal"]}
                for e in entidades
            ],
            "contexto": contexto,
            "no_acionado": no_selecionado["dialog_node"] if no_selecionado else None,
            "emergencia": bool(emergencia),
            "origem": "mock",
        }

    # -- Selecao de nos ----------------------------------------------------

    def _selecionar_no(
        self,
        intents: List[Dict[str, Any]],
        entidades: List[Dict[str, Any]],
        contexto: Dict[str, Any],
        turno_de_boas_vindas: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Seleciona o no a ser acionado em tres estagios de prioridade.

        A ordem reproduz o comportamento de continuidade e digressao do runtime
        oficial:

            1. Resposta esperada ao no em foco (filho com condicao especifica).
            2. Digressao: o usuario mudou de assunto e um no de topo e satisfeito.
            3. Excecao: `anything_else` local do no em foco ou global do skill.
        """
        no_em_foco = contexto.get("_no_em_foco")

        # Estagio 1 - continuidade do fluxo em andamento.
        if no_em_foco and no_em_foco in self._nos_por_id:
            filho = self._avaliar_filhos(
                no_em_foco, intents, entidades, contexto,
                turno_de_boas_vindas, permitir_anything_else=False,
            )
            if filho is not None:
                return filho, contexto

        # Estagio 2 - digressao para outro topico do dominio.
        for no in self._raizes:
            if self.avaliador.avaliar(
                no.get("conditions"), intents, entidades, contexto, turno_de_boas_vindas
            ):
                return no, contexto

        # Estagio 3a - excecao local do no em foco.
        if no_em_foco and no_em_foco in self._nos_por_id:
            filho = self._avaliar_filhos(
                no_em_foco, intents, entidades, contexto,
                turno_de_boas_vindas, permitir_anything_else=True,
            )
            if filho is not None:
                return filho, contexto

        # Estagio 3b - excecao global do skill.
        for no in self._raizes:
            if self.avaliador.avaliar(
                no.get("conditions"), intents, entidades, contexto,
                turno_de_boas_vindas, modo_anything_else=True
            ):
                return no, contexto

        return None, contexto

    def _avaliar_filhos(
        self,
        id_pai: str,
        intents: List[Dict[str, Any]],
        entidades: List[Dict[str, Any]],
        contexto: Dict[str, Any],
        turno_de_boas_vindas: bool,
        permitir_anything_else: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Avalia os filhos de um no e retorna o primeiro cuja condicao e satisfeita.

        Quando `permitir_anything_else` e falso, apenas condicoes especificas sao
        consideradas, o que permite distinguir continuidade de digressao.
        """
        filhos = self._ordenar_irmaos(id_pai)
        if not filhos:
            return None

        for filho in filhos:
            condicao = (filho.get("conditions") or "").strip()
            eh_excecao = condicao in ("anything_else", "true")

            if eh_excecao and not permitir_anything_else:
                continue

            if self.avaliador.avaliar(
                filho.get("conditions"), intents, entidades, contexto,
                turno_de_boas_vindas, modo_anything_else=permitir_anything_else,
            ):
                return filho

        return None

    # -- Contexto ----------------------------------------------------------

    @staticmethod
    def _atualizar_contexto_automatico(
        contexto: Dict[str, Any], entidades: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Deriva variaveis de contexto a partir das entidades reconhecidas.

        Os valores sistolico e diastolico extraidos pela entidade de padrao
        `@pressao_arterial` sao gravados em `$pa_sistolica` e `$pa_diastolica`,
        variaveis usadas nas condicoes dos nos filhos de classificacao da PA.
        Valores informados em escala reduzida (ex.: "14 por 9") sao convertidos
        para mmHg, conforme praxe clinica de registro.
        """
        for entidade in entidades:
            if entidade["entity"] != "pressao_arterial":
                continue
            grupos = entidade.get("groups") or []
            if len(grupos) < 2:
                continue
            try:
                sistolica = int(grupos[0])
                diastolica = int(grupos[1])
            except (TypeError, ValueError):
                continue

            if sistolica < 30:
                sistolica *= 10
            if diastolica < 30:
                diastolica *= 10

            contexto["pa_sistolica"] = sistolica
            contexto["pa_diastolica"] = diastolica

        for entidade in entidades:
            if entidade["entity"] == "sintoma" and not contexto.get("sintoma_principal"):
                contexto["sintoma_principal"] = entidade["value"]
                break

        return contexto

    @staticmethod
    def _aplicar_contexto_do_no(no: Dict[str, Any], contexto: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica o bloco `context` declarado no no, preservando expressoes SpEL.

        Valores que contenham expressoes do Watson (`<?...?>`) sao ignorados no
        modo local, pois as variaveis correspondentes ja foram preenchidas pelo
        reconhecedor de entidades.
        """
        for chave, valor in (no.get("context") or {}).items():
            if isinstance(valor, str) and "<?" in valor:
                continue
            if valor is None and contexto.get(chave) is not None:
                continue
            contexto[chave] = valor
        return contexto

    # -- Saida -------------------------------------------------------------

    @staticmethod
    def _extrair_texto(no: Dict[str, Any], contexto: Dict[str, Any]) -> str:
        """Extrai o texto de resposta do no, respeitando a politica de selecao."""
        blocos = (no.get("output") or {}).get("generic") or []
        partes: List[str] = []

        for bloco in blocos:
            if bloco.get("response_type") != "text":
                continue
            valores = bloco.get("values") or []
            if not valores:
                continue

            if bloco.get("selection_policy") == "sequential" and len(valores) > 1:
                chave = f"_seq_{no['dialog_node']}"
                indice = int(contexto.get(chave, 0))
                texto = valores[min(indice, len(valores) - 1)].get("text", "")
                contexto[chave] = min(indice + 1, len(valores) - 1)
            else:
                texto = valores[0].get("text", "")

            if texto:
                partes.append(texto)

        return "\n\n".join(partes)

    # -- Metadados ---------------------------------------------------------

    def resumo_skill(self) -> Dict[str, Any]:
        """Retorna um resumo do skill carregado (usado no endpoint de saude)."""
        return {
            "nome": self.skill.get("name"),
            "idioma": self.skill.get("language"),
            "total_intents": len(self.skill.get("intents", [])),
            "total_entities": len(self.skill.get("entities", [])),
            "total_dialog_nodes": len(self.skill.get("dialog_nodes", [])),
            "arquivo": self.caminho_skill,
        }
