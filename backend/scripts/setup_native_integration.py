"""Create an ignored acceptance env file, never display or replace credentials."""

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
    target = root / ".env.native-integration-local"
    if target.exists():
        raise SystemExit(
            "Private configuration already exists; retained without replacement"
        )
    values = {
        name: secrets.token_hex(24)
        for name in (
            "NATIVE_DB_PASSWORD",
            "NATIVE_API_DB_PASSWORD",
            "NATIVE_WORKER_DB_PASSWORD",
        )
    }
    values["NATIVE_FRONTEND_PATH"] = frontend.as_posix()
    # Quotes preserve paths containing spaces; newline paths are never supported.
    if "\n" in values["NATIVE_FRONTEND_PATH"] or '"' in values["NATIVE_FRONTEND_PATH"]:
        raise SystemExit("Unsupported checkout path")
    target.write_text(
        "".join(k + '="' + v + '"\n' for k, v in values.items()), encoding="utf-8"
    )
    target.chmod(0o600)
    print("Private acceptance configuration created; no credentials displayed")


if __name__ == "__main__":
    main()
