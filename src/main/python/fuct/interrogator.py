# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import binascii
import struct
try:
    import queue
except ImportError:
    import Queue as queue
from . import log
from collections import namedtuple
from .protocol import Protocol

LOG = log.fuct_logger('fuctlog')


class Interrogator(object):

    def __init__(self, ser, queue_in, queue_out):
        self.ser = ser
        self.queue_in = queue_in
        self.queue_out = queue_out

    def get_metadata(self):
        meta_cmds = [
            ("interface", Protocol.FE_CMD_INTERFACE),
            ("firmware", Protocol.FE_CMD_FIRMWARE),
            ("decoder", Protocol.FE_CMD_DECODER),
            ("build_date", Protocol.FE_CMD_BUILDDATE),
            ("compiler", Protocol.FE_CMD_COMPILER),
            ("os", Protocol.FE_CMD_OSNAME),
            ("build_by", Protocol.FE_CMD_USER),
            ("email", Protocol.FE_CMD_EMAIL)
        ]
        meta = {}
        location_ids = None

        for _, cmd in meta_cmds:
            self.queue_out.put(Protocol.create_packet(cmd))

        self.queue_out.put(Protocol.create_packet(Protocol.FE_CMD_LOCATION_ID_LIST, data=bytearray(b'\x00\x00\x00'), use_length=True))

        while True:
            if all(name in meta for name, _ in meta_cmds) and location_ids is not None:
                break

            try:
                if not self.queue_out.empty():
                    packet = self.queue_out.get(False)
                    LOG.debug("--> %s" % binascii.hexlify(packet[1:-2]))
                    self.ser.write(packet)
                    self.ser.flush()

                    resp = self.queue_in.get()
                    LOG.debug("<-- %s" % binascii.hexlify(resp))
                    data = Protocol.decode_packet(resp)

                    # FIXME: hax, make more elegant
                    meta_info = [(name, data[1].decode("ascii").rstrip('\0')) for name, cmd_id in meta_cmds if cmd_id + 1 == data[0]]
                    if meta_info:
                        m = meta_info[0]
                        LOG.debug("Received meta: %s" % m[0])
                        meta[m[0]] = m[1]
                    elif data[0] == Protocol.FE_CMD_LOCATION_ID_LIST + 1:
                        ids = len(data[1]) / 2
                        LOG.debug("Received %d location IDs" % ids)
                        location_ids = struct.unpack_from(">%dH" % ids, data[1])

                    # TODO: error message handling

            except queue.Empty:
                pass

        return meta, location_ids

    def get_location_info(self, location_id):
        LOG.debug("Get location info: 0x%02x" % location_id)
        packet = Protocol.create_packet(Protocol.FE_CMD_LOCATION_ID_INFO, data=struct.pack(">H", location_id))
        LOG.debug("--> %s" % binascii.hexlify(packet[1:-2]))
        self.ser.write(packet)
        self.ser.flush()

        locinfo = namedtuple('LocationInfo', ['flags', 'parent', 'ram_page', 'flash_page', 'ram_addr', 'flash_addr', 'size'])
        resp = self.queue_in.get(5)
        if resp:
            LOG.debug("<-- %s" % binascii.hexlify(resp))
            data = Protocol.decode_packet(resp)
            if data[0] == Protocol.FE_CMD_LOCATION_ID_INFO + 1:
                return locinfo(*struct.unpack_from(">HHBBHHH", data[1]))
        else:
            LOG.warn("Failed to load location...")

    def get_ram_data(self, location, size):
        LOG.debug("Get RAM location: 0x%02x, offset: %d, size: %d" % (location[0], location[1], size))
        packet = Protocol.create_packet(Protocol.FE_CMD_RAM_READ, location, size)
        LOG.debug("--> %s" % binascii.hexlify(packet[1:-2]))
        self.ser.write(packet)
        self.ser.flush()

        resp = self.queue_in.get(5)
        if resp:
            LOG.debug("<-- %s" % binascii.hexlify(resp))
            data = Protocol.decode_packet(resp)
            if data[0] == Protocol.FE_CMD_RAM_READ + 1:
                return data[1]
        else:
            LOG.warn("Failed to load location...")

    def get_flash_data(self, location, size):
        LOG.debug("Get FLASH location: 0x%02x, offset: %d, size: %d" % (location[0], location[1], size))
        packet = Protocol.create_packet(Protocol.FE_CMD_FLASH_READ, location, size)
        LOG.debug("--> %s" % binascii.hexlify(packet[1:-2]))
        self.ser.write(packet)
        self.ser.flush()

        resp = self.queue_in.get(5)
        if resp:
            LOG.debug("<-- %s" % binascii.hexlify(resp))
            data = Protocol.decode_packet(resp)
            if data[0] == Protocol.FE_CMD_FLASH_READ + 1:
                return data[1]
        else:
            LOG.warn("Failed to load location...")