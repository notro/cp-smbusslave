import cpboard
import pytest
import smbus
import sys

def pytest_addoption(parser):
    group = parser.getgroup('smbusslave')
    group.addoption("--bus", dest='i2cbus', type=int, help='I2C bus number')
    group.addoption("--serial-wait", default=20, dest='serial_wait', type=int, help='Number of milliseconds to wait before checking board output (default: 20ms)')
    group.addoption("--smbus-timeout", default=True, dest='smbus_timeout', type=bool, help='Use SMBUS timeout limit (default: True)')


@pytest.fixture(scope='session')
def board(request):
    board = cpboard.CPboard.from_try_all(request.config.option.boarddev)
    board.open()
    board.repl.reset()
    return board


@pytest.fixture
def bus(request):
    return smbus.SMBus(request.config.option.i2cbus)
