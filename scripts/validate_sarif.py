"""Validate a SARIF file against the vendored SARIF 2.1.0 JSON schema.

Replaces @microsoft/sarif-multitool in CI: the npm wrapper crashes on Linux
(single-file exe with empty Assembly.Location) and the dotnet tool build
targets .NET Core 3.1, which no longer ships on Ubuntu 24.04 runners.
Schema vendored at security/sarif-schema-2.1.0.json (json.schemastore.org,
mirroring the OASIS sarif-spec repository).

Usage: python scripts/validate_sarif.py <file.sarif> [<file2.sarif> ...]
"""

import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "security" / "sarif-schema-2.1.0.json"


def main(paths: list[str]) -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    failures = 0
    for path in paths:
        doc = json.loads(Path(path).read_text())
        try:
            jsonschema.validate(doc, schema)
        except jsonschema.ValidationError as err:
            failures += 1
            location = "/".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"INVALID {path}: at {location}: {err.message}")
        else:
            runs = len(doc.get("runs", []))
            results = sum(len(r.get("results", [])) for r in doc.get("runs", []))
            print(f"VALID {path}: SARIF {doc.get('version')}, {runs} run(s), {results} result(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
