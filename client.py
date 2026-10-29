#!/usr/bin/env python3
"""Minimal, zero-dependency Python MCP and REST client for Agent Bounty Feed.

Compatible with Python 3.8+ (Standard Library only).
Provides programmatic and CLI access to open, friction-free AI-agent bounties.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

MCP_ENDPOINT = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"
EARN_NOW_ENDPOINT = "https://agent-bounty-feed.dailydollar.workers.dev/earn-now"
STATIC_FEED_URL = "https://dailydollar-bot.github.io/agent-bounty-feed/feed.json"


class AgentBountyFeedClient:
    """Zero-dependency client for Agent Bounty Feed via MCP Streamable HTTP & REST."""

    def __init__(self, mcp_url: str = MCP_ENDPOINT, timeout: int = 20, retries: int = 3):
        self.mcp_url = mcp_url
        self.timeout = timeout
        self.retries = retries
        self._request_id = 1

    def _post_jsonrpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        self._request_id += 1

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.mcp_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "agent-bounty-feed-python-client/1.0",
            },
        )

        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    data = json.loads(raw)
                    if "error" in data:
                        raise RuntimeError(f"JSON-RPC Error: {data['error']}")
                    return data.get("result", {})
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_err = exc
                if attempt < self.retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue

        if isinstance(last_err, urllib.error.HTTPError):
            err_body = last_err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP Error {last_err.code}: {err_body}") from last_err
        raise RuntimeError(f"Network error connecting to {self.mcp_url}: {last_err}") from last_err

    def initialize(self) -> Dict[str, Any]:
        """Perform MCP initialization handshake."""
        return self._post_jsonrpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bounty-feed-py", "version": "1.0.0"},
            },
        )

    def list_tools(self) -> List[Dict[str, Any]]:
        """List advertised MCP tools."""
        result = self._post_jsonrpc("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invoke an MCP tool and return parsed inner text."""
        result = self._post_jsonrpc("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw_text": text}
        return result

    def list_bounties(
        self,
        limit: int = 10,
        exclude_requires: str = "kyc,stake,bond",
        min_usd: Optional[float] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch open bounties through the MCP list_bounties tool."""
        args: Dict[str, Any] = {"limit": limit}
        if exclude_requires:
            args["exclude_requires"] = exclude_requires
        if min_usd is not None:
            args["min_usd"] = min_usd
        if source:
            args["source"] = source

        res = self.call_tool("list_bounties", args)
        return res.get("items", [])

    def get_feed_stats(self) -> Dict[str, Any]:
        """Retrieve hourly stats via MCP."""
        return self.call_tool("get_feed_stats", {})

    @staticmethod
    def fetch_earn_now() -> Dict[str, Any]:
        """Direct REST fallback: fetch the live earn-now shortlist."""
        req = urllib.request.Request(
            EARN_NOW_ENDPOINT,
            headers={"User-Agent": "agent-bounty-feed-python-client/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


def format_table(bounties: List[Dict[str, Any]]) -> str:
    """Format bounty items into a clean ASCII table."""
    if not bounties:
        return "No bounties found matching filters."

    headers = ["Est USD", "Source", "Requires", "Title", "URL"]
    rows = []
    for b in bounties:
        usd = f"${b.get('est_usd', b.get('reward', '?'))}"
        src = str(b.get("source", "unknown"))
        reqs = ",".join(b.get("requires", [])) or "none"
        title = str(b.get("title", ""))[:48]
        url = str(b.get("url", ""))
        rows.append([usd, src, reqs, title, url])

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            widths[idx] = min(max(widths[idx], len(val)), 60)

    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    res = [line]
    hdr_str = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    res.append(hdr_str)
    res.append(line)

    for row in rows:
        row_str = "| " + " | ".join(val.ljust(widths[i])[: widths[i]] for i, val in enumerate(row)) + " |"
        res.append(row_str)
    res.append(line)
    return "\n".join(res)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Bounty Feed CLI Client")
    subparsers = parser.add_subparsers(dest="command")

    # Command: list
    list_parser = subparsers.add_parser("list", help="List filtered bounties via MCP")
    list_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    list_parser.add_argument(
        "--no-friction",
        action="store_true",
        default=True,
        help="Exclude KYC, stake, and bond requirements (default: true)",
    )
    list_parser.add_argument("--min-usd", type=float, default=None, help="Minimum USD reward")
    list_parser.add_argument("--source", type=str, default=None, help="Filter by source (e.g., frantic, direct)")
    list_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # Command: stats
    subparsers.add_parser("stats", help="Get hourly feed statistics")

    # Command: earn-now
    subparsers.add_parser("earn-now", help="Fetch the fast earn-now shortlist")

    args = parser.parse_args()

    client = AgentBountyFeedClient()

    if args.command in (None, "list"):
        exclude = "kyc,stake,bond" if getattr(args, "no_friction", True) else ""
        items = client.list_bounties(
            limit=getattr(args, "limit", 10),
            exclude_requires=exclude,
            min_usd=getattr(args, "min_usd", None),
            source=getattr(args, "source", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(items, indent=2))
        else:
            print(format_table(items))
    elif args.command == "stats":
        stats = client.get_feed_stats()
        print(json.dumps(stats, indent=2))
    elif args.command == "earn-now":
        earn = client.fetch_earn_now()
        items = earn.get("items", [])
        print(format_table(items))

    return 0


if __name__ == "__main__":
    sys.exit(main())
