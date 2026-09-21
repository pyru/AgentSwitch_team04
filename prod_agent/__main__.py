"""Ad-hoc CLI: python -m prod_agent --instance suryodaya "This work order WO-2026-00048 is late..." [--apply]"""
import argparse
import datetime as dt
import json

from . import config
from .agent import ProductionAgent
from .mcp_client import McpClient, Session


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("request")
    ap.add_argument("--instance", default="suryodaya", choices=sorted(config.INSTANCES))
    ap.add_argument("--apply", action="store_true", help="allow writes, each approved at the prompt")
    ap.add_argument("--escalate", action="store_true", help="allow the agent to raise one escalation to a person")
    args = ap.parse_args()

    run_dir = config.ROOT / "runs" / "adhoc" / f"{dt.datetime.now():%Y%m%d-%H%M%S-%f}-{args.instance}"
    run_dir.mkdir(parents=True, exist_ok=False)
    trace_file = (run_dir / "trace.jsonl").open("x", encoding="utf-8")

    def trace(event):
        trace_file.write(json.dumps(event, default=str) + "\n")
        trace_file.flush()

    def approve(p):
        print(f"\nProposed: {p['number']} {p['current_start']}..{p['current_end']} -> {p['new_start']}..{p['new_end']} ({p['reason']})")
        return input("Write this change? [y/N] ").strip().lower() == "y"

    agent = ProductionAgent(McpClient(Session(args.instance)), apply_mode=args.apply, escalate_mode=args.escalate,
                            approve=approve, trace=trace)
    out = agent.run(args.request)
    (run_dir / "result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(out["final_answer"] or f"(no final answer: {out['stop_reason']})")
    print(f"\ntrace: {run_dir}")


if __name__ == "__main__":
    main()
