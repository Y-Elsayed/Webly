"""Capture the installed runtime dependency closure for one extras/platform profile."""

import argparse
import importlib.metadata as metadata
import json
import platform
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def profile(extras=()):
    pending = [("webly", set(extras))]
    expanded = {}
    selected = {}
    environment = default_environment()
    while pending:
        name, wanted_extras = pending.pop()
        name = canonicalize_name(name)
        if name in expanded and wanted_extras <= expanded[name]:
            continue
        active = wanted_extras | expanded.get(name, set())
        expanded[name] = active
        distribution = metadata.distribution(name)
        selected[name] = distribution.version
        for raw in distribution.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or any(
                requirement.marker.evaluate({**environment, "extra": extra}) for extra in {"", *active}
            ):
                pending.append((requirement.name, set(requirement.extras)))
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "extras": sorted(extras),
        "packages": selected,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extras", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(profile(set(filter(None, args.extras.split(",")))), indent=2), encoding="utf-8")
