# File: main.py - entry point of isa-dnsproxy
# Author: xtrebur00

import sys
import threading

from cli import parse_args
from listeners import run_udp, run_tcp, open_udp, open_tcp
from blocklist import load_blocklist
from shutdown import handle_signals, wait_for_queries


# return host:port of bound socket
def format_address(sock):
    host, port = sock.getsockname()[:2]

    if ":" in host:
        host = "[" + host + "]"

    return host + ":" + str(port)


def main():
    options = parse_args(sys.argv[1:])

    # load all blocklist files into one set before serving anything
    names = set()
    for path in options.blocklist_files:
        error = load_blocklist(path, names)
        if error is not None:
            print(error, file=sys.stderr)
            return 78

    # open both sockets here, so a failure can be reported before serving 
    try:
        udp_sock = open_udp(options)
        tcp_sock = open_tcp(options)

    except OSError as error:
        print("cannot bind: " + str(error), file=sys.stderr)
        return 69

    print("listening on", format_address(udp_sock), file= sys.stderr)
    print("listening on", format_address(tcp_sock), file= sys.stderr)

    handle_signals()

    # TCP runs in its own thread, because both run_tcp and run_udp never return
    thread = threading.Thread(target=run_tcp, args=(tcp_sock, options, names), daemon=True)
    thread.start()

    run_udp(udp_sock, options, names)
    wait_for_queries(1.5)

    udp_sock.close()
    tcp_sock.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
