"""python -m viewer [--port 8765]: local run console for the harness. See viewer/server.py."""
import argparse

from harness.runner import load_tasks
from prod_agent import config

from .jobs import JobRunner
from .server import HOST, make_server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    runs_dir = config.ROOT / "runs"
    jobs = JobRunner(load_tasks(include_samples=False), runs_dir / "demo", adhoc_base=runs_dir / "adhoc")
    server = make_server(args.port, {"committed": runs_dir, "demo": runs_dir / "demo", "adhoc": runs_dir / "adhoc"}, jobs)
    print(f"Console on http://{HOST}:{args.port}  (Ctrl-C stops the console; a run in progress finishes on its own)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
