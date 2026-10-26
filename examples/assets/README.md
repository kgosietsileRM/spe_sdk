# Demo assets

- `link.json` maps each demo's camera and recorded-clip keys to local files or
  remote URLs. The current camera feeds are remote sources.
- Each standalone example installs `spe-engine==0.2.1` from PyPI in its own
  virtual environment; no SDK wheel is required in this folder.
- Remote media downloaded by the demos is cached in `.cache/`.
