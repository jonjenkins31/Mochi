# control_cli.py
import sys, zmq, time, os, yaml

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def main():
    # --- Load Config ---
    try:
        config_path = os.path.join(PROJECT_ROOT, "config.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        gui_config = config.get("gui", {})
        pub_addr = gui_config.get("pub_address", "tcp://127.0.0.1:5556")
    except Exception as e:
        print(f"Warning: Could not load config.yaml ({e}). Using default address.")
        pub_addr = "tcp://127.0.0.1:5556"

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    # A client/controller should CONNECT, while the server/node/main_gui BINDS.
    pub.connect(pub_addr)
    time.sleep(0.1)  # allow SUBs to connect

    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        pub.send_multipart([b"ctrl", cmd.encode()])
        print("sent:", cmd)
        return

    print("Interactive. Examples:")
    print("  idle")
    print("  bars")
    print("  rainbow")
    print("  color 255 100 50")
    print("Ctrl+C to exit.")
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            pub.send_multipart([b"ctrl", line.encode()])
        except (EOFError, KeyboardInterrupt):
            break

if __name__ == "__main__":
    main()
