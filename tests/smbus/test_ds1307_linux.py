import os
import random
import subprocess
import sys
import time
import pytest
import cpboard

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def ds1307slave_func():
    import board
    import time
    import ds1307slave
    import rtc
    from i2cslave import I2CSlave

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

        def seek(self, pos):
            self._pos = pos

    ram = BytesIO(bytearray(56))
    ds1307 = ds1307slave.DS1307Slave(rtc.RTC(), ram=ram)

    with I2CSlave(board.SCL, board.SDA, (0x68,), smbus=False) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
                with r:
                    if r.address == 0x68:
                        ds1307.process(r)
            except OSError as e:
                print('ERROR:', e)


@pytest.fixture(scope='module')
def ds1307slave(board):
    server = cpboard.Server(board, ds1307slave_func, out=sys.stdout)
    server.start()
    time.sleep(1)
    yield server
    server.stop()



#   $ cat /lib/udev/rules.d/50-udev-default.rules
#
#   # select "system RTC" or just use the first one
#   SUBSYSTEM=="rtc", ATTR{hctosys}=="1", SYMLINK+="rtc"
#   SUBSYSTEM=="rtc", KERNEL=="rtc0", SYMLINK+="rtc", OPTIONS+="link_priority=-100"


#   # Remove any existing /dev/random, then create symlink /dev/random pointing to
#   # /dev/urandom
#   KERNEL=="urandom", PROGRAM+="/bin/rm -f /dev/random", SYMLINK+="random"


#    rulef = '/run/udev/rules.d/10-no-rtc-symlink.rules'
#    if not os.path.exists(rulef):
#        sudo('/bin/mkdir -p /run/udev/rules.d')
#
#        sudo('/bin/udevadm control --reload-rules')


def sudo(cmd):
    print('sudo ' + cmd)
    if os.system('sudo ' + cmd) != 0:
        raise RuntimeError('Failed to sudo: %s' % (cmd,))

def dev_rtcs():
    return [d for d in os.listdir('/dev') if d.startswith('rtc')]

@pytest.fixture(scope='module')
def rtc_ds1307(request, ds1307slave):
    dev = '/sys/bus/i2c/devices/i2c-%d' % (request.config.option.i2cbus,)
    rtcs = dev_rtcs()

    # Use a finalizer to ensure that teardown happens should an exception occur during setup
    def teardown():
        if os.path.exists(dev):
            sudo('sh -c "echo 0x68 > %s/delete_device"; dmesg | tail' % (dev,))
    request.addfinalizer(teardown)

    sudo('/sbin/modprobe rtc-ds1307')
    sudo('sh -c "echo ds1307 0x68 > %s/new_device" && dmesg | tail' % (dev,))

    if not rtcs:
        # Keep systemd from accessing the device we added
        # Do this by removing the symlink added by:
        #  /lib/udev/rules.d/50-udev-default.rules
        sudo('rm -f /dev/rtc')

    rtc = list(set(dev_rtcs()) - set(rtcs))
    if len(rtc) != 1:
        raise RuntimeError('rtc should have one item: %r' % (rtc,))
    return os.path.join('/dev', rtc[0])


@pytest.fixture(scope='module')
def rtc_ds1307_nvram(request, rtc_ds1307):
    fname = '/sys/bus/i2c/drivers/rtc-ds1307/%d-0068/nvram' % (request.config.option.i2cbus,)
    sudo('chmod 666 %s' % (fname,))
    return fname


#  2018-07-22 17:40:06.110331+0200
def hwlock_get(dev):
    output = subprocess.check_output(['sudo', 'hwclock', '-r', '-f', dev])
    clock, _, _ = str(output, 'utf-8').partition('.')
    return time.strptime(clock, '%Y-%m-%d %H:%M:%S')


def hwclock_set(dev, t):
    clock = time.strftime('%Y-%m-%d %H:%M:%S', t)
    sudo('hwclock --utc --noadjfile --set --date="%s" -f %s' % (clock, dev))


@pytest.mark.parametrize('date',
    [
        (2020, 3, 28, 18, 30, 0, 0, 0, 0),
        (2018, 7, 23, 19, 2, 20, 0, 0, 0),
        (2000, 1, 1, 1, 0, 0, 0, 0, 0),
        (2001, 1, 1, 1, 0, 0, 0, 0, 0),
    ]
)
def test_clock(ds1307slave, rtc_ds1307, date):
    server = ds1307slave
    dev = rtc_ds1307
    #time.sleep(1)
    #print()
    #sudo('hwclock -r -f %s' % (dev,))
    #print()
    #print('clock', hwlock_get(dev))
    #print()
    #hwclock_set(dev, time.localtime())
    #print()
    #print('clock', hwlock_get(dev))
    #print()

    try:
        ts = time.struct_time(date)
        hwclock_set(dev, ts)
        tr = hwlock_get(dev)
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        server.check()

    assert tuple(tr)[:6] == tuple(ts)[:6]

    #os.system('cat /proc/driver/rtc')
    #print()


@pytest.mark.parametrize('data',
    [
        [0x32] * 56,
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
        [random.randrange(0x00, 0xff + 1) for _ in range(56)],
    ]
)
def test_nvram(ds1307slave, rtc_ds1307_nvram, data):
    server = ds1307slave
    fname = rtc_ds1307_nvram
    b = bytes(data)

    try:
        with open(fname, 'wb') as f:
            f.write(b)

        with open(fname, 'rb') as f:
            res = f.read()
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        server.check()

    assert res == b


@pytest.mark.parametrize('pos', [0, 1, 2, 3, 4, 10, 32])
@pytest.mark.parametrize('data',
    [
        [0x44],
        [0x00, 0x01,],
        [0x35, 0x56, 0x67,],
        [0x21, 0x34, 0x04, 0x12, 0x89, 0xde, 0x04, 0xfe, 0x00, 0xff],
    ]
)
def test_nvram_part(ds1307slave, rtc_ds1307_nvram, pos, data):
    server = ds1307slave
    fname = rtc_ds1307_nvram
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
