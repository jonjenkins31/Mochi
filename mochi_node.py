# mochi_node.py
import time, math, random, struct, threading, signal, argparse, logging, zmq

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"

# Defaults (can be overridden by CLI or ctrl commands)
DEFAULT_W, DEFAULT_H = 64, 64
DEFAULT_FPS = 60
PUB_ADDR = "tcp://127.0.0.1:5555"   # frames out
CTRL_ADDR = "tcp://127.0.0.1:5556"  # control in (SUB)

shutdown_evt = threading.Event()

ctx = zmq.Context.instance()

def pack_frame(w, h, seq, pixels_rgb_bytes):
    ts_ms = int(time.time() * 1000)
    header = struct.pack(HEADER_FMT, w, h, ts_ms, seq)
    return header + pixels_rgb_bytes

class Anim:
    def __init__(self, w=DEFAULT_W, h=DEFAULT_H):
        self.w, self.h = w, h
        self.mode = "idle"
        self.fg = (235, 235, 255)
        self.bg = (8, 8, 12)
        self._lock = threading.Lock()
        # blink timing
        self._next_blink_t = time.time() + random.uniform(3.0, 7.0)
        self._blink_dur = 0.12
        self._blink_end_t = None

    def set_mode(self, m):
        with self._lock:
            self.mode = m

    def set_color(self, r, g, b):
        with self._lock:
            self.fg = (max(0, min(255, int(r))),
                       max(0, min(255, int(g))),
                       max(0, min(255, int(b))))

    def set_size(self, w, h):
        with self._lock:
            self.w, self.h = int(w), int(h)

    def frame(self, t):
        with self._lock:
            mode = self.mode
            fg = self.fg
            w, h = self.w, self.h
        # base background with gentle breathing
        breath = (math.sin(t*0.8)*0.5+0.5)*0.12
        tint = int(15 + breath*80)
        buf = bytearray(w*h*3)
        for i in range(0, len(buf), 3):
            buf[i+0] = 8
            buf[i+1] = 8
            buf[i+2] = min(255, 12 + tint)

        def put_pixel(x, y, color):
            if 0 <= x < w and 0 <= y < h:
                idx = (y*w + x)*3
                r, g, b = color
                # clamp
                if r < 0: r = 0
                elif r > 255: r = 255
                if g < 0: g = 0
                elif g > 255: g = 255
                if b < 0: b = 0
                elif b > 255: b = 255
                buf[idx:idx+3] = bytes((r, g, b))

        def eyes_and_mouth(blink_amt=0.0, vu=0.25):
            eye_y = h//2 - 2
            eye_dx = max(1, w//6)
            lx, rx = w//2 - eye_dx, w//2 + eye_dx
            r_eye = max(2, w//10)
            # draw eye discs
            r2 = r_eye*r_eye
            for y in range(max(0, eye_y-r_eye), min(h, eye_y+r_eye+1)):
                dy2 = (y-eye_y)*(y-eye_y)
                for x in range(max(0, lx-r_eye), min(w, lx+r_eye+1)):
                    if (x-lx)*(x-lx) + dy2 <= r2:
                        put_pixel(x, y, (235,235,255))
                for x in range(max(0, rx-r_eye), min(w, rx+r_eye+1)):
                    if (x-rx)*(x-rx) + dy2 <= r2:
                        put_pixel(x, y, (235,235,255))
            # eyelid line (blink)
            if blink_amt > 0:
                lid_y = eye_y + int(blink_amt*1.0)
                for x in range(max(0, lx-r_eye), min(w, lx+r_eye+1)):
                    put_pixel(x, lid_y, (230,230,240))
                for x in range(max(0, rx-r_eye), min(w, rx+r_eye+1)):
                    put_pixel(x, lid_y, (230,230,240))
            # pupils
            pr = max(1, r_eye-2)
            for dy in range(-pr, pr+1):
                yy = eye_y+dy
                if 0 <= yy < h:
                    for dx in range(-pr, pr+1):
                        if dx*dx+dy*dy <= pr*pr:
                            put_pixel(lx+dx, yy, (25,25,40))
                            put_pixel(rx+dx, yy, (25,25,40))
            # mouth
            mouth_y = h//2 + r_eye + 2
            width = w//4
            open_amt = int(min(h//6, 1 + int(vu*4)))
            for y in range(open_amt):
                yy = mouth_y + y
                if 0 <= yy < h:
                    for x in range(w//2 - width//2, w//2 + width//2):
                        put_pixel(x, yy, (255,120,120))

        # Blink timing (smoother than modulo check)
        if mode == "idle":
            now = t
            if self._blink_end_t is None and now >= self._next_blink_t:
                self._blink_end_t = now + self._blink_dur
            blink_amt = 0.0
            if self._blink_end_t is not None:
                # simple linear close/open over duration
                phase = 1.0 - max(0.0, (self._blink_end_t - now)/self._blink_dur)
                blink_amt = max(0.0, min(1.0, phase))
                if now >= self._blink_end_t:
                    self._blink_end_t = None
                    self._next_blink_t = now + random.uniform(3.0, 7.0)
            vu = (math.sin(t*3.1)*0.5+0.5)*0.5
            eyes_and_mouth(blink_amt=blink_amt, vu=vu)
        elif mode == "bars":
            for x in range(w):
                v = (math.sin(t*2.0 + x*0.3)*0.5+0.5)
                col = (int(fg[0]*v), int(fg[1]*v), int(fg[2]*v))
                for y in range(h):
                    put_pixel(x, y, col)
        elif mode == "rainbow":
            for y in range(h):
                for x in range(w):
                    u = (x + t*20.0)/w
                    r = int((math.sin(2*math.pi*u)+1)*127.5)
                    g = int((math.sin(2*math.pi*u+2.094)+1)*127.5)
                    b = int((math.sin(2*math.pi*u+4.188)+1)*127.5)
                    put_pixel(x, y, (r, g, b))
        else:
            eyes_and_mouth()

        return bytes(buf)

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
            if cmd in ("idle","bars","rainbow","blink"):
                anim.set_mode(cmd if cmd != "blink" else "idle")
            elif cmd == "color" and len(parts) == 4:
                r, g, b = map(int, parts[1:])
                anim.set_color(r, g, b)
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                anim.set_size(int(w_str), int(h_str))
                print(f"[CTRL] resized to {w_str}x{h_str}")
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
    p.add_argument("--size", default=f"{DEFAULT_W}x{DEFAULT_H}", help="matrix WxH, default 32x32")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="frames per second")
    p.add_argument("--pub", default=PUB_ADDR, help="PUB address for frames")
    p.add_argument("--ctrl", default=CTRL_ADDR, help="SUB address for control")
    p.add_argument("--mode", default="idle", choices=["idle","bars","rainbow"], help="initial mode")
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
    print("[MochiNode] Commands: idle | bars | rainbow | color R G B | size WxH | quit")

    # Animator
    global anim
    anim = Anim(w, h)
    anim.set_mode(args.mode)

    seq = 0
    next_frame = time.time()
    dt = 1.0 / float(fps)
    try:
        while not shutdown_evt.is_set():
            now = time.time()
            if now < next_frame:
                time.sleep(next_frame - now)
            t = time.time()
            payload = anim.frame(t)
            packet = pack_frame(anim.w, anim.h, seq, payload)
            pub.send_multipart([FRAME_TOPIC, packet])
            seq += 1
            next_frame += dt
    finally:
        try:
            pub.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
