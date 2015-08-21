# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import sys
import logging
import argparse
import serial
import time
import math
import os
try:
    import queue
except ImportError:
    import Queue as queue
import json
import binascii
import bz2
import concurrent.futures as futures
from serial.serialutil import SerialException
from fuct import log, rx, interrogator, __version__, __git__

LOG = log.fuct_logger('fuctlog')
QUEUE_SIZE_LOG = 50


def compress_file(filename):
    comp = bz2.BZ2Compressor()
    src = open(filename, "rb")
    dst = open(filename + ".bz2", "wb")
    block = src.read(2048)
    while block:
        cblock = comp.compress(block)
        dst.write(cblock)
        block = src.read(2048)
    cblock = comp.flush()
    dst.write(cblock)
    src.close()
    dst.close()
    os.remove(filename)


def create_filename(prefix, path, tstamp=time.strftime("%Y%m%d-%H%M%S"), ext="bin", identifier="none"):
    name = "%s-%s-%s.%s" % (prefix if prefix is not None else "log", tstamp, identifier, ext)
    if path is not None:
        name = os.path.join(path, name)
    return name


def convert_sizelimit(limit):
    unit = limit[-1]
    size = limit[:-1]
    if size.isdigit():
        if unit == 'M':
            return int(size) * math.pow(1000, 2)
        if unit == 'G':
            return int(size) * math.pow(1000, 3)
        else:
            raise ValueError("Size has invalid unit (%s)" % unit)
    else:
        raise ValueError("Size (%s) is not numeric value" % size)


def busy_icon():
    while True:
        for cursor in '|/-\\':
            yield cursor


def execute():
    parser = argparse.ArgumentParser(
        prog='fuctlogger',
        description='''FUCT - FreeEMS Unified Console Tools, version: %s (Git: %s)

    'fuctlogger' is a logging tool for FreeEMS. It basically just collects streaming data from the FreeEMS device
    into a binary logfile. The logfile contains raw data which means that the serial protocol is not parsed. You
    can set a size limit so the logger will start a new logfile when the limit is exceeded. Also fixed path and
    filename prefix can be used. A date (ddmmYY-HHMMSS) is added into to the filename automatically.

    Example: fuctlogger -p /home/user/logs -x testcar1 -s 50M /dev/ttyUSB0''' % (__version__, __git__),
        formatter_class=argparse.RawTextHelpFormatter,)
    parser.add_argument('-v', '--version', action='store_true', help='show program version')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug information')
    parser.add_argument('-p', '--path', nargs='?', help='path for the logfile (default: ./)')
    parser.add_argument('-x', '--prefix', nargs='?', help='prefix for the logfile name (default: log)')
    parser.add_argument('-s', '--size', nargs='?', help='size of single logfile with unit (xxM/xxG) (default 128M)')
    parser.add_argument('serial', nargs='?', help='serialport device (eg. /dev/xxx, COM1)')

    args = parser.parse_args()

    if args.version:
        print("fuctlogger %s (Git: %s)" % (__version__, __git__))
    elif args.serial is not None:
        LOG.info("FUCT - fuctlogger %s (Git: %s)" % (__version__, __git__))
        ser = logfile = None
        try:
            if args.debug:
                LOG.setLevel(logging.DEBUG)

            LOG.info("Opening port %s" % args.serial)
            ser = serial.Serial(args.serial, 115200, bytesize=8, parity=serial.PARITY_ODD, stopbits=1)
            LOG.debug(ser)

            file_identifier = binascii.hexlify(os.urandom(3)).decode('ascii')
            timestamp = time.strftime("%Y%m%d-%H%M%S")

            basename = logname = create_filename(args.prefix, args.path, tstamp=timestamp, identifier=file_identifier)
            LOG.info("Opening logfile: %s" % logname)
            logfile = open(logname, 'wb+')

            metaname = create_filename("meta", args.path, ext="json", tstamp=timestamp, identifier=file_identifier)
            LOG.info("Opening metafile: %s" % metaname)
            metafile = open(metaname, 'w+')

            queue_in = queue.Queue(0)
            queue_out = queue.Queue(0)

            executor = futures.ThreadPoolExecutor(max_workers=1)

            ser.timeout = 0
            rxThread = rx.RxThread(ser, queue_in)
            rxThread.buffer_size = 64
            rxThread.start()

            # interrogation
            time1 = time.time()
            i = interrogator.Interrogator(ser, queue_in, queue_out)
            meta = i.get_metadata()
            LOG.info("Reading metadata and location IDs")
            meta_out = {'firmware': meta[0]}

            LOG.info("Reading location data")
            for lid in meta[1]:
                info = i.get_location_info(lid)
                if info.ram_page > 0:
                    ram_data = i.get_ram_data((lid, 0), info.size)
                    # FIXME: store data to json?
                if info.flash_page > 0:
                    flash_data = i.get_flash_data((lid, 0), info.size)
                    # FIXME: store data to json?

            LOG.info("Interrogation done (%.2f sec)" % (time.time() - time1))

            rxThread.stop()
            rxThread.join()

            LOG.info("Writing meta file")
            metafile.write(json.dumps(meta_out, sort_keys=True, indent=2))
            metafile.close()

            # logging
            ser.timeout = 0.02
            rxThread.buffer_size = 8196
            sizelimit = convert_sizelimit(args.size) if args.size is not None else 128000000
            LOG.info("Setting logfile size to: %d bytes" % sizelimit)

            LOG.info("Start logging... (Ctrl+C to quit)")
            spinner = busy_icon()
            logcounter = 1

            msg = None
            while True:
                buf = ser.read(128)

                if os.path.getsize(logname) >= sizelimit:
                    logfile.close()
                    executor.submit(compress_file, logfile.name)
                    logname = "%s.%d" % (basename, logcounter)
                    logfile = open(logname, 'w')
                    sys.stdout.flush()
                    sys.stdout.write('\b')
                    LOG.info("=> %s" % logname)
                    logcounter += 1

                logfile.write(buf)
                sys.stdout.write(next(spinner))
                sys.stdout.flush()
                sys.stdout.write('\b')
        except KeyboardInterrupt:
            LOG.info("Logging stopped")
            ser.close()
            logfile.close()
            LOG.info("Compressing logfile")
            compress_file(logfile.name)
            exit(0)
        except (NotImplementedError, AttributeError, ValueError, SerialException, IOError, OSError) as ex:
            LOG.error(ex)
    else:
        parser.print_usage()
