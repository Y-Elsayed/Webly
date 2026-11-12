"""Build and verify released wheels in an isolated, temporary environment.

Run from any directory: python scripts/verify_core_package.py
Requires pip, setuptools and wheel in the invoking environment. Dependencies are
resolved from the configured pip index; WebCreeper itself comes from the pinned
submodule. No provider requests or public package publication occur.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path
from xml.etree import ElementTree

CRAWLER_COMMIT = "8db4429e0a2b964eca634beed249a833e8934bb0"
ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def inspect_wheel(wheel):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        forbidden = {"websites_storage", "webcreeper", ".env", "issue.md", "tests", "scripts", "docs"}
        for name in names:
            assert not forbidden.intersection(Path(name).parts), f"Unexpected wheel file: {name}"
            assert not any(part.startswith(".env.") or part.endswith(".local.md") for part in Path(name).parts), name
            assert name.startswith(("webly/", "webly-")), f"Unexpected top-level package: {name}"
        metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode()
        assert "Requires-Dist: webcreeper==0.2.0" in metadata
        for prompt in ("context_builder_agent.txt", "webly_chat_agent_system.txt"):
            assert f"webly/chatbot/prompts/{prompt}" in names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="Retain wheels, environment and report in an empty directory")
    parser.add_argument(
        "--extras", action="store_true", help="Also install/test API and UI extras separately from Core"
    )
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="webly-package-verification-") if args.work_dir is None else None
    work = Path(temporary.name if temporary else args.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise ValueError("Verification work directory must be empty")
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT / "webcreeper"), "rev-parse", "HEAD"], text=True
        ).strip()
        if commit != CRAWLER_COMMIT:
            raise ValueError(f"Update the reviewed crawler pin before building: {commit}")
        dirty = subprocess.check_output(
            ["git", "-C", str(ROOT / "webcreeper"), "status", "--porcelain", "--untracked-files=no"], text=True
        )
        if dirty.strip():
            raise ValueError("Crawler checkout is dirty; verification requires the exact pinned source")
        wheels = work / "wheels"
        wheels.mkdir()
        # Build the exact crawler commit, excluding local build output/untracked
        # files, and stage Core without stale build/lib files or client data.
        crawler_source = work / "crawler-source"
        crawler_source.mkdir()
        crawler_archive = work / "crawler.zip"
        crawler_archive.write_bytes(
            subprocess.check_output(["git", "-C", str(ROOT / "webcreeper"), "archive", "--format=zip", "HEAD"])
        )
        with zipfile.ZipFile(crawler_archive) as archive:
            archive.extractall(crawler_source)
        core_source = work / "core-source"
        core_source.mkdir()
        for name in ("pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "NOTICE"):
            shutil.copy2(ROOT / name, core_source / name)
        shutil.copytree(
            ROOT / "webly",
            core_source / "webly",
            ignore=shutil.ignore_patterns(
                "websites_storage",
                "webcreeper",
                "__pycache__",
                "*.pyc",
                "*.log",
                ".env",
                ".env.*",
            ),
        )
        for source in (crawler_source, core_source):
            run(
                sys.executable,
                "-m",
                "pip",
                "wheel",
                source,
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                wheels,
                cwd=work,
            )
        wheel = next(wheels.glob("webly-*.whl"))
        inspect_wheel(wheel)
        environment = work / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY"):
            env.pop(key, None)
        crawler_wheel = next(wheels.glob("webcreeper-*.whl"))
        run(python, "-m", "pip", "install", "--find-links", wheels, crawler_wheel, wheel, cwd=work, env=env)
        run(python, "-m", "pip", "check", cwd=work, env=env)
        run(python, "-I", ROOT / "scripts/core_package_smoke.py", cwd=work, env=env)
        core_dependencies = subprocess.check_output(
            [str(python), "-m", "pip", "list", "--format=freeze"], cwd=work, env=env, text=True
        ).splitlines()
        service_test_count = 0
        if args.extras:
            # Core-only smoke already passed; only now allow adapter dependencies.
            run(
                python,
                "-m",
                "pip",
                "install",
                "--find-links",
                wheels,
                f"{wheel}[api,ui]",
                "httpx",
                "pytest",
                cwd=work,
                env=env,
            )
            run(python, "-m", "pip", "check", cwd=work, env=env)
            run(python, "-I", ROOT / "scripts/adapter_package_smoke.py", cwd=work, env=env)
            service_tests = work / "adapter-tests"
            service_tests.mkdir()
            for test in (ROOT / "tests").glob("test_service*.py"):
                shutil.copy2(test, service_tests / test.name)
            # Copy tests alone, without checkout conftest/sys.path changes.
            junit = work / "service-tests.xml"
            run(python, "-I", "-m", "pytest", service_tests, "-q", "-rA", f"--junitxml={junit}", cwd=work, env=env)
            cases = ElementTree.parse(junit).findall(".//testcase")
            assert cases and all(case.find("skipped") is None for case in cases), "Service tests must run without skips"
            service_test_count = len(cases)
        freeze = subprocess.check_output(
            [str(python), "-m", "pip", "list", "--format=freeze"], cwd=work, env=env, text=True
        )
        report = {
            "python": sys.version,
            "crawler_commit": commit,
            "core_contract": "passed",
            "adapter_checks": "passed" if args.extras else "not_requested",
            "service_tests_passed": service_test_count,
            "wheels": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in wheels.glob("*.whl")},
            "core_dependencies": core_dependencies,
            "resolved_dependencies": freeze.splitlines(),
        }
        (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Package verification passed. Evidence: {work / 'verification.json'}", flush=True)
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
