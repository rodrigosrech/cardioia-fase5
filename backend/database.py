"""
database.py
===========

Camada de persistencia do CardioIA - Fase 5.

Utiliza SQLite (biblioteca padrao do Python, sem servidor dedicado) para
armazenar o historico das conversas, permitindo:

    * recuperar o historico de uma sessao para continuidade do atendimento;
    * auditar as interacoes, requisito relevante em aplicacoes de saude;
    * gerar metricas agregadas de uso (distribuicao de intencoes, taxa de
      fallback e volume de encaminhamentos para emergencia).

Esquema da tabela `conversas`:

    id                  INTEGER PRIMARY KEY AUTOINCREMENT
    sessao              TEXT     identificador da conversa
    timestamp           TEXT     data e hora em formato ISO 8601 (UTC)
    mensagem_usuario    TEXT     texto enviado pelo usuario
    resposta_assistente TEXT     texto devolvido pelo assistente
    intent_detectada    TEXT     intencao reconhecida (NULL em caso de fallback)
    confianca           REAL     confianca da intencao reconhecida
    entidades           TEXT     entidades reconhecidas, serializadas em JSON
    no_dialogo          TEXT     identificador do dialog node acionado
    emergencia          INTEGER  1 quando houve encaminhamento de urgencia
    origem              TEXT     'watson' ou 'mock'

Autor: equipe CardioIA - Fase 5
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

#: Caminho padrao do banco (sobrescrevivel pela variavel de ambiente DATABASE_PATH).
CAMINHO_PADRAO = str(Path(__file__).resolve().parent / "cardioia.db")

_lock = threading.Lock()


def _caminho_banco() -> str:
    return os.getenv("DATABASE_PATH", CAMINHO_PADRAO)


@contextmanager
def conexao() -> Iterator[sqlite3.Connection]:
    """Gerenciador de contexto que abre, confirma e fecha a conexao com seguranca."""
    conn = sqlite3.connect(_caminho_banco(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar() -> None:
    """Cria a tabela e os indices, caso ainda nao existam (idempotente)."""
    with _lock, conexao() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversas (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao              TEXT    NOT NULL,
                timestamp           TEXT    NOT NULL,
                mensagem_usuario    TEXT    NOT NULL,
                resposta_assistente TEXT    NOT NULL,
                intent_detectada    TEXT,
                confianca           REAL    DEFAULT 0,
                entidades           TEXT    DEFAULT '[]',
                no_dialogo          TEXT,
                emergencia          INTEGER DEFAULT 0,
                origem              TEXT    DEFAULT 'mock'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conversas_sessao ON conversas (sessao)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conversas_intent ON conversas (intent_detectada)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conversas_timestamp ON conversas (timestamp)")


def registrar_interacao(
    sessao: str,
    mensagem_usuario: str,
    resposta_assistente: str,
    intent_detectada: Optional[str] = None,
    confianca: float = 0.0,
    entidades: Optional[List[Dict[str, Any]]] = None,
    no_dialogo: Optional[str] = None,
    emergencia: bool = False,
    origem: str = "mock",
) -> int:
    """Persiste um turno da conversa e retorna o identificador do registro."""
    registro = (
        sessao,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        mensagem_usuario,
        resposta_assistente,
        intent_detectada,
        float(confianca or 0.0),
        json.dumps(entidades or [], ensure_ascii=False),
        no_dialogo,
        1 if emergencia else 0,
        origem,
    )

    with _lock, conexao() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversas (
                sessao, timestamp, mensagem_usuario, resposta_assistente,
                intent_detectada, confianca, entidades, no_dialogo,
                emergencia, origem
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registro,
        )
        return int(cursor.lastrowid)


def obter_historico(sessao: str, limite: int = 50) -> List[Dict[str, Any]]:
    """Retorna as interacoes de uma sessao em ordem cronologica."""
    with conexao() as conn:
        linhas = conn.execute(
            """
            SELECT * FROM conversas
            WHERE sessao = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (sessao, limite),
        ).fetchall()

    return [_linha_para_dicionario(linha) for linha in linhas]


def limpar_sessao(sessao: str) -> int:
    """Remove o historico de uma sessao. Retorna a quantidade de registros apagados."""
    with _lock, conexao() as conn:
        cursor = conn.execute("DELETE FROM conversas WHERE sessao = ?", (sessao,))
        return int(cursor.rowcount)


def obter_metricas() -> Dict[str, Any]:
    """Calcula metricas agregadas de uso do assistente.

    As metricas apoiam a avaliacao da qualidade do modelo conversacional,
    especialmente a taxa de fallback, que indica lacunas de cobertura nas
    intencoes treinadas.
    """
    with conexao() as conn:
        total = conn.execute("SELECT COUNT(*) AS total FROM conversas").fetchone()["total"]
        sessoes = conn.execute(
            "SELECT COUNT(DISTINCT sessao) AS total FROM conversas"
        ).fetchone()["total"]
        emergencias = conn.execute(
            "SELECT COUNT(*) AS total FROM conversas WHERE emergencia = 1"
        ).fetchone()["total"]
        fallbacks = conn.execute(
            "SELECT COUNT(*) AS total FROM conversas WHERE intent_detectada IS NULL"
        ).fetchone()["total"]
        distribuicao = conn.execute(
            """
            SELECT COALESCE(intent_detectada, 'fallback') AS intent,
                   COUNT(*) AS ocorrencias,
                   ROUND(AVG(confianca), 4) AS confianca_media
            FROM conversas
            GROUP BY COALESCE(intent_detectada, 'fallback')
            ORDER BY ocorrencias DESC
            """
        ).fetchall()

    return {
        "total_interacoes": total,
        "total_sessoes": sessoes,
        "encaminhamentos_emergencia": emergencias,
        "total_fallbacks": fallbacks,
        "taxa_fallback": round(fallbacks / total, 4) if total else 0.0,
        "distribuicao_intents": [dict(linha) for linha in distribuicao],
    }


def _linha_para_dicionario(linha: sqlite3.Row) -> Dict[str, Any]:
    """Converte uma linha do banco em dicionario serializavel em JSON."""
    registro = dict(linha)
    try:
        registro["entidades"] = json.loads(registro.get("entidades") or "[]")
    except json.JSONDecodeError:
        registro["entidades"] = []
    registro["emergencia"] = bool(registro.get("emergencia"))
    return registro
