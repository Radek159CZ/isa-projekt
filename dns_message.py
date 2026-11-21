# File: dns_message.py - reading and building DNS messages
# Author: xtrebur00

OPT = bytes.fromhex("00 0029 04d0 00000000 0000")

# Header of DNS message
class Header:
    def __init__(self):
        self.id = 0
        self.flags = 0
        self.qr = 0       
        self.opcode = 0   
        self.rd = 0   
        self.cd = 0    
        self.qdcount = 0    # number of question
        self.ancount = 0    # number of answers
        self.nscount = 0    # number of authority records
        self.arcount = 0    # number of additional records


# Question part of DNS message
class Question:
    def __init__(self):
        self.qname = []
        self.qtype = 0
        self.qclass = 0
        self.end = 0
        self.raw = b""
        

# Read the header from the first 12 bytes of data
def parse_header(data):
    header = Header()

    # join of two bytes into one number
    header.id = (data[0] << 8) + data[1]
    header.flags = (data[2] << 8) + data[3]
    header.qdcount = (data[4] << 8) + data[5]
    header.ancount = (data[6] << 8) + data[7]
    header.nscount = (data[8] << 8) + data[9]
    header.arcount = (data[10] << 8) + data[11]
    

    # shift the bit to the right end, mask the rest
    header.qr = (header.flags >> 15) & 1
    header.opcode = (header.flags >> 11) & 0xF
    header.rd = (header.flags >> 8) & 1
    header.cd = (header.flags >> 4) & 1
    return header

# Read the question that follow the header
def parse_question(data):
    question = Question()
    position = 12
    name_length = 0

    # read the name label by label until end of question (zero byte)
    while True:

        # the message ends before name is finished
        if position >= len(data):
            return None

        length = data[position]
        position += 1

        if length == 0:
            break

        if length >= 64:
            return None

        if position + length > len(data):
            return None

        name_length += length + 1
        if name_length > 255:
            return None

        label = data[position : position + length]
        question.qname.append(label)
        position += length

    if position + 4 > len(data):
        return None

    question.qtype = (data[position] << 8) + data[position + 1]
    question.qclass = (data[position + 2] << 8) + data[position + 3]
    position += 4
    question.end = position
    question.raw = data[12:position]
    return question

# Build a response: header + the question copied from the query
def build_response(query_header, question_raw, rcode, aa=0, opt=False):

    # put the single values into one 16-bit flags number
    flags = (1 << 15) | (query_header.opcode << 11) | (aa << 10) | (query_header.rd << 8) | (1 << 7) | (query_header.cd << 4) | rcode

    # if no question was parsed
    if question_raw is None:
        qdcount = 0
        question_raw = b""

    else:
        qdcount = 1

    response = query_header.id.to_bytes(2, "big")
    response += flags.to_bytes(2, "big")
    response += qdcount.to_bytes(2, "big")
    
    if opt:
        arcount = 1
    else:
        arcount = 0
        
    response += b"\x00" * 4
    response += arcount.to_bytes(2, "big")

    # the question must be copied unchanged
    response += question_raw
    
    if opt:
        response += OPT
    
    return response


# build the short message with TC = 1 from a response that is too big
def truncate(response, question_raw, has_opt):
    flags = int.from_bytes(response[2:4], "big") | (1 << 9)

    if has_opt:
        arcount = 1

    else:
        arcount = 0

    short = response[0:2]
    short += flags.to_bytes(2, "big")
    short += response[4:6]
    short += b"\x00" * 4
    short += arcount.to_bytes(2, "big")
    short += question_raw

    if has_opt:
        short += OPT

    return short

    
# skip one domain name inside a record
def skip_name(data, position):
    
    while True:
        if position >= len(data):
            return None
        length = data[position]

        # end of the name
        if length == 0:
            return position + 1

        # compression pointer also ends the name
        if length >= 192:
            if position + 2 > len(data):
                return None
            return position + 2

        # 64-191 is invalid length
        if length >= 64:
            return None

        # label must fit into the message
        if position + 1 + length > len(data):
            return None
        position += 1 + length

# walk throught all records after the question
def parse_records(data, position, header):
    total = header.ancount + header.nscount + header.arcount
    first_additional = header.ancount + header.nscount
    has_opt = False
    udp_size = 0

    for index in range(total):
        start = position
        position = skip_name(data, position)

        if position is None:
            return None

        # type + class + ttl + rdllength
        if position + 10 > len(data):
            return None
        rtype = (data[position] << 8) + data[position + 1]
        rclass = (data[position + 2] << 8) + data[position + 3]
        rdlength = (data[position + 8] << 8) + data[position + 9]
        position += 10

        if position + rdlength > len(data):
            return None
        position += rdlength

        if rtype == 41:
            if index < first_additional:
                return None
            if has_opt:
                return None
            if data[start] != 0:
                return None
            has_opt = True
            udp_size = rclass

    return has_opt, udp_size

