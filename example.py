import argparse
from pathlib import Path
from parser import load
from renderer import ChainbeetRenderer
import skia as sk

if __name__ == '__main__':
    cli = argparse.ArgumentParser(description='Render a JSON or binary ChainBeeT chart.')
    cli.add_argument('chart', nargs='?', type=Path, default=Path(__file__).parent / 'assets/gengaozo.json')
    cli.add_argument('-o', '--output', type=Path)
    cli.add_argument('--mirror', action='store_true')
    cli.add_argument('--name', help='Chart title displayed in the preview.')
    args = cli.parse_args()
    chart = load(args.chart, mirror=args.mirror)
    chart_name = args.name or ('G e n g a o z o [EXTRA 10]' if args.chart.name == 'gengaozo.json' else args.chart.stem)
    renderer = ChainbeetRenderer(chart, chart_name=chart_name)
    image = renderer.render()
    image.save(str(args.output or args.chart.with_suffix('.png').name), sk.EncodedImageFormat.kPNG)
