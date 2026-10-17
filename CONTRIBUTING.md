# Contributing

Thanks for your interest in improving the SPE SDK.

## Development setup

```console
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

python -m pip install -e ".[dev]"
```

`numpy` and `opencv-python` are installed as runtime dependencies; the dev extra
adds `pytest`, `pytest-cov`, `ruff`, `mypy`, `build`, and `twine`.

## Quality gates

Run the full suite before opening a pull request:

```console
ruff check .
ruff format --check .
mypy
pytest --cov=spe --cov-report=term-missing
```

- **Lint/format**: [ruff](https://docs.astral.sh/ruff/) (config in
  `pyproject.toml`). Run `ruff check --fix .` and `ruff format .` to autofix.
- **Types**: [mypy](https://mypy.readthedocs.io/) in strict-ish mode. All
  public functions must be fully annotated.
- **Tests**: [pytest](https://docs.pytest.org/). Coverage must stay at or above
  90%.

Pre-commit hooks are provided; enable them once:

```console
pre-commit install
```

## Guidelines

- Keep the local core dependency-light: only `numpy` and `opencv-python`.
- Keep behaviour faithful to the engine's coordinate contract
  (`source_pixels` → `calibrated_reference_plane`, point order
  `top_left, top_right, bottom_right, bottom_left`).
- Add tests for new behaviour and update `CHANGELOG.md` under `Unreleased`.
- Write [Google-style docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
  for public APIs.

## Releasing

1. Bump `__version__` in `src/spe/_version.py`.
2. Move the `Unreleased` changelog entries under the new version.
3. Tag and push: `git tag v0.1.1 && git push origin v0.1.1`.
   The release workflow builds, checks, and publishes to PyPI.
