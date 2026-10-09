import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTANCES = {
    "suryodaya": "https://agentswitch.theschoolofai.in",
    "keystone": "https://class.agentswitch.theschoolofai.in",
}

# Every row this team's harness creates carries this marker in `notes`/`content`,
# so nothing we write can be confused with another team's data.
HARNESS_MARKER = "team04-harness"
FINDING_PREFIX = "TEAM04_FINDING "


def on_platform() -> bool:
    """True under AgentSwitch's harness runner ("Our harness" -> Submit for a run).

    Read from the process environment only, like AGENT_OFFLINE: the runner provides no .env, and a stray .env
    line must not be able to move a local run onto a token it was never given.
    """
    return bool(os.environ.get("AGENTSWITCH_TOKEN"))


def platform() -> dict | None:
    """The runner's instance, base URL and seat token, or None anywhere else. Raises on a half-set environment."""
    if not on_platform():
        return None
    base = (os.environ.get("AGENTSWITCH_BASE_URL") or "").strip().rstrip("/")
    instance = (os.environ.get("AGENTSWITCH_INSTANCE") or "").strip()
    missing = [name for name, value in (("AGENTSWITCH_BASE_URL", base), ("AGENTSWITCH_INSTANCE", instance)) if not value]
    if missing:
        raise RuntimeError(f"AGENTSWITCH_TOKEN is set but {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not")
    if instance not in INSTANCES:
        raise RuntimeError(f"AGENTSWITCH_INSTANCE={instance!r} is not one of {sorted(INSTANCES)}")
    return {"base": base, "token": os.environ["AGENTSWITCH_TOKEN"].strip(), "instance": instance}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Non-empty values in the project .env win over the process environment.

    Except under the harness runner, which provides its own model settings: ours must not override them.
    """
    if on_platform() or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ[key.strip()] = value


def env(name: str, default: str | None = None) -> str | None:
    load_dotenv()
    return os.environ.get(name) or default


def credentials(instance: str) -> tuple[str, str]:
    email = env("TEAM04_EMAIL", "team04@theschoolofai.in")
    password = env(f"TEAM04_PASSWORD_{instance.upper()}")
    if not password:
        raise RuntimeError(f"Set TEAM04_PASSWORD_{instance.upper()} in .env")
    return email, password


def today() -> dt.date:
    pinned = env("AGENT_TODAY")
    return dt.date.fromisoformat(pinned) if pinned else dt.date.today()
