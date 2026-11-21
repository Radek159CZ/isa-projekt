# File: blocklist.py - loading blocklist files and matching names
# Author: xtrebur00

ALLOWED = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

IGNORED = {"localhost", "localhost.localdomain", "local", "broadcasthost",
           "ip6-localhost", "ip6-loopback", "ip6-localnet", "ip6-mcastprefix",
           "ip6-allnodes", "ip6-allrouters", "ip6-allhosts"}

# if is valid domain name for the blocklist
def is_valid_name(name):

    if name.endswith("."):
        name = name[:-1]

    if len(name) < 1 or len(name) > 253:
        return False

    # split the name into labels
    labels = name.split(".")
    if len(labels) > 127:
        return False

    # checking if every character is in allowed characters
    for label in labels:
        if len(label) < 1 or len(label) > 63:
            return False

        for ch in label:
            if ch not in ALLOWED:
                return False

    return True

# True when the name is in the blocklist
def is_blocked(qname, names):

    labels = []
    for label in qname:
        labels.append(label.decode("latin-1").lower())

    for start in range(len(labels)):
        name = ".".join(labels[start:])
        if name in names: 
            return True
        
    return False

# Read one blocklist file and add its names to the set
def load_blocklist(path, names):

    try: 
        with open(path, encoding="utf-8") as file:
            lines = file.readlines()
    except (OSError, UnicodeDecodeError) as error:
        return path + ":0: cannot read the file: " + str(error)

    for number, line in enumerate(lines, 1):

        tokens = line.split("#")[0].split()

        # an IPv6 address in front is skipped
        if tokens and ":" in tokens[0]:
            tokens = tokens[1:]

        for token in tokens:
            if not is_valid_name(token):
                return path + ":" + str(number) + ": invalid domain name: " + token

            name = token.lower()

            if name.endswith("."):
                name = name[:-1]

            # an IPv4 address (digits and dots) and hosts(5) header names are ignored
            if name.strip("0123456789.") == "" or name in IGNORED:
                continue

            names.add(name)
        
    return None
      