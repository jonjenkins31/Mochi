# control_cli.py
import sys, zmq, time

PUB_ADDR = "tcp://127.0.0.1:5556"

def main():
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.bind(PUB_ADDR)
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
