import sys
import time
import pytest
import cpboard
import smbus

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def ds1307slave_func(addresses):
    import board
    import time
    import ds1307slave
    import rtc
    from i2cslave import I2CSlave

    ds1307 = ds1307slave.DS1307Slave(rtc.RTC())

    with I2CSlave(board.SCL, board.SDA, addresses, smbus=False) as slave:
        while True:
            try:
                r = slave.request(timeout=2)

                with r:
                    if r.address == 0x68:
                        ds1307.process(r)

            except OSError as e:
                print('ERROR:', e)


@pytest.fixture(scope='module')
def ds1307slave(board):
    server = cpboard.Server(board, ds1307slave_func, out=sys.stdout)
    server.start((0x68,))
    time.sleep(1)
    yield server
    server.stop()
    sys.stderr.write('slave: Slave stopped:\n')


def readreg(bus, address, reg):
    sys.stdout.write("Read 0x%02x: 0x%02x==" % (address, reg))
    val = bus.read_byte_data(address, reg)
    sys.stdout.write("0x%02x\n" % (val))
    return val


def writereg(bus, address, reg, val):
    print("Write 0x%02x: 0x%02x=0x%02x" % (address, reg, val))
    bus.write_byte_data(address, reg, val)


def test_clock(ds1307slave, bus):
    val = readreg(bus, 0x68, 0x0)
    assert val < 0x60
    val = readreg(bus, 0x68, 0x1)
    assert val < 0x60
    val = readreg(bus, 0x68, 0x2)
    assert val < 0x24
