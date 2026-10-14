"""Add acceptance-only settings to the ignored root .env without replacing values."""

import argparse
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-path", required=True)
    args = parser.parse_args()
    frontend = Path(args.frontend_path).resolve()
    if not (frontend / "dashboard/app/native.py").is_file():
        raise SystemExit("Frontend checkout must contain dashboard/app/native.py")
    root = Path(__file__).resolve().parents[2]
    target = root / ".env"
    existing = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    configured = {
        line.split("=", 1)[0]
        for line in existing
        if "=" in line and not line.lstrip().startswith("#")
    }
    values = {
        name: secrets.token_hex(24)
        for name in (
            "NATIVE_DB_PASSWORD",
            "NATIVE_API_DB_PASSWORD",
            "NATIVE_WORKER_DB_PASSWORD",
        )
    }
    values["NATIVE_FRONTEND_PATH"] = frontend.as_posix()
    if "\n" in values["NATIVE_FRONTEND_PATH"] or '"' in values["NATIVE_FRONTEND_PATH"]:
        raise SystemExit("Unsupported checkout path")
    additions = {key: value for key, value in values.items() if key not in configured}
    if additions:
        with target.open("a", encoding="utf-8", newline="\n") as env_file:
            if existing and existing[-1]:
                env_file.write("\n")
            env_file.write(
                "\n".join(k + '=\"' + v + '\"' for k, v in additions.items()) + "\n"
            )
    target.chmod(0o600)
    print("Acceptance settings added to root .env where absent; credentials not displayed")


if __name__ == "__main__":
    main()
