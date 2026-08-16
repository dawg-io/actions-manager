#!/usr/bin/env python3
"""
Validate CycloneDX SBOMs, and fail when there is nothing worth validating.

Replaces `cyclonedx-py validate --input-file ...`, which never worked: the
cyclonedx-bom package only *generates* SBOMs, so that invocation always exited
with "invalid choice: 'validate'". Paired with `|| true` in the workflow, it
meant Verify SBOM Quality had never validated anything.

The real validator lives in cyclonedx-python-lib, which cyclonedx-bom already
depends on - so this adds no dependency.

Checks, per file:
  * parses as JSON
  * carries a recognised CycloneDX specVersion
  * passes strict schema validation for that version
  * lists at least one component (a broken generation still validates cleanly,
    which is the failure actually worth catching)

Usage: python3 validate_sbom.py sbom-*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from cyclonedx.schema import SchemaVersion
    from cyclonedx.validation.json import JsonStrictValidator
except ImportError:
    print(
        "::error::cyclonedx-python-lib is not installed - cannot validate SBOMs",
        file=sys.stderr,
    )
    sys.exit(1)


def _schema_version(spec: str) -> "SchemaVersion | None":
    # "1.6" -> SchemaVersion.V1_6
    try:
        return SchemaVersion["V" + spec.replace(".", "_")]
    except KeyError:
        return None


def validate(path: Path) -> list[str]:
    problems: list[str] = []
    raw = path.read_text()

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"{path.name} is not valid JSON: {exc}"]

    spec = str(doc.get("specVersion", "")).strip()
    if not spec:
        return [f"{path.name} has no specVersion - not a CycloneDX document"]

    version = _schema_version(spec)
    if version is None:
        return [f"{path.name} declares unknown CycloneDX specVersion {spec!r}"]

    error = JsonStrictValidator(version).validate_str(raw)
    if error is not None:
        problems.append(f"{path.name} failed CycloneDX {spec} schema validation: {error}")

    components = doc.get("components") or []
    if len(components) == 0:
        problems.append(
            f"{path.name} lists 0 components - generation did not capture the "
            "dependency tree"
        )
    else:
        print(f"  {path.name}: CycloneDX {spec}, {len(components)} components")

    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv if Path(a).is_file()]

    # An empty glob used to pass silently - `[ -e "$sbom" ] || continue` over
    # zero matches validated nothing and exited 0.
    if not paths:
        print(
            "::error::No SBOM files to validate - generation produced nothing",
            file=sys.stderr,
        )
        return 1

    print(f"Validating {len(paths)} SBOM file(s):")
    problems: list[str] = []
    for path in sorted(paths):
        problems.extend(validate(path))

    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1

    print("OK: all SBOMs valid and non-empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
