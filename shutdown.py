# File: shutdown.py - flag that is set when SIGINT or SIGTERM arrives
# Author: xtrebur00

import signal
import threading
import time

STOP = threading.Event()
RUNNING = 0
LOCK = threading.Lock()

# when signal arrives
def on_signal(number, frame):
    STOP.set()

# make SIGINT and SIGTERM raise the flag
def handle_signals():
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)


# A handler starts working on one message
def query_started():
    global RUNNING

    with LOCK:
        RUNNING += 1

# A handler is done with its message
def query_finished():
    global RUNNING

    with LOCK:
        RUNNING -= 1

# Wait until no query is running, but at most the given number of seconds
def wait_for_queries(seconds):
    deadline = time.monotonic() + seconds

    while RUNNING > 0 and time.monotonic() < deadline:
        time.sleep(0.05)