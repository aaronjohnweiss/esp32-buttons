# esp32-buttons
Pair esp32 boards together and toggle between them using button presses.

## Installation

1. Run `esptool --port /dev/ttyUSB0 erase-flash`
2. Download latest release from https://micropython.org/download/ESP32_GENERIC/ and run `esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash 0x1000 ESP32_GENERIC-20260406-v1.28.0.bin`
3. Run `mpremote connect /dev/ttyUSB0 resume cp boot.py :boot.py + soft-reset + repl`
4. Run `mpremote cp main.py :main.py`
5. Reboot, hold button for 3s to start pairing. Board will flash.
6. Press buttons on other boards to pair. Will double-flash to confirm pairing.
7. Press flashing host board to stop pairing. 
8. Press buttons to send LED state between paired devices.
