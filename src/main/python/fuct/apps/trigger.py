# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import logging
import argparse
import serial
import time
import struct
import re
import binascii
import sys
try:
    import queue
except ImportError:
    import Queue as queue
from serial.serialutil import SerialException
from fuct import log, rx, protocol, __version__, __git__

LOG = log.fuct_logger('fuctlog')
ANGLE_FACTOR = 50.00
ANGLE_MAX = 719.98
QUEUE_SIZE_LOG = 50


def get_timing_values(rows):
    values = []
    for row in rows:
        values.append(struct.unpack('>H', row[54:56]))
    return to_angle(min(values)[0]), to_angle(max(values)[0])


def write_trigger_message(offset, flash=False):
    return protocol.Protocol.create_packet(
        protocol.Protocol.FE_CMD_RAM_WRITE if flash is False else protocol.Protocol.FE_CMD_FLASH_WRITE,
        location=protocol.Protocol.FE_LOCATION_TRIGGER,
        data=offset,
        size=2,
        use_length=True)


def read_trigger_message(flash=False):
    return protocol.Protocol.create_packet(
        protocol.Protocol.FE_CMD_RAM_READ if flash is False else protocol.Protocol.FE_CMD_FLASH_READ,
        location=protocol.Protocol.FE_LOCATION_TRIGGER,
        size=2)


def to_angle(value):
    return float(value) / ANGLE_FACTOR


def to_raw_angle(value):
    return round(float(value) * ANGLE_FACTOR)


def check_offset_arg(value):
    val = float(value)
    if val < 0 or val > ANGLE_MAX:
        raise argparse.ArgumentTypeError("Value %s is invalid, use 0-%.2f." % (val, ANGLE_MAX))
    return val


def execute():
    parser = argparse.ArgumentParser(
        prog='fucttrigger',
        description='''FUCT - FreeEMS Unified Console Tools, version: %s (Git: %s)

    'fucttrigger' is a tool to adjust the decoder trigger offset on a fresh FreeEMS install. You need a timinglight
    or a similar tool to check the correct alignment. Also make sure you use flat timing tables (ex. 10 deg BTDC) so
    you get a good consistent reading. An initial offset can be used to load it to the device when the application
    is started.

    Example: fucttrigger -o 90 /dev/ttyUSB0''' % (__version__, __git__),
        formatter_class=argparse.RawTextHelpFormatter,)
    parser.add_argument('-v', '--version', action='store_true', help='show program version')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug information')
    parser.add_argument('-o', '--offset', type=check_offset_arg, nargs='?', help='initial trigger offset in degrees ATDC (0-719.98)')
    parser.add_argument('serial', nargs='?', help='serialport device (eg. /dev/xxx, COM1)')

    args = parser.parse_args()

    if args.version:
        print("fucttrigger %s (Git: %s)" % (__version__, __git__))
    elif args.serial is not None:
        LOG.info("FUCT - fucttrigger %s (Git: %s)" % (__version__, __git__))
        rxThread = None
        try:
            if args.debug:
                LOG.setLevel(logging.DEBUG)

            LOG.info("Opening port %s" % args.serial)
            ser = serial.Serial(args.serial, 115200, bytesize=8, parity=serial.PARITY_ODD, stopbits=1)
            LOG.debug(ser)

            queue_in = queue.Queue(0)
            queue_out = queue.Queue(0)
            queue_log = queue.Queue(QUEUE_SIZE_LOG)

            ser.timeout = 0.02
            rxThread = rx.RxThread(ser, queue_in, queue_log)
            rxThread.buffer_size = 1024
            rxThread.logging = True
            rxThread.start()

            init = True
            offset_value = 0  # 1 unit = 0.02 deg
            queue_out.put(protocol.Protocol.create_packet(protocol.Protocol.FE_CMD_DECODER))
            updating = False

            while True:
                try:
                    time.sleep(0.2)
                    packet = queue_out.get(False)
                    LOG.debug("--> %s" % binascii.hexlify(packet[1:-2]))
                    ser.write(packet)
                    ser.flush()
                except queue.Empty:
                    pass

                try:
                    msg = queue_in.get(False)
                    LOG.debug("<-- %s" % binascii.hexlify(msg))
                    data = protocol.Protocol.decode_packet(msg)

                    if init:
                        if data[0] == protocol.Protocol.FE_CMD_DECODER + 1:
                            LOG.info("Decoder: %s" % data[1])
                            queue_out.put(read_trigger_message(flash=True))
                        if data[0] == protocol.Protocol.FE_CMD_FLASH_READ + 1:
                            offset_value = struct.unpack('>H', data[1])[0]
                            LOG.info("Current trigger offset in flash: %.2f deg" % to_angle(offset_value))
                            if args.offset is not None:
                                offset_value = to_raw_angle(args.offset)
                                LOG.info("Initial trigger offset: %.2f deg" % args.offset)
                                queue_out.put(write_trigger_message(struct.pack('>H', offset_value), flash=True))
                            LOG.info("Type a new value (0-%.2f) or use predefined commands" % ANGLE_MAX)
                            LOG.info("Commands: 'a' => +1, 'z' => -1, 's' => +10, 'x' => -10, 'd' => +0.1, 'c' => -0.1")
                            LOG.info("          'quit' or 'exit' => Exit program")
                            init = False
                    else:
                        if data[0] == protocol.Protocol.FE_CMD_FLASH_WRITE + 1:
                            LOG.info("Trigger offset set to: %.2f deg" % to_angle(offset_value))
                            updating = False

                except queue.Empty:
                    pass

                if not init and not updating:
                    log_rows = []
                    for x in range(0, QUEUE_SIZE_LOG):
                        log_rows.append(queue_log.get(x))
                    ign = get_timing_values(log_rows)
                    if ign[0] != ign[1]:
                        LOG.warning("Ignition advance is not steady, travels between %.2f <-> %.2f deg" % ign)

                    line = raw_input('>>> ') if sys.version_info[0] < 3 else input('>>> ')
                    offset_new = offset_value
                    if line == 'a':
                        offset_new += ANGLE_FACTOR
                    elif line == 'z':
                        offset_new -= ANGLE_FACTOR
                    elif line == 's':
                        offset_new += ANGLE_FACTOR * 10
                    elif line == 'x':
                        offset_new -= ANGLE_FACTOR * 10
                    elif line == 'd':
                        offset_new += ANGLE_FACTOR / 10
                    elif line == 'c':
                        offset_new -= ANGLE_FACTOR / 10
                    elif re.match("^(?=.*\d)\d{1,3}(?:\.\d{1,2})?$", line) is not None:
                        v = float(line)
                        if v >= 0 or v <= ANGLE_MAX:
                            offset_new = to_raw_angle(v)
                        else:
                            LOG.error("Invalid value, use 0-%.2f" % ANGLE_MAX)
                    elif line == '':
                        LOG.info("Advance: %.2f deg, Trigger offset: %.2f" % (ign[0], to_angle(offset_value)))
                    elif line == 'exit' or line == 'quit':
                        rxThread.stop()
                        LOG.info("Exiting...")
                        sys.exit(0)

                    if offset_new != offset_value:
                        offset_value = offset_new
                        LOG.debug("Raw offset value: %d" % offset_new)
                        queue_out.put(write_trigger_message(struct.pack('>H', int(offset_value)), flash=True))
                        updating = True

        except KeyboardInterrupt:
            rxThread.stop()
            LOG.info("Exiting...")
        except (NotImplementedError, AttributeError, ValueError, SerialException, OSError) as ex:
            LOG.error(ex)
    else:
        parser.print_usage()
