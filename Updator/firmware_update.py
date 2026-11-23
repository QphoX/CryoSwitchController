"""Send a ready-made update.bin to a Labphox board over UDP (protocol v1, firmware repo docs/udp-image-download.md).

image_protocol.py is a verbatim copy from the firmware repo: re-copy it when the protocol changes.
The board only installs the image after RESET, so any failure before that leaves the running firmware untouched.
"""
import random
import socket
import time
from pathlib import Path

from .image_protocol import (
    CHUNK_COUNT, CHUNK_SIZE, IMAGE_SIZE, REPLY_FLAG, START_PAYLOAD, STATE_NAMES, STATUS_NAMES,
    STATUS_OK, STATUS_OUT_OF_ORDER, TYPE_ABORT, TYPE_DATA, TYPE_FINISH, TYPE_RESET, TYPE_START,
    build_request, chunk, image_crc, packet_crc, parse_reply,
)

# Spec sec. 6: (timeout in s, retransmissions of the identical packet)
RETRIES = {TYPE_START: (15.0, 2), TYPE_DATA: (0.5, 5), TYPE_FINISH: (2.0, 3), TYPE_RESET: (1.0, 1),
           TYPE_ABORT: (0.5, 3)}
MAX_OUT_OF_ORDER = 10          # consecutive OUT_OF_ORDER replies before giving up
VERSION_WAIT_S = 3
BOOT_WAIT_S = 60               # bootloader install + app start (measured: 8 s)
VERSION_COMMAND = b"W:2:H:0;"  # reply "FW_Ver. X.Y.Z;"
TRANSFER_PERCENT = 90          # progress: transfer 0..90 %, verify + install 90..100 %


class UpdateError(Exception):
    pass


def load_update_image(path):
    """update.bin is always IMAGE_SIZE (mkimage pads the app to the full DOWNLOAD area)."""
    data = Path(path).read_bytes()
    if len(data) != IMAGE_SIZE:
        raise UpdateError(f"{path} is {len(data)} B, an update.bin must be exactly {IMAGE_SIZE} B")
    return data


def update_firmware(ip, port, image_path, progress=None, before_send=None):
    """Returns (version_before, version_after); raises UpdateError.
    progress(percent, message): optional. before_send(): optional, runs once the image is valid and
    the board answers, right before anything is written."""
    def report(percent, message):
        if progress:
            progress(percent, message)

    image = load_update_image(image_path)
    addr = (ip, int(port))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        before = _read_version(sock, addr, VERSION_WAIT_S)
        if before is None:
            raise UpdateError(f"No answer from {ip}:{port} (is the board running and reachable?)")
        if before_send:
            before_send()

        report(0, f"Board firmware {before}. Erasing download area (~3 s)...")
        session = _send_image(sock, addr, image, report)

        report(TRANSFER_PERCENT + 2, "Image verified. Resetting, the bootloader installs it...")
        reply = _request(sock, addr, TYPE_RESET, session)  # no reply is fine: the board may already be resetting
        if reply is not None and reply["status"] != STATUS_OK:
            _abort_and_raise(sock, addr, session, "RESET", reply)

        time.sleep(1.0)
        after = _read_version(sock, addr, BOOT_WAIT_S)
        if after is None:
            raise UpdateError(f"The board did not answer within {BOOT_WAIT_S} s after RESET. The new image may "
                              f"still be installing: wait, then check the board before retrying.")
    report(100, f"Done: firmware {before} -> {after}")
    return before, after


def _request(sock, addr, ptype, session, seq=0, payload=b""):
    """Retransmit until the matching reply arrives (spec sec. 6); None after all retries.
    Replies for another session/seq/type or with a bad CRC are ignored."""
    packet = build_request(ptype, session, seq, payload)
    timeout_s, retries = RETRIES[ptype]
    for _ in range(retries + 1):
        sock.sendto(packet, addr)
        deadline = time.monotonic() + timeout_s
        while (left := deadline - time.monotonic()) > 0:
            sock.settimeout(left)
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                break
            reply = parse_reply(data)
            if (reply and reply["type"] == ptype | REPLY_FLAG and reply["session"] == session
                    and reply["seq"] == seq and reply["crc32"] == packet_crc(data)):
                return reply
    return None


def _read_version(sock, addr, wait_s):
    """Version via the ASCII command path, None if no answer."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        sock.sendto(VERSION_COMMAND, addr)
        sock.settimeout(1.0)
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            continue
        text = data.split(b";")[0].decode(errors="replace")
        if text.startswith("FW_Ver."):
            return text[len("FW_Ver."):].strip()
    return None


def _abort_and_raise(sock, addr, session, what, reply):
    """ABORT withdraws a possible pending mark on the board."""
    _request(sock, addr, TYPE_ABORT, session)
    if reply is None:
        raise UpdateError(f"{what}: no reply. Nothing was installed.")
    status = _name(STATUS_NAMES, reply["status"])
    state = _name(STATE_NAMES, reply["state"])
    raise UpdateError(f"{what}: {status} (board state {state}). Nothing was installed.")


def _name(names, code):
    return names[code] if 0 <= code < len(names) else f"code {code}"


def _send_image(sock, addr, image, report):
    """START, DATA chunks, FINISH. Afterwards the board is READY with pending set."""
    session = random.randint(1, 0xFFFE)

    reply = _request(sock, addr, TYPE_START, session,
                     payload=START_PAYLOAD.pack(IMAGE_SIZE, CHUNK_SIZE, 0, image_crc(image)))
    if reply is None or reply["status"] != STATUS_OK:
        _abort_and_raise(sock, addr, session, "START", reply)

    seq, out_of_order, shown = 0, 0, -1
    while True:
        while seq < CHUNK_COUNT:
            reply = _request(sock, addr, TYPE_DATA, session, seq, chunk(image, seq))
            if reply is None:
                _abort_and_raise(sock, addr, session, f"DATA {seq}", None)
            if reply["status"] == STATUS_OK:
                out_of_order = 0
            elif reply["status"] == STATUS_OUT_OF_ORDER and out_of_order < MAX_OUT_OF_ORDER:
                out_of_order += 1                     # board tells where to go on
            else:
                _abort_and_raise(sock, addr, session, f"DATA {seq}", reply)
            seq = reply["next_seq"]
            percent = seq * TRANSFER_PERCENT // CHUNK_COUNT
            if percent != shown:
                shown = percent
                report(percent, f"Sending image: {seq}/{CHUNK_COUNT} chunks")

        report(TRANSFER_PERCENT, "Verifying the image on the board...")
        reply = _request(sock, addr, TYPE_FINISH, session)
        if reply is not None and reply["status"] == STATUS_OK:
            return session
        if reply is not None and reply["status"] == STATUS_OUT_OF_ORDER and out_of_order < MAX_OUT_OF_ORDER:
            out_of_order += 1
            seq = reply["next_seq"]                   # chunks missing: send from there
            continue
        _abort_and_raise(sock, addr, session, "FINISH", reply)
