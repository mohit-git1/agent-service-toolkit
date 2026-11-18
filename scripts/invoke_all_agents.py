#!/usr/bin/env python3
"""
Invokes all agents on the deployed service to evaluate real responses,
latencies, and token/cost parameters.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

AGENT_URL = os.getenv("AGENT_URL", "https://agent-service-toolkit-vwvd.onrender.com").rstrip("/")

PROMPTS = {
    "chatbot": "Explain the difference between machine learning and deep learning in two sentences.",
    "research-assistant": "Calculate 45 * 28 and state the result clearly.",
    "rag-assistant": "What is Retrieval-Augmented Generation (RAG)? Give a one-sentence summary.",
    "command-agent": "A",
    "bg-task-agent": "Provide a brief 1-sentence status of the background monitoring worker.",
    "langgraph-supervisor-agent": "What are the primary duties of an AI supervisor agent?",
    "langgraph-supervisor-hierarchy-agent": "Explain why multi-agent hierarchies improve task execution in two sentences.",
    "interrupt-agent": "My birthdate is 1995-06-15. Please record it.",
    "knowledge-base-agent": "What are the key benefits of enterprise knowledge management?",
    "github-mcp-agent": "What is the recommended commit message convention for new features?",
}

def post_json(url: str, payload: dict[str, Any], timeout: float = 60.0) -> tuple[int, Any, float]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - start
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body), elapsed
            except Exception:
                return resp.status, body, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body), elapsed
        except Exception:
            return e.code, body, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return 0, str(e), elapsed


def main():
    print(f"Target Service: {AGENT_URL}\n")
    print("=" * 120)
    print(f"{'Agent Name':<34} | {'Status':<6} | {'HTTP':<4} | {'Latency':<8} | {'Model':<20} | {'Response Snippet'}")
    print("=" * 120)

    results = []

    for agent_name, prompt in PROMPTS.items():
        url = f"{AGENT_URL}/{agent_name}/invoke"
        payload = {"message": prompt}
        code, resp_data, latency = post_json(url, payload, timeout=60.0)

        model_name = "openai/gpt-4o-mini"
        if isinstance(resp_data, dict):
            metadata = resp_data.get("response_metadata", {})
            if "model_name" in metadata:
                model_name = metadata["model_name"]
            content = str(resp_data.get("content", ""))
        else:
            content = str(resp_data)

        status = "PASS" if code == 200 else "FAIL"
        snippet = content.replace("\n", " ").strip()
        if len(snippet) > 42:
            snippet = snippet[:40] + "..."

        print(
            f"{agent_name:<34} | {status:<6} | {code:<4} | {latency:>6.2f}s | {model_name[:20]:<20} | {snippet}"
        )

        results.append({
            "agent": agent_name,
            "status": status,
            "code": code,
            "latency": latency,
            "model": model_name,
            "full_response": content,
            "prompt": prompt,
        })

    print("=" * 120)
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    avg_latency = sum(r["latency"] for r in results) / total if total > 0 else 0
    print(f"\nExecution Summary: {passed}/{total} agents passed | Avg Latency: {avg_latency:.2f}s\n")

    # Output detailed responses
    print("--- Detailed Agent Responses ---")
    for r in results:
        print(f"\n[{r['agent']}] (HTTP {r['code']} in {r['latency']:.2f}s):")
        print(f"Prompt: {r['prompt']}")
        print(f"Response: {r['full_response']}")

if __name__ == "__main__":
    main()
