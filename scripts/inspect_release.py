"""Audit a resolved profile against PyPI metadata and write a platform-specific version lock.

No claim of exploitability or license approval is inferred from this inventory.
Unknown scan results and unpublished local packages remain explicitly recorded.
"""

import argparse
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def inspect(package):
    name, version = package
    if name in {"webly", "webcreeper"}:
        return {"name": name, "version": version, "status": "local_review_required", "advisories": []}
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
        advisories = []
        identities = set()
        for item in data.get("vulnerabilities", []):
            aliases = {item.get("id"), *item.get("aliases", [])} - {None}
            if item.get("withdrawn") or identities.intersection(aliases):
                continue
            identities.update(aliases)
            advisories.append(
                {
                    "id": item.get("id"),
                    "aliases": sorted(aliases),
                    "fixed_in": item.get("fixed_in"),
                    "link": item.get("link"),
                }
            )
        info = data["info"]
        return {
            "name": name,
            "version": version,
            "status": "checked",
            "source": url,
            "license_expression": info.get("license_expression"),
            "license_classifiers": [c for c in info.get("classifiers", []) if c.startswith("License ::")],
            "advisories": advisories,
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"name": name, "version": version, "status": "unknown", "error": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        packages = list(pool.map(inspect, sorted(profile["packages"].items())))
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "packages": packages,
        "advisory_records": sum(len(p.get("advisories", [])) for p in packages),
        "unknown_packages": [p["name"] for p in packages if p["status"] == "unknown"],
        "release_ready": False,
        "limitations": "PyPI advisory metadata only; local source review, exploitability/license triage, "
        "container scanning and real-model evaluation remain separate release gates.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    lock = [
        "# Generated resolved profile: " + profile["platform"],
        "# Python: " + profile["python"],
        ("# Extras: " + ",".join(profile["extras"])).rstrip(),
        "# Install reviewed webly/webcreeper wheels explicitly; use this lock as constraints.",
        *[f"{name}=={version}" for name, version in sorted(profile["packages"].items())],
    ]
    args.lock.write_text("\n".join(lock) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"packages", "profile"}}, indent=2))
    if args.fail_on_findings and (report["advisory_records"] or report["unknown_packages"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
