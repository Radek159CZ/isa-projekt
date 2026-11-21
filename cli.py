# File: cli.py - parsing arguments
# Author: xtrebur00


import ipaddress
import sys
from urllib.parse import urlsplit

USAGE = """\
./isa-dnsproxy -u DOH_URL [-p PORT] [-a ADDRESS] [-b BLOCKLIST]... [-w TIMEOUT] [--insecure]
./isa-dnsproxy -h | --help
"""


class Options:
    def __init__(self):
        self.upstream_url = None
        self.port = 53
        self.address = None
        self.blocklist_files = []
        self.timeout_s = 3
        self.insecure = False


# Print an error to stderr and exit with code 64
def fail(message):
    print("isa-dnsproxy: " + message, file=sys.stderr)
    sys.exit(64)


# Convert text to int and check it lies between low and high
def to_int_in_range(text, low, high, name):
    try:
        number = int(text)
    except ValueError:
        fail(name + " must be a number, got '" + text + "'")
    if number < low or number > high:
        fail(name + " must be " + str(low) + ".." + str(high))
    return number


# Go through the arguments one by one and fill in Options
def parse_args(argv):
    
    if "-h" in argv or "--help" in argv:
        print(USAGE, end="")
        sys.exit(0)

    options = Options()
    seen = set()
    i = 0

    while i < len(argv):
        arg = argv[i]

        if arg == "--insecure":
            if arg in seen:
                fail("--insecure given more than once")

            seen.add(arg)
            options.insecure = True
            i += 1
            continue

        if arg not in ("-u", "-p", "-a", "-b", "-w"):
            fail("unknown argument: " + arg)

        # every remaining option needs a value right after it
        if i + 1 >= len(argv):
            fail("option " + arg + " needs a value")

        value = argv[i + 1]
        i += 2  

        # -b may be repeated
        if arg == "-b":
            options.blocklist_files.append(value)
            continue

        # the rest may be used only once
        if arg in seen:
            fail("option " + arg + " given more than once")
        seen.add(arg)

        if arg == "-u":
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                fail("-u must be an http(s) URL, got '" + value + "'")
            options.upstream_url = value

        elif arg == "-p":
            options.port = to_int_in_range(value, 1, 65535, "-p")

        elif arg == "-w":
            options.timeout_s = to_int_in_range(value, 1, 3600, "-w")

        elif arg == "-a":

            if "%" in value:
                fail("-a must not contain a zone index")
            try:
                ipaddress.ip_address(value)
            except ValueError:
                fail("-a must be a literal IP address, got '" + value + "'")
            options.address = value

    if options.upstream_url is None:
        fail("option -u is mandatory")

    return options
