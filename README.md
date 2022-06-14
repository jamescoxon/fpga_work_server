# fpga_work_server

## Introduction
  * I currently run my own work server which provides work for my projects (NanoQuake etc) as well as the Public API/Nault backend https://rainstorm.city/api . It was also extensively used during the 2021 spam attack to re-work block PoW to 'kick' chains forward. 
  * The server uses a Nvidia Tesla K20 GPU Computing Card bought off ebay for $75 which draws 300W on its own. At the time of it release in 2013 it was state of the art but it certainly is not now. I also had to rig cooling as the card doesn't have its own fan.

## Goal
  * Allow me to shutdown my horrible monster of a work server and instead generate PoW more efficiently, much more in keeping with the approach of Nano.

### Process
  * About a year ago a FPGA implementation of a PoW generator called [CoNano](https://gitlab.com/QuantumRipple/CoNano) was released by QuantumRipple and silverstar194 however to my knowledge no one had implemented it in the real world.
  * The implementation was based on the Pynq2 board which combines a Xilinx FPGA with a dual core Cortex-A9 processor running linux and has its own python libraries. The board can run off 5V usb port and draws about 5W. The CoNano project provided a standard implementation and 2 overclocked versions which can be used if the onboard power supply is re-programmed to increase the current limits.
  * Following a bit of support from QuantumRipple I was able to get it the FPGA component working which allowed me to pass a block hash/private key and read a work nonce value. I was keen to use the standard (not overclocked) version and tests showed that it could generate PoW for send/change blocks in between 5 and 10 seconds and receive/open blocks in about 1 second.
  * My projects don't constantly request work and often the requests from the public api come in bursts which makes the system not particularly effective. I therefore implemented a pre-caching system using redis, the work server tracks and keeps a up-to-date PoW value on any nano address that it has seen ready for quick responses. In the gaps between work requests it will scan for new frontier blocks and calculate new PoW. 
  * It was also necessary to adjust NanoRPCProxy code used by rainstorm.city to increase the timeout value for when it requests work to allow for the slower realtime work generation.

### Whats next?
  * Next step is to sort out a solar powered system so we can generate our work with the power of the sun.

### Summary
  * I've upgraded my work server from an ancient GPU power hungry to a more efficient FPGA. We've gone from 300W to 5W. 
