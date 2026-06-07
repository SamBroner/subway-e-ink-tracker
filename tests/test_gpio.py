import pytest
import sys
from pathlib import Path

try:
    import spidev
except ImportError as e:
    spidev = None
    SPIDEV_IMPORT_ERROR = e
else:
    SPIDEV_IMPORT_ERROR = None


def _is_raspberry_pi() -> bool:
    if sys.platform != "linux":
        return False
    model_path = Path("/proc/device-tree/model")
    try:
        return "raspberry pi" in model_path.read_text(errors="ignore").lower()
    except OSError:
        return False

def test_spi():
    if spidev is None:
        if _is_raspberry_pi():
            pytest.fail(
                "spidev is not importable on this Raspberry Pi; install it in "
                "the active Python environment before running the SPI gate",
                pytrace=False,
            )
        pytest.skip("Pi-only SPI library is unavailable")

    # Open SPI bus 0, device 0
    spi = spidev.SpiDev()
    opened = False
    try:
        spi.open(0, 0)
        opened = True
        
        # Configure SPI settings
        spi.max_speed_hz = 4000000
        spi.mode = 0
        
        print("SPI initialized successfully")
        
        # Try to send some test data
        test_data = [0x01, 0x02, 0x03]
        result = spi.xfer2(test_data)
        print(f"Sent data: {test_data}")
        print(f"Received data: {result}")
        assert len(result) == len(test_data)
        
        print("SPI test completed")
    finally:
        if opened:
            spi.close()

if __name__ == "__main__":
    test_spi()
