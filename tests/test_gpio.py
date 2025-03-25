import spidev
import time

def test_spi():
    try:
        # Open SPI bus 0, device 0
        spi = spidev.SpiDev()
        spi.open(0, 0)
        
        # Configure SPI settings
        spi.max_speed_hz = 4000000
        spi.mode = 0
        
        print("SPI initialized successfully")
        
        # Try to send some test data
        test_data = [0x01, 0x02, 0x03]
        result = spi.xfer2(test_data)
        print(f"Sent data: {test_data}")
        print(f"Received data: {result}")
        
        spi.close()
        print("SPI test completed")
        
    except Exception as e:
        print(f"SPI Error: {e}")

if __name__ == "__main__":
    test_spi()