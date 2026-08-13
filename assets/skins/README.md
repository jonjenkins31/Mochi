# Popup player skins

Each skin owns a `skin.yaml` with the bezel image and the rectangle where the
live character frame is painted. Add another folder here to make it appear in
the Popup Player Settings window; no Python or manifest edit is required.

```yaml
schema: mochi/player-skin/v1
id: example
name: Example
image: assets/skins/example/body.png
screen_bbox: [left, top, width, height]
```
