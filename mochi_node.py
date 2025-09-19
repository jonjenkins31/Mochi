# mochi_node.py
import time, math, random, struct, threading, signal, argparse, logging, json, zmq

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"
HEALTH_TOPIC = b"health"

# Defaults (can be overridden by CLI or ctrl commands)
DEFAULT_W, DEFAULT_H = 64, 64
DEFAULT_FPS = 60
PUB_ADDR = "tcp://127.0.0.1:5555"   # frames out
CTRL_ADDR = "tcp://127.0.0.1:5556"  # control in (SUB)

shutdown_evt = threading.Event()

ctx = zmq.Context.instance()

# Animation plugin system
from animations import create as create_anim, list_names as list_anims

# Current animation instance and mode name are stored globally
anim = None
current_mode = None

# --- Reusable buffers to avoid per-frame allocations ---
packet_buf = None  # HEADER + payload (kept as a single blob to keep protocol unchanged)
pixel_buf = None   # payload-only RGB buffer (w*h*3)

def _ensure_buffers(w: int, h: int):
    """Ensure pixel/packet buffers match (w,h)."""
    global packet_buf, pixel_buf
    need = int(w) * int(h) * 3
    if pixel_buf is None or len(pixel_buf) != need:
        pixel_buf = bytearray(need)
    # keep protocol as [topic, header+payload] to avoid changing viewers
    total = HEADER_SIZE + need
    if packet_buf is None or len(packet_buf) != total:
        packet_buf = bytearray(total)

def pack_frame_into(buf: bytearray, w: int, h: int, seq: int, pixels_rgb_bytes: memoryview | bytes | bytearray):
    """Pack header + pixels into preallocated `buf` in-place."""
    ts_ms = int(time.time() * 1000)
    # header
    struct.pack_into(HEADER_FMT, buf, 0, int(w), int(h), int(ts_ms), int(seq))
    # payload
    mv = pixels_rgb_bytes if isinstance(pixels_rgb_bytes, memoryview) else memoryview(pixels_rgb_bytes)
    buf[HEADER_SIZE:HEADER_SIZE+len(mv)] = mv
    return buf

# --- Simple timeline script engine ---
current_script = None
script_start_t = None
script_idx = 0

def _load_script(path: str):
    with open(path, "r") as f:
        data = json.load(f)
    if "timeline" not in data or not isinstance(data["timeline"], list):
        raise ValueError("script missing 'timeline' list")
    # normalize & sort by 'at'
    tl = []
    for step in data["timeline"]:
        at = float(step.get("at", 0.0))
        cmd = str(step.get("cmd", "")).lower()
        args = step.get("args", {}) or {}
        tl.append({"at": at, "cmd": cmd, "args": args})
    tl.sort(key=lambda s: s["at"])
    data["timeline"] = tl
    return data

def start_script(path: str):
    global current_script, script_start_t, script_idx
    current_script = _load_script(path)
    script_start_t = time.time()
    script_idx = 0
    print(f"[SCRIPT] started '{path}' with {len(current_script['timeline'])} steps")

def stop_script():
    global current_script
    if current_script is not None:
        print("[SCRIPT] stopped")
    current_script = None

def run_script_if_due(now: float):
    global script_idx, anim, current_script, current_mode
    if not current_script:
        return
    elapsed = now - script_start_t
    tl = current_script["timeline"]
    while script_idx < len(tl) and elapsed >= tl[script_idx]["at"]:
        step = tl[script_idx]
        script_idx += 1
        cmd = step["cmd"]
        args = step.get("args", {})
        if cmd == "mode":
            name = args.get("name")
            if not name:
                print("[SCRIPT] mode step missing 'name'")
                continue
            fg = args.get("fg")
            try:
                new = create_anim(name, anim.w, anim.h, fg=fg)
                anim = new
                current_mode = name
                print(f"[SCRIPT] mode -> {name}")
            except Exception as e:
                print(f"[SCRIPT] mode error: {e}")
        elif cmd == "event":
            ev = args.get("name")
            kwargs = {k: v for k, v in args.items() if k != "name"}
            try:
                anim.on_event(ev, **kwargs)
                print(f"[SCRIPT] event -> {ev} {kwargs if kwargs else ''}")
            except Exception as e:
                print(f"[SCRIPT] event error: {e}")
        elif cmd == "stop":
            stop_script()
        else:
            print(f"[SCRIPT] unknown cmd '{cmd}'")

def control_loop():
    sub = ctx.socket(zmq.SUB)
    sub.connect(CTRL_ADDR)
    sub.setsockopt_string(zmq.SUBSCRIBE, CTRL_TOPIC)
    print(f"[MochiNode] Control subscriber connected -> {CTRL_ADDR}, topic='{CTRL_TOPIC}'")
    while not shutdown_evt.is_set():
        topic, msg = sub.recv_multipart()
        try:
            parts = msg.decode().strip().split()
            if not parts:
                continue
            cmd = parts[0].lower()
            if cmd in ("idle", "bars", "rainbow") and len(parts) == 1:
                # Back-compat: treat bare mode names as `mode <name>`
                try:
                    new = create_anim(cmd, anim.w, anim.h)
                    globals()["anim"] = new
                    globals()["current_mode"] = cmd
                except Exception as e:
                    print(f"[CTRL] unknown mode '{cmd}': {e}")
            elif cmd == "mode" and len(parts) >= 2:
                name = parts[1]
                try:
                    new = create_anim(name, anim.w, anim.h)
                    globals()["anim"] = new
                    globals()["current_mode"] = name
                    print(f"[CTRL] mode -> {name}")
                except Exception as e:
                    print(f"[CTRL] mode error: {e}")
                    print("[CTRL] available:", ", ".join(list_anims()))
            elif cmd == "color" and len(parts) == 4:
                r, g, b = map(int, parts[1:])
                try:
                    anim.set_color(r, g, b)
                except Exception as e:
                    print(f"[CTRL] color not supported by current animation: {e}")
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                w_i, h_i = int(w_str), int(h_str)
                try:
                    anim.set_size(w_i, h_i)
                except Exception:
                    pass
                print(f"[CTRL] resized to {w_i}x{h_i}")
            elif cmd in ("modes", "anims", "animations"):
                print("[CTRL] modes:", ", ".join(list_anims()))
            elif cmd == "play" and len(parts) >= 2:
                path = " ".join(parts[1:])
                try:
                    start_script(path)
                except Exception as e:
                    print(f"[CTRL] play error: {e}")
            elif cmd == "stop":
                stop_script()
            elif cmd == "event" and len(parts) >= 2:
                ev = parts[1]
                kwargs = {}
                for token in parts[2:]:
                    if "=" in token:
                        k, v = token.split("=", 1)
                        try:
                            if "." in v:
                                v = float(v)
                            else:
                                v = int(v)
                        except Exception:
                            pass
                        kwargs[k] = v
                try:
                    anim.on_event(ev, **kwargs)
                except Exception as e:
                    print(f"[CTRL] event error: {e}")
            elif cmd == "quit":
                print("[CTRL] quit received")
                shutdown_evt.set()
            else:
                print("[CTRL] unknown:", msg.decode())
        except Exception as e:
            print("CTRL parse error:", e)

def parse_args():
    p = argparse.ArgumentParser(description="Mochi node (ZeroMQ PUB/SUB)")
    p.add_argument("--size", default=f"{DEFAULT_W}x{DEFAULT_H}", help=f"matrix WxH, default {DEFAULT_W}x{DEFAULT_H}")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="frames per second")
    p.add_argument("--pub", default=PUB_ADDR, help="PUB address for frames")
    p.add_argument("--ctrl", default=CTRL_ADDR, help="SUB address for control")
    p.add_argument("--mode", default="idle", help="initial mode (one of: " + ", ".join(list_anims()) + ")")
    return p.parse_args()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def main():
    args = parse_args()
    try:
        w_str, h_str = args.size.lower().split("x", 1)
        w, h = int(w_str), int(h_str)
    except Exception:
        w, h = DEFAULT_W, DEFAULT_H
    fps = max(1, int(args.fps))

    global CTRL_ADDR
    CTRL_ADDR = args.ctrl

    # Signal handlers for graceful shutdown
    def _sig_handler(signum, frame):
        shutdown_evt.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _sig_handler)
        except Exception:
            pass

    # Start control thread
    threading.Thread(target=control_loop, daemon=True).start()

    # Publisher
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.setsockopt(zmq.SNDHWM, 2)  # keep last few frames only
    pub.bind(args.pub)
    time.sleep(0.1)
    print(f"[MochiNode] Frame publisher bound -> {args.pub}; FPS={fps}; matrix={w}x{h}")
    print("[MochiNode] ctrl SUB ->", args.ctrl)
    print("[MochiNode] Commands: mode <name> | color R G B | size WxH | modes | play <script.json> | stop | event <name> [k=v...] | quit")
    print("[MochiNode] Available modes:", ", ".join(list_anims()))

    # Animator (plugin-based)
    global anim, current_mode
    try:
        anim = create_anim(args.mode, w, h)
        current_mode = args.mode
    except Exception as e:
        names = list_anims()
        fallback = names[0] if names else "bars"
        print(f"[MochiNode] unknown mode '{args.mode}' ({e}); falling back to '{fallback}'")
        anim = create_anim(fallback, w, h)
        current_mode = fallback

    seq = 0
    clock = time.perf_counter
    next_frame = clock()
    dt = 1.0 / float(fps)
    last_health = 0.0
    try:
        while not shutdown_evt.is_set():
            now = clock()
            if now < next_frame:
                time.sleep(max(0.0, next_frame - now))
                now = clock()
            # Run due script steps before rendering
            run_script_if_due(time.time())  # keep wall-clock for scripts/events

            # Ensure buffers match current animation size
            _ensure_buffers(anim.w, anim.h)

            # Render into a reusable pixel buffer if supported
            try:
                render_into = getattr(anim, "render_into", None)
                if callable(render_into):
                    render_into(time.time(), pixel_buf)
                    payload_mv = memoryview(pixel_buf)
                else:
                    frame_bytes = anim.frame(time.time())
                    if not isinstance(frame_bytes, (bytes, bytearray, memoryview)):
                        raise TypeError("anim.frame() must return bytes-like")
                    fb_mv = frame_bytes if isinstance(frame_bytes, memoryview) else memoryview(frame_bytes)
                    # If size changed under us, resize buffers and try to place
                    if len(fb_mv) != len(pixel_buf):
                        _ensure_buffers(anim.w, anim.h)
                    pixel_buf[:len(fb_mv)] = fb_mv
                    payload_mv = memoryview(pixel_buf)
            except Exception as e:
                print(f"[MochiNode] frame() error from '{current_mode}': {e}")
                try:
                    anim = create_anim("bars", anim.w, anim.h)
                    current_mode = "bars"
                    # render bars once to keep stream alive
                    frame_bytes = anim.frame(time.time())
                    fb_mv = frame_bytes if isinstance(frame_bytes, memoryview) else memoryview(frame_bytes)
                    _ensure_buffers(anim.w, anim.h)
                    pixel_buf[:len(fb_mv)] = fb_mv
                    payload_mv = memoryview(pixel_buf)
                    print("[MochiNode] fell back to 'bars'")
                except Exception as e2:
                    print(f"[MochiNode] fallback error: {e2}")
                    # send a blank frame
                    _ensure_buffers(anim.w, anim.h)
                    for i in range(0, len(pixel_buf), 3):
                        pixel_buf[i:i+3] = b"\x00\x00\x00"
                    payload_mv = memoryview(pixel_buf)

            # Pack header+payload into preallocated packet buffer
            pack_frame_into(packet_buf, anim.w, anim.h, seq, payload_mv)
            # Publish as a single blob to keep viewer compatibility
            pub.send_multipart([FRAME_TOPIC, packet_buf], copy=False)

            # Periodic health heartbeat (1 Hz)
            wall_now = time.time()
            if wall_now - last_health >= 1.0:
                try:
                    hb = {
                        "ts": int(wall_now * 1000),
                        "seq": int(seq),
                        "w": int(anim.w),
                        "h": int(anim.h),
                        "fps": fps,
                        "mode": current_mode or "?",
                    }
                    pub.send_multipart([HEALTH_TOPIC, json.dumps(hb).encode("utf-8")])
                except Exception:
                    pass
                last_health = wall_now

            seq += 1
            next_frame += dt
    finally:
        try:
            pub.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
