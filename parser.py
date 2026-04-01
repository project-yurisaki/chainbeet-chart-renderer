import json
from model import Note, NoteInfo, NoteRawInfo, NoteType


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
        note_position = position_idx / (position_split - 1)
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
            case NoteType.CHARGE_MIDDLE:
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
