# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import sys
import logging
import binascii
import hashlib
import common
from time import sleep
from struct import pack, unpack_from
from serial import SerialTimeoutException
from srecord import SRecord, STYPES

LOG = logging.getLogger('fuctlog')


class SMResponse():
    def __init__(self, response, status, data=None):
        self.response_code = response
        self.status_code = status
        self.data = data[:]  # Copy data

    def __str__(self):
        return "SM response code 0x%02x, status code 0x%02x, data %d bytes" % \
               (self.response_code if self.response_code is not None else 0,
                self.status_code if self.status_code is not None else 0,
                len(self.data))


class SMDevice():
    # Motorola/Freescale serial monitor command characters
    # application note AN2548

    # TODO: implement common progress bar for load, rip and erase tasks

    SM_OPEN = 0x0D  # Carriage return
    SM_PROMPT = 0x3E  # > Prompt symbol
    SM_PPAGE = 0x30  # 0

    SM_DEVICE_IDX = 0x06F8
    SM_MONTH_IDX = 0x06FA
    SM_DAY_IDX = 0x06FB
    SM_YEAR_IDX = 0x06FC
    SM_VERSION_IDX = 0x06FE

    # Commands
    CMD_READ_BYTE = 0xA1
    CMD_WRITE_BYTE = 0xA2
    CMD_READ_WORD = 0xA3
    CMD_WRITE_WORD = 0xA4
    CMD_READ_NEXT = 0xA5
    CMD_WRITE_NEXT = 0xA6
    CMD_READ_BLOCK = 0xA7
    CMD_WRITE_BLOCK = 0xA8
    CMD_READ_REGS = 0xA9
    CMD_WRITE_SP = 0xAA
    CMD_WRITE_PC = 0xAB
    CMD_WRITE_IY = 0xAC
    CMD_WRITE_IX = 0xAD
    CMD_WRITE_D = 0xAE
    CMD_WRITE_CCR = 0xAF

    CMD_GO = 0xB1
    CMD_TRACE_ONE = 0xB2
    CMD_HALT = 0xB3
    CMD_RESET = 0xB4
    CMD_ERASE_RANGE = 0xB5  # Not implemented in SM
    CMD_ERASE_ALL = 0xB6
    CMD_DEVICE_INFO = 0xB7
    CMD_ERASE_PAGE = 0xB8
    CMD_ERASE_EEPROM = 0xB9

    # Response codes
    RC_NO_ERROR = 0xE0
    RC_NOT_RECOGNISED = 0xE1
    RC_NOT_ALLOWED_IN_RUN_MODE = 0xE2
    RC_STACK_POINTER_OUT_OF_RANGE = 0xE3
    RC_INVALID_SP_VALUE = 0xE4
    RC_ACCESS_TO_NON_VOLATILE = 0xE5
    RC_FLASH_ERROR = 0xE6
    # 0xE7 and 0xE8 not implemented in SM
    RC_EEPROM_ERROR = 0xE9

    # Status codes
    SC_MONITOR_ACTIVE = 0x00
    SC_USER_PROGRAM_RUNNING = 0x01
    SC_USER_PROGRAM_HALTED = 0x02
    SC_TRACE_ONE_RETURNED = 0x04
    SC_COLD_RESET_EXECUTED = 0x08
    SC_WARM_RESET_EXECUTED = 0x0C

    # Misc
    DEVICE_INFO_CONSTANT = 0xDC
    BLOCK_SIZE = 256

    # SM versions TODO: add more versions
    SM_VERSIONS = {
        'e886a55bf927f9c86cad5d26ca41ba88': 'Motorola SM v2.2 (with USB hack)'
    }

    def __init__(self, ser):
        self.ser = ser
        self.ns_per_byte = 86805  # 10 ^ 6ns / 115200 * 10 = 86.805ns per byte

    # Highlevel commands

    @property
    def check_device(self):
        resp = self.__device_info()
        if len(resp.data) == 3:
            cid = ord(resp.data[0])
            if cid == self.DEVICE_INFO_CONSTANT:
                device_id = unpack_from('>H', resp.data, 1)[0]
                LOG.debug("Device ID: 0x%04x" % device_id)
                device = self.__parse_device_info(device_id)
                if device[0] == 0x0C:
                    LOG.info("Device is S12X/XE family")
                    if device[1] == 0x04 and device[2] == 1 and 0 <= device[3] <= 2:
                        LOG.info("Device looks FreeEMS compatible :)")
                        return True
                    elif 1 >= device[1] >= 0 == device[2]:
                        LOG.warn("Device looks FreeEMS compatible, but with wrong maskset :/")
                    elif device[1] == 0x0C and (device[2] == 8 or device[2] == 9) and 0 <= device[3] <= 2:
                        LOG.warn("Device looks XEP100 (Megasquirt-III?)")
                    else:
                        LOG.warn("Device is not FreeEMS compatible :(")
                elif device[0] == 0x03:
                    LOG.warn("Device is S12C family (Megasquirt-II/Microsquirt?)")
                else:
                    LOG.error("Device is unknown family")
                return False
            else:
                raise ValueError("Invalid device info constant (0x%02x), should be 0x%02x" % (cid, self.DEVICE_INFO_CONSTANT))
        else:
            raise ValueError("Invalid device info size (%d bytes), should be 3 bytes" % len(resp))

    def analyse_device(self, rip=False):
        # TODO: Interim serialmonitor ripper solution (should make S19 files)
        if rip:
            sm_file = open('serialmonitor.dat', 'w')
            sm_file.write("# Ripped serialmonitor range (F800-FF00)\n# Format: <memory address>:::<hexdata (256 bytes)>\n")
        smdata = bytearray()
        for addr in range(0xF800, 0x10000, 256):
            resp = self.__read_block(addr, 0xFF)
            smdata += resp.data
            if rip:
                sm_file.write("%04x:::%s\n" % (addr, binascii.hexlify(resp.data)))
        if rip:
            sm_file.close()

        if len(smdata) != 2048:
            raise ValueError('Invalid SM size (%d bytes), should be 2k' % len(smdata))

        m = hashlib.md5()
        m.update(smdata)
        sm_hash = binascii.hexlify(m.digest())
        LOG.debug('SM MD5: %s' % sm_hash)
        info = self.SM_VERSIONS.get(sm_hash)
        if info is not None:
            LOG.info('SM Identified as: %s' % info)
        else:
            LOG.warning('SM is not recognized, use debug mode to get more info')

        LOG.debug('SM Device ID: 0x%02x%02x' % (smdata[self.SM_DEVICE_IDX], smdata[self.SM_DEVICE_IDX + 1]))
        LOG.debug('SM Date: %02x/%02x/%02x%02x' % (smdata[self.SM_MONTH_IDX], smdata[self.SM_DAY_IDX], smdata[self.SM_YEAR_IDX], smdata[self.SM_YEAR_IDX + 1]))
        LOG.debug('SM Version: %x.%x' % (smdata[self.SM_VERSION_IDX], smdata[self.SM_VERSION_IDX + 1]))

        return True

    def erase_and_write(self, mempage, erase=True, verify=True):
        if mempage.address < 0x8000 or mempage.address >= 0xC000:
            raise ValueError('Address 0x%04x is out of range for page 0x%02x' % (mempage.address, mempage.page))

        if len(mempage.data) > 0xC000 - mempage.address:
            raise ValueError('Invalid amount of data (%d bytes), will overflow page 0x%02x @ 0x%04x' %
                             (len(mempage.data), mempage.page, mempage.address))

        if erase:
            self.__set_page(mempage.page)
            self.__erase_page()

        blocks = len(mempage.data) / self.BLOCK_SIZE
        trailing = len(mempage.data) % self.BLOCK_SIZE
        start_block = 0
        start_addr = mempage.address

        for block in range(0, blocks):
            block_data = mempage.data[start_block:start_block + self.BLOCK_SIZE]
            start_block += self.BLOCK_SIZE

            self.__write_block(start_addr, block_data)

            if verify:
                read_back = self.__read_block(start_addr, self.BLOCK_SIZE - 1)
                if block_data != read_back.data:
                    raise ValueError('Verification failed @ 0x%04x' % start_addr)

            start_addr += self.BLOCK_SIZE

        if trailing > 0:  # TODO: add trailing write to for loop and verify
            block_data = mempage.data[-trailing:]
            self.__write_block(start_addr, block_data)

    def rip_pages(self, start, end, filepath):
        last = end + 1
        pages = last - start

        f = open(filepath, 'a+')

        # Add S0 header record
        f.write(SRecord(STYPES['S0'], bytearray([0x00, 0x00]), binascii.hexlify("S19 ripped by fuct")).print_srec() + '\r\n')

        for i, page in enumerate(xrange(start, last)):
            addr = 0x8000
            rec_len = 16
            progress = float(i) / pages
            common.print_progress(progress)
            self.__set_page(page)
            page_data = binascii.hexlify(self.__read_page()).upper()

            # Split data into lines of readable length and stringify
            records = ''
            while len(page_data):
                rec_data = page_data[:rec_len * 2]
                records += SRecord(STYPES['S2'], bytearray([page, (addr >> 8) & 0xFF, addr & 0xFF]), rec_data).print_srec() + '\r\n'
                addr += len(rec_data) // 2
                page_data = page_data[rec_len * 2:]

            if len(records):
                f.write(records)

        # Add execution start address record
        f.write(SRecord(STYPES['S8'], bytearray([0x00, 0xC0, 0x00])).print_srec() + '\r\n')

        f.close()

        sys.stdout.write("\r")
        sys.stdout.flush()
        LOG.info("Firmware ripped successfully")

    def erase_pages(self, start, end):
        total = end - start
        last = end + 1
        counter = 0
        for page in xrange(start, last):
            self.__set_page(page)
            self.__erase_page()
            if LOG.getEffectiveLevel() == logging.INFO:
                progress = float(counter) / total
                common.print_progress(progress)
            counter += 1
        if LOG.getEffectiveLevel() == logging.INFO:
            sys.stdout.write("\r")
            sys.stdout.flush()

        LOG.info("Firmware erased successfully")

        return True

    def reinit(self):
        if self.__reset() is not None:
            if self.__open_comm() is not None:
                return True
        return None

    # -----

    @staticmethod
    def __get_addr_data(addr, data):
        return pack('>HB', int(addr), data)

    def __read_page(self):
        addr = 0x8000
        data = bytearray()

        for page in range(0, 64):
            resp = self.__read_block(addr, 0xFF)
            data += resp.data
            #if LOG.getEffectiveLevel() == logging.INFO:
            #    progress = float(page) / 64
            #    common.print_progress(progress)
            addr += 256
        #if LOG.getEffectiveLevel() == logging.INFO:
        #    sys.stdout.write("\r")
        #    sys.stdout.flush()

        #LOG.info("Firmware ripped successfully")

        return data

    def __set_page(self, page):
        self.__write_byte(self.SM_PPAGE, page)

    def __erase_page(self):
        # 330ms read delay can be a bit lower but this should be safe
        return self.__write_and_read(3, self.CMD_ERASE_PAGE, 330)

    def __device_info(self):
        return self.__write_and_read(6, self.CMD_DEVICE_INFO)

    def __reset(self):
        if self.__write_command(self.CMD_RESET) is not None:
            rdata = self.__get_data_after_wait(5, 2)
            if len(rdata) <= 1:
                return SMResponse(None, None, rdata)
        return None

    def __open_comm(self):
        if self.__write_command(self.SM_OPEN) is not None:
            rdata = self.__get_data_after_wait(4)
            if self.__check_open_response(rdata, 1 if len(rdata) == 4 else 0) is not None:
                return True
        return None

    def __write_command(self, cmd, args=None):
        try:
            self.ser.flushInput()
            LOG.debug("--> 0x%02x" % cmd)
            cmd_bytes = self.ser.write(chr(cmd))
            if cmd_bytes > 0:
                if args is not None:
                    LOG.debug("--> %s" % binascii.hexlify(args))
                    arg_bytes = self.ser.write(args)
                    if arg_bytes > 0:
                        return cmd_bytes + arg_bytes
                    else:
                        LOG.error("Sending command arguments failed (0 bytes written).")
                        return None
                return cmd_bytes
            else:
                LOG.error("Sending command failed (0 bytes written).")
        except SerialTimeoutException:
            LOG.error("Serial timeout occured when sending command. Check port connection.")
        return None

    def __write_byte(self, addr, byte):
        args = self.__get_addr_data(addr, byte)
        return self.__write_and_read(3, self.CMD_WRITE_BYTE, 0, args)

    def __read_block(self, addr, length):
        return self.__write_and_read(length + 4, self.CMD_READ_BLOCK, 0, self.__get_addr_data(addr, length))

    def __write_block(self, addr, data):
        if len(data) > self.BLOCK_SIZE:
            LOG.error("Block has %d bytes, needs to be 256 bytes or less" % len(data))
            return None

        args = self.__get_addr_data(addr, len(data) - 1)
        args += data

        return self.__write_and_read(3, self.CMD_WRITE_BLOCK, 0, args)

    def __write_and_read(self, resp_length, command, wait_ms=0, args=None):
        if resp_length < 3:
            LOG.error('Response for command %d must have at least 3 bytes' % command)
            return None

        if self.__write_command(command, args) is not None:
            offset = resp_length - 3
            sent_bytes = 1 if args is None else len(args) + 1
            total_bytes = sent_bytes + resp_length
            rdata = self.__get_data_after_wait(total_bytes, wait_ms)

            return self.__check_response(rdata, offset if len(rdata) == resp_length else 0)
        return None

    def __get_data_after_wait(self, total_bytes, wait_ms=0):
        if total_bytes <= 0:
            LOG.warning("Requested total bytes of response is zero or less.")

        # Sleep at least 1 ms before reading. Remember sleep operation is OS specific and cannot be guaranteed
        # to be accurate. Use ns_per_byte to fine tune the read delay per byte.
        pre_sleep = (float(total_bytes * self.ns_per_byte) / 1000000) + wait_ms
        LOG.debug("~ %.2f ms (%d bytes)" % (pre_sleep, total_bytes))
        sleep(pre_sleep / 1000 if pre_sleep > 1 else 1)

        data = self.ser.read(total_bytes)
        LOG.debug("<-- %s" % binascii.hexlify(data))
        return data

    def __check_open_response(self, data, offset=0):
        if len(data) < 3:
            LOG.error('Invalid open response (too few bytes)')
            return None

        resp = tuple([ord(x) for x in data[offset:offset + 3]])
        if resp == (self.RC_NO_ERROR, self.SC_COLD_RESET_EXECUTED, self.SM_PROMPT) or \
                resp == (self.RC_NOT_RECOGNISED, self.SC_MONITOR_ACTIVE, self.SM_PROMPT):
            return SMResponse(resp[0], resp[1], data)

        LOG.error('Invalid open response, is device in load/SM mode?')
        return None

    def __check_response(self, data, offset):
        if len(data) < offset + 3:
            LOG.error('Invalid response (too few bytes)')
            return None

        resp = tuple([ord(x) for x in data[offset:offset + 3]])
        if resp == (self.RC_NO_ERROR, self.SC_MONITOR_ACTIVE, self.SM_PROMPT):
            return SMResponse(resp[0], resp[1], data[:-3])

        LOG.error('Invalid response (no prompt or unrecognized command)')
        return None

    # Helpers

    @staticmethod
    def __parse_device_info(device_id):
        """
        The coding is as follows and is converted to a tuple:
        Bit 15-12: Major family identifier
        Bit 11-6: Minor family identifier
        Bit 5-4: Major mask set revision number including FAB transfers
        Bit 3-0: Minor — non full — mask set revision
        """
        return (device_id >> 12), (device_id >> 8 & 0x0F), (device_id >> 4 & 0x0F), (device_id & 0x0F)