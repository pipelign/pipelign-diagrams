"""Entry point inside a private user/PID/network namespace; never an HTTP API."""

import ctypes
import fcntl
import os
import socket
import struct
import sys


def main():
    # Puppeteer communicates with Chromium over loopback. No other interface
    # exists in this namespace, so neither engine can reach the API or network.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        fcntl.ioctl(control, 0x8914, struct.pack("16sH22x", b"lo", 1))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(47, 4, 0, 0, 0) != 0:  # PR_CAP_AMBIENT_CLEAR_ALL
        raise OSError(ctypes.get_errno(), "Cannot clear namespace capabilities")

    class Header(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class Capabilities(ctypes.Structure):
        _fields_ = [
            ("effective", ctypes.c_uint32),
            ("permitted", ctypes.c_uint32),
            ("inheritable", ctypes.c_uint32),
        ]

    header = Header(0x20080522, 0)
    data = (Capabilities * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), "Cannot drop namespace capabilities")
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()
