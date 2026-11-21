# File: query_log.py - writes one line per query to stdout
# Author: xtrebur00

import sys
import threading
import ipaddress
from datetime import datetime


LOCK = threading.Lock()

TYPE = {
    1: "A",
    28: "AAAA",
    2: "NS",
    5: "CNAME",
    6: "SOA",
    10: "NULL",
    12: "PTR",
    13: "HINFO",
    15: "MX",
    16: "TXT",
    17: "RP",
    18: "AFSDB",
    29: "LOC",
    33: "SRV",
    35: "NAPTR",
    37: "CERT",
    39: "DNAME",
    43: "DS",
    44: "SSHFP",
    45: "IPSECKEY",
    46: "RRSIG",
    47: "NSEC",
    48: "DNSKEY",
    50: "NSEC3",
    51: "NSEC3PARAM",
    52: "TLSA",
    59: "CDS",
    60: "CDNSKEY",
    61: "OPENPGPKEY",
    64: "SVCB",
    65: "HTTPS",
    99: "SPF",
    249: "TKEY",
    250: "TSIG",
    251: "IXFR",
    252: "AXFR",
    255: "ANY",
    256: "URI",
    257: "CAA"
}

RCODE = {
    0: "NOERROR",
    1: "FORMERR",
    2: "SERVFAIL",
    3: "NXDOMAIN",
    4: "NOTIMP",
    5: "REFUSED",
    6: "YXDOMAIN",
    7: "YXRRSET",
    8: "NXRRSET",
    9: "NOTAUTH",
    10: "NOTZONE",
    11: "DSOTYPENI"
}

# return ip:port of the client
def format_client(client_address):
    host = client_address[0].split("%")[0]
    port = client_address[1]

    address = ipaddress.ip_address(host)

    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped

    if address.version == 6:
        return "[" + str(address) + "]:" + str(port)

    return str(address) + ":" + str(port)

# Escape one label for the log
def escape_label(label):
    text = ""

    for byte in label:
        character = chr(byte)

        if character in '.;()@$"\\':
            text += "\\" + character

        elif 0x21 <= byte <= 0x7E:
            text += character.lower()

        else:
            text += "\\" + f"{byte:03d}"

    return text

def write_log(client_address, question, verdict, rcode):
    
    if question is None:
        name = "-"
        qtype = "-"

    else:    
        if not question.qname:
            name = "."

        else:
            name = ""
            for label in question.qname:
                name += escape_label(label) + "."

        qtype = TYPE.get(question.qtype, "TYPE" + str(question.qtype))

    if rcode is None:
        rcode_name = "-"

    else:
        rcode_name = RCODE.get(rcode, "RCODE" + str(rcode))

    timestamp = datetime.now().astimezone().replace(microsecond=0).isoformat()

    # one line, written under a lock so lines of different threads never mix
    with LOCK:
        print(timestamp + " " + format_client(client_address) + " " + name + " " + qtype + " " + verdict + " " + rcode_name)
        sys.stdout.flush()
