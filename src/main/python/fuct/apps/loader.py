# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import os
import argparse
import serial
import textwrap
import logging
import sys
import time
from serial.serialutil import SerialException
from fuct import common, log, serialmonitor, validator, pages, __version__, __git__

LOG = log.fuct_logger('fuctlog')


class CmdHandler:

    def __init__(self):
        pass

    def lookup_method(self, command):
        method = getattr(self, 'do_%s' % command.lower(), None)
        if callable(method):
            return method
        else:
            raise NotImplementedError('Command "%s" not implemented' % command)

    @staticmethod
    def is_ascii(s):
        return all(c < 128 for c in s)

    @staticmethod
    def get_device(port):
        LOG.info("Checking device...")
        dev = serialmonitor.SMDevice(port)
        if dev.reinit() is not None:
            if dev.check_device:
                return dev
        else:
            LOG.error("Reinitializing device failed.")

        raise ValueError("Device failed verification, won't proceed")

    @staticmethod
    def do_check(params):
        if params[1] is not None:
            if os.path.isfile(params[1]) and os.access(params[1], os.R_OK):
                LOG.info("Checking firmware...")
                records = validator.verify_firmware(params[1])
                if records:
                    LOG.info("Parsed %d records" % len(records))
                    if records[0].stype[0] == 'S0':
                        header = records[0].data if CmdHandler.is_ascii(records[0].data) else "[binary data]"
                        LOG.info("Header info: [%s]" % header)
                    else:
                        LOG.warning("No header...")
                    LOG.info("File OK")
                    return True
                else:
                    return False
            else:
                raise ValueError('Cannot find firmware file or no read access')

        raise ValueError('No firmware given')

    @staticmethod
    def do_device(params):
        if params[0] is not None:
            dev = CmdHandler.get_device(params[0])
            dev.analyse_device(rip=True)

            return True

        raise ValueError('serial port argument cannot be empty')

    @staticmethod
    def do_load(params, verify=True):
        if params[0] is not None and params[1] is not None:
            LOG.info("Checking firmware file...")
            records = validator.verify_firmware(params[1])
            if records is None:
                raise ValueError('Firmware file is corrupt or has no records, won\'t load')
            LOG.info("File OK, got %d records" % len(records))

            dev = CmdHandler.get_device(params[0])

            LOG.info("Converting records to memory pages...")
            header = records.pop(0)  # S0 Record
            termination = records.pop()  # S8 Record
            pagedata = pages.records_to_pages(records)
            pagelist = pagedata[0]
            LOG.info("Received %d pages" % len(pagelist))
            LOG.info("Loading firmware: '%s'" % str(header.data))

            last_page = None
            loaded_size = 0
            for page in pagelist:
                page_size = len(page.data)
                LOG.debug("%6d bytes to 0x%02x @ 0x%04x" % (page_size, page.page, page.address))
                dev.erase_and_write(page, erase=False if page.page == last_page else True, verify=verify)
                last_page = page.page
                loaded_size += page_size
                common.print_progress(float(loaded_size) / pagedata[1])

            sys.stdout.write("\r")
            sys.stdout.flush()
            LOG.info("Firmware loaded successfully")

            return True

        raise ValueError("Can't load sh*t captain, no file nor serial?!")

    @staticmethod
    def do_fastload(params):
        CmdHandler.do_load(params, False)
        return True

    @staticmethod
    def do_rip(params):
        filename = "rip-%s.s19" % time.strftime("%Y%m%d-%H%M%S")
        if params[0] is not None:
            dev = CmdHandler.get_device(params[0])
            LOG.info("Ripping pages from 0xE0 to 0xFF")
            dev.rip_pages(0xE0, 0xFF, filename)
            return True

        raise ValueError('serial port argument cannot be empty')

    @staticmethod
    def do_erase(params):
        if params[0] is not None:
            dev = CmdHandler.get_device(params[0])
            LOG.info("Erasing pages from 0xE0 to 0xFF")
            resp = dev.erase_pages(0xE0, 0xFF)  # TODO: get pages from device info

            return True

        raise ValueError('serial port argument cannot be empty')


def execute():
    parser = argparse.ArgumentParser(
        prog='fuctloader',
        description='''FUCT - FreeEMS Unified Console Tools, version: %s (Git: %s)

    'fuctloader' is a firmware loader application for FreeEMS. With this tool you can check your device info,
    validate S19 files and of course load, verify, rip and erase firmware data. You can also rip the serial
    monitor for further analysis.

    Example: fuctloader -s /dev/ttyUSB0 load testcar1-firmware.S19''' % (__version__, __git__),
        formatter_class=argparse.RawTextHelpFormatter,)
    parser.add_argument('-v', '--version', action='store_true', help='show program version')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug information')
    parser.add_argument('-s', '--serial', nargs='?', help='serialport device (eg. /dev/xxx, COM1)')
    parser.add_argument(
        'command',
        nargs='?',
        help=textwrap.dedent('''\
        command to execute. available commands:

        check      validate S19 firmware file (no device needed)
        device     poll device for correct device ID and serial monitor
        load       validate, load and verify firmware file into device
        fastload   load firmware file into device without any validation
        rip        rip firmware from device
        erase      erase device (serial monitor is not erased)

        '''))
    parser.add_argument('firmware', nargs='?', help='location and name of the S19 firmware file')

    args = parser.parse_args()

    if args.version:
        print "fuctloader %s (Git: %s)" % (__version__, __git__)
    elif args.command is not None:
        LOG.info("FUCT - fuctloader %s (Git: %s)" % (__version__, __git__))
        try:
            ser = None
            if args.debug:
                LOG.setLevel(logging.DEBUG)
            if args.serial is not None:
                LOG.info("Opening port %s" % args.serial)
                ser = serial.Serial(args.serial, 115200, timeout=0.02, bytesize=8, parity=serial.PARITY_NONE, stopbits=1)
                LOG.debug(ser)
            if CmdHandler().lookup_method(args.command)((ser, args.firmware)):
                LOG.info("Exiting...")
            else:
                LOG.error("Exiting on error")
        except NotImplementedError, ex:
            LOG.error(ex.message)
        except (AttributeError, ValueError), ex:
            LOG.error(ex.message)
        except SerialException, ex:
            LOG.error("Serial: " + ex.message)
        except OSError, ex:
            LOG.error("OS: " + ex.message)
    else:
        parser.print_usage()
