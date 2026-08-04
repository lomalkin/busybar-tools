# STM32 system bootloader in DFU mode. Note this VID/PID is shared by ALL STM32
# devices, so it must never be the only device-selection criterion — the DfuSe
# target name and the DFU suffix USB IDs are checked as well.
DFU_VENDOR_ID = 0x0483
DFU_PRODUCT_ID = 0xDF11

# Address submitted with the DfuSe "leave" request (mirrors the web recovery utility).
DFU_LEAVE_ADDRESS = 0x080FFFFF

DFU_MANUAL_INSTRUCTIONS = """\
Could not switch the device to DFU automatically.

Put BUSY Bar into DFU mode manually:
  1. Hold Start and Back buttons simultaneously for 3 seconds.
  2. Release Back and keep holding Start for 2 more seconds.
  3. The lights should slowly flash yellow.
  4. Plug the USB cable in, then press Enter here.
"""

RECOVERY_RESET_INSTRUCTIONS = """\
If BUSY Bar stays in DFU/recovery mode, reboot it manually:
  1. Hold Start and Back buttons simultaneously for about 3 seconds.
  2. Release the buttons and wait for the device to boot.
"""
