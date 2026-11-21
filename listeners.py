# File: listeners.py - network listeners 
# Author: xtrebur00

import socket
import sys
import threading

from proxy import process, truncate_udp
from query_log import write_log
from shutdown import STOP, query_started, query_finished


# Choose the address family and the addres to bind to
def choose_address(options):
    if options.address is None:
        return socket.AF_INET6, "::"

    if ":" in options.address:
        return socket.AF_INET6, options.address

    return socket.AF_INET, options.address


# UDP part:

# Handle one UDP datagram
def handle_udp(sock, data, client_address, names, options):
    query_started()

    try:
        response, verdict, rcode, question = process(data, names, options)

        response = truncate_udp(data, response, question)

        if response is not None:
            try:
                sock.sendto(response, client_address)
            except OSError:
                pass

        write_log(client_address, question, verdict, rcode)

    except Exception as error:
        print("internal error:" + str(error), file=sys.stderr)

    finally:
        query_finished()

# Create UDP socket and bind it
def open_udp(options):

    family, address = choose_address(options)
    sock = socket.socket(family, socket.SOCK_DGRAM)

    if family == socket.AF_INET6:

        if options.address is None:
            only_ipv6 = 0

        else:
            only_ipv6 = 1

        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, only_ipv6)
        
    sock.bind((address, options.port))

    return sock


# Receive DNS queries over UDP and answer them
def run_udp(sock, options, names):
    sock.settimeout(0.2)

    while not STOP.is_set():

        try:
            data, client_address = sock.recvfrom(65535)

        except socket.timeout:
            continue

        thread = threading.Thread(target=handle_udp, args=(sock, data, client_address, names, options), daemon=True)
        thread.start()


# TCP part:

# Read exactly count bytes from the connection
def read_bytes(connection, count):
    data = b""
    
    while len(data) < count:
        received = connection.recv(count - len(data))

        # if the connection was closed
        if not received:
            return None
        data += received
    
    return data

# Serve one TCP connection
def handle_tcp(connection, client_address, names, options):
    connection.settimeout(10)

    try:
        while True:
            
            length_bytes = read_bytes(connection, 2)
        
            if length_bytes is None:
                break

            length = int.from_bytes(length_bytes, "big")
            data = read_bytes(connection, length)

            # client closed the connection in the middle of a message
            if data is None:
                break

            query_started() 

            try:
                response, verdict, rcode, question = process(data, names, options)

                if response is not None:
                    try:
                        connection.sendall(len(response).to_bytes(2, "big") + response)
                    except OSError:
                        pass

                write_log(client_address, question, verdict, rcode)

            finally:
                query_finished()

            if response is None:
                break
            
            if STOP.is_set():
                break

    except OSError:
        pass

    except Exception as error:
        print("internal error:" +str(error), file=sys.stderr)

    finally:
        connection.close()

# Create TCP socket, bind it and start listening
def open_tcp(options):

    family, address = choose_address(options)
    sock = socket.socket(family, socket.SOCK_STREAM)

    if family == socket.AF_INET6:
        if options.address is None:
            only_ipv6 = 0

        else:
            only_ipv6 = 1

        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, only_ipv6)

    
    # if server ends and you immediately start it again, TCP port is blocked for a while
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    sock.bind((address, options.port))
    sock.listen()

    return sock


# Accepts TCP connections, every connection is served in its own thread
def run_tcp(sock, options, names):
    sock.settimeout(0.2)

    while not STOP.is_set():

        try:
            connection, client_address = sock.accept()

        except socket.timeout:
            continue

        # every client gets its own socket and its own thread
        thread = threading.Thread(target=handle_tcp, args=(connection, client_address, names, options), daemon=True)
        thread.start()



