# File: proxy.py - decides what to do with one message
# Author: xtrebur00

from dns_message import parse_header, parse_question, build_response, parse_records, truncate
from blocklist import is_blocked
from upstream import ask_upstream


# shorten the response if it does not fit into the UDP limit of this client
def truncate_udp(data, response, question):

    if response is None or question is None:
        return response

    header = parse_header(data)
    records = parse_records(data, question.end, header)

    # invalid message
    if records is None:
        return response

    has_opt, udp_size = records

    # without OPT is the limit 512, with OPT depends on the client
    if has_opt:
        limit = max(512, min(udp_size, 1232))
    else:
        limit = 512

    if len(response) <= limit:
        return response
    
    return truncate(response, question.raw, has_opt)


# respopnse is none if nothing should be sent back
def process(data, names, options):

    if len(data) < 12:
        return None, "dropped", None, None

    header = parse_header(data)

    # if its response, not a query
    if header.qr == 1:
        return None, "dropped", None, None

    # only opcode = 0 is supported
    if header.opcode != 0:
        response = build_response(header, None, 4)
        return response, "invalid", 4, None

    # one question is required
    if header.qdcount != 1:
        response = build_response(header, None, 1)
        return response, "invalid", 1, None

    question = parse_question(data)

    # the question cannot be parsed
    if question is None:
        response = build_response(header, None, 1)
        return response, "invalid", 1, None

    # rest of the message must be valid
    records = parse_records(data, question.end, header)
    if records is None:
        response = build_response(header, question.raw, 1)
        return response, "invalid", 1, question
    
    has_opt, udp_size = records

    # only class IN is supported
    if question.qclass != 1:
        response = build_response(header, question.raw, 4, opt=has_opt)
        return response, "invalid", 4, question

    # AXFR or IXFR are refused
    if question.qtype in (252, 251):
        response = build_response(header, question.raw, 5, opt=has_opt)
        return response, "invalid", 5, question

    # names on blocklist get NXDOMAIN
    if is_blocked(question.qname, names):
        response = build_response(header, question.raw, 3, opt=has_opt)
        return response, "blocked", 3, question

    # relay the reply unchanged, only the ID of the client is put back
    reply = ask_upstream(data, options)
    if reply is None:
        response = build_response(header, question.raw, 2, opt=has_opt)
        return response, "forwarded", 2, question

    response = header.id.to_bytes(2, "big") + reply[2:]
    return response, "forwarded", reply[3] & 15, question