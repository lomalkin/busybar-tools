"""Application error hierarchy for busybar-tools."""


class BusybarError(RuntimeError):
    """Base class for expected, user-facing failures."""


class DeviceError(BusybarError):
    """A device could not be reached or did not complete an operation."""


class DeviceProtocolError(DeviceError):
    """The device returned an invalid or unsuccessful protocol response."""


class FirmwareError(BusybarError):
    """Firmware resolution, validation, or installation failed."""


class StorageError(DeviceError):
    """An on-device storage operation failed."""


class RecoveryError(BusybarError):
    """USB DFU recovery failed."""

