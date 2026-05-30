import os
from pathlib import Path
from PIL import Image
import cairosvg
import logging
from config.config import config
from io import BytesIO

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ICON_ROOT = BASE_DIR / 'assets' / 'icons'
WEATHER_ICON_DIR = ICON_ROOT / 'weather'
UI_ICON_DIR = ICON_ROOT / 'ui'

def _render_svg(icon_path: Path, size: int) -> Image.Image:
    """Convert an SVG at icon_path to a Pillow Image of roughly size x size."""
    png_data = BytesIO()
    try:
        cairosvg.svg2png(
            url=str(icon_path),
            write_to=png_data,
            output_width=size,
            output_height=size,
            parent_width=size,
            parent_height=size
        )
        png_data.seek(0)
        return Image.open(png_data)
    except Exception as e:
        logger.error(f"Error creating icon from {icon_path}: {str(e)}")
        raise

def getWeatherIcon(weatherReportJson, size):
    """Convert SVG weather icon to PNG and return as PIL Image without saving to disk"""
    iconPath = getWeatherIconPath(weatherReportJson)
    return _render_svg(iconPath, size)

def get_ui_icon(icon_name: str, size: int) -> Image.Image:
    """Render a non-weather UI icon (e.g., bike, bolt) from assets/icons/ui."""
    icon_path = UI_ICON_DIR / f"{icon_name}.svg"
    if not icon_path.exists():
        raise FileNotFoundError(f"UI icon '{icon_name}' not found at {icon_path}.")
    return _render_svg(icon_path, size)

# Takes a 1hr report or a "currentDay" report
def getWeatherIconPath(weatherReportJson):
    iconNum = mapWeatherCodeToWeatherIconDir(weatherReportJson["condition"]["code"])
    return getWeatherIconFromSVGs(iconNum, weatherReportJson.get("is_day"))

def getWeatherIconFromSVGs(iconNum, dayNum):
    if not iconNum:
        return WEATHER_ICON_DIR / "Extra" / "wi-na.svg"

    weatherIconDir = WEATHER_ICON_DIR / iconNum
    icons = [icon for icon in os.listdir(weatherIconDir) if icon != ".DS_Store"]
    if dayNum is None:
        dayNum = 1

    if len(icons) == 1:
        return weatherIconDir / icons[0]

    for icon in icons:
        if dayNum == 0 and "night" in icon:
            return weatherIconDir / icon
        if dayNum == 1 and "night" not in icon:
            return weatherIconDir / icon

    return WEATHER_ICON_DIR / "Extra" / "wi-na.svg"

def emptyImage():
    emptyImage = Image.new('1', (config.display.WIDTH, config.display.HEIGHT), 255)
    return emptyImage

def mapWeatherCodeToWeatherIconDir(code):
    switcher = {
        1000: "113",
        1003: "116",
        1006: "119",
        1009: "122",
        1030: "143",
        1063: "176",
        1066: "179",
        1069: "182",
        1072: "185",
        1087: "200",
        1114: "227",
        1117: "230",
        1135: "248",
        1147: "260",
        1150: "263",
        1153: "266",
        1168: "281",
        1171: "284",
        1180: "293",
        1183: "296",
        1186: "299",
        1189: "302",
        1192: "305",
        1195: "308",
        1198: "311",
        1201: "314",
        1204: "317",
        1207: "320",
        1210: "323",
        1213: "326",
        1216: "329",
        1219: "332",
        1222: "335",
        1225: "338",
        1237: "350",
        1240: "353",
        1243: "356",
        1246: "359",
        1249: "362",
        1252: "365",
        1255: "368",
        1258: "371",
        1261: "374",
        1264: "377",
        1273: "386",
        1276: "389",
        1279: "392",
        1282: "395",
    }
    return switcher.get(code)

def shortenWeatherText(desc):
    desc = desc.replace("with", "w/")
    desc = desc.replace("Patchy", "Some")
    desc = desc.replace("Moderate or h", "H")
    return desc
