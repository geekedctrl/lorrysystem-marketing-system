import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
API_KEY = os.getenv("MARKETING_API_KEY")

if not API_KEY:
    print("ERROR: MARKETING_API_KEY is not set")
    sys.exit(1)


results = []


def request(method, path, headers=None, data=None):
    url = BASE_URL + path

    req_headers = {
        "Accept": "application/json",
    }

    if headers:
        req_headers.update(headers)

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body,
        headers=req_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

            return {
                "status": resp.status,
                "body": raw,
                "headers": dict(resp.headers),
                "error": None,
            }

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")

        return {
            "status": exc.code,
            "body": raw,
            "headers": dict(exc.headers),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": None,
            "body": "",
            "headers": {},
            "error": str(exc),
        }


def record(name, passed, status=None, detail=""):
    results.append(
        {
            "name": name,
            "passed": passed,
            "status": status,
            "detail": detail,
        }
    )

    icon = "PASS" if passed else "FAIL"

    status_text = ""
    if status is not None:
        status_text = f" [{status}]"

    print(f"{icon:<4} {name}{status_text}")

    if detail:
        print(f"     {detail}")


print()
print("=" * 72)
print("LORRYSYSTEM DEV API FULL SMOKE TEST")
print("=" * 72)
print(f"Target: {BASE_URL}")
print()


# ---------------------------------------------------------
# 1. Health
# ---------------------------------------------------------

health = request("GET", "/health")

record(
    "GET /health",
    health["status"] == 200,
    health["status"],
    health["error"] or health["body"][:200],
)


# ---------------------------------------------------------
# 2. OpenAPI
# ---------------------------------------------------------

openapi_response = request("GET", "/openapi.json")

openapi_ok = openapi_response["status"] == 200

record(
    "GET /openapi.json",
    openapi_ok,
    openapi_response["status"],
    openapi_response["error"] or "",
)

if not openapi_ok:
    print()
    print("Cannot continue endpoint discovery without OpenAPI.")
    sys.exit(1)

try:
    spec = json.loads(openapi_response["body"])
except Exception as exc:
    print(f"ERROR parsing OpenAPI JSON: {exc}")
    sys.exit(1)


paths = spec.get("paths", {})

print()
print(f"Discovered {len(paths)} API paths")


# ---------------------------------------------------------
# 3. Find a protected GET endpoint
# ---------------------------------------------------------

protected_test_path = None

for path, methods in paths.items():
    if not path.startswith("/api"):
        continue

    if "{" in path:
        continue

    if "get" in methods:
        protected_test_path = path
        break


if protected_test_path:
    print()
    print(f"Authentication test endpoint: {protected_test_path}")

    # No key
    no_key = request(
        "GET",
        protected_test_path,
    )

    record(
        f"Missing key → {protected_test_path}",
        no_key["status"] == 401,
        no_key["status"],
    )

    # Wrong key
    wrong_key = request(
        "GET",
        protected_test_path,
        headers={
            "X-API-Key": "definitely-wrong-key",
        },
    )

    record(
        f"Wrong key → {protected_test_path}",
        wrong_key["status"] == 401,
        wrong_key["status"],
    )

    # Correct key
    valid_key = request(
        "GET",
        protected_test_path,
        headers={
            "X-API-Key": API_KEY,
        },
    )

    record(
        f"Valid key → {protected_test_path}",
        valid_key["status"] is not None
        and valid_key["status"] != 401,
        valid_key["status"],
        valid_key["body"][:200],
    )

else:
    record(
        "Authentication endpoint discovery",
        False,
        detail="No protected GET endpoint found",
    )


# ---------------------------------------------------------
# 4. Enumerate all endpoints
# ---------------------------------------------------------

print()
print("=" * 72)
print("ENDPOINT INVENTORY")
print("=" * 72)

supported_methods = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
}

endpoint_inventory = []

for path, operations in sorted(paths.items()):
    for method, operation in operations.items():
        method_lower = method.lower()

        if method_lower not in supported_methods:
            continue

        endpoint_inventory.append(
            (
                method_lower.upper(),
                path,
                operation.get("summary", ""),
            )
        )

        print(
            f"{method_lower.upper():7} "
            f"{path:50} "
            f"{operation.get('summary', '')}"
        )


# ---------------------------------------------------------
# 5. Test safe GET endpoints
# ---------------------------------------------------------

print()
print("=" * 72)
print("SAFE GET TESTS")
print("=" * 72)

for path, operations in sorted(paths.items()):
    operation = operations.get("get")

    if not operation:
        continue

    if "{" in path:
        print(f"SKIP GET  {path} — requires path parameter")
        continue

    parameters = operation.get("parameters", [])

    required_query = []

    for parameter in parameters:
        if (
            parameter.get("in") == "query"
            and parameter.get("required") is True
        ):
            required_query.append(parameter.get("name"))

    if required_query:
        print(
            f"SKIP GET  {path} — required query parameter(s): "
            + ", ".join(required_query)
        )
        continue

    headers = {}

    if path.startswith("/api"):
        headers["X-API-Key"] = API_KEY

    response = request(
        "GET",
        path,
        headers=headers,
    )

    success = (
        response["status"] is not None
        and 200 <= response["status"] < 400
    )

    detail = response["error"] or response["body"][:300]

    record(
        f"GET {path}",
        success,
        response["status"],
        detail,
    )


# ---------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------

print()
print("=" * 72)
print("SUMMARY")
print("=" * 72)

passed = sum(1 for result in results if result["passed"])
failed = sum(1 for result in results if not result["passed"])
total = len(results)

print(f"Total tests : {total}")
print(f"Passed      : {passed}")
print(f"Failed      : {failed}")

print()
print(f"Discovered endpoints: {len(endpoint_inventory)}")

methods = {}

for method, path, summary in endpoint_inventory:
    methods[method] = methods.get(method, 0) + 1

for method in sorted(methods):
    print(f"{method:7}: {methods[method]}")

print()

if failed:
    print("RESULT: SOME TESTS FAILED")
    sys.exit(1)

print("RESULT: ALL EXECUTED TESTS PASSED")
