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