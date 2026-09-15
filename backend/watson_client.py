"""
watson_client.py
================

Camada de integracao com o servico IBM Watson Assistant (API v2).

Responsabilidades:
    * Autenticar na instancia do Watson Assistant por meio de IAM API Key.
    * Criar e reaproveitar sessoes de dialogo por usuario.
    * Enviar mensagens ao endpoint `message` e normalizar a resposta.
    * Degradar de forma controlada para o motor local (`MockDialogEngine`)
      quando as credenciais nao estiverem configuradas ou quando o servico
      remoto estiver indisponivel.

A normalizacao da resposta e essencial: tanto o runtime oficial quanto o motor
local devolvem o mesmo dicionario para a camada de aplicacao, de modo que a API
REST e a interface web permanecem identicas nos dois modos de operacao.

Autor: equipe CardioIA - Fase 5
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from mock_dialog_engine import MockDialogEngine

logger = logging.getLogger("cardioia.watson")

#: Tempo maximo de espera, em segundos, por uma resposta do servico remoto.
TIMEOUT_PADRAO = 20

#: Sinais de alarme usados para marcar o turno como emergencia, independentemente
#: da origem da resposta.
SINAIS_DE_ALARME = {"desmaio", "suor_frio", "irradiacao_braco"}


class WatsonAssistantIndisponivel(Exception):
    """Levantada quando a comunicacao com o Watson Assistant falha."""


class AssistantService:
    """Fachada unica de conversacao usada pela aplicacao Flask.

    O modo de operacao e definido pela variavel de ambiente `ASSISTANT_MODE`:

        * ``watson`` - utiliza a API do IBM Watson Assistant v2;
        * ``mock``   - utiliza exclusivamente o motor de dialogo local;
        * ``auto``   - tenta o Watson e, em caso de falha ou ausencia de
          credenciais, recorre ao motor local (valor padrao).
    """

    def __init__(
        self,
        modo: Optional[str] = None,
        api_key: Optional[str] = None,
        service_url: Optional[str] = None,
        assistant_id: Optional[str] = None,
        api_version: Optional[str] = None,
        skill_file: Optional[str] = None,
    ):
        self.modo_configurado = (modo or os.getenv("ASSISTANT_MODE", "auto")).strip().lower()
        self.api_key = api_key or os.getenv("WATSON_API_KEY", "")
        self.service_url = service_url or os.getenv("WATSON_SERVICE_URL", "")
        self.assistant_id = assistant_id or os.getenv("WATSON_ASSISTANT_ID", "")
        self.api_version = api_version or os.getenv("WATSON_API_VERSION", "2021-06-14")

        self.engine_local = MockDialogEngine(skill_file or os.getenv("SKILL_FILE"))

        self._assistant = None
        self._sessoes: Dict[str, str] = {}
        self._lock = threading.Lock()
        self.ultimo_erro: Optional[str] = None

        if self.modo_configurado in ("watson", "auto"):
            self._inicializar_watson()

    # -- Inicializacao -----------------------------------------------------

    def _credenciais_completas(self) -> bool:
        return all([self.api_key, self.service_url, self.assistant_id])

    def _inicializar_watson(self) -> None:
        """Instancia o SDK do Watson Assistant, se possivel."""
        if not self._credenciais_completas():
            self.ultimo_erro = "Credenciais do Watson Assistant nao configuradas."
            logger.warning("%s Operando com o motor de dialogo local.", self.ultimo_erro)
            return

        try:
            from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
            from ibm_watson import AssistantV2

            autenticador = IAMAuthenticator(self.api_key)
            assistant = AssistantV2(version=self.api_version, authenticator=autenticador)
            assistant.set_service_url(self.service_url)
            assistant.set_http_config({"timeout": TIMEOUT_PADRAO})
            self._assistant = assistant
            self.ultimo_erro = None
            logger.info("Conexao com o IBM Watson Assistant inicializada com sucesso.")
        except ImportError:
            self.ultimo_erro = (
                "Pacote 'ibm-watson' nao instalado. Execute: pip install -r requirements.txt"
            )
            logger.warning(self.ultimo_erro)
        except Exception as erro:  # pragma: no cover - depende de ambiente externo
            self.ultimo_erro = f"Falha ao inicializar o Watson Assistant: {erro}"
            logger.error(self.ultimo_erro)

    # -- Propriedades ------------------------------------------------------

    @property
    def modo_ativo(self) -> str:
        """Modo efetivamente em uso neste momento."""
        if self.modo_configurado == "mock":
            return "mock"
        if self._assistant is not None:
            return "watson"
        return "mock"

    # -- Sessoes -----------------------------------------------------------

    def _obter_sessao(self, session_id: str) -> Optional[str]:
        """Recupera (ou cria) a sessao remota associada ao identificador local."""
        if self._assistant is None:
            return None

        with self._lock:
            if session_id in self._sessoes:
                return self._sessoes[session_id]

        try:
            resposta = self._assistant.create_session(assistant_id=self.assistant_id).get_result()
            sessao_remota = resposta["session_id"]
            with self._lock:
                self._sessoes[session_id] = sessao_remota
            return sessao_remota
        except Exception as erro:  # pragma: no cover - depende de ambiente externo
            raise WatsonAssistantIndisponivel(f"Nao foi possivel criar a sessao: {erro}") from erro

    def encerrar_sessao(self, session_id: str) -> None:
        """Encerra a sessao remota e limpa o cache local."""
        with self._lock:
            sessao_remota = self._sessoes.pop(session_id, None)

        if sessao_remota and self._assistant is not None:
            try:
                self._assistant.delete_session(
                    assistant_id=self.assistant_id, session_id=sessao_remota
                )
            except Exception as erro:  # pragma: no cover - depende de ambiente externo
                logger.warning("Falha ao encerrar sessao remota: %s", erro)

    # -- Conversacao -------------------------------------------------------

    def enviar_mensagem(
        self,
        mensagem: str,
        session_id: str,
        contexto: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Processa um turno da conversa e devolve a resposta normalizada.

        Args:
            mensagem: texto enviado pelo usuario.
            session_id: identificador local da conversa.
            contexto: variaveis de contexto acumuladas.

        Returns:
            Dicionario com as chaves `resposta`, `intent`, `confianca`,
            `entidades`, `contexto`, `no_acionado`, `emergencia` e `origem`.
        """
        if not mensagem or not mensagem.strip():
            return {
                "resposta": (
                    "Nao recebi nenhuma mensagem. Descreva o sintoma ou a duvida "
                    "que voce gostaria de esclarecer."
                ),
                "intent": None,
                "confianca": 0.0,
                "intents": [],
                "entidades": [],
                "contexto": dict(contexto or {}),
                "no_acionado": None,
                "emergencia": False,
                "origem": "validacao",
            }

        if self.modo_ativo == "watson":
            try:
                return self._enviar_para_watson(mensagem, session_id, contexto)
            except WatsonAssistantIndisponivel as erro:
                self.ultimo_erro = str(erro)
                logger.error("Watson indisponivel (%s). Executando fallback local.", erro)
                if self.modo_configurado == "watson":
                    # Em modo estrito, o erro e propagado a camada de aplicacao.
                    raise

        return self.engine_local.processar(mensagem, contexto)

    def _enviar_para_watson(
        self,
        mensagem: str,
        session_id: str,
        contexto: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Envia a mensagem ao endpoint `message` da API v2 e normaliza o retorno."""
        sessao_remota = self._obter_sessao(session_id)
        if sessao_remota is None:
            raise WatsonAssistantIndisponivel("Sessao remota indisponivel.")

        payload_contexto = self._montar_contexto(contexto)

        try:
            resultado = self._assistant.message(
                assistant_id=self.assistant_id,
                session_id=sessao_remota,
                input={
                    "message_type": "text",
                    "text": mensagem,
                    "options": {"return_context": True, "alternate_intents": True},
                },
                context=payload_contexto,
            ).get_result()
        except Exception as erro:  # pragma: no cover - depende de ambiente externo
            # Sessao expirada: remove do cache para que seja recriada no proximo turno.
            with self._lock:
                self._sessoes.pop(session_id, None)
            raise WatsonAssistantIndisponivel(f"Erro na chamada ao Watson: {erro}") from erro

        return self._normalizar_resposta(resultado)

    @staticmethod
    def _montar_contexto(contexto: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Monta o bloco `context` no formato esperado pela API v2."""
        variaveis = {
            chave: valor
            for chave, valor in (contexto or {}).items()
            if not chave.startswith("_")
        }
        return {"skills": {"main skill": {"user_defined": variaveis}}}

    @staticmethod
    def _normalizar_resposta(resultado: Dict[str, Any]) -> Dict[str, Any]:
        """Converte a resposta bruta da API v2 no formato interno da aplicacao."""
        saida = resultado.get("output", {}) or {}

        textos: List[str] = []
        for item in saida.get("generic", []) or []:
            if item.get("response_type") == "text" and item.get("text"):
                textos.append(item["text"])

        intents = [
            {"intent": i.get("intent"), "confidence": round(float(i.get("confidence", 0)), 4)}
            for i in (saida.get("intents") or [])
        ]
        entidades = [
            {
                "entity": e.get("entity"),
                "value": e.get("value"),
                "literal": e.get("literal", ""),
            }
            for e in (saida.get("entities") or [])
        ]

        contexto_usuario: Dict[str, Any] = {}
        skills = (resultado.get("context") or {}).get("skills") or {}
        for dados_skill in skills.values():
            contexto_usuario.update(dados_skill.get("user_defined") or {})
        contexto_usuario["_conversa_iniciada"] = True

        nos_visitados = (saida.get("debug") or {}).get("nodes_visited") or []
        no_acionado = None
        if nos_visitados:
            ultimo = nos_visitados[-1]
            no_acionado = ultimo.get("dialog_node") or ultimo.get("title")

        emergencia = contexto_usuario.get("encaminhamento") == "emergencia" or any(
            e["entity"] == "sintoma" and e["value"] in SINAIS_DE_ALARME for e in entidades
        )

        resposta = "\n\n".join(textos).strip()
        if not resposta:
            resposta = (
                "Nao consegui formular uma resposta para esta mensagem. "
                "Tente reformular a sua duvida ou digite \"falar com atendente\" "
                "para ser transferido a um profissional da equipe."
            )

        return {
            "resposta": resposta,
            "intent": intents[0]["intent"] if intents else None,
            "confianca": intents[0]["confidence"] if intents else 0.0,
            "intents": intents,
            "entidades": entidades,
            "contexto": contexto_usuario,
            "no_acionado": no_acionado,
            "emergencia": bool(emergencia),
            "origem": "watson",
        }

    # -- Diagnostico -------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Retorna informacoes de diagnostico usadas no endpoint de saude."""
        return {
            "modo_configurado": self.modo_configurado,
            "modo_ativo": self.modo_ativo,
            "credenciais_configuradas": self._credenciais_completas(),
            "assistant_id": self.assistant_id[:8] + "..." if self.assistant_id else None,
            "ultimo_erro": self.ultimo_erro,
            "skill": self.engine_local.resumo_skill(),
        }
