import cpboard
import errno
import pytest
import sys
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def slave_func(tout, addresses, protocol):
    import board
    from i2cslave import I2CSlave
    from smbusslave import SMBusSlave

    class Slave(SMBusSlave):
        def __init__(self, prot):
            super().__init__()
            self.print = False  # Slows down too much for the seq tests resulting in a timeout
            if prot == 0:
                self.protocol = SMBusSlave.SMBUS_BYTE
                self.print = True
            elif prot == 1:
                self.protocol = SMBusSlave.SMBUS_BYTE_SEQ
            elif prot == 2:
                self.protocol = SMBusSlave.SMBUS_WORD
                self.print = True
            elif prot == 3:
                self.protocol = SMBusSlave.SMBUS_WORD_SEQ
            self.max_reg = 7
            self.regs = [0] * (self.max_reg + 1)

        def readreg(self, reg):
            val = self.regs[reg]
            if self.print == True:
                print(' 0x%02x==0x%x' % (reg, val))
            return val

        def writereg(self, reg, val):
            if self.print == True:
                print(' 0x%02x=0x%x' % (reg, val))
            self.regs[reg] = val

    print('\nboard: slave_func:', ','.join(['0x%02x' % (addr,) for addr in addresses]), 'prot:', protocol)
    bs = Slave(protocol)

    with I2CSlave(board.SCL, board.SDA, addresses, smbus=tout) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue

                with r:
                    #print('address==0x%02x' % r.address)
                    #print('is_read', r.is_read)
                    #print('is_restart', r.is_restart)

                    if r.address == addresses[0]:
                        bs.process(r)

            except OSError as e:
                print('ERROR:', e)

address = 0x41


class TestByte:
    @pytest.fixture(scope='class', params=[0, 1], ids=['BYTE', 'BYTE_SEQ'])
    def slave(self, request, board):
        tout = request.config.option.smbus_timeout
        server = cpboard.Server(board, slave_func, out=sys.stdout)
        server.start(tout, (address,), request.param)
        time.sleep(1)
        yield server
        server.stop()

    @pytest.fixture(autouse=True)
    def server(self, slave):
        self.server = slave
        self.protocol = self.server.args[2]

    test_reg_data = [
        (0x00, 0x12),
        (0x05, 0x56),
        (0x05, 0x78),
        (0x07, 0xfe),
    ]
    test_reg_data_ids = ['%02x=%02x' % (d[0], d[1]) for d in test_reg_data]

    @pytest.mark.parametrize('reg, val', test_reg_data, ids=test_reg_data_ids)
    def test_write(self, bus, reg, val):
        try:
            bus.write_byte_data(address, reg, val)
            res = bus.read_byte_data(address, reg)
        finally:
            out = self.server.check()
        assert res == val
        if self.protocol == 0:
            assert '0x%02x=0x%x' % (reg, val) in out

    # Test wrap-around by using multiple starting registers
    @pytest.mark.parametrize('reg', list(range(8)))
    def test_write_seq(self, bus, reg):
        if self.protocol != 1:
            return
        # Workaround the need for a pure i2c function since smbus can't seq write without length:
        # The block length==6 will be stored in reg and vals in the following registers
        vals = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16]
        try:
            bus.write_block_data(address, reg, vals)
            res = bus.read_block_data(address, reg)
        finally:
            self.server.check()
        assert res == vals
        assert bus.read_byte_data(address, reg) == len(vals)

    @pytest.mark.parametrize('reg', [8, 9])
    def test_write_illegal_reg(self, bus, reg):
        try:
            with pytest.raises(OSError):
                bus.write_byte_data(address, reg, 0)
        finally:
            self.server.check()
        # Make sure it still works after a failure
        bus.write_byte_data(address, 1, 56)
        assert bus.read_byte_data(address, 1) == 56

    @pytest.mark.parametrize('reg', [8, 9])
    def test_read_illegal_reg(self, bus, reg):
        try:
            with pytest.raises(OSError):
                bus.read_byte_data(address, reg)
        finally:
            self.server.check()
        # Make sure it still works after a failure
        bus.write_byte_data(address, 3, 45)
        assert bus.read_byte_data(address, 3) == 45


class TestWord:
    @pytest.fixture(scope='class', params=[2, 3], ids=['WORD', 'WORD_SEQ'])
    def slave(self, request, board):
        tout = request.config.option.smbus_timeout
        server = cpboard.Server(board, slave_func, out=sys.stdout)
        server.start(tout, (address,), request.param)
        time.sleep(1)
        yield server
        server.stop()

    @pytest.fixture(autouse=True)
    def server(self, slave):
        self.server = slave
        self.protocol = self.server.args[2]

    test_reg_data = [
        (0x01, 0x1234),
        (0x03, 0x5678),
        (0x04, 0x789a),
        (0x06, 0xfedc),
    ]
    test_reg_data_ids = ['%02x=%02x' % (d[0], d[1]) for d in test_reg_data]

    @pytest.mark.parametrize('reg, val', test_reg_data, ids=test_reg_data_ids)
    def test_write(self, bus, reg, val):
        try:
            bus.write_word_data(address, reg, val)
            res = bus.read_word_data(address, reg)
        finally:
            out = self.server.check()
        assert res == val
        # Verify little endian
        if self.protocol == 0:
            assert '0x%02x=0x%x' % (reg, val) in out

    # Test wrap-around by using multiple starting registers
    @pytest.mark.parametrize('reg', list(range(8)))
    def test_write_seq(self, bus, reg):
        if self.protocol != 3:
            return
        # The block length will be stored in reg low byte (little endian)
        vals = [0x1102, 0x1203, 0x1304, 0x1405, 0x1506, 0x1607]
        data = [0x00]  # high byte reg value
        for val in vals:
            data.append(val & 0xff)
            data.append(val >> 8)
        try:
            bus.write_block_data(address, reg, data)
            res = bus.read_block_data(address, reg)
        finally:
            out = self.server.check()
        assert res == data
        if self.protocol == 2:
            for i in range(len(vals)):
                assert '0x%02x=0x%x' % ((reg + i + 1) % 8, vals[i]) in out
        out = self.server.check()
        res = bus.read_word_data(address, reg)
        out = self.server.check()
        assert res == len(data)

    @pytest.mark.parametrize('reg', [8, 9])
    def test_write_illegal_reg(self, bus, reg):
        try:
            with pytest.raises(OSError):
                bus.write_word_data(address, reg, 0)
        finally:
            self.server.check()
        # Make sure it still works after a failure
        bus.write_word_data(address, 1, 56)
        assert bus.read_word_data(address, 1) == 56

    @pytest.mark.parametrize('reg', [8, 9])
    def test_read_illegal_reg(self, bus, reg):
        try:
            with pytest.raises(OSError):
                bus.read_word_data(address, reg)
        finally:
            self.server.check()
        # Make sure it still works after a failure
        bus.write_word_data(address, 3, 4567)
        assert bus.read_word_data(address, 3) == 4567
