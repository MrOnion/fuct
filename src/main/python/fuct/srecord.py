# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import binascii
from struct import unpack_from

STYPES = {
    'S0': ('S0', 2, True),
    'S1': ('S1', 2, True),
    'S2': ('S2', 3, True),
    'S3': ('S3', 4, True),
    'S5': ('S5', 2, False),
    'S7': ('S7', 4, False),
    'S8': ('S8', 3, False),
    'S9': ('S9', 2, False)
}

# FIXME: Add support for S5 2,3,4 byte address space


class SRecord(object):

    def __init__(self, stype, address, data=None):
        self.stype = stype
        self.address = address
        self.data = data
        # TODO: validate data and address

    def __str__(self):
        return "S-record (%s) @ <%s> with %d bytes" % (self.stype[0], binascii.hexlify(self.address), len(self.data))

    def get_page(self):
        if self.stype[0] != 'S2' or len(self.address) != 3:
            raise TypeError('Paging in %s records is not supported or not enough address bytes' % self.stype[0])

        return int(self.address[0])

    def get_page_address(self):
        if self.stype[0] != 'S2' or len(self.address) != 3:
            raise TypeError('Paging in %s records is not supported or not enough address bytes' % self.stype[0])

        return unpack_from('>H', self.address[-2:])[0]

    def print_srec(self):
        def srec_length():
            # Record length field includes address, data and checksum bytes
            address_length = self.stype[1]
            data_length = 0
            checksum_length = 1

            # Calculate data length if data is present
            if self.stype[2] and self.data is not None:
                data_length = int(len(self.data) // 2)

            return address_length + data_length + checksum_length

        def srec_checksum():
            # Checksum is calculated over length, address and data fields
            if len(self.address) != self.stype[1]:
                raise TypeError('Wrong number of address bytes for %s record type' % self.stype[0])

            checksum = srec_length()

            for address_byte in self.address:
                checksum += int(address_byte)

            # Checksum the data if present for this record type
            if self.stype[2]:
                rec_data = self.data
                while len(rec_data):
                    checksum += int(rec_data[:2], 16)
                    rec_data = rec_data[2:]

            checksum = int(255) - checksum
            checksum = checksum & int(255)

            return checksum

        srec_string = self.stype[0]
        srec_string += hex(srec_length()).upper()[2:].zfill(2)
        srec_string += str(binascii.hexlify(self.address)).upper()

        if self.stype[2] and self.data is not None:
            srec_string += str(self.data)

        srec_string += hex(srec_checksum())[2:].zfill(2).upper()

        return srec_string
