import os
from PIL import ImageFont
from config.config import config

class FontManager:
    def __init__(self):
        self.font_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'assets/fonts/Font.ttc')
        self._fonts = {}
        self._load_fonts()

    def _load_fonts(self):
        """Load all font sizes on initialization"""
        for name, size in config.FONT_SIZES.items():
            self._fonts[name] = ImageFont.truetype(self.font_path, size)
    
    def get(self, size_name: str) -> ImageFont.FreeTypeFont:
        """Get a font by its size name"""
        if size_name not in self._fonts:
            raise ValueError(f"Font size '{size_name}' not found. Available sizes: {list(self._fonts.keys())}")
        return self._fonts[size_name]

# Create a global font manager instance
fonts = FontManager() 