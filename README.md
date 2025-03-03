# e-ink Subway & Weather Display
A Raspberry Pi-powered e-ink display showing real-time subway arrival times and weather forecasts. Perfect for mounting on your wall to check train times and weather before heading out.

# Features
- Real-time subway arrival times
- Current weather and 3-day forecast
- Debug mode with automatic image preview
- Native e-ink display support on Raspberry Pi

![E-Ink Display Demo](docs/display_demo.jpg)


## Getting Started

### Hardware
- Raspberry Pi 4b+
    - SD Card, power supply, (optionally keyboard, mouse, hdmi cord, etc.)
- Waveshare 9.7inch E-Ink display HAT for Raspberry Pi
- Frame (optional)
- Custom Mat (Optional)

### Raspberry Pi Setup
0. Figure out how you're going to connect to the Raspberry Pi
1. Install UV
2. Enable the SPI interface
3. Attach the e-ink display to the Raspberry Pi

To test the display on Raspberry Pi:
```bash
git clone https://github.com/sambroner/subway-eink.git
cd subway-eink
uv sync
uv run test.py
```

### Installation
1. Install uv (if not already installed)
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Set up .env file (copy from .env.template)

Running on your wall
1. Set up a systemd service

### Running

If `DEBUG=true` in your .env:
- Images will be saved to `debug_output/current_display.png`
- Your system's default image viewer will automatically open and update with each refresh
- The image viewer will refresh automatically when new data arrives

If `DEBUG=false`:
- On Raspberry Pi: The e-ink display will update
- On other platforms: An error will be raised (e-ink display only works on Raspberry Pi)

To run:
```bash
uv run runner.py
```

## CairoSVG

- CairoSVG is used to convert SVGs to PNGs for the display.
- On mac, you may need to manually compile Cairo: https://stackoverflow.com/questions/36225410/installing-cairo-and-pycairo-mac-osx

## To Do
- [ ] Consider checking if the wait time still makes sense and then refresh. E.g. It's 11am. Train Arrives at 11:04 and there's no update. When time turns to 11:01, even if no update, refresh.
- [ ] Fix hourly weather... seems like it's only 100% or zero?


## Credits
- IT8951 library by GregDMeyer: https://github.com/GregDMeyer/IT8951

## Setting up as a service
To have the display start automatically on boot:

```bash
sudo systemctl restart subway-eink.service
sudo systemctl stop subway-eink.service
```

```bash
[Unit]
Description=Subway E-Ink Display Service
After=network.target

[Service]
Type=simple
User=sambroner
WorkingDirectory=/path/to/repo
ExecStart=/path/to/uv run runner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```