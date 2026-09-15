"""
app.py
======

Aplicacao backend do CardioIA - Fase 5.

Expoe uma API REST que intermedia a comunicacao entre a interface web e o
assistente conversacional, persistindo o historico das interacoes em SQLite.

Endpoints disponiveis:

    GET  /                      Serve a interface web do chat.
    POST /api/chat              Processa uma mensagem do usuario.
    GET  /api/historico/<id>    Recupera o historico de uma sessao.
    POST /api/sessao/reiniciar  Encerra a sessao e limpa o contexto.
    GET  /api/metricas          Metricas agregadas de uso.
    GET  /api/saude             Diagnostico do servico (health check).

Execucao local:

    cd backend
    pip install -r requirements.txt
    python app.py

Autor: equipe CardioIA - Fase 5
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from flask import Flask, jsonify, request, send_from_directory

import database
from watson_client import AssistantService, WatsonAssistantIndisponivel

# ---------------------------------------------------------------------------
# Configuracao de ambiente e log
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dependencia opcional
    pass

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("cardioia.app")

DIRETORIO_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

#: Tamanho maximo aceito para a mensagem do usuario (protecao basica de entrada).
LIMITE_CARACTERES_MENSAGEM = 1000

#: Contextos mantidos em memoria por sessao (o historico persistido fica no SQLite).
_contextos_por_sessao: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Fabrica da aplicacao
# ---------------------------------------------------------------------------

def criar_app() -> Flask:
    """Cria e configura a instancia Flask da aplicacao."""
    app = Flask(__name__, static_folder=None)

    # CORS e habilitado para permitir que a interface seja servida de outra origem
    # durante o desenvolvimento (por exemplo, abrindo o HTML diretamente).
    try:
        from flask_cors import CORS

        CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})
    except ImportError:  # pragma: no cover - dependencia opcional
        logger.warning("flask-cors nao instalado; requisicoes cross-origin podem falhar.")

    database.inicializar()
    servico = AssistantService()
    app.config["ASSISTANT_SERVICE"] = servico

    logger.info(
        "CardioIA iniciado | modo configurado=%s | modo ativo=%s",
        servico.modo_configurado,
        servico.modo_ativo,
    )

    _registrar_rotas(app, servico)
    _registrar_tratadores_de_erro(app)
    return app


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

def _registrar_rotas(app: Flask, servico: AssistantService) -> None:

    @app.route("/", methods=["GET"])
    def interface():
        """Serve a interface web do chat."""
        if not (DIRETORIO_FRONTEND / "index.html").exists():
            return jsonify({
                "servico": "CardioIA - Assistente Cardiologico Conversacional",
                "aviso": "Interface nao encontrada. Verifique a pasta 'frontend'.",
            }), 200
        return send_from_directory(DIRETORIO_FRONTEND, "index.html")

    @app.route("/api/chat", methods=["POST"])
    def chat() -> Tuple[Any, int]:
        """Processa uma mensagem do usuario e devolve a resposta do assistente."""
        dados = request.get_json(silent=True) or {}
        mensagem = (dados.get("message") or dados.get("mensagem") or "").strip()
        sessao = (dados.get("session_id") or dados.get("sessao") or "").strip()

        if not mensagem:
            return jsonify({
                "erro": "campo_obrigatorio",
                "mensagem": "O campo 'message' e obrigatorio e nao pode estar vazio.",
            }), 400

        if len(mensagem) > LIMITE_CARACTERES_MENSAGEM:
            return jsonify({
                "erro": "mensagem_muito_longa",
                "mensagem": (
                    f"A mensagem excede o limite de {LIMITE_CARACTERES_MENSAGEM} caracteres. "
                    "Descreva a sua duvida de forma mais objetiva."
                ),
            }), 413

        if not sessao:
            sessao = str(uuid.uuid4())

        contexto = _contextos_por_sessao.get(sessao, {})

        try:
            resultado = servico.enviar_mensagem(mensagem, sessao, contexto)
        except WatsonAssistantIndisponivel as erro:
            logger.error("Falha na comunicacao com o assistente: %s", erro)
            return jsonify({
                "erro": "servico_indisponivel",
                "mensagem": (
                    "Nao foi possivel contatar o servico de dialogo neste momento. "
                    "Tente novamente em instantes ou procure atendimento humano."
                ),
                "detalhe": str(erro),
                "session_id": sessao,
            }), 503
        except Exception as erro:  # pragma: no cover - protecao de ultimo nivel
            logger.exception("Erro inesperado ao processar a mensagem.")
            return jsonify({
                "erro": "erro_interno",
                "mensagem": (
                    "Ocorreu um erro interno ao processar a sua mensagem. "
                    "Se a situacao for urgente, ligue para o SAMU (192)."
                ),
                "detalhe": str(erro),
                "session_id": sessao,
            }), 500

        _contextos_por_sessao[sessao] = resultado.get("contexto", {})

        try:
            database.registrar_interacao(
                sessao=sessao,
                mensagem_usuario=mensagem,
                resposta_assistente=resultado["resposta"],
                intent_detectada=resultado.get("intent"),
                confianca=resultado.get("confianca", 0.0),
                entidades=resultado.get("entidades", []),
                no_dialogo=resultado.get("no_acionado"),
                emergencia=resultado.get("emergencia", False),
                origem=resultado.get("origem", "mock"),
            )
        except Exception:  # pragma: no cover - falha de log nao interrompe o atendimento
            logger.exception("Falha ao registrar a interacao no banco de dados.")

        return jsonify({
            "session_id": sessao,
            "resposta": resultado["resposta"],
            "intent": resultado.get("intent"),
            "confianca": resultado.get("confianca", 0.0),
            "entidades": resultado.get("entidades", []),
            "no_dialogo": resultado.get("no_acionado"),
            "emergencia": resultado.get("emergencia", False),
            "origem": resultado.get("origem", "mock"),
            "contexto": {
                chave: valor
                for chave, valor in resultado.get("contexto", {}).items()
                if not chave.startswith("_")
            },
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }), 200

    @app.route("/api/historico/<session_id>", methods=["GET"])
    def historico(session_id: str) -> Tuple[Any, int]:
        """Retorna o historico persistido de uma sessao."""
        limite = request.args.get("limite", default=50, type=int)
        limite = max(1, min(limite, 200))
        registros = database.obter_historico(session_id, limite)
        return jsonify({
            "session_id": session_id,
            "total": len(registros),
            "interacoes": registros,
        }), 200

    @app.route("/api/sessao/reiniciar", methods=["POST"])
    def reiniciar_sessao() -> Tuple[Any, int]:
        """Encerra a sessao, limpa o contexto e opcionalmente apaga o historico."""
        dados = request.get_json(silent=True) or {}
        sessao = (dados.get("session_id") or dados.get("sessao") or "").strip()
        apagar_historico = bool(dados.get("apagar_historico", False))

        if not sessao:
            return jsonify({
                "erro": "campo_obrigatorio",
                "mensagem": "O campo 'session_id' e obrigatorio.",
            }), 400

        _contextos_por_sessao.pop(sessao, None)
        servico.encerrar_sessao(sessao)

        removidos = database.limpar_sessao(sessao) if apagar_historico else 0

        return jsonify({
            "session_id": sessao,
            "mensagem": "Sessao reiniciada com sucesso.",
            "registros_removidos": removidos,
        }), 200

    @app.route("/api/metricas", methods=["GET"])
    def metricas() -> Tuple[Any, int]:
        """Metricas agregadas de uso do assistente."""
        return jsonify(database.obter_metricas()), 200

    @app.route("/api/saude", methods=["GET"])
    def saude() -> Tuple[Any, int]:
        """Health check do servico, incluindo o modo de operacao ativo."""
        return jsonify({
            "status": "operacional",
            "servico": "CardioIA - Assistente Cardiologico Conversacional",
            "versao": "1.0.0",
            "assistente": servico.status(),
            "sessoes_em_memoria": len(_contextos_por_sessao),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }), 200


# ---------------------------------------------------------------------------
# Tratamento global de erros
# ---------------------------------------------------------------------------

def _registrar_tratadores_de_erro(app: Flask) -> None:

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        return jsonify({
            "erro": "nao_encontrado",
            "mensagem": "O recurso solicitado nao existe nesta API.",
        }), 404

    @app.errorhandler(405)
    def metodo_nao_permitido(_erro):
        return jsonify({
            "erro": "metodo_nao_permitido",
            "mensagem": "O metodo HTTP utilizado nao e aceito por este endpoint.",
        }), 405

    @app.errorhandler(500)
    def erro_interno(_erro):  # pragma: no cover
        return jsonify({
            "erro": "erro_interno",
            "mensagem": "Erro interno do servidor.",
        }), 500


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

app = criar_app()

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=porta, debug=debug)
