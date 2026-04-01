from enum import IntEnum
from typing import NamedTuple


class NoteType(IntEnum):
    # Type 1: Play Bgm
    PLAY_BGM = 1
    # Type 2: Bpm Change
    BPM_CHANGE = 2
    # Type 3: Time Scale
    TIME_SCALE = 3

    # Type 10: NormalNote
    NORMAL = 10

    # Type 20: ChargeBeginNote
    CHARGE_BEGIN = 20
    # Type 21: ChargeEndNote
    CHARGE_END = 21
    # Type 22: ChargeMiddleNote
    CHARGE_MIDDLE = 22

    # Type 30: ChainNote
    CHAIN_BEGIN = 30
    # Type 31: ChainNote
    CHAIN_MIDDLE = 31
    # Type 32: ChainNote
    CHAIN_END = 32
    # Type 33: ChainMiddleNote (Conditional) (Automatically created by game, not used in chart)
    CHAIN_AUTO_MIDDLE = 33

    # Type 40: WideNote
    WIDE = 40

    # Type 50: WideChargeBeginNote
    WIDE_CHARGE_BEGIN = 50
    # Type 51: WideChargeEndNote
    WIDE_CHARGE_END = 51

    # Type 60: LongChainBeginNote
    LONG_CHAIN_BEGIN = 60
    # Type 61: LongChainEndNote
    LONG_CHAIN_END = 61
    # Type 62: LongChinaNote
    LONG_CHAIN_MIDDLE = 62

    @classmethod
    def _missing_(cls, value):
        if not isinstance(value, int):
            return None
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN_{value}"
        member._value_ = value
        return member


class NoteRawInfo(NamedTuple):
    beat_plus: int
    position_split: int
    beat_split: int
    position_idx: int
    beat_idx: int
    note_type: NoteType
    raw_params: list[int | float]


class Note:
    note_type: NoteType
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

    def __init__(self, note_type: NoteType, position: float, time: float, bpm: float, type_arg, type_arg_2, raw_info: NoteRawInfo) -> None:
        self.note_type = note_type
        self.position = position
        self.time = time
        self.bpm = bpm
        self.raw_info = raw_info
        self.file = type_arg if isinstance(type_arg, str) else None
        self.change_bpm = float(type_arg) if (isinstance(type_arg, float) or isinstance(type_arg, int)) and self.note_type == NoteType.BPM_CHANGE else None
        self.time_scale = float(type_arg) if (isinstance(type_arg, float) or isinstance(type_arg, int)) and self.note_type == NoteType.TIME_SCALE else None
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
        return self.note_type in {
            NoteType.WIDE,
            NoteType.WIDE_CHARGE_BEGIN,
            NoteType.WIDE_CHARGE_END,
        }

    def is_chain_note(self, arg: int):
        if self.note_type in {
            NoteType.CHAIN_BEGIN,
            NoteType.CHAIN_MIDDLE,
            NoteType.CHAIN_END,
        }:
            return True
        return self.note_type == NoteType.CHAIN_AUTO_MIDDLE and ((arg ^ 1) & 1) == 1

    def is_long_chain_note(self):
        return self.note_type in {
            NoteType.LONG_CHAIN_BEGIN,
            NoteType.LONG_CHAIN_END,
            NoteType.LONG_CHAIN_MIDDLE,
        }

    def is_long_note(self):
        return self.note_type in {
            NoteType.CHARGE_BEGIN,
            NoteType.CHARGE_END,
            NoteType.CHARGE_MIDDLE,
            NoteType.WIDE_CHARGE_BEGIN,
            NoteType.WIDE_CHARGE_END,
        }

    def is_tap_note(self):
        return self.note_type in {NoteType.NORMAL, NoteType.WIDE}

    def is_meta_note(self):
        return self.note_type in {
            NoteType.PLAY_BGM,
            NoteType.BPM_CHANGE,
            NoteType.TIME_SCALE,
        }


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
