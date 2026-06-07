# e-ink Subway & Weather Display
A Raspberry Pi-powered e-ink display showing real-time subway arrival times, Citi Bike availability, and weather forecasts. Perfect for mounting on your wall to check train times and weather before heading out.

Full Post [here](https://sambroner.com/posts/raspberry-pi-train).

# Features
- Real-time subway arrival times (NYCT GTFS feeds — no API key)
- Current Citi Bike availability for a station (GBFS feeds — no API key)
- Current weather and hourly/daily forecast (Open-Meteo — no API key)
- Debug mode with automatic image preview
- Native e-ink display support on Raspberry Pi

<p align="center">
  <img src="assets/images/display_demo.jpeg" alt="The display mounted in a cherry frame on the wall" width="45%">
  &nbsp;&nbsp;
  <img src="assets/images/display_render.jpeg" alt="A render of the display output" width="45%">
</p>

<p align="center"><sub><b>Left:</b> mounted on the wall in a laser-cut mat &amp; frame. &nbsp; <b>Right:</b> a render of the display output.</sub></p>

## Getting Started

### Hardware
- Raspberry Pi 4b+
    - SD Card, power supply, (optionally keyboard, mouse, hdmi cord, etc.)
- [Waveshare 9.7inch E-Ink display HAT for Raspberry Pi](https://www.waveshare.com/product/displays/e-paper/9.7inch-e-paper-hat.htm)

(For the frame and mounting, see [Physical Build](#physical-build) below.)

### Raspberry Pi Setup
0. Figure out how you're going to connect to the Raspberry Pi
1. Install UV
2. Enable the SPI interface
3. Attach the e-ink display to the Raspberry Pi

```bash
git clone https://github.com/SamBroner/subway-e-ink-tracker.git
cd subway-e-ink-tracker
uv sync
```

### Installation
1. Install uv (if not already installed)
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Set up your environment file:
   ```bash
   cp config/.env.template config/.env
   # then edit config/.env with your station IDs and preferences
   ```

### Configuration

All configuration lives in `config/.env` (gitignored — your personal values stay
local). Copy `config/.env.template` and fill it in:

| Variable | Required | Description |
|---|---|---|
| `STATION_ID` | yes | MTA station ID for arrivals (e.g. `F20S`) |
| `TRAIN_LINE_1`, `TRAIN_LINE_2` | yes | Train lines to monitor (e.g. `F`, `G`) |
| `CITIBIKE_STATION_ID` | yes | Citi Bike station UUID (see below) |
| `CITIBIKE_STATION_NAME` | yes | Display name for the bike station |
| `WEATHER_LAT`, `WEATHER_LON` | no | Coordinates (defaults to NYC center) |
| `DEBUG` | no | `true` saves a render to `debug_output/` instead of driving the display |
| `DEBUG_FRAME_HISTORY` | no | `true` also saves timestamped debug frames and `debug_output/frame_manifest.csv` |
| `QUIET_MODE` | no | `true` suppresses console output |

Values provided in the shell take precedence over `config/.env`, which is useful
for smoke tests such as `DEBUG=true QUIET_MODE=false uv run runner.py`.

Find your Citi Bike station's UUID and name in the GBFS feed:
<https://gbfs.citibikenyc.com/gbfs/en/station_information.json>

### Running

If `DEBUG=true` in your environment:
- Images will be saved to `debug_output/current_display.png`
- If `DEBUG_FRAME_HISTORY=true`, timestamped frames are also saved to `debug_output/frames/` with timing metadata in `debug_output/frame_manifest.csv`
- Your system's default image viewer will automatically open and update with each refresh
- The image viewer will refresh automatically when new data arrives

If `DEBUG=false`:
- On Raspberry Pi: The e-ink display will update
- On other platforms: An error will be raised (e-ink display only works on Raspberry Pi)

To run:
```bash
uv run runner.py
```

## Physical Build

The display reads best when it's framed like a piece of art rather than left as a
bare panel. The key is a **laser-cut mat**: a precise cutout window holds the e-ink
panel square and aligned behind the glass, and gives it a clean, finished border.

- **Frame:** I used this [natural cherry gallery frame](https://www.americanframe.com/natural-cherry-gallery-frame).
- **Mat:** a custom **laser-cut mat** sized to the display's active area, also from
  [American Frame](https://www.americanframe.com/). This is what makes the mount look
  intentional and keeps everything aligned.

See the [full write-up](https://sambroner.com/posts/raspberry-pi-train) for the
framing and mounting technique, including how the Pi and ribbon cable tuck behind.

## Testing

The unit tests for the Citi Bike module use the stdlib `unittest`
(no extra dependencies). Run them from the repo root:

```bash
uv run python -m unittest tests.test_citibike_service
```

(The other scripts under `tests/` are manual Raspberry Pi hardware checks —
SPI/GPIO and the e-ink display — and only run on the Pi.)

## CairoSVG

- CairoSVG is used to convert SVGs to PNGs for the display.
- On mac, you may need to manually compile Cairo: https://stackoverflow.com/questions/36225410/installing-cairo-and-pycairo-mac-osx

## Display Modes
Figuring out the right display mode was annoying. The full spec is [here](https://www.waveshare.net/w/upload/c/c4/E-paper-mode-declaration.pdf).

## To Do
- [ ] Consider checking if the wait time still makes sense and then refresh. E.g. It's 11am. Train Arrives at 11:04 and there's no update. When time turns to 11:01, even if no update, refresh.
- [ ] Fix hourly weather... seems like it's only 100% or zero?

## Credits
- IT8951 library by GregDMeyer: https://github.com/GregDMeyer/IT8951

## Setting up as a service
To have the display start automatically on boot, create a systemd service:

```ini
[Unit]
Description=Subway E-Ink Display Service
After=network.target

[Service]
Type=simple
User=<your-username>
WorkingDirectory=/path/to/repo
ExecStart=/path/to/uv run runner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then manage it with:
```bash
sudo systemctl restart subway-eink.service
sudo systemctl stop subway-eink.service
```

# Project Structure

```
.
├── runner.py            # main loop: fetch data, render, update display
├── utils.py             # icon rendering + shared helpers
├── config/
│   ├── config.py        # all configuration + display geometry
│   └── .env.template    # copy to config/.env and fill in
├── services/
│   ├── subway_service.py    # MTA arrivals
│   ├── citibike_service.py  # Citi Bike availability
│   ├── weather_service.py   # Open-Meteo weather
│   └── weather_codes.py     # WMO weather code sets
├── ui/
│   ├── display.py       # e-ink / debug display driver
│   ├── layout.py        # screen layout + drawing
│   └── fonts.py         # font loading
├── assets/
│   ├── fonts/           # Font.ttc
│   ├── bitmaps/         # display test bitmaps
│   └── icons/           # weather + UI (bike, bolt) SVG icons
└── tests/               # unit tests + Pi hardware checks
```
