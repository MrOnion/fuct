# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import sys
import threading
try:
    import queue
except ImportError:
    import Queue as queue
from . import log

LOG = log.fuct_logger('fuctlog')


class RxThread(threading.Thread):
    def __init__(self, ser, queue_in, queue_log=None):
        super(RxThread, self).__init__()
        self.ser = ser
        self.buffer_size = 1024
        self.queue_in = queue_in
        self.queue_log = queue_log
        self.logging = False
        self._active = True

    def stop(self):
        self._active = False

    def run(self):
        in_packet = False
        in_escape = False
        outbuf = bytearray()

        LOG.debug("Starting RX thread")
        while self._active:

            # Incoming
            buf = self.ser.read(self.buffer_size)
            if sys.version_info[0] < 3:
                buf = bytearray(buf)

            for c in buf:
                if c == 0xAA:
                    if in_packet:
                        """ Start byte in the middle of a packet, start fresh """
                        in_escape = False
                        outbuf = bytearray()

                    in_packet = True

                elif c == 0xCC and in_packet:
                    in_packet = False

                    size = len(outbuf)
                    flags = outbuf[0]
                    payload = (outbuf[1] << 8) + outbuf[2]
                    length = 0
                    if flags == 0x01:
                        length = (outbuf[3] << 8) + outbuf[4]
                    checksum1 = outbuf.pop()

                    # Check checksum
                    checksum2 = sum(outbuf) & 0xff
                    if (size == length + 5) or (checksum1 == checksum2):
                        if payload == 0x191:  # log packet
                            try:
                                if self.logging and self.queue_log is not None:
                                    self.queue_log.put(outbuf[5:], False)
                            except queue.Full:
                                pass
                        else:
                            self.queue_in.put(outbuf)

                    outbuf = bytearray()

                else:
                    if in_packet and not in_escape:
                        """ Escape next byte """
                        if c == 0xBB:
                            in_escape = True
                        else:
                            outbuf.append(c)

                    elif in_packet and in_escape:
                        if c == 0x55:
                            outbuf.append(0xAA)
                        elif c == 0x44:
                            outbuf.append(0xBB)
                        elif c == 0x33:
                            outbuf.append(0xCC)

                        in_escape = False

        LOG.debug("Exiting RX thread")