import logging
import sys
from time import sleep
import traceback
import subprocess
from PIL import Image, ImageChops
from pathlib import Path
from typing import List, Dict
import threading
import time

from layout import getImage
from config import config
from subway_service import TrainArrival

logger = logging.getLogger(__name__)

# Only import IT8951 on Raspberry Pi
IS_RASPBERRY_PI = sys.platform == 'linux'
if IS_RASPBERRY_PI:
    from IT8951.display import AutoEPDDisplay # type: ignore
    from IT8951 import constants # type: ignore

class DebugDisplay:
    def __init__(self):
        self.output_dir = Path("debug_output")
        self.output_dir.mkdir(exist_ok=True)
        self.current_image_path = self.output_dir / "current_display.png"
    
    def initialize(self):
        """Initialize the debug display"""
        logger.info("Initialized debug display - images will be saved to debug_output/current_display.png")
        
    def update(self, img: Image.Image, partial: bool = False, clear: bool = False):
        """Update the debug display with new data"""
        try:
            self._update_display(img)
                
        except Exception as e:
            logger.error(f"Error updating debug display: {str(e)}")
            raise

    def _update_display(self, img: Image.Image):
        """Save the image without automatically opening it"""
        try:
            img = img.rotate(180)
            # Save the image
            img.save(self.current_image_path)
            logger.info(f"Saved display image to {self.current_image_path}")
                
        except Exception as e:
            logger.error(f"Error updating debug display: {str(e)}")
            raise

class EInkDisplay:
    def __init__(self):
        if IS_RASPBERRY_PI:
            self.display = AutoEPDDisplay(vcom=-2.06, rotate='CCW', spi_hz=12000000)
            logger.info(f"VCOM set to {self.display.epd.get_vcom()}")
        else:
            raise RuntimeError("EInkDisplay can only be used on Raspberry Pi")
        
        self.previous_image = None
    
    def initialize(self):
        """Initialize the e-ink display"""
        pass

    def _clear_display(self):
        """Clear the e-ink display"""
        try:
            logger.info("Clearing display")
            self.display.frame_buf.paste(0xFF, box=(0, 0, config.display.WIDTH, config.display.HEIGHT))
            self.display.draw_full(constants.DisplayModes.GC16)
            logger.info("Display cleared")
            
        except Exception as e:
            logger.error(f"Error clearing display: {str(e)}")
            raise

    def restart(self):
        logger.error("Likely Error: Restarting display")

        self.display.epd.sleep()
        sleep(2)
        self.display = AutoEPDDisplay(vcom=-2.06, rotate='CCW', spi_hz=12000000)
        sleep(2)
        logger.error("Display restarted")
    
    def _update_display(self, img: Image.Image, clear: bool = False):
        """Update the e-ink display using IT8951"""
        try:
            if clear:
                self._clear_display()

            logger.info("Sending image to display")
            self.display.frame_buf.paste(img)
            self.display.draw_full(constants.DisplayModes.GLR16)
            
            logger.info("Display update complete")
            
        except Exception as e:
            print(f"Error updating display: {str(e)}")
            self.display.epd.wait_display_ready()
            logger.error(f"Error updating display: {str(e)}")
            raise

    def _update_partial_display(self, img: Image.Image, box: tuple):
        """Update a portion of the e-ink display using IT8951"""
        try:
            logger.info("Sending partial image to display")
            self.display.frame_buf.paste(img.crop(box), box)
            self.display.draw_partial(constants.DisplayModes.GLR16) # .DU is faster but has ghosting
            
            logger.info("Partial display update complete")
            
        except Exception as e:
            print(f"Error updating partial display: {str(e)}")
            self.display.epd.wait_display_ready()
            # self.restart()

            logger.error(f"Error updating partial display: {str(e)}")
            raise

    def _get_diff_box(self, img1: Image.Image, img2: Image.Image) -> tuple:
        """Get bounding box of differences between two images"""
        diff = ImageChops.difference(img1, img2)
        return diff.getbbox()

    def update(self, img: Image.Image, partial: bool = False, clear: bool = False):
        """Update the e-ink display with new data
        ToDo: I'm hiding logic here that only does a partial refresh on small changes rather than plumbing all the way through.
        """
        try:
            if self.previous_image:
                diff_box = self._get_diff_box(self.previous_image, img)
            else:
                diff_box = None
            
            # Fix - maybe have the partial boolean parameter be tuple of max width/height"
            if diff_box and (diff_box[2] - diff_box[0] > 50 or diff_box[3] - diff_box[1] > 50):
                logger.info("Large diff detected, doing full update")
                diff_box = None

            if partial and diff_box:
                self._update_partial_display(img, diff_box)
            else:
                self._update_display(img, clear)
            
            self.previous_image = img
                
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")
            logger.error(traceback.format_exc())
            raise

class Display:
    def __init__(self):
        self.display = None
        self.next_frame = None
        self.update_thread = threading.Thread(target=self._process_queue)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def initialize(self):
        """Initialize the appropriate display based on config"""
        if config.DEBUG:
            self.display = DebugDisplay()
        elif IS_RASPBERRY_PI:
            self.display = EInkDisplay()
        else:
            raise RuntimeError("Cannot initialize e-ink display on non-Raspberry Pi device when not in debug mode")
        
        self.display.initialize()

    def _process_queue(self):
        """Process the latest img, ensuring only one update per second"""
        while True:
            try:
                if self.next_frame is not None:
                    img, partial, clear = self.next_frame
                    self.display.update(img, partial, clear)
                    self.next_frame = None
                time.sleep(1)  # Ensure only one update per second
            except Exception as e:
                logger.error(f"Error processing update queue: {str(e)}")
                logger.error(traceback.format_exc())

    def update(self, weather_data: Dict, train_data: List[TrainArrival], partial: bool = False, clear: bool = False):
        """Queue an update for the display with new data"""
        try:
            logger.info("Generating display image...")
            img = getImage(weather_data, train_data)
            self.next_frame = (img, partial, clear)
                
        except Exception as e:
            logger.error(f"Error queuing display update: {str(e)}")
            logger.error(traceback.format_exc())
            raise