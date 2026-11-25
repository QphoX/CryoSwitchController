"""Labphox UDP image download protocol v1: packet format and image handling (docs/udp-image-download.md).

Used by the bench test udp_download_test.py. It is also the reference implementation for the host
side, which lives in the Labphox application (separate repository) and sends ready-made update.bin files.
Packets only, no sockets and no policy. Python standard library only.
"""
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

__all__ = [
    "MAGIC0", "MAGIC1", "VERSION", "HEADER", "REPLY_PAYLOAD", "START_PAYLOAD", "HEADER_SIZE", "REPLY_SIZE",
    "MAX_REQUEST", "REPLY_FLAG", "CRC_FIELD", "IMAGE_SIZE", "CHUNK_SIZE", "CHUNK_COUNT", "TRAILER_OFFSET",
    "STATUS_OFFSET", "TYPE_START", "TYPE_DATA", "TYPE_FINISH", "TYPE_ABORT", "TYPE_RESET", "TYPE_STATUS",
    "STATUS_OK", "STATUS_BAD_LENGTH", "STATUS_BAD_SESSION", "STATUS_BAD_STATE", "STATUS_OUT_OF_ORDER",
    "STATUS_FLASH_ERROR", "STATUS_VERIFY_FAILED", "STATUS_BAD_IMAGE", "STATUS_BAD_VERSION", "STATUS_NAMES",
    "STATE_IDLE", "STATE_RECEIVING", "STATE_READY", "STATE_ERROR", "STATE_NAMES",
    "packet_crc", "build_request", "start_packet", "parse_reply", "image_crc", "chunk", "load_image",
]

# ---- Packet format (spec sec. 3) ------------------------------------------------
MAGIC0, MAGIC1, VERSION = 0xA5, 0x5A, 1
HEADER = struct.Struct("<BBBBHHII")    # magic0 magic1 version type session length seq crc32
REPLY_PAYLOAD = struct.Struct("<BBHI")  # status state reserved next_seq
START_PAYLOAD = struct.Struct("<IHHI")  # total_size chunk_size reserved image_crc32
HEADER_SIZE = HEADER.size              # 16
REPLY_SIZE = HEADER_SIZE + REPLY_PAYLOAD.size   # 24
MAX_REQUEST = 1040                     # 16 B header + 1024 B payload
REPLY_FLAG = 0x80                      # reply type = request type | 0x80
CRC_FIELD = 12                         # offset of crc32 in the header

TYPE_START, TYPE_DATA, TYPE_FINISH, TYPE_ABORT, TYPE_RESET, TYPE_STATUS = 0x01, 0x02, 0x03, 0x04, 0x05, 0x06

(STATUS_OK, STATUS_BAD_LENGTH, STATUS_BAD_SESSION, STATUS_BAD_STATE, STATUS_OUT_OF_ORDER, STATUS_FLASH_ERROR,
 STATUS_VERIFY_FAILED, STATUS_BAD_IMAGE, STATUS_BAD_VERSION) = range(9)
STATUS_NAMES = ["OK", "BAD_LENGTH", "BAD_SESSION", "BAD_STATE", "OUT_OF_ORDER", "FLASH_ERROR",
                "VERIFY_FAILED", "BAD_IMAGE", "BAD_VERSION"]

STATE_IDLE, STATE_RECEIVING, STATE_READY, STATE_ERROR = range(4)
STATE_NAMES = ["IDLE", "RECEIVING", "READY", "ERROR"]

# ---- Image (lpbl_layout.h, spec sec. 5) -----------------------------------------
IMAGE_SIZE = 393216                    # DOWNLOAD area = update.bin
CHUNK_SIZE = 1024
CHUNK_COUNT = IMAGE_SIZE // CHUNK_SIZE  # 384
TRAILER_OFFSET = 0x5FF00               # trailer in the image
STATUS_OFFSET = 0x5FFE0                # trailer status words: never written by the board, not in the CRC

MKIMAGE = Path(__file__).resolve().parents[2] / "tools" / "lpbl" / "mkimage.py"


def packet_crc(packet):
    """CRC-32 over header bytes 0..11, then everything after the 16 B header (spec sec. 3.1)."""
    return zlib.crc32(packet[HEADER_SIZE:], zlib.crc32(packet[:CRC_FIELD]))


def build_request(ptype, session, seq, payload=b"", version=VERSION, length=None):
    """Header with its crc32 filled in, followed by the payload.
    version and length can be overridden to build deliberately wrong (but CRC-correct) requests."""
    length = len(payload) if length is None else length
    packet = HEADER.pack(MAGIC0, MAGIC1, version, ptype, session, length, seq, 0) + payload
    return packet[:CRC_FIELD] + struct.pack("<I", packet_crc(packet)) + packet[CRC_FIELD + 4:]


def start_packet(session, image_crc32, total_size=IMAGE_SIZE, chunk_size=CHUNK_SIZE):
    return build_request(TYPE_START, session, 0, START_PAYLOAD.pack(total_size, chunk_size, 0, image_crc32))


def parse_reply(data):
    """Return the reply fields as a dict, or None if it is not 24 B."""
    if data is None or len(data) != REPLY_SIZE:
        return None
    m0, m1, ver, ptype, session, length, seq, crc = HEADER.unpack_from(data, 0)
    status, state, reserved, next_seq = REPLY_PAYLOAD.unpack_from(data, HEADER_SIZE)
    return dict(magic=(m0, m1), version=ver, type=ptype, session=session, length=length, seq=seq,
                crc32=crc, status=status, state=state, reserved=reserved, next_seq=next_seq)


def image_crc(image):
    """image_crc32 for START: everything before the trailer status words (spec sec. 5)."""
    return zlib.crc32(image[:STATUS_OFFSET])


def chunk(image, seq):
    return image[seq * CHUNK_SIZE:(seq + 1) * CHUNK_SIZE]


def load_image(path, fw_version="0.0.0"):
    """Returns (update.bin bytes, description). path is either a ready update.bin (exactly IMAGE_SIZE bytes)
    or an app .bin, which is wrapped here with tools/lpbl/mkimage.py --area download."""
    data = Path(path).read_bytes()
    if len(data) == IMAGE_SIZE:
        return data, f"{path} (update.bin)"
    sys.dont_write_bytecode = True                    # no __pycache__ next to mkimage.py
    spec = importlib.util.spec_from_file_location("mkimage", MKIMAGE)
    mkimage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mkimage)
    image = mkimage.make_area_image(data, "download", mkimage.parse_version(fw_version))
    return image, f"{path} ({len(data)} B app) + mkimage --area download --version {fw_version}"
