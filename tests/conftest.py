"""
pytest never calls the real API and never costs money:
  - ANTHROPIC_API_KEY is removed, so get_client() raises AIUnavailable
  - anthropic.Anthropic and socket connections raise if anything tries anyway
  - the AI disk cache points at a per-test temp folder, never the real .cache/
"""

import socket

import anthropic
import pytest

import ai_analyst


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    def refuse(*args, **kwargs):
        raise NetworkBlocked("Tests must not use the network or the real Anthropic API.")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_analyst, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(anthropic, "Anthropic", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(ai_analyst, "CACHE_DIR", tmp_path / "ai-cache")
    monkeypatch.setattr(ai_analyst, "LEDGER", ai_analyst.CostLedger())
