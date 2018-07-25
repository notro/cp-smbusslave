import os
import random
import subprocess
import sys
import time
import pytest
import cpboard

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def  at24slave_func(address):
    import board
    import busio
    import at24slave

    # Adapted from CPython
    class BytesIO:
        def __init__(self, initial_bytes):
            self._buffer = initial_bytes
            self._pos = 0

        def read(self, size):
            if len(self._buffer) <= self._pos:
                return b''
            newpos = min(len(self._buffer), self._pos + size)
            b = self._buffer[self._pos : newpos]
            self._pos = newpos
            return bytes(b)

        def write(self, b):
            n = len(b)
            pos = self._pos
            if n == 0 or pos + n > len(self._buffer):
                return 0
            self._buffer[pos:pos + n] = b
            self._pos += n

        def seek(self, pos, whence=0):
            if whence == 0:
                self._pos = pos
            elif whence == 2:
                if pos != 0:
                    raise ValueError("pos unsupported on whence==2")
                self._pos = max(0, len(self._buffer) + pos)
            else:
                raise ValueError("unsupported whence value")
            return self._pos

        def tell(self):
            return self._pos

    file = BytesIO(bytearray(128))
    at24 =  at24slave.AT24Slave(file)
    #at24.debug= True

    with busio.I2CSlave(board.SCL, board.SDA, (address,), smbus=False) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
                with r:
                    if r.address == address:
                        at24.process(r)
            except OSError as e:
                print('ERROR:', e)


address = 0x50

@pytest.fixture(scope='module')
def at24slave(board):
    server = cpboard.Server(board, at24slave_func, out=sys.stdout)
    server.start(address)
    time.sleep(1)
    yield server
    server.stop()


def sudo(cmd):
    print('sudo ' + cmd)
    if os.system('sudo ' + cmd) != 0:
        raise RuntimeError('Failed to sudo: %s' % (cmd,))

@pytest.fixture(scope='module')
def at24(request, at24slave):
    dev = '/sys/bus/i2c/devices/i2c-%d' % (request.config.option.i2cbus,)

    # Use a finalizer to ensure that teardown happens should an exception occur during setup
    def teardown():
        if os.path.exists(dev):
            sudo('sh -c "echo 0x%02x > %s/delete_device"; dmesg | tail' % (address, dev))
    request.addfinalizer(teardown)

    #sudo('/sbin/modprobe at24')
    sudo('sh -c "echo 24c01 0x%02x > %s/new_device" && dmesg | tail' % (address, dev))

    #return at24slave, '/sys/bus/i2c/devices/%d-%04x/eeprom' % (request.config.option.i2cbus, address)


@pytest.fixture(scope='module')
def at24_eeprom(request, at24):
    fname = '/sys/bus/i2c/devices/%d-%04x/eeprom' % (request.config.option.i2cbus, address)
    sudo('chmod 666 %s' % (fname,))
    return fname


def readreg(bus, address, reg):
    sys.stdout.write("Read 0x%02x: 0x%02x==" % (address, reg))
    val = bus.read_byte_data(address, reg)
    sys.stdout.write("0x%02x\n" % (val))
    return val


def writereg(bus, address, reg, val):
    print("Write 0x%02x: 0x%02x=0x%02x" % (address, reg, val))
    bus.write_byte_data(address, reg, val)


primes54 = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251]

@pytest.mark.parametrize('pos', [0, 1, 2, 3, 4, 10, 32])
@pytest.mark.parametrize('data',
    [
        [0x44],
        [0x00, 0x01,],
        [0x35, 0x56, 0x67,],
        [0x21, 0x34, 0x04, 0x12, 0x89, 0xde, 0x04, 0xfe, 0x00, 0xff],
        primes54[:32],
        primes54 + primes54[:10],
    ]
)
def test_eeprom(at24slave, at24_eeprom, pos, data):
    server = at24slave
    fname = at24_eeprom

    b = bytes(data)

    try:
        with open(fname, 'wb') as f:
            f.seek(pos)
            f.write(b)

        with open(fname, 'rb') as f:
            f.seek(pos)
            res = f.read(len(b))
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        server.check()

    assert res == b


def test_eeprom_128(at24slave, at24_eeprom):
    server = at24slave
    fname = at24_eeprom

    b = bytes(primes54 + primes54 + primes54[:20])

    try:
        with open(fname, 'wb') as f:
            #f.seek(pos)
            f.write(b)

        with open(fname, 'rb') as f:
            #f.seek(pos)
            res = f.read(len(b))
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        server.check()

    assert res == b
