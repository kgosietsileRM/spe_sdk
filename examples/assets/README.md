# Demo assets

- `link.json` maps media keys to local files or a remote URL.
- `spe_sdk-0.1.0-py3-none-any.whl` is the built SDK wheel installed by each demo.
- `trafic-r.mp4` (640x360) and `trafic.mp4` (1920x1080) are local sample clips
  and are gitignored because of their size.
- Remote media downloaded by the demos is cached in `.cache/`.

Rebuild the wheel from the repository root before refreshing the copy here:

```powershell
python -m build
Copy-Item dist\spe_sdk-0.1.0-py3-none-any.whl examples\assets\ -Force
```
