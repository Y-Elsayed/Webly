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

CRAWLER_VERSION = "0.3.0"
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
        assert f"Requires-Dist: webcreeper=={CRAWLER_VERSION}" in metadata
        for prompt in ("context_builder_agent.txt", "webly_chat_agent_system.txt"):
            assert f"webly/chatbot/prompts/{prompt}" in names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="Retain wheels, environment and report in an empty directory")
    parser.add_argument(
        "--extras", action="store_true", help="Also install/test API and UI extras separately from Core"
    )
    parser.add_argument("--allow-dirty", action="store_true", help="Development builds only; cannot certify a release")
    parser.add_argument("--audit", action="store_true", help="Capture runtime profiles, advisory inventories and locks")
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
        expected = subprocess.check_output(["git", "ls-tree", "HEAD", "webcreeper"], cwd=ROOT, text=True).split()[2]
        if commit != expected and not args.allow_dirty:
            raise ValueError("Crawler commit differs from the reviewed submodule pointer")
        dirty = subprocess.check_output(
            ["git", "-C", str(ROOT / "webcreeper"), "status", "--porcelain", "--untracked-files=normal"], text=True
        )
        if dirty.strip() and not args.allow_dirty:
            raise ValueError("Crawler checkout is dirty; verification requires the exact pinned source")
        core_dirty = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                "webly",
                "pyproject.toml",
                "MANIFEST.in",
                "README.md",
                "LICENSE",
                "NOTICE",
            ],
            cwd=ROOT,
            text=True,
        )
        if core_dirty.strip() and not args.allow_dirty:
            raise ValueError("Core source is dirty; use --allow-dirty only for development verification")
        wheels = work / "wheels"
        wheels.mkdir()
        # Build the exact crawler commit, excluding local build output/untracked
        # files, and stage Core without stale build/lib files or client data.
        crawler_source = work / "crawler-source"
        crawler_source.mkdir()
        if args.allow_dirty:
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                shutil.copy2(ROOT / "webcreeper" / name, crawler_source / name)
            shutil.copytree(
                ROOT / "webcreeper" / "webcreeper",
                crawler_source / "webcreeper",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", ".env", ".env.*"),
            )
        else:
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
        profiles = work / "profiles"
        profiles.mkdir()
        run(
            python,
            "-I",
            ROOT / "scripts/profile_dependencies.py",
            "--output",
            profiles / "core.json",
            cwd=work,
            env=env,
        )
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
            run(
                python,
                "-I",
                ROOT / "scripts/profile_dependencies.py",
                "--extras",
                "api,ui",
                "--output",
                profiles / "api-ui.json",
                cwd=work,
                env=env,
            )
        freeze = subprocess.check_output(
            [str(python), "-m", "pip", "list", "--format=freeze"], cwd=work, env=env, text=True
        )
        report = {
            "release_ready": False,
            "artifact_checks_passed": True,
            "source_clean": not (dirty.strip() or core_dirty.strip()),
            "remaining_release_gates": ["source_review", "dependency_triage", "human_and_live_quality_evaluation"],
            "python": sys.version,
            "crawler_commit": commit,
            "crawler_dirty": bool(dirty.strip()),
            "source_digests": {
                directory.name: hashlib.sha256(
                    b"".join(
                        str(file.relative_to(directory)).replace("\\", "/").encode() + file.read_bytes()
                        for file in sorted(directory.rglob("*"))
                        if file.is_file()
                        and "build" not in file.parts
                        and not any(part.endswith(".egg-info") for part in file.parts)
                    )
                ).hexdigest()
                for directory in (core_source, crawler_source)
            },
            "core_contract": "passed",
            "adapter_checks": "passed" if args.extras else "not_requested",
            "service_tests_passed": service_test_count,
            "wheels": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in wheels.glob("*.whl")},
            "core_dependencies": core_dependencies,
            "resolved_dependencies": freeze.splitlines(),
        }
        (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if args.audit:
            for profile in list(profiles.glob("*.json")):
                run(
                    sys.executable,
                    ROOT / "scripts/inspect_release.py",
                    profile,
                    "--output",
                    profiles / (profile.stem + "-audit.json"),
                    "--lock",
                    profiles / (profile.stem + ".txt"),
                    "--fail-on-findings",
                    cwd=work,
                    env=env,
                )
        print(f"Package verification passed. Evidence: {work / 'verification.json'}", flush=True)
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
