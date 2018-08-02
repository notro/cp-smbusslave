import os
import random
import subprocess
import sys
import time
import pytest
import cpboard

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def ads1015slave_func(tout, address):
    import board
    import analogio
    import ads1015slave
    from i2cslave import I2CSlave

    class MockAnalogIn:
        v = 0
        @property
        def value(self):
            self.v += 2
            if self.v > 0x7ff:
                self.v = 0
            return self.v << 4

    adc0 = analogio.AnalogIn(board.A0)
    adc1 = MockAnalogIn()
    ads1015 = ads1015slave.ADS1015Slave([adc0, adc1])
    #ads1015.debug = True

    with I2CSlave(board.SCL, board.SDA, (address,), smbus=tout) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
                with r:
                    if r.address == address:
                        ads1015.process(r)
            except OSError as e:
                print('ERROR:', e)


address = 0x48

@pytest.fixture(scope='module')
def ads1015slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, ads1015slave_func, out=sys.stdout)
    server.start(tout, address)
    time.sleep(1)
    yield server
    server.stop()


def sudo(cmd):
    print('sudo ' + cmd)
    if os.system('sudo ' + cmd) != 0:
        raise RuntimeError('Failed to sudo: %s' % (cmd,))

@pytest.fixture(scope='module')
def ads1015(request, ads1015slave):
    dev = '/sys/bus/i2c/devices/i2c-%d' % (request.config.option.i2cbus,)

    # Use a finalizer to ensure that teardown happens should an exception occur during setup
    def teardown():
        if os.path.exists(dev):
            sudo('sh -c "echo 0x%02x > %s/delete_device"; dmesg | tail' % (address, dev))
    request.addfinalizer(teardown)

    #sudo('/sbin/modprobe ')
    sudo('sh -c "echo ads1015 0x%02x > %s/new_device" && dmesg | tail' % (address, dev))


def getval(hwmon, ch):
    fname = '/sys/class/hwmon/hwmon%d/device/in%d_input' % (hwmon, ch)
    with open(fname) as f:
        val = f.read()
    return int(val)

i = 0

# This is not a very reliable test.

@pytest.mark.parametrize('progress', list(range(10)))  # Just to show some progress
def test_mock(pytestconfig, ads1015slave, ads1015, progress):
    server = ads1015slave
    global i
    if i > 1000:
        pytest.skip('Test is not designed to run over 1000 iterations')
    for _ in range(10):
        i += 1
        val = getval(0, 4)  # ADC
        if pytestconfig.option.verbose:  # -v -s
            print(val, end=' ', flush=True)
        val = getval(0, 5)  # Mock
        server.check()

        # A failing test might break the following tests depending on when/where the transmission error happens
        if val == i - 1:
            i = val

        assert val == i
