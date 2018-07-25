import time
from smbusslave import SMBusSlave

def bcd2bin(val):
    return (val & 0x0f) + ((val >> 4) * 10)

def bin2bcd(val):
    return ((val // 10) << 4) + val % 10

class DS1307Slave(SMBusSlave):
    def __init__(self, rtc, ram=None):
        super().__init__()
        self.rtc = rtc
        self.ram = ram
        self.protocol = SMBusSlave.SMBUS_BYTE_SEQ
        self.max_reg = 0x3f
        self.debug = False

    def readreg(self, reg):
        t = self.rtc.datetime

        if reg == 0x00:
            val = bin2bcd(t.tm_sec)
        elif reg == 0x01:
            val = bin2bcd(t.tm_min)
        elif reg == 0x02:
            val = bin2bcd(t.tm_hour)
        elif reg == 0x03:
            val = bin2bcd(t.tm_wday)
        elif reg == 0x04:
            val = bin2bcd(t.tm_mday)
        elif reg == 0x05:
            val = bin2bcd(t.tm_mon)
        elif reg == 0x06:
            val = bin2bcd(t.tm_year % 100)
        elif reg == 0x07: # Control register
            val = 0
        else:
            return self.readram(reg - 0x08)

        if self.debug:
            print(" 0x%02x==0x%02x" % (reg, val))
        return val

    def writereg(self, reg, val):
        if self.debug:
            print(" 0x%02x=0x%02x" % (reg, val))

        if reg == 0x07: # Control register
            return
        elif reg > 0x07:
            self.writeram(reg - 0x08, val)

        t = list(self.rtc.datetime)

        # AttributeError: can't set attribute
        if reg == 0x00:
            t[5] = bcd2bin(val)
        elif reg == 0x01:
            t[4] = bcd2bin(val)
        elif reg == 0x02:
            t[3] = bcd2bin(val)
        elif reg == 0x03:
            t[6] = bcd2bin(val)
        elif reg == 0x04:
            t[2] = bcd2bin(val)
        elif reg == 0x05:
            t[1] = bcd2bin(val)
        elif reg == 0x06:
            t[0] = (t[0] - (t[0] % 100)) + bcd2bin(val)

        self.rtc.datetime = time.struct_time(tuple(t))

    def readram(self, addr):
        if self.ram:
            self.ram.seek(addr)
            return self.ram.read(1)[0]
        else:
            return 0

    def writeram(self, addr, data):
        if self.ram:
            self.ram.seek(addr)
            self.ram.write(bytes([data]))
