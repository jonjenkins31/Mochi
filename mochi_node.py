# mochi_node.py
import time, struct, threading, signal, logging, json, zmq, yaml, sys, os
import psutil

# --- Core components ---
from animations import create as create_anim
from core.mochi_script_engine import load_script, Command
from core.logging_utils import setup_logger

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"
HEALTH_TOPIC = b"health"

shutdown_evt = threading.Event()

ctx = zmq.Context.instance()

# --- Node State ---
class NodeState:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.anim = None
        self.current_mode = None
        self.script = None # Holds the active script object

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

# --- Command Processing ---
def process_command(cmd: Command, logger, resolve_dir: str | None = None):
    """Executes a command received from a script."""
    global node_state
    try:
        if cmd.name == "mode":
            args = cmd.args.copy()
            name = args.pop("name", None)
            if not name:
                logger.warning("Script: mode step missing 'name'")
                return
            
            # Inject the script's directory to resolve relative paths
            if resolve_dir:
                args['resolve_dir'] = resolve_dir

            new = create_anim(name, node_state.w, node_state.h, **args)
            node_state.anim, node_state.current_mode = new, name
            logger.info(f"Script: mode -> {name} with args {args}")

        elif cmd.name == "event":
            ev_name = cmd.args.pop("name", None)
            if not ev_name:
                logger.warning("Script: event step missing 'name'")
                return
            if node_state.anim:
                node_state.anim.on_event(ev_name, **cmd.args)
            logger.info(f"Script: event -> {ev_name} {cmd.args if cmd.args else ''}")
        elif cmd.name == "stop_script":
            if node_state.script:
                logger.info("Script finished")
                node_state.script = None
        else:
            logger.warning(f"Script: unknown cmd '{cmd.name}'")
    except Exception as e:
        logger.error(f"Script error processing step {cmd}: {e}")

# --- Control Loop (handles commands from GUI) ---
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
                path = " ".join(parts[1:])
                try:
                    node_state.script = load_script(path)
                    logger.info(f"Ctrl: Started script '{path}'")
                except Exception as e:
                    logger.error(f"Failed to start script '{path}': {e}")
                    node_state.script = None
            elif cmd == "stop":
                if node_state.script:
                    logger.info("Ctrl: Script stopped by command")
                    node_state.script = None
            elif cmd == "quit":
                logger.info("Ctrl: quit received"); shutdown_evt.set()
            else:
                logger.warning(f"Ctrl: unknown command: {msg.decode()}")
        except Exception as e:
            logger.error(f"CTRL parse error: {e}")

# --- Main Loop ---
def main():
    logger = setup_logger("MochiNode")

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
            
            # --- Run script if active ---
            if node_state.script:
                script_dir = os.path.dirname(node_state.script.path)
                due_commands = node_state.script.update(time.time())
                for command in due_commands:
                    process_command(command, logger, resolve_dir=script_dir)

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
