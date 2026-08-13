# Bitmap Man

Monochrome eye character imported from the legacy `2.json` animation map and
`eye_sprites.json` unpacked sprite collection.

`character.yaml` exposes six playable expressions. The generated bitmap files
under `assets/faces/` use the packed format consumed by Jaeger's bitmap
adapter. Rebuild them after changing either legacy source file with:

```bash
python3 dev/tools/build_bitmap_man_assets.py
```
