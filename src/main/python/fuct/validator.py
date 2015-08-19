# -*- coding: utf-8 -*-
#
# This file is part of fuct. Copyright (c) 2014 Ari Karhu.
# See the LICENSE file for license rights and limitations (MIT).
#

__author__ = 'ari'

import logging
from .srecord import SRecord, STYPES

LOG = logging.getLogger('fuctlog')


def verify_firmware(filepath):
    content = open(filepath).read()
    cr_count = content.count('\r')
    lf_count = content.count('\n')

    if lf_count > 0 and cr_count == 0:
        LOG.info("S19 file contains " + str(lf_count) + " lines (Unix)")
    elif lf_count == 0 and cr_count > 0:
        LOG.info("S19 file contains " + str(lf_count) + " lines (old Macintosh)")
    elif 0 < cr_count == lf_count:
        LOG.info("S19 file contains " + str(lf_count) + " lines (Windows)")
    elif 0 < lf_count != 0 < cr_count:
        LOG.warning("S19 file contains mixed EOL characters?!")
    elif lf_count == cr_count == 0:
        LOG.warning("S19 file contains no EOL chatacters?!")

    records = []
    for ln, line in enumerate(content.splitlines()):
        try:
            records.append(parse_line(line))
        except TypeError as ex:
            LOG.error("Line %d: %s" % (ln + 1, ex.message))
            return None

    return records


def parse_line(line):
    if len(line) == 0:
        raise TypeError('Blank line detected')
    if len(line) < 10:
        raise TypeError('Not enough characters to make up a minimal S19 record')
    if len(line) % 2 != 0:
        raise TypeError('Length of line is not even, must contain 2-byte hex pairs')
    if not line.islower() and not line.isupper():
        raise TypeError('Line contains mixed case characters')

    prefix = line[0] + line[1]
    if prefix not in STYPES:
        raise TypeError('Line did not begin with S0 record and end with S9 record')

    return parse_record(line)


def parse_record(line):
    stype = STYPES.get(line[:2])
    adata = bytearray(line[2:].decode("hex"))
    bytecount = ord(adata[:1])
    address = adata[1:stype[1]+1]  # FIXME: Add support for S5 2,3,4 byte address space
    data = adata[stype[1]+1:-1]
    checksum = ord(adata[-1:])

    if len(data) > 256:
        raise TypeError('Data too long (>256 bytes)')

    lrc = (sum(adata[:-1]) & 0xFF) ^ 0xFF
    if lrc != checksum:
        raise TypeError('Checksum mismatch')

    if bytecount != len(adata) - 1:
        raise TypeError('Count field mismatch')

    if stype[0] == 'S5' and len(data) > 4:
        raise TypeError('S5 records may only have 16, 24 or 32 bit unsigned byte count')
    elif stype[2] and len(data) == 0:
        raise TypeError('%s records need at least %i address bytes and data byte(s)' % (stype[0], stype[1]))
    elif not stype[2] and len(data) > 0:
        raise TypeError('%s records must only have %i bytes for its address' % (stype[0], stype[1]))

    return SRecord(stype, address, data)
