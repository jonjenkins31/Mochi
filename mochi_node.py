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

def pack_frame(w, h, seq, pixels_rgb_bytes):
    ts_ms = int(time.time() * 1000)
    header = struct.pack(HEADER_FMT, w, h, ts_ms, seq)
    return header + pixels_rgb_bytes

# Current animation instance and mode name are stored globally
anim = None
current_mode = None

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
            elif cmd == "quit":
                print("[CTRL] quit received")
                shutdown_evt.set()
            else:
                print("[CTRL] unknown:", msg.decode())
            print("[CTRL]", msg.decode())
        except Exception as e:
            print("CTRL parse error:", e)

def parse_args():
    p = argparse.ArgumentParser(description="Mochi node (ZeroMQ PUB/SUB)")
    p.add_argument("--size", default=f"{DEFAULT_W}x{DEFAULT_H}", help=f"matrix WxH, default {DEFAULT_W}x{DEFAULT_H}")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="frames per second")
    p.add_argument("--pub", default=PUB_ADDR, help="PUB address for frames")
    p.add_argument("--ctrl", default=CTRL_ADDR, help="SUB address for control")
    p.add_argument("--mode", default="bars", help="initial mode (one of: " + ", ".join(list_anims()) + ")")
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
    print("[MochiNode] Commands: mode <name> | color R G B | size WxH | modes | quit")
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
    next_frame = time.time()
    dt = 1.0 / float(fps)
    last_health = 0.0
    try:
        while not shutdown_evt.is_set():
            now = time.time()
            if now < next_frame:
                time.sleep(next_frame - now)
            t = time.time()
            payload = anim.frame(t)
            packet = pack_frame(anim.w, anim.h, seq, payload)
            pub.send_multipart([FRAME_TOPIC, packet])
            # Periodic health heartbeat (1 Hz)
            if now - last_health >= 1.0:
                try:
                    hb = {
                        "ts": int(time.time() * 1000),
                        "seq": int(seq),
                        "w": int(anim.w),
                        "h": int(anim.h),
                        "fps": fps,
                        "mode": current_mode or "?",
                    }
                    pub.send_multipart([HEALTH_TOPIC, json.dumps(hb).encode("utf-8")])
                except Exception as _e:
                    pass
                last_health = now
            seq += 1
            next_frame += dt
    finally:
        try:
            pub.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
