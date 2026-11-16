import subprocess
import sys
from pathlib import Path

# Ensure repository root is on sys.path so scripts/ can be imported in tests
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest


def test_verify_script_missing_api_key(monkeypatch):
    """Exits with code 1 if CONTROL_TOWER_API_KEY is not set."""
    monkeypatch.delenv("CONTROL_TOWER_API_KEY", raising=False)
    cmd = [sys.executable, "scripts/verify_control_tower.py"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "CONTROL_TOWER_API_KEY is required" in res.stderr


def test_verify_script_success(monkeypatch):
    """Passes and returns 0 when all agents are present in Control Tower."""
    from scripts import verify_control_tower

    info_data = {
        "agents": [
            {"key": "chatbot", "description": "Chatbot"},
            {"key": "research-assistant", "description": "Research"},
        ]
    }
    ct_data = {
        "agents": [
            {
                "name": "chatbot",
                "last_seen_at": "2026-11-16T18:00:00Z",
                "hosting": {"platform": "Render", "region": "oregon"},
            },
            {
                "name": "research-assistant",
                "last_seen_at": "2026-11-16T18:00:10Z",
                "hosting": {"platform": "Render", "region": "oregon"},
            },
        ]
    }

    def mock_get(url, headers=None, timeout=15.0):
        if url.endswith("/info"):
            return info_data
        if "/api/v1/agents" in url:
            return ct_data
        raise ValueError(f"Unexpected url: {url}")

    monkeypatch.setattr(verify_control_tower, "_http_get", mock_get)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_control_tower.py",
            "--agent-url",
            "http://localhost:8080",
            "--control-tower-url",
            "http://localhost:8000",
            "--control-tower-api-key",
            "act_live_test",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        verify_control_tower.main()
    assert exc_info.value.code == 0


def test_verify_script_missing_agent_exits_nonzero(monkeypatch):
    """Exits with code 1 when an agent from /info is missing in Control Tower."""
    from scripts import verify_control_tower

    info_data = {
        "agents": [
            {"key": "chatbot", "description": "Chatbot"},
            {"key": "research-assistant", "description": "Research"},
        ]
    }
    ct_data = {
        "agents": [
            {
                "name": "chatbot",
                "last_seen_at": "2026-11-16T18:00:00Z",
                "hosting": {"platform": "Render", "region": "oregon"},
            }
        ]
    }

    def mock_get(url, headers=None, timeout=15.0):
        if url.endswith("/info"):
            return info_data
        if "/api/v1/agents" in url:
            return ct_data
        raise ValueError(f"Unexpected url: {url}")

    monkeypatch.setattr(verify_control_tower, "_http_get", mock_get)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_control_tower.py",
            "--control-tower-api-key",
            "act_live_test",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        verify_control_tower.main()
    assert exc_info.value.code == 1


def test_verify_script_with_invoke(monkeypatch):
    """Executes invoke branch when --invoke is passed."""
    from scripts import verify_control_tower

    info_data = {"agents": [{"key": "chatbot"}]}
    ct_data = {
        "agents": [
            {
                "name": "chatbot",
                "last_seen_at": "2026-11-16T18:00:00Z",
                "hosting": {"platform": "local", "region": "unknown"},
            }
        ]
    }

    monkeypatch.setattr(verify_control_tower, "_http_get", lambda url, headers=None, timeout=15.0: info_data if url.endswith("/info") else ct_data)
    monkeypatch.setattr(
        verify_control_tower,
        "_http_post_json",
        lambda url, payload, headers=None, timeout=30.0: (200, {"content": "pong"}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_control_tower.py",
            "--control-tower-api-key",
            "act_live_test",
            "--invoke",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        verify_control_tower.main()
    assert exc_info.value.code == 0
