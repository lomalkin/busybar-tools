from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DfuDevice:
    """A physical USB device exposed by a DFU backend."""

    key: str
    vendor_id: int
    product_id: int
    bus: Optional[int] = None
    address: Optional[int] = None
    path: Optional[str] = None
    serial: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None

    @property
    def label(self):
        details = []
        if self.product:
            details.append(self.product)
        if self.serial:
            details.append(f"serial={self.serial}")
        if self.path:
            details.append(f"path={self.path}")
        elif self.bus is not None and self.address is not None:
            details.append(f"bus={self.bus}, address={self.address}")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{self.vendor_id:04x}:{self.product_id:04x}{suffix}"
