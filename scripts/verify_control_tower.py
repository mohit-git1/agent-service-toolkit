#!/usr/bin/env python3
"""Verify Control Tower agent registration and heartbeat health.

Queries the agent service /info endpoint to discover all configured agents,
then queries the Control Tower API to verify each agent has registered via the SDK
and emitted recent heartbeats.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


def _http_get(url: str, headers: dict[str, str] | None = None, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to {url}: {e.reason}") from e


def _http_post_json(
    url: str, payload: dict, headers: dict[str, str] | None = None, timeout: float = 30.0
) -> tuple[int, dict | str]:
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=all_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(resp_body)
            except Exception:
                return resp.status, resp_body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error to {url}: {e.reason}") from e


def _parse_iso(timestamp_str: str) -> datetime | None:
    try:
        cleaned = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Control Tower registration and heartbeat status for all service agents."
    )
    parser.add_argument(
        "--agent-url",
        default=os.getenv("AGENT_URL", "http://localhost:8080"),
        help="Agent service base URL (default: AGENT_URL or http://localhost:8080)",
    )
    parser.add_argument(
        "--control-tower-url",
        default=os.getenv("CONTROL_TOWER_URL", "http://localhost:8000"),
        help="Control Tower base URL (default: CONTROL_TOWER_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--control-tower-api-key",
        default=os.getenv("CONTROL_TOWER_API_KEY", ""),
        help="Control Tower API key (default: CONTROL_TOWER_API_KEY)",
    )
    parser.add_argument(
        "--auth-secret",
        default=os.getenv("AUTH_SECRET", ""),
        help="Agent service bearer token secret (default: AUTH_SECRET)",
    )
    parser.add_argument(
        "--invoke",
        action="store_true",
        help="Invoke each agent once with a short test message and report the result",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP request timeout in seconds (default: 15.0)",
    )

    args = parser.parse_args()

    agent_url = args.agent_url.rstrip("/")
    control_tower_url = args.control_tower_url.rstrip("/")
    api_key = args.control_tower_api_key.strip()

    if not api_key:
        print(
            "ERROR: CONTROL_TOWER_API_KEY is required. Pass --control-tower-api-key or set CONTROL_TOWER_API_KEY env var.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Agent Service URL: {agent_url}")
    print(f"Control Tower URL: {control_tower_url}")
    print("Checking agent service /info...")

    service_headers: dict[str, str] = {}
    if args.auth_secret:
        service_headers["Authorization"] = f"Bearer {args.auth_secret}"

    try:
        info_resp = _http_get(f"{agent_url}/info", headers=service_headers, timeout=args.timeout)
    except Exception as e:
        print(f"ERROR: Failed to retrieve /info from agent service: {e}", file=sys.stderr)
        sys.exit(1)

    configured_agents = [a["key"] for a in info_resp.get("agents", []) if "key" in a]
    if not configured_agents:
        print("ERROR: No agents discovered from /info endpoint.", file=sys.stderr)
        sys.exit(1)

    print(f"Discovered {len(configured_agents)} agent(s) from service: {configured_agents}\n")
    print("Checking Control Tower registered agents...")

    ct_headers = {"X-API-Key": api_key}
    ct_endpoint = (
        f"{control_tower_url}/api/v1/agents?registration_method=sdk&last_seen_within_seconds=180"
    )

    try:
        ct_resp = _http_get(ct_endpoint, headers=ct_headers, timeout=args.timeout)
    except Exception as e:
        print(f"ERROR: Failed to query Control Tower: {e}", file=sys.stderr)
        sys.exit(1)

    ct_agent_list = []
    if isinstance(ct_resp, dict):
        ct_agent_list = ct_resp.get("agents", [])
    elif isinstance(ct_resp, list):
        ct_agent_list = ct_resp

    ct_agents_by_name = {
        a.get("name"): a for a in ct_agent_list if isinstance(a, dict) and a.get("name")
    }

    # Print PASS/FAIL table
    col_name = 38
    col_reg = 13
    col_seen = 16
    col_plat = 16
    col_regn = 16

    header = (
        f"{'Agent Name':<{col_name}} | "
        f"{'Registered?':<{col_reg}} | "
        f"{'Last Seen':<{col_seen}} | "
        f"{'Platform':<{col_plat}} | "
        f"{'Region':<{col_regn}}"
    )
    divider = "-" * len(header)

    print(divider)
    print(header)
    print(divider)

    now = datetime.now(UTC)
    missing_agents: list[str] = []

    for name in configured_agents:
        ct_entry = ct_agents_by_name.get(name)
        if ct_entry:
            reg_status = "PASS"
            last_seen_val = ct_entry.get("last_seen_at")
            if last_seen_val:
                parsed_dt = _parse_iso(str(last_seen_val))
                if parsed_dt:
                    secs = max(0, int((now - parsed_dt).total_seconds()))
                    last_seen_str = f"{secs}s ago"
                else:
                    last_seen_str = str(last_seen_val)[:14]
            else:
                last_seen_str = "never"

            hosting = ct_entry.get("hosting") or {}
            platform = str(hosting.get("platform") or hosting.get("cloud") or "unknown")
            region = str(hosting.get("region") or "unknown")
        else:
            reg_status = "FAIL"
            last_seen_str = "N/A"
            platform = "N/A"
            region = "N/A"
            missing_agents.append(name)

        print(
            f"{name:<{col_name}} | "
            f"{reg_status:<{col_reg}} | "
            f"{last_seen_str:<{col_seen}} | "
            f"{platform:<{col_plat}} | "
            f"{region:<{col_regn}}"
        )

    print(divider)

    # Optional invocation test
    invoke_failures = 0
    if args.invoke:
        print("\nInvoking agents for verification (--invoke)...")
        inv_col_name = 38
        inv_col_status = 10
        inv_col_code = 12
        inv_col_time = 12
        inv_col_resp = 40

        inv_header = (
            f"{'Agent Name':<{inv_col_name}} | "
            f"{'Result':<{inv_col_status}} | "
            f"{'HTTP Status':<{inv_col_code}} | "
            f"{'Latency':<{inv_col_time}} | "
            f"{'Response Snippet':<{inv_col_resp}}"
        )
        inv_divider = "-" * len(inv_header)
        print(inv_divider)
        print(inv_header)
        print(inv_divider)

        for name in configured_agents:
            invoke_url = f"{agent_url}/{name}/invoke"
            payload = {"message": "Health check ping from Control Tower verification script."}
            start_time = time.time()
            try:
                code, resp_data = _http_post_json(
                    invoke_url, payload=payload, headers=service_headers, timeout=args.timeout
                )
                latency = time.time() - start_time
                if code == 200:
                    status_text = "PASS"
                    if isinstance(resp_data, dict):
                        content = str(resp_data.get("content", ""))
                    else:
                        content = str(resp_data)
                    snippet = (content[:37] + "...") if len(content) > 40 else content
                else:
                    status_text = "FAIL"
                    invoke_failures += 1
                    snippet = str(resp_data)[:37]
            except Exception as e:
                latency = time.time() - start_time
                status_text = "FAIL"
                code = 0
                invoke_failures += 1
                snippet = str(e)[:37]

            print(
                f"{name:<{inv_col_name}} | "
                f"{status_text:<{inv_col_status}} | "
                f"{code:<{inv_col_code}} | "
                f"{latency:.2f}s{'':<{inv_col_time - 5}} | "
                f"{snippet:<{inv_col_resp}}"
            )
        print(inv_divider)

    # Final summary and exit
    if missing_agents:
        print(
            f"\nFAIL: {len(missing_agents)} of {len(configured_agents)} agent(s) missing or not seen recently in Control Tower: {missing_agents}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"\nPASS: All {len(configured_agents)} agent(s) verified registered and active in Control Tower."
    )
    if args.invoke and invoke_failures > 0:
        print(
            f"WARNING: {invoke_failures} agent invocation(s) failed during test.", file=sys.stderr
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
