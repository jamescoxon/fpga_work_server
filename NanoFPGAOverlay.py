from pynq import Overlay


class NanoFPGAOverlay(Overlay):
    def __init__(self, bitfile, **kwargs):
        super().__init__(bitfile, **kwargs)
#        self.nano_driver = self.conano_axil_verilog_0.s_axil
        self.nano_driver = self.conano_axil_verilog_0
