# test_logging.py
import os
import sys
import logging
from datetime import datetime

def test_logging_setup():
    log_file = 'log.txt'
    
    # Test 1: Direct file write
    try:
        with open(log_file, 'w') as f:
            f.write(f"Test write at {datetime.now()}\n")
        print(f"Successfully wrote to {log_file}")
    except Exception as e:
        print(f"Error writing to file: {e}")
        sys.exit(1)

    # Test 2: Configure logging
    try:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, mode='a'),
                logging.StreamHandler()
            ],
            force=True  # Override any existing logging config
        )
    except Exception as e:
        print(f"Error configuring logging: {e}")
        sys.exit(1)

    # Test 3: Write test log messages
    logger = logging.getLogger(__name__)
    logger.debug("Debug test message")
    logger.info("Info test message")
    logger.warning("Warning test message")
    
    # Test 4: Verify file contents
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            print("\nLog file contents:")
            print(content)
    except Exception as e:
        print(f"Error reading log file: {e}")

if __name__ == "__main__":
    test_logging_setup()