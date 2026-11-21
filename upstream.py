# File: upstream.py - forwarding queries to a DoH upstream
# Author: xtrebur00

import http.client
import ssl
import threading
import time
import os

from urllib.parse import urlsplit
from dns_message import parse_header, parse_question
from shutdown import STOP

# True when the reply is a valid DNS answer to the query
def is_valid_reply(reply, query):

    # DNS message has 12 - 65535 bytes
    if len(reply) < 12 or len(reply) > 65535:
        return False

    header = parse_header(reply)
    if header.qr != 1 or header.opcode != 0 or header.qdcount != 1:
        return False

    question = parse_question(reply)
    sent = parse_question(query)
    if question is None or sent is None:
        return False

    reply_name = [label.lower() for label in question.qname]
    sent_name = [label.lower() for label in sent.qname]

    return reply_name == sent_name and question.qtype == sent.qtype and question.qclass == sent.qclass


# send the DNS query to the upstream
def send_request(query, options):

    query = b"\x00\x00" + query[2:]

    url = urlsplit(options.upstream_url)
    path = url.path or "/"

    if url.query:
        path += "?" + url.query

    connection = None

    try:

        if url.scheme == "https":

            # the certificate is verified against SSL_CERT_FILE when it is set, otherwise against the system certificates
            cafile = os.environ.get("SSL_CERT_FILE")
            if cafile:
                context = ssl.create_default_context(cafile=cafile)
            else:
                context = ssl.create_default_context()

            if options.insecure:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            connection = http.client.HTTPSConnection(url.hostname, url.port or 443, timeout=options.timeout_s, context=context)

        else:
            connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=options.timeout_s)


        # the DNS query is the body of the POST request
        connection.request("POST", path, body=query, headers={"Content-Type":"application/dns-message","Accept":"application/dns-message"})

        response = connection.getresponse()

        # Successful responses are 200 - 299
        if response.status < 200 or response.status > 299:
            return None

        body = response.read(65536)

        # body must be a valid DNS answer to this query
        if not is_valid_reply(body, query):
            return None
        
        return body

    except (OSError, ValueError, http.client.HTTPException):
        return None

    finally:
        if connection is not None:
            connection.close()
         
# Ask the uprstream in a helper thread
def ask_upstream(query, options):
    result = []
    done = threading.Event()

    def work():
        try:
            result.append(send_request(query, options))

        finally:
            done.set()

    thread = threading.Thread(target=work, daemon=True)
    thread.start()

    deadline = time.monotonic() + options.timeout_s

    while not done.is_set() and not STOP.is_set() and time.monotonic() < deadline:
        done.wait(0.1)

    if not done.is_set() or not result:
        return None
    
    return result[0]



