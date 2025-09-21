# mochi_node.py
import time, math, random, struct, threading, signal, logging, json, zmq, yaml, sys, os
import psutil

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"
HEALTH_TOPIC = b"health"

shutdown_evt = threading.Event()

ctx = zmq.Context.instance()

# Animation plugin system
from animations import create as create_anim, list_names as list_anims

# --- Node State ---
class NodeState:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.anim = None
        self.current_mode = None

node_state = NodeState(64, 64) # Default, will be overwritten by config

# --- Reusable buffers ---
packet_buf = None
pixel_buf = None

def _ensure_buffers(w: int, h: int):
    global packet_buf, pixel_buf
    need = int(w) * int(h) * 3
    if pixel_buf is None or len(pixel_buf) != need:
        pixel_buf = bytearray(need)
    total = HEADER_SIZE + need
    if packet_buf is None or len(packet_buf) != total:
        packet_buf = bytearray(total)

def pack_frame_into(buf: bytearray, w: int, h: int, seq: int, pixels_rgb_bytes: memoryview | bytes | bytearray):
    ts_ms = int(time.time() * 1000)
    struct.pack_into(HEADER_FMT, buf, 0, int(w), int(h), int(ts_ms), int(seq))
    mv = pixels_rgb_bytes if isinstance(pixels_rgb_bytes, memoryview) else memoryview(pixels_rgb_bytes)
    buf[HEADER_SIZE:HEADER_SIZE+len(mv)] = mv
    return buf

# --- Script Engine ---
current_script = None
script_start_t = None
script_idx = 0

def _load_script(path: str):
    with open(path, "r") as f: data = json.load(f)
    if "timeline" not in data: raise ValueError("script missing 'timeline' list")
    tl = sorted(data["timeline"], key=lambda s: float(s.get("at", 0.0)))
    data["timeline"] = tl
    return data

def start_script(path: str, logger):
    global current_script, script_start_t, script_idx
    try:
        current_script = _load_script(path)
        script_start_t = time.time()
        script_idx = 0
        logger.info(f"Started script '{path}' with {len(current_script['timeline'])} steps")
    except Exception as e:
        logger.error(f"Failed to start script '{path}': {e}")
        current_script = None

def stop_script(logger):
    global current_script
    if current_script is not None: logger.info("Script stopped")
    current_script = None

def run_script_if_due(now: float, logger):
    global script_idx, current_script
    if not current_script: return
    elapsed = now - script_start_t
    tl = current_script["timeline"]
    while script_idx < len(tl) and elapsed >= tl[script_idx]["at"]:
        step = tl[script_idx]
        script_idx += 1
        cmd, args = step["cmd"].lower(), step.get("args", {})
        try:
            if cmd == "mode":
                name = args.get("name")
                if not name: logger.warning("Script: mode step missing 'name'"); continue
                kwargs = {k: v for k, v in args.items() if k != "name"}
                new = create_anim(name, node_state.w, node_state.h, **kwargs)
                node_state.anim, node_state.current_mode = new, name
                logger.info(f"Script: mode -> {name} with args {kwargs}")
            elif cmd == "event":
                ev_name = args.get("name")
                if not ev_name: logger.warning("Script: event step missing 'name'"); continue
                kwargs = {k: v for k, v in args.items() if k != "name"}
                if node_state.anim: node_state.anim.on_event(ev_name, **kwargs)
                logger.info(f"Script: event -> {ev_name} {kwargs if kwargs else ''}")
            elif cmd == "stop": stop_script(logger); break
            else: logger.warning(f"Script: unknown cmd '{cmd}'")
        except Exception as e: logger.error(f"Script error processing step {step}: {e}")

def control_loop(ctrl_addr, logger):
    sub = ctx.socket(zmq.SUB)
    sub.connect(ctrl_addr)
    sub.setsockopt_string(zmq.SUBSCRIBE, CTRL_TOPIC)
    logger.info(f"Control subscriber connected -> {ctrl_addr}, topic='{CTRL_TOPIC}'")
    while not shutdown_evt.is_set():
        try:
            _, msg = sub.recv_multipart()
            parts = msg.decode().strip().split()
            if not parts: continue
            cmd = parts[0].lower()
            if cmd == "mode" and len(parts) >= 2:
                name = " ".join(parts[1:])
                new = create_anim(name, node_state.w, node_state.h)
                node_state.anim, node_state.current_mode = new, name
                logger.info(f"Ctrl: mode -> {name}")
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                new_w, new_h = int(w_str), int(h_str)
                node_state.w, node_state.h = new_w, new_h
                logger.info(f"Ctrl: resized to {new_w}x{new_h}")
                # Re-create the current animation with the new size to apply it
                if node_state.current_mode:
                    try:
                        new_anim = create_anim(node_state.current_mode, new_w, new_h)
                        node_state.anim = new_anim
                        logger.info(f"Reloaded animation '{node_state.current_mode}' with new size.")
                    except Exception as e:
                        logger.error(f"Failed to reload animation '{node_state.current_mode}' after resize: {e}")
            elif cmd == "color" and len(parts) == 4 and node_state.anim:
                r, g, b = map(int, parts[1:])
                node_state.anim.set_color((r,g,b))
            elif cmd == "play" and len(parts) >= 2:
                start_script(" ".join(parts[1:]), logger)
            elif cmd == "stop": stop_script(logger)
            elif cmd == "quit": logger.info("Ctrl: quit received"); shutdown_evt.set()
            else: logger.warning(f"Ctrl: unknown command: {msg.decode()}")
        except Exception as e: logger.error(f"CTRL parse error: {e}")

def main():
    logger = logging.getLogger("MochiNode")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    info_handler = logging.StreamHandler(sys.stdout); info_handler.setLevel(logging.INFO); info_handler.addFilter(lambda r: r.levelno == logging.INFO); info_handler.setFormatter(formatter)
    err_handler = logging.StreamHandler(sys.stderr); err_handler.setLevel(logging.WARNING); err_handler.setFormatter(formatter)
    logger.addHandler(info_handler); logger.addHandler(err_handler)

    try:
        with open("config.yaml", "r") as f: config = yaml.safe_load(f)
    except Exception as e: logger.error(f"Cannot load config.yaml: {e}"); return

    node_config = config.get("node", {})
    node_state.w, node_state.h = node_config.get("logical_width", 64), node_config.get("logical_height", 64)
    fps = node_config.get("fps", 60)
    pub_addr = node_config.get("pub_address", "tcp://127.0.0.1:5555")
    ctrl_addr = node_config.get("ctrl_address", "tcp://127.0.0.1:5556")
    default_mode = node_config.get("default_mode", "idle")

    process = psutil.Process(os.getpid())

    def _sig_handler(s, f): shutdown_evt.set()
    signal.signal(signal.SIGINT, _sig_handler); signal.signal(signal.SIGTERM, _sig_handler)

    threading.Thread(target=control_loop, args=(ctrl_addr, logger), daemon=True).start()

    pub = ctx.socket(zmq.PUB); pub.setsockopt(zmq.LINGER, 0); pub.setsockopt(zmq.SNDHWM, 2); pub.bind(pub_addr)
    time.sleep(0.1)
    logger.info(f"Publisher bound -> {pub_addr}; logical_size={node_state.w}x{node_state.h}; FPS={fps}")

    try:
        node_state.anim = create_anim(default_mode, node_state.w, node_state.h)
        node_state.current_mode = default_mode
    except Exception as e:
        logger.warning(f"Unknown mode '{default_mode}' ({e}); falling back to 'idle'"); node_state.anim = create_anim("idle", node_state.w, node_state.h); node_state.current_mode = "idle"

    seq = 0
    clock = time.perf_counter
    next_frame = clock()
    dt = 1.0 / float(fps)
    last_health_t = 0.0
    bytes_sent_since_health = 0
    try:
        while not shutdown_evt.is_set():
            now = clock()
            if now < next_frame: time.sleep(max(0.0, next_frame - now))
            
            run_script_if_due(time.time(), logger)

            if node_state.anim is None: continue

            _ensure_buffers(node_state.anim.w, node_state.anim.h)

            try:
                node_state.anim.render_into(time.time(), pixel_buf)
            except Exception as e:
                logger.error(f"frame() error from '{node_state.current_mode}': {e}")
                pixel_buf[:] = b'\x80\x00\x00' * (node_state.anim.w * node_state.anim.h)

            packet_len = len(pack_frame_into(packet_buf, node_state.anim.w, node_state.anim.h, seq, pixel_buf))
            pub.send_multipart([FRAME_TOPIC, packet_buf], copy=False)
            bytes_sent_since_health += packet_len

            now_wall = time.time()
            if now_wall - last_health_t >= 1.0:
                mem_info = process.memory_info()
                tx_rate_mbps = (bytes_sent_since_health / (now_wall - last_health_t)) / (1024*1024)
                hb = {
                    "ts": int(now_wall * 1000), "seq": seq,
                    "w": node_state.anim.w, "h": node_state.anim.h,
                    "fps": fps, "mode": node_state.current_mode or "?",
                    "mem_mb": mem_info.rss / (1024 * 1024),
                    "tx_rate_mbps": tx_rate_mbps
                }
                pub.send_multipart([HEALTH_TOPIC, json.dumps(hb).encode("utf-8")])
                last_health_t = now_wall
                bytes_sent_since_health = 0

            seq += 1
            next_frame += dt
    finally:
        try: pub.close()
        except Exception: pass

if __name__ == "__main__":
    main()
