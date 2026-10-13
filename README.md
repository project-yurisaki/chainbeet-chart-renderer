# ChainBeeT Chart Renderer

![Yurisaki SubProject](https://img.shields.io/badge/SubProject-Yurisaki-A5D8FF?style=for-the-badge)
![Language Python](https://img.shields.io/badge/Language-Python-blue?style=for-the-badge)

Read ChainBeeT chart JSON or binary charts, analyze notes and
render a 2D chart preview.

Features:
* Coincident Note Hints
* Beat Hints
* Speed Change Hints
## Example Usage

Install the dependencies:

```bash
pip install -r requirements.txt
```

`parse()` accepts JSON strings, JSON bytes, or binary `CBNE` / `CBTN` bytes.
`load()` detects the format of a chart file automatically:

```python
from parser import load, parse, parse_blob
from renderer import ChainbeetRenderer

chart = load('chart.blob')  # An exported note.data_v2 BLOB, or a JSON file.
image = ChainbeetRenderer(chart, chart_name='My chart').render()
image.save('chart.png')
```

The example renderer also accepts chart files:

```bash
python example.py
python example.py chart.blob -o chart.png --name "My chart"
python example.py chart.blob -o chart-mirror.png --mirror
```

Run regression tests with `python -m unittest discover -s tests -v`.
## Sample Chart
2D chart preview for "G e n g a o z o" [EXTRA]:

![Gengaozo](/assets/gengaozo.png)
