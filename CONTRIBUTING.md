# Contributing

1. Keep pull requests small and focused.
2. Add or update tests for behavior changes.
3. Run before opening a PR:
```bash
git submodule update --init --recursive
pip install -r requirements-dev.txt
pytest
ruff check .
```
4. In your PR, include scope, rationale, and validation notes.

For packaging changes, run `python scripts/verify_core_package.py --extras`.
This builds Core and its pinned WebCreeper dependency and checks installed wheels
outside the checkout. See [Core integration](docs/CORE_INTEGRATION.md).

