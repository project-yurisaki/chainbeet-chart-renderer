from collections import Counter
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from binary_chart import decode_blob
from model import NoteType
from parser import load, parse, parse_blob


ROOT = Path(__file__).resolve().parents[1]


def uint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def sint(value):
    return uint((value << 1) ^ (value >> 31))


def record(kind, delta, position, index, extra=b'', pair=None):
    return (bytes([kind | (0x80 if pair is not None else 0)])
            + (uint(pair) if pair is not None else b'')
            + sint(delta) + sint(position) + sint(index) + extra)


def cbtn(records, *, pairs=((7, 16),), strings=('Sound/test/', 'bgm'),
         compressed=False, bpm=120.0, suffix=b''):
    payload = struct.pack('<diHHII', bpm, -20, 0, 0, 0, 0)
    payload += b''.join(sint(a) + sint(b) for a, b in pairs)
    payload += b''.join(uint(len(s.encode())) + s.encode() for s in strings)
    payload += b''.join(records) + suffix
    stored = zlib.compress(payload) if compressed else payload
    return struct.pack('<4sHHIIIIHHI', b'CBTN', 3, int(compressed), 32,
                       len(payload), len(stored), len(records), len(pairs),
                       len(strings), zlib.crc32(payload)) + stored


class BinaryChartTests(unittest.TestCase):
    def test_real_cbne_matches_every_legacy_record(self):
        blob = (ROOT / 'tests/fixtures/gengaozo.cbne').read_bytes()
        expected = json.loads((ROOT / 'assets/gengaozo.json').read_text())
        actual = decode_blob(blob)
        self.assertEqual(actual['info'], expected['info'])
        self.assertEqual(len(actual['notes']), 1629)
        self.assertEqual(Counter(map(tuple, actual['notes'])),
                         Counter(map(tuple, expected['notes'])))
        binary_notes = parse_blob(blob).notes
        json_notes = parse(json.dumps(expected)).notes
        def signature(note):
            return (note.note_type, round(note.time, 9), round(note.position, 9),
                    note.bpm, note.group, note.file,
                    round(note.next_note.time, 9) if note.next_note else None)
        self.assertEqual(Counter(map(signature, binary_notes)),
                         Counter(map(signature, json_notes)))

    def test_parse_and_load_detect_json_and_binary(self):
        value = {'info': {'bpm': 120, 'delay': -20, 'dir': 'Sound/test/'},
                 'notes': [[1, 7, 16, 1, 0, 10]]}
        binary = cbtn([record(10, 1, 1, 0)])
        for data in [json.dumps(value), json.dumps(value).encode(),
                     binary, bytearray(binary), memoryview(binary)]:
            with self.subTest(kind=type(data).__name__):
                self.assertEqual(parse(data).notes[0].time, 2.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chart.blob'
            path.write_bytes(binary)
            self.assertEqual(load(path).directory, 'Sound/test/')

    def test_compressed_and_uncompressed_cbtn(self):
        records = [record(1, 0, 0, 0, uint(1)), record(10, 1, 6, 4)]
        expected = {'info': {'bpm': 120.0, 'delay': -20, 'dir': 'Sound/test/'},
                    'notes': [[0, 7, 16, 0, 0, 1, 'bgm'], [1, 7, 16, 6, 4, 10]]}
        for compressed in [False, True]:
            self.assertEqual(decode_blob(cbtn(records, compressed=compressed)), expected)

    def test_negative_indices_do_not_change_accumulated_raw_beat(self):
        chart = parse_blob(cbtn([
            record(30, 16, 1, 14, sint(144)),
            record(31, 1, 2, -1, sint(144)),
            record(32, 0, 3, 0, sint(144)),
        ]))
        self.assertEqual([(n.raw_info.beat_plus, n.raw_info.beat_idx) for n in chart.notes],
                         [(16, 14), (16, 15), (17, 0)])
        self.assertIs(chart.notes[0].next_note, chart.notes[1])
        self.assertIs(chart.notes[1].next_note, chart.notes[2])

    def test_layout_switches_bpm_speed_width_audio_and_mirror(self):
        records = [
            record(0, 0, 0, 0, uint(1)),
            record(2, 0, 0, 0, struct.pack('<d', 240), pair=1),
            record(3, 0, 0, 0, struct.pack('<d', 0.5), pair=1),
            record(40, 1, 6, 0, struct.pack('<d', 0.25)),
        ]
        chart = parse_blob(cbtn(records, pairs=((7, 16), (1, 1))), mirror=True)
        self.assertTrue(chart.notes[0].is_meta_note())
        self.assertEqual(chart.notes[0].file, 'bgm')
        self.assertEqual(chart.notes[1].change_bpm, 240)
        self.assertEqual(chart.notes[1].position, 0)
        self.assertEqual(chart.notes[2].time_scale, 0.5)
        self.assertEqual(chart.notes[3].time, 1)
        self.assertEqual(chart.notes[3].position, 0)
        self.assertEqual(chart.notes[3].width, 0.25)

    def test_wide_charge_middle_and_interleaved_long_chain_groups(self):
        records = [
            record(50, 0, 0, 0, sint(3) + struct.pack('<d', 0.2)),
            record(52, 0, 1, 4, sint(3) + struct.pack('<d', 0.3)),
            record(51, 0, 2, 8, sint(3) + struct.pack('<d', 0.4)),
            record(60, 1, 0, 0, sint(7)),
            record(60, 0, 6, 0, sint(8)),
            record(62, 0, 1, 4, sint(7)),
            record(62, 0, 5, 4, sint(8)),
            record(61, 0, 2, 8, sint(7)),
            record(61, 0, 4, 8, sint(8)),
        ]
        chart = parse_blob(cbtn(records))
        middle = chart.notes[1]
        self.assertEqual(middle.note_type, NoteType.WIDE_CHARGE_MIDDLE)
        self.assertTrue(middle.is_long_note())
        self.assertTrue(middle.is_wide_note())
        self.assertEqual(middle.width, 0.3)
        self.assertIs(chart.notes[0].next_note, middle)
        self.assertIs(middle.next_note, chart.notes[2])
        for group in [7, 8]:
            notes = [n for n in chart.notes if n.group == group]
            self.assertIs(notes[0].next_note, notes[1])
            self.assertIs(notes[1].next_note, notes[2])

    def test_tampered_cbne_header_ciphertext_and_tag_are_rejected(self):
        original = (ROOT / 'tests/fixtures/gengaozo.cbne').read_bytes()
        for offset in [16, 32, 40, 56, len(original) - 1]:
            data = bytearray(original)
            data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'authentication'):
                decode_blob(data)

    def test_unsupported_headers_and_size_mismatches(self):
        original = cbtn([record(10, 1, 1, 0)])
        for offset, value in [(4, 4), (6, 2), (8, 31), (12, 0), (16, 1)]:
            data = bytearray(original)
            data[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_blob(data)
        for data in [b'', b'CBTN', b'CBNE', original[:-1], original + b'\0']:
            with self.assertRaises(ValueError):
                decode_blob(data)

    def test_crc_and_compressed_length_checks(self):
        corrupted = bytearray(cbtn([record(10, 1, 1, 0)]))
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC32'):
            decode_blob(corrupted)
        data = bytearray(cbtn([record(10, 1, 1, 0)], compressed=True))
        struct.pack_into('<I', data, 12, 1)
        with self.assertRaises(ValueError):
            decode_blob(data)
        corrupted = bytearray(cbtn([record(10, 1, 1, 0)], compressed=True))
        corrupted[32] ^= 1
        with self.assertRaisesRegex(ValueError, 'zlib'):
            decode_blob(corrupted)

    def test_invalid_records_are_rejected(self):
        invalid = [
            record(33, 0, 0, 0),
            record(10, 0, 7, 0),
            record(10, 0, -1, 0),
            record(10, 0, 0, 0, pair=2),
            record(1, 0, 0, 0, uint(2)),
            record(2, 0, 0, 0, struct.pack('<d', math.inf)),
            b'\x0a' + b'\x80' * 10 + b'\x00\x00',
            record(10, 0, 0, 0)[:-1],
        ]
        for data in invalid:
            with self.subTest(record=data.hex()), self.assertRaises(ValueError):
                decode_blob(cbtn([data]))
        with self.assertRaisesRegex(ValueError, 'Trailing'):
            decode_blob(cbtn([record(10, 0, 0, 0)], suffix=b'\0'))
        with self.assertRaises(ValueError):
            decode_blob(cbtn([record(10, 0, 0, 0)], pairs=((1, 1),)))


if __name__ == '__main__':
    unittest.main()
