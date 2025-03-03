import os
from pathlib import Path
from PIL import Image,ImageFont
import requests
import cairosvg
import time
import time
import shutil
import logging
from config import config
from io import BytesIO

logger = logging.getLogger(__name__)

picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pic')
font16 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16)
font24 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 24)
font36 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 36)

imgdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'img')
svgdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'weather_icons')

def getWeather(key, days):
    resp = requests.get("https://api.weatherapi.com/v1/forecast.json?key={}&q=11231&days={}&aqi=no&alerts=no".format(key, days))
    logger.info("Received Weather")
    return resp.json()

def getHeadlines(apiKey):
    headlineJson = requests.get("https://newsapi.org/v2/top-headlines?country=us&apiKey={}".format(apiKey)).json()
    logger.info("Received News")
    return headlineJson["articles"]

def getWeatherIcon(weatherReportJson, size):
    """Convert SVG weather icon to PNG and return as PIL Image without saving to disk"""
    
    iconPath = getWeatherIconPath(weatherReportJson)
    png_data = BytesIO()
    
    try:
        cairosvg.svg2png(url=iconPath, write_to=png_data, parent_width=size, parent_height=size)
        png_data.seek(0)
        return Image.open(png_data)
    except Exception as e:
        logger.error(f"Error creating weather icon: {str(e)}")
        raise

# Takes a 1hr report or a "currentDay" report
def getWeatherIconPath(weatherReportJson):
    iconNum = mapWeatherCodeToWeatherIconDir(weatherReportJson["condition"]["code"])
    return getWeatherIconFromSVGs(iconNum, weatherReportJson.get("is_day"))

def getWeatherIconFromSVGs(iconNum, dayNum):
    weatherIconDir = os.path.join(svgdir, iconNum)
    icons = os.listdir(weatherIconDir)
    if dayNum == None:
        dayNum = 1

    if len(icons) == 1:
        return os.path.join(weatherIconDir, icons[0])
    else:
        for icon in icons:
            if icon == ".DS_Store":
                # skip
                logger.info("skip")
            elif dayNum == 0 and icon.find("night") >= 0:
                return os.path.join(weatherIconDir, icon)
            elif dayNum == 1 and icon.find("night") == -1:
                return os.path.join(weatherIconDir, icon)

    return os.path.join(svgdir, "Extra/wi-na.svg")

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
