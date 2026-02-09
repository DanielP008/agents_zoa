"""Request-scoped timing/profiler for measuring performance across the stack."""

import time
import os
import json
import threading
import contextvars
from datetime import datetime, timezone

TIMING_DIR = os.getenv("TIMING_DIR", "/tmp/timings")

# Request-scoped context variables
_request_trace: contextvars.ContextVar["RequestTrace | None"] = contextvars.ContextVar("request_trace", default=None)
_current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_agent", default="")

_file_lock = threading.Lock()


class RequestTrace:
    """Accumulates timing entries for a single request."""

    def __init__(self, session_id: str, channel: str = "unknown"):
        self.session_id = session_id
        self.channel = channel
        self.start = time.perf_counter()
        self.entries: list[dict] = []

    def record(self, category: str, label: str, duration_ms: float, parent: str = "", model: str = ""):
        self.entries.append({
            "category": category,
            "label": label,
            "duration_ms": round(duration_ms, 1),
            "parent": parent,
            "model": model,
        })

    def dump(self):
        """Write the full trace to request_trace.txt."""
        total_ms = round((time.perf_counter() - self.start) * 1000, 1)
        os.makedirs(TIMING_DIR, exist_ok=True)
        filepath = os.path.join(TIMING_DIR, "request_trace.txt")

        # Group entries by category
        by_cat: dict[str, list[dict]] = {}
        for e in self.entries:
            by_cat.setdefault(e["category"], []).append(e)

        lines: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        lines.append(f"========== REQUEST {ts} | session={self.session_id} | channel={self.channel} ==========")
        lines.append(f"TOTAL: {total_ms}ms")
        lines.append("")

        # Postgres
        pg = by_cat.get("postgres", [])
        if pg:
            lines.append("[POSTGRES]")
            for e in pg:
                lines.append(f"  {e['label']:.<35s} {e['duration_ms']}ms")
            pg_total = sum(e["duration_ms"] for e in pg)
            lines.append(f"  {'SUBTOTAL':.<35s} {round(pg_total, 1)}ms")
            lines.append("")

        # Agents
        agents = by_cat.get("agent", [])
        if agents:
            lines.append("[AGENTS]")
            for e in agents:
                # Find tool calls that belong to this agent
                agent_name = e["label"]
                model_info = f" [{e['model']}]" if e.get("model") else ""
                child_tools = [t for t in self.entries if t["category"] in ("erp", "zoa", "tool") and t["parent"] == agent_name]
                tool_info = f" (LLM + {len(child_tools)} tool calls)" if child_tools else " (LLM only, no tools)"
                lines.append(f"  {agent_name:.<35s} {e['duration_ms']}ms{model_info}{tool_info}")
                for ct in child_tools:
                    lines.append(f"    └─ {ct['label']:.<31s} {ct['duration_ms']}ms [{ct['category'].upper()}]")
            agent_total = sum(e["duration_ms"] for e in agents)
            lines.append(f"  {'SUBTOTAL':.<35s} {round(agent_total, 1)}ms")
            lines.append("")

        # External calls
        erp = by_cat.get("erp", [])
        zoa = by_cat.get("zoa", [])
        wildix = by_cat.get("wildix", [])
        if erp or zoa or wildix:
            lines.append("[EXTERNAL CALLS]")
            if erp:
                erp_total = sum(e["duration_ms"] for e in erp)
                lines.append(f"  ERP total .................. {round(erp_total, 1)}ms ({len(erp)} calls)")
                for e in erp:
                    lines.append(f"    └─ {e['label']:.<31s} {e['duration_ms']}ms")
            if zoa:
                zoa_total = sum(e["duration_ms"] for e in zoa)
                lines.append(f"  ZOA total .................. {round(zoa_total, 1)}ms ({len(zoa)} calls)")
                for e in zoa:
                    lines.append(f"    └─ {e['label']:.<31s} {e['duration_ms']}ms")
            if wildix:
                wdx_total = sum(e["duration_ms"] for e in wildix)
                lines.append(f"  Wildix total ............... {round(wdx_total, 1)}ms ({len(wildix)} calls)")
                for e in wildix:
                    lines.append(f"    └─ {e['label']:.<31s} {e['duration_ms']}ms")
            lines.append("")

        # Summary
        pg_total = sum(e["duration_ms"] for e in pg)
        agent_total = sum(e["duration_ms"] for e in agents)
        erp_total = sum(e["duration_ms"] for e in erp)
        zoa_total = sum(e["duration_ms"] for e in zoa)
        wdx_total = sum(e["duration_ms"] for e in wildix)
        tool_total = erp_total + zoa_total
        other = max(0, total_ms - pg_total - agent_total - wdx_total)

        def pct(v):
            return f"{(v / total_ms * 100):.1f}%" if total_ms > 0 else "0%"

        lines.append("[SUMMARY]")
        lines.append(f"  Postgres ......... {round(pg_total, 1)}ms ({pct(pg_total)})")
        lines.append(f"  Agent LLM ........ {round(agent_total - tool_total, 1)}ms ({pct(agent_total - tool_total)})")
        lines.append(f"  Tool calls ....... {round(tool_total, 1)}ms ({pct(tool_total)})")
        lines.append(f"  Wildix API ....... {round(wdx_total, 1)}ms ({pct(wdx_total)})")
        lines.append(f"  Other ............ {round(other, 1)}ms ({pct(other)})")
        lines.append("")

        text = "\n".join(lines) + "\n"
        with _file_lock:
            with open(filepath, "a") as f:
                f.write(text)

        # Also write structured JSONL for analytics
        jsonl_path = os.path.join(TIMING_DIR, "request_trace.jsonl")
        record = {
            "timestamp": ts,
            "session_id": self.session_id,
            "channel": self.channel,
            "total_ms": total_ms,
            "postgres_ms": round(pg_total, 1),
            "postgres_calls": len(pg),
            "agent_total_ms": round(agent_total, 1),
            "agent_llm_ms": round(agent_total - tool_total, 1),
            "tool_calls_ms": round(tool_total, 1),
            "erp_ms": round(erp_total, 1),
            "erp_calls": len(erp),
            "zoa_ms": round(zoa_total, 1),
            "zoa_calls": len(zoa),
            "wildix_ms": round(wdx_total, 1),
            "wildix_calls": len(wildix),
            "other_ms": round(other, 1),
            "agents": [
                {
                    "name": e["label"],
                    "duration_ms": e["duration_ms"],
                    "model": e.get("model", ""),
                    "tools": [
                        {"name": t["label"], "duration_ms": t["duration_ms"], "category": t["category"]}
                        for t in self.entries
                        if t["category"] in ("erp", "zoa", "tool") and t["parent"] == e["label"]
                    ]
                }
                for e in agents
            ],
            "postgres_detail": [{"op": e["label"], "duration_ms": e["duration_ms"]} for e in pg],
        }
        with _file_lock:
            with open(jsonl_path, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


def start_trace(session_id: str, channel: str = "unknown") -> RequestTrace:
    """Start a new request trace and set it in the current context."""
    trace = RequestTrace(session_id, channel)
    _request_trace.set(trace)
    return trace


def get_trace() -> "RequestTrace | None":
    """Get the current request trace."""
    return _request_trace.get()


def record(category: str, label: str, duration_ms: float, parent: str = "", model: str = ""):
    """Record a timing entry into the current trace (if active)."""
    trace = _request_trace.get()
    if trace:
        trace.record(category, label, duration_ms, parent, model)


def set_current_agent(name: str):
    """Set the currently executing agent name (for parent tracking in tools)."""
    _current_agent.set(name)


def get_current_agent() -> str:
    """Get the currently executing agent name."""
    return _current_agent.get()


class Timer:
    """Context manager that measures elapsed time and records to the active trace."""

    def __init__(self, category: str, label: str, parent: str = "", model: str = ""):
        self.category = category
        self.label = label
        self.parent = parent
        self.model = model
        self.duration_ms = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.duration_ms = round((time.perf_counter() - self._start) * 1000, 1)
        record(self.category, self.label, self.duration_ms, self.parent, self.model)
