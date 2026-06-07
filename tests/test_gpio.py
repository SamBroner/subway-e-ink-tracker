import pytest

spidev = pytest.importorskip(
    "spidev",
    reason="Pi-only SPI library is unavailable",
)
import time

def test_spi():
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
