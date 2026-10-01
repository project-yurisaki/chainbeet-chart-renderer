import json
from pathlib import Path
from binary_chart import decode_blob
from model import Note, NoteInfo, NoteRawInfo, NoteType


def _raw_note_sort_key(note) -> float:
    beat_plus: int = note[0]
    beat_split: int = note[2]
    beat_idx: int = note[4]
    return ((beat_idx / beat_split) + beat_plus)

    
def parse(info_json: str | bytes | bytearray | memoryview, mirror: bool=False) -> NoteInfo:
    """Analyze a JSON chart or a binary CBNE/CBTN chart (including SQLite BLOBs)."""
    if not isinstance(info_json, str):
        info_json = bytes(info_json)
        if info_json.startswith((b'CBNE', b'CBTN')):
            return parse_blob(info_json, mirror)
    return _parse_value(json.loads(info_json), mirror)


def parse_blob(data: bytes | bytearray | memoryview, mirror: bool=False) -> NoteInfo:
    """Analyze a binary chart exported from note.data_v2 or saved as a file."""
    return _parse_value(decode_blob(data), mirror)


def load(path: str | Path, mirror: bool=False) -> NoteInfo:
    """Load a chart file, automatically detecting JSON, CBNE or CBTN."""
    return parse(Path(path).read_bytes(), mirror)


def _parse_value(value: dict, mirror: bool) -> NoteInfo:
    info_value = value['info']
    info = NoteInfo(float(info_value['bpm']), info_value.get('dir'), int(info_value.get('delay', 0)), [], mirror)
    notes = value['notes']
    curr_time = 0.0
    curr_bpm = info.bpm
    minus_beat = 0.0
    charge_group_end: dict[int | None, Note] = {}
    chain_group_end: dict[int | None, Note] = {}
    long_chain_group_end: dict[int | None, Note] = {}
    notes.sort(key=_raw_note_sort_key)
    for note in notes:
        beat_plus: int = note[0]
        position_split: int = note[1]
        beat_split: int = note[2]
        position_idx: int = note[3]
        beat_idx: int = note[4]
        note_type = NoteType(note[5])
        raw_info: NoteRawInfo = NoteRawInfo(beat_plus, position_split, beat_split, position_idx, beat_idx, note_type, note)
        if mirror:
            position_idx = ~position_idx + position_split
        time_delta = (60.0 / curr_bpm * 4) * (((beat_idx / beat_split) + beat_plus) - minus_beat)
        note_time = curr_time + time_delta
        type_arg = note[6] if len(note) >= 7 else None
        type_arg_2 = note[7] if len(note) >= 8 else None
        # Timing/audio events can use the client's single-position (1, 1) layout.
        note_position = 0.0 if position_split == 1 and note_type in {0, 1, 2, 3} else position_idx / (position_split - 1)
        logic_note = Note(note_type, note_position, note_time, curr_bpm, type_arg, type_arg_2, raw_info)
        info.notes.append(logic_note)
        match logic_note.note_type:
            case NoteType.BPM_CHANGE:
                curr_time += time_delta
                minus_beat = beat_idx / beat_split + beat_plus
                curr_bpm = logic_note.change_bpm
            case NoteType.CHARGE_BEGIN | NoteType.WIDE_CHARGE_BEGIN:
                charge_group_end[logic_note.group] = logic_note
            case NoteType.CHARGE_END | NoteType.WIDE_CHARGE_END:
                prev = charge_group_end.pop(logic_note.group)
                prev.next_note = logic_note
                logic_note.prev_note = prev
            case NoteType.CHARGE_MIDDLE | NoteType.WIDE_CHARGE_MIDDLE:
                prev = charge_group_end[logic_note.group]
                prev.next_note = logic_note
                logic_note.prev_note = prev
                charge_group_end[logic_note.group] = logic_note
            case NoteType.CHAIN_BEGIN:
                chain_group_end[logic_note.group] = logic_note
            case NoteType.CHAIN_MIDDLE | NoteType.CHAIN_END:
                prev = chain_group_end[logic_note.group]
                prev.next_note = logic_note
                logic_note.prev_note = prev
                chain_group_end[logic_note.group] = logic_note
            case NoteType.LONG_CHAIN_BEGIN:
                long_chain_group_end[logic_note.group] = logic_note
            case NoteType.LONG_CHAIN_END | NoteType.LONG_CHAIN_MIDDLE:
                prev = long_chain_group_end[logic_note.group]
                prev.next_note = logic_note
                logic_note.prev_note = prev
                long_chain_group_end[logic_note.group] = logic_note
    return info
