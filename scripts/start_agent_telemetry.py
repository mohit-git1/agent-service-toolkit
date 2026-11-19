#!/usr/bin/env python3
"""Registers all toolkit agents with AI Control Tower and runs background heartbeats."""
import os
import signal
import sys
import time
from control_tower_sdk import ControlTower

CONTROL_TOWER_URL = os.getenv("CONTROL_TOWER_URL", "http://localhost:8000")
CONTROL_TOWER_API_KEY = os.getenv(
    "CONTROL_TOWER_API_KEY", "act_live_0da809aa4672a6316b237389ae07e88e1606ebfc"
)
ENVIRONMENT = os.getenv("ENVIRONMENT", "test")

AGENTS = [
    ("chatbot", "A simple chatbot with conversational memory."),
    ("research-assistant", "A research assistant with web search and calculator capabilities."),
    ("rag-assistant", "A RAG assistant with access to information in a vector database."),
    ("command-agent", "A command execution and orchestration agent."),
    ("bg-task-agent", "A background task monitoring and processing agent."),
    ("langgraph-supervisor-agent", "A LangGraph supervisor agent coordinating specialized sub-agents."),
    ("langgraph-supervisor-hierarchy-agent", "A hierarchical LangGraph supervisor agent managing nested sub-agents."),
    ("interrupt-agent", "An interactive agent that supports human-in-the-loop interrupts and approvals."),
    ("knowledge-base-agent", "A knowledge base assistant utilizing enterprise vector search."),
    ("github-mcp-agent", "A GitHub agent equipped with Model Context Protocol tools.")
]

def main():
    print(f"Connecting to Control Tower at {CONTROL_TOWER_URL} (env={ENVIRONMENT})...")
    tower = ControlTower(
        api_key=CONTROL_TOWER_API_KEY,
        base_url=CONTROL_TOWER_URL,
        environment=ENVIRONMENT,
        heartbeat_seconds=30,
    )

    for name, desc in AGENTS:
        handle = tower.agent(
            name=name,
            description=desc,
            framework="langgraph",
            environment=ENVIRONMENT,
            llms=["openai/gpt-4o-mini"]
        )
        handle.register()
        hb = handle.heartbeat_once()
        print(f"Registered {name}: ID={handle.agent_id}, hb={hb.get('status') if hb else 'ok'}")

    tower.start()
    print("Background heartbeat thread running. All 10 agents active.")

    def shutdown(signum, frame):
        print("Shutting down telemetry...")
        tower.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()
