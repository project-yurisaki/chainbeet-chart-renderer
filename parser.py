import json
from typing import NamedTuple


class NoteRawInfo(NamedTuple):
    beat_plus: int
    position_split: int
    beat_split: int
    position_idx: int
    beat_idx: int
    note_type: int
    raw_params: list[int | float]


class Note:
    note_type: int
    position: float
    time: float
    bpm: float
    file: str | None
    group: int | None
    change_bpm: float | None
    width: float | None
    time_scale: float | None
    prev_note: "Note | None"
    next_note: "Note | None"
    raw_info: NoteRawInfo
    
    def __init__(self, note_type: int, position: float, time: float, bpm: float, type_arg, type_arg_2, raw_info: NoteRawInfo) -> None:
        self.note_type = note_type
        self.position = position
        self.time = time
        self.bpm = bpm
        self.raw_info = raw_info
        self.file = type_arg if isinstance(type_arg, str) else None
        self.change_bpm = float(type_arg) if (isinstance(type_arg, float) or isinstance(type_arg, int)) and self.note_type == 2 else None
        self.time_scale = float(type_arg) if (isinstance(type_arg, float) or isinstance(type_arg, int)) and self.note_type == 3 else None
        self.group = int(type_arg) if self.is_long_note() or self.is_chain_note(0) else None
        if self.is_wide_note():
            if self.is_tap_note():
                self.width = type_arg
            else:
                self.width = type_arg_2
        else:
            self.width = None
        self.prev_note, self.next_note = None, None
        
    def is_wide_note(self):
        return self.note_type >= 40
        
    def is_chain_note(self, arg: int):
        # Type 30,31,32: ChainNote
        if (self.note_type - 30) < 3 and (self.note_type >= 30):
            return True
        # Type 33: ChainMiddleNote (Conditional) (Automatically created by game, not used in chart)
        return self.note_type == 33 and ((arg ^ 1) & 1) == 1
        
    def is_long_note(self):
        # Type 20: ChargeBeginNote
        # Type 21: ChargeEndNote
        # Type 22: ChargeMiddleNote
        if (self.note_type - 20) < 3 and (self.note_type >= 20):
            return True
        # Type 50: WideChargeBeginNote
        # Type 51: WideChargeEndNote
        return (self.note_type - 50) < 2 and (self.note_type >= 50)
    
    def is_tap_note(self):
        # Type 10: NormalNote
        # Type 40: WideNote
        return self.note_type == 10 or self.note_type == 40

    def is_meta_note(self):
        # Type 1: Play Bgm
        # Type 2: Bpm Change
        # Type 3: Time Scale
        return self.note_type < 10


class NoteInfo:
    bpm: float
    directory: str | None
    delay: int
    notes: list[Note]
    is_mirror: bool

    def __init__(self, bpm: float, directory: str | None, delay: int, notes: list[Note], is_mirror: bool = False) -> None:
        self.bpm = bpm
        self.directory = directory
        self.delay = delay
        self.notes = notes
        self.is_mirror = is_mirror


def _raw_note_sort_key(note) -> float:
    beat_plus: int = note[0]
    beat_split: int = note[2]
    beat_idx: int = note[4]
    return ((beat_idx / beat_split) + beat_plus)

    
def parse(info_json: str, mirror: bool=False) -> NoteInfo:
    value = json.loads(info_json)
    info_value = value['info']
    info = NoteInfo(float(info_value['bpm']), info_value.get('dir'), int(info_value.get('delay', 0)), [], mirror)
    notes = value['notes']
    curr_time = 0.0
    curr_bpm = info.bpm
    minus_beat = 0.0
    charge_group_end: dict[int | None, Note] = {}
    chain_group_end: dict[int | None, Note] = {}
    notes.sort(key=_raw_note_sort_key)
    for note in notes:
        beat_plus: int = note[0]
        position_split: int = note[1]
        beat_split: int = note[2]
        position_idx: int = note[3]
        beat_idx: int = note[4]
        note_type: int = note[5]
        raw_info: NoteRawInfo = NoteRawInfo(beat_plus, position_split, beat_split, position_idx, beat_idx, note_type, note)
        if mirror:
            position_idx = ~position_idx + position_split
        time_delta = (60.0 / curr_bpm * 4) * (((beat_idx / beat_split) + beat_plus) - minus_beat)
        note_time = curr_time + time_delta
        type_arg = note[6] if len(note) >= 7 else None
        type_arg_2 = note[7] if len(note) >= 8 else None
        note_position = position_idx / (position_split - 1)
        logic_note = Note(note_type, note_position, note_time, curr_bpm, type_arg, type_arg_2, raw_info)
        info.notes.append(logic_note)
        match logic_note.note_type:
            case 2:
                curr_time += time_delta
                minus_beat = beat_idx / beat_split + beat_plus
                curr_bpm = logic_note.change_bpm
            case 20 | 50:
                charge_group_end[logic_note.group] = logic_note
            case 21 | 51:
                prev = charge_group_end.pop(logic_note.group)
                prev.next_note = logic_note
                logic_note.prev_note = prev
            case 22:
                prev = charge_group_end[logic_note.group]
                prev.next_note = logic_note
                logic_note.prev_note = prev
                charge_group_end[logic_note.group] = logic_note
            case 30:
                chain_group_end[logic_note.group] = logic_note
            case 31 | 32:
                prev = chain_group_end[logic_note.group]
                prev.next_note = logic_note
                logic_note.prev_note = prev
                chain_group_end[logic_note.group] = logic_note
    return info
