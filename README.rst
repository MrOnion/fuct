====================================
FUCT - FreeEMS Unified Console Tools
====================================

``fuct`` is a set of command line tools used to operate the FreeEMS firmware. The tools included are:

fuctloader
    This tool lets you operate the firmware (S19) files. It is mostly used to load a new file into the device using the dedicated serial monitor.

    Features:
        * Check device for correct MCU and serial monitor
        * Validate S19 firmware file
        * Load S19 firmware file with or without verification
        * Rip S19 firmware from device
        * Erase device

fuctlogger
    This tool can be used to collect data from the device for further analysis. When the device is in run mode it streams data into the serial port.

    Features:
        * Saves data from the device into binary logfiles (can be used with OLV/ULV log viewer apps)
        * Size limit to split/rotate into multiple files
        * Uses bz2 to compress logfiles when logger is stopped or file is rotated
        * Reads and stores metadata from device at startup
        * Does full interrogation on startup (data is not used at the moment)
        * Prefix option to name logfiles accordingly

fucttrigger
    This tool is used when you have a fresh FreeEMS install and need to adjust the trigger offset before doing any further tuning (important!).

    **The trigger tool is considered experimental. Use at your own risk.**

    Features:
        * Set the initial firmware trigger angle into flash
        * Adjust the trigger angle on-the-fly (Flash only, RAM not available yet)
        * Shortcut keys for 0.1 and 1.0 deg steps

Build
-----

This project uses `PyBuilder <http://pybuilder.github.io/>` as a build tool. Just type:

.. code-block:: bash

    $ pyb

If the build is successful the result can be found in: target/dist/fuct-<version>

Install
-------

Build first. Use the distutils setup.py installation script in the generated dist folder:

.. code-block:: bash

    $ cd target/dist/fuct-<version>
    $ python setup.py install

Dependencies
------------

* pyserial >=2.7
* futures >= 3.0.3
* colorlog >=2.0.0

Examples
---------------

To check if your device is compatible with the FreeEMS firmware run the ``device`` command with serial port ``-s`` option:

    .. code-block:: bash

        $ fuctloader -s /dev/tty.usbserial device

    It will first check if the device ID is supported. Other commands that communicate with the device will perform
    this same task before going further.

    If the device is supported the serial monitor is ripped from the device and compared to a support list. If the serial
    monitor is supported the name and version will be printed. If the serial monitor is unknown you can use debugging
    ``-d`` option to get more information.

To validate firmware files without having the device connected you can use the ``check`` command:

    .. code-block:: bash

        $ fuctloader check MyFirmware.S19

    This will parse all the S-records and print information.

To load the firmware into the device run the ``load`` or ``fastload`` command with serial port ``-s`` option:

    .. code-block:: bash

        $ fuctloader -s /dev/tty.usbserial load MyFirmware.S19

    The ``load`` will verify every memory page that is written to the device. With ``fastload`` the verification is skipped
    and therefore is faster.

To rip the present firmware from the device run the ``rip`` command with serial port ``-s`` option:

    .. code-block:: bash

        $ fuctloader -s /dev/tty.usbserial rip MyRippedFirmware.s19

    The memory pages from the device are ripped and stored into the specified file in S-record format.

To erase the memory pages in the device use the ``erase`` command with serial port ``-s`` option:

    .. code-block:: bash

        $ fuctloader -s /dev/tty.usbserial erase

    The memory range used by the firmware is cleaned page by page. The serial monitor itself will remain in the device and
    is not erased.

To log binary data into a prefixed file with 50 Mb size limit:

    .. code-block:: bash

        $ fuctlogger -p /home/user/freeems-logs -x testcar1 -s 10M /dev/tty.serial

    This will create files with maximum size of 10Mb. The filename is prefixed and date + starttime is added: ``testcar1-20140627-124507.bin``



License
-------
Copyright (c) 2014 Ari Karhu. See the LICENSE file for license rights and limitations (MIT).

