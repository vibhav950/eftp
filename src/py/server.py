import socket
import threading
import time
import os
import ip_util
from ip_util import DATA_PORT, CONTROL_PORT, GREET_PORT, CHUNK_SIZE
from handshakes import (
    perform_handshake,
    receive_handshake,
    create_socket,
    send_pub_key,
    receive_session_key,
    receive_file_digest,
)
import select
import crypto_utils as cu


busy_flag = 0
connection = 0
filereceivetext = ""


def handle_receive(conn, addr, handshake_mode, data_socket, hostname, ui=None):
    global busy_flag, connection
    if busy_flag:
        perform_handshake(conn, "reject")
        return
    connection = 1
    print(f"Connection established with {addr} {handshake_mode.split(' ')[1]}")
    while True:
        print("in loop")
        pub = conn.recv(1024)
        time.sleep(0.1)
        if pub:
            break
    print("out of loop")
    print(pub)
    with open("../../keys/pubclient.pem", "wb") as f:
        f.write(pub)
    public_key = "pubclient.pem"
    send_pub_key(conn)
    session_key = receive_session_key(conn)

    print(session_key)
    digest = receive_file_digest(conn, True)
    print(digest)
    global filereceivetext
    filereceivetext = f"Incoming file {handshake_mode.split(' ')[2]} {handshake_mode.split(' ')[3]}MB transfer request. Do you want to accept? (yes/no): "
    print(filereceivetext)
    if ui:
        ui[0].show()
        ui[1].filename.setText(f"File Name: {handshake_mode.split()[2]}")
        ui[1].filesize.setText(f"File Size: {handshake_mode.split()[3]} MB")
        ui[1].addr.setText(f"{addr[0]}")
        while not ui[1].get_input():
            pass
        user_input = ui[1].get_input().lower()
    else:
        user_input = input().lower()

    if user_input == "yes":
        busy_flag = 1
        perform_handshake(conn, "send", public_key)
        data_socket.setblocking(True)
        conn, addr = data_socket.accept()
        receive_file(
            conn,
            handshake_mode.split(" ")[2],
            handshake_mode.split(" ")[3],
            session_key,
            digest,
            ui,
        )
    else:
        perform_handshake(conn, "reject")
        connection = 0


def handle_ping(conn, hostname):
    print("ping")
    if busy_flag:
        perform_handshake(conn, "reject")
    else:
        perform_handshake(conn, hostname)


def handle_client(conn, addr, data_socket, hostname, ui=None):
    handshake_mode = receive_handshake(conn)
    if handshake_mode.startswith("receive"):
        handle_receive(conn, addr, handshake_mode, data_socket, hostname, ui)
    elif handshake_mode.startswith("ping"):
        handle_ping(conn, hostname)


def receive_file(sock, file_name, size, session_key, hash, ui=None):
    global busy_flag, connection
    file_name = os.path.basename(file_name)
    if ui:
        ui[2].show()
    with open(f"../../files/{file_name}.tmp", "wb") as f:
        received = 0
        data = sock.recv(CHUNK_SIZE)
        while data:
            f.write(data)
            data = sock.recv(CHUNK_SIZE)
            received = os.path.getsize(f"../../files/{file_name}.tmp")
            if received >= float(size) * 1024 * 1024:
                received = float(size) * 1024 * 1024
            print(f"Received {received/(1024*1024)}/{size} MB", end="\r")
            if ui:
                ui[3].update_progress(int(received / (float(size) * 1024 * 1024) * 100))

    print(f"Received {received/(1024*1024)}/{size} MB")
    if ui:
        ui[3].label.setText("Decrypting file...")
    cu.decryptFile(
        session_key,
        f"../../files/{file_name}.tmp",
        f"../../files/{file_name}",
        CHUNK_SIZE,
        ui,
    )
    os.remove(f"../../files/{file_name}.tmp")
    print("Decrypting file...")
    recvhash = cu.calculateFileDigest(f"../../files/{file_name}")
    if recvhash == hash:
        print(f"Hashes match. File {file_name} received successfully")
    else:
        print("Hashes do not match. File transfer failed")
        os.remove(f"../../files/{file_name}")
    os.remove(f"../../keys/pubclient.pem")
    busy_flag = 0
    connection = 0


def start_server(ip, hostname, mk=None, ui=None):
    # threads = []
    if mk:
        cu.setMasterKey(mk)

    data_socket = create_socket(ip, DATA_PORT)
    data_socket.listen()

    greet_socket = create_socket(ip, GREET_PORT)
    greet_socket.listen()

    control_socket = create_socket(ip, CONTROL_PORT)
    control_socket.listen()

    socks = [greet_socket, control_socket]

    print(f"Server listening on socket {ip}")

    while True:
        readable, _, _ = select.select(socks, [], [])

        for i in readable:
            conn, addr = i.accept()
            threading.Thread(
                target=handle_client, args=(conn, addr, data_socket, hostname, ui)
            ).start()


if __name__ == "__main__":
    mk = input("Enter Master Key: ")
    cu.setMasterKey(mk)
    if not (
        os.path.isfile("../../keys/public.pem")
        and os.path.isfile("../../keys/private.der")
    ):
        cu.generateNewKeypair(public_out="public.pem", private_out="private.der")
    ip_addr, hostname = ip_util.get_ip()
    ip = ip_util.choose_ip(ip_addr, hostname)
    start_server(ip, hostname)
