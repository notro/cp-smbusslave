import sys
from smbusslave import SMBusSlave

class ADS1015Slave(SMBusSlave):
    def __init__(self, adcs):
        if len(adcs) == 0:
            raise ValueError('adcs is empty')
        super().__init__()
        self.protocol = SMBusSlave.SMBUS_WORD_SEQ
        self.max_reg = 3
        self.config = 0x8583
        self.lo_thresh = 0x8000;
        self.hi_thresh = 0x7fff;
        self.adcs = adcs
        self.index = 0
        self.debug = False

    def value(self):
        if self.index < len(self.adcs):
            return self.adcs[self.index].value
        return 0

    def readreg(self, reg):
        if reg == 0x00:
            # ADS101x: 12 bits of data in binary two's complement format that is left justified within the 16-bit data word.
            # analogio.AnalogIn: 16-bit regardless of the underlying hw
            val = self.value() >> 1  # Make it a signed value
        elif reg == 0x01:
            val = self.config
        elif reg == 0x02:
            val = self.lo_thresh
        elif reg == 0x03:
            val = self.hi_thresh
        else:
            val = 0xdead

        if self.debug:
            print(" 0x%02x==0x%02x" % (reg, val))

        # doesn't follow smbus standard (little endian), so swap bytes
        return (val >> 8) | (val << 8)

    def writereg(self, reg, val):
        # doesn't follow smbus standard (little endian), so swap bytes
        val = (val >> 8) | (val << 8);

        if self.debug:
            print(" 0x%02x=0x%02x" % (reg, val))

        if reg == 0x01:
            mux = (val >> 12) & 0b111
            if mux & 0b100:
                self.index = mux & 0b011
            else:
                # Differential, not supported
                self.index = 0
            if self.debug:
                print("   index=%d" % (self.index,))
            self.config = val;

        elif reg == 0x02:
            self.lo_thresh = val & 0b0000

        elif reg == 0x03:
            self.hi_thresh = val | 0b1111
