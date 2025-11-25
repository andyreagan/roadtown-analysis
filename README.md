# Race Results Analysis

Interactive D3.js visualization showing fastest race times by age for male and female runners.

## Files

- `results.txt` - Race results data (tab-separated)
- `server.py` - Flask server that parses and serves the data as JSON
- `race_chart.html` - D3.js interactive chart visualization

## Setup

Dependencies are managed with `uv`:

```bash
uv add flask
```

## Running

Start the Flask server:

```bash
uv run python server.py
```

Then open your browser to:
```
http://localhost:5000
```

## Features

- Interactive line chart with two curves (Male and Female)
- Shows the fastest time for each age
- Hover over data points to see:
  - Runner's age
  - Time
  - Runner's name
- Summary statistics for both male and female runners
- Responsive design with clean styling

## Data API

The server exposes a JSON endpoint at `/data` that returns:
```json
{
  "male": [
    {"age": 24, "time_seconds": 1039.9, "time_display": "17:19.9", "name": "Willem Goff"},
    ...
  ],
  "female": [
    {"age": 30, "time_seconds": 1223.1, "time_display": "20:23.1", "name": "Kaitlyn Howard"},
    ...
  ]
}
```
