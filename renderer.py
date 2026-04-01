from model import NoteInfo, Note, NoteType
from typing import Optional
import math
import skia as sk


def analyze_beat_lines(chart: NoteInfo, max_time: Optional[float] = None) -> list[float]:
    bpm_changes = [x for x in chart.notes if x.note_type == NoteType.BPM_CHANGE]
    max_time = max(x.time for x in chart.notes) if max_time is None else max_time
    curr_bpm = chart.bpm
    curr_time = 0.0
    timings: list[float] = []
    curr_index = 0
    while True:
        limit_time = max_time if curr_index >= len(bpm_changes) else bpm_changes[curr_index].time
        delta_time = 60 / curr_bpm * 4
        while curr_time + delta_time < limit_time:
            curr_time += delta_time
            timings.append(curr_time)
        if curr_index < len(bpm_changes):
            curr_bpm = bpm_changes[curr_index].change_bpm
            timings.append(bpm_changes[curr_index].time)
            curr_time = bpm_changes[curr_index].time
        else:
            break
        curr_index += 1
    return timings


def analyze_coincident_lines(notes: list[Note]) -> list[tuple[float, list[Note]]]:
    timings: dict[float, list[Note]] = {}
    for note in notes:
        if note.is_meta_note():
            continue
        if note.time not in timings:
            timings[note.time] = []
        timings[note.time].append(note)
    result: list[tuple[float, list[Note]]] = []
    for time, note_list in timings.items():
        if len(note_list) < 2:
            continue
        note_list.sort(key=lambda x: x.position)
        result.append((time, note_list))
    return result


def analyze_beats(notes: list) -> list[tuple[float, int]]:
    timings: list[float] = []
    timing_bpm: dict[float, float] = {}
    for note in notes:
        if note.is_meta_note():
            continue
        timings.append(note.time)
        timing_bpm[note.time] = note.bpm
    timings = sorted(list(set(timings)))
    result: list[tuple[float, int]] = []
    error_tolerance: float = 0.05
    for i in range(len(timings)):
        curr = timings[i]
        time_delta = 60.0 / timing_bpm[curr] * 4
        beat = 0
        # if i > 0:
        #     prev = time_delta / (curr - timings[i - 1])
        #     if abs(prev - round(prev)) < error_tolerance:
        #         beat = max(beat, round(prev))
        if i < len(timings) - 1:
            nxt = time_delta / (timings[i + 1] - curr)
            if abs(nxt - round(nxt)) < error_tolerance:
                beat = max(beat, round(nxt))
        if beat % 2 == 0 and beat:
            result.append((curr, beat))
    return result


def _create_charge_path(width: float, base_size: float):
    """Create note head/tail path for charge notes"""
    extra_width = width - base_size * 2
    half_width = extra_width / 2
    path = sk.Path()
    half_base = base_size / 2
    a = half_base * (3 ** 0.5)
    path.moveTo(-base_size - half_width, 0)
    path.lineTo(-half_base - half_width, -a)
    path.lineTo(half_base + half_width, -a)
    path.lineTo(base_size + half_width, 0)
    path.lineTo(half_base + half_width, a)
    path.lineTo(-half_base - half_width, a)
    path.close()
    return path


def _create_chain_path(base_size: float):
    """Create note head/tail path for chain notes"""
    path = sk.Path()
    path.moveTo(0, -base_size)
    path.lineTo(base_size, 0)
    path.lineTo(0, base_size)
    path.lineTo(-base_size, 0)
    path.close()
    return path


def _get_time_description(time: float) -> str:
    seconds = time % 60
    minutes = int(time // 60)
    return '{}:{:.2f}'.format(minutes, seconds)


class ChainbeetRenderConfig:
    height_factor: int = 300
    track_width: int = 450
    height_extra: int = 100
    width_extra: int = 150
    width_scale: float = 0.9
    page_height: int = 3000
    top_margin: int = 50
    bottom_margin: int = 50
    note_base_size: int = 10

    min_time_scale: float = 0.5
    max_time_scale: float = 2.0


class ChainbeetRenderer:
    def __init__(
        self,
        chart: NoteInfo,
        config: Optional[ChainbeetRenderConfig] = None,
        chart_name: Optional[str] = None,
        text_font: Optional[sk.Font] = None
    ):
        self.config = config or ChainbeetRenderConfig()
        self.chart = chart
        self.bpm = chart.bpm
        self.notes: list[Note] = chart.notes.copy()
        self.notes.sort(key=lambda x: x.time)
        self.speed_changes = [x for x in self.notes if x.note_type == NoteType.TIME_SCALE]
        self.chart_name = chart_name
        self.text_font = text_font

    def compute_time_y(self, time: float) -> float:
        current_sum = 0.0
        last_change_time = 0.0
        current_speed = 1.0
        for i in range(len(self.speed_changes)):
            if time > self.speed_changes[i].time:
                current_sum += current_speed * (self.speed_changes[i].time - last_change_time)
                last_change_time = self.speed_changes[i].time
                current_speed = min(max(self.config.min_time_scale, self.speed_changes[i].time_scale), self.config.max_time_scale)
            else:
                break
        if time > last_change_time:
            current_sum += current_speed * (time - last_change_time)
        return current_sum * self.config.height_factor
    
    def get_combo_before(self, time: float) -> int:
        return len([x for x in self.notes if x.time < time and not x.is_meta_note()])

    def render(self) -> sk.Image:
        base_size = self.config.note_base_size
        notes = self.notes
        max_time = max(x.time for x in notes) + 2
        height = int(self.compute_time_y(max_time)) + 1
        width = self.config.track_width
        surface = sk.Surface(width + self.config.width_extra, height + self.config.height_extra)
        canvas: sk.Canvas = surface.getCanvas()
        canvas.translate(self.config.width_extra / 2, self.config.height_extra / 2)
        tap_paint = sk.Paint(Color=0xff7b013d, AntiAlias=True)
        note_stroke_paint = sk.Paint(Color=0xffe8c9c7, AntiAlias=True, Style=sk.Paint.kStroke_Style, StrokeWidth=2.5)
        note_bold_stroke_paint = sk.Paint(Color=0xffe8c9c7, AntiAlias=True, Style=sk.Paint.kStroke_Style, StrokeWidth=4)
        chain_paint = sk.Paint(Color=0xff004a80)
        charge_paint = sk.Paint(Color=0xff3c7b1e)
        long_chain_paint = sk.Paint(Color=0xff1d4674)
        long_chain_segment_paint = sk.Paint(Color=0xff1f2e41)
        charge_segment_paint = sk.Paint(Color=0xff374219, AntiAlias=True)
        charge_segment_stroke_paint = sk.Paint(Color=0xdde8c9c7, AntiAlias=True, Style=sk.Paint.kStroke_Style,
                                               StrokeWidth=1)
        chain_connection_paint = sk.Paint(Color=0xffeeeeee, AntiAlias=True,
                                          PathEffect=sk.DashPathEffect.Make([15, 15], 0))
        line_paint = sk.Paint(Color=0xffeeeeee)
        beat_line_paint = sk.Paint(Color=0xff888888, StrokeWidth=1)
        chain_path = _create_chain_path(base_size)
        for note in notes:
            note.position -= (note.position - 0.5) * (1.0 - self.config.width_scale)
        layer_paint = sk.Paint(Color=0x11ffff00)
        # Speed Change Hint
        for i in range(len(self.speed_changes)):
            if self.speed_changes[i].time_scale != 1:
                limit_time = max_time if i + 1 >= len(self.speed_changes) else self.speed_changes[i + 1].time
                canvas.drawRect(sk.Rect(0, height - self.compute_time_y(limit_time), width, height - self.compute_time_y(self.speed_changes[i].time)), layer_paint)
        # Beatline Hint
        hint_paint = sk.Paint(Color=0xffffffff)
        hint_font = sk.Font()
        hint_font.setSize(20)
        for time in analyze_beat_lines(self.chart, max_time):
            y = height - self.compute_time_y(time)
            combo = str(self.get_combo_before(time))
            canvas.drawLine(0, y, width, y, beat_line_paint)
            text_width = hint_font.measureText(combo)
            canvas.drawString(combo, -text_width - 10, y + hint_font.getMetrics().fDescent - hint_font.getSpacing() / 2, hint_font, hint_paint)
            t = _get_time_description(time)
            text_width = hint_font.measureText(t)
            canvas.drawString(t, - text_width - 10, y + hint_font.getMetrics().fDescent + hint_font.getSpacing() / 2, hint_font, hint_paint)
        analyzed_lines = analyze_coincident_lines(notes)
        for time, note_list in analyzed_lines:
            y = height - self.compute_time_y(time)
            start_pos = min(x.position for x in note_list)
            end_pos = max(x.position for x in note_list)
            canvas.drawLine(start_pos * width, y, end_pos * width, y, line_paint)
        # Chart Notes
        coincident_timings = set(x[0] for x in analyzed_lines)
        notes.sort(key=lambda x: x.time)
        for note in notes:
            if note.is_tap_note():
                note_width = width * (note.width or 0) * self.config.width_scale if note.is_wide_note() else base_size * 2
                y = height - self.compute_time_y(note.time)
                rect = sk.Rect(width * note.position - note_width / 2, y - base_size,
                               width * note.position + note_width / 2, y + base_size)
                canvas.drawRoundRect(rect, base_size, base_size, tap_paint)
                canvas.drawRoundRect(rect, base_size, base_size,
                                     note_bold_stroke_paint if note.time in coincident_timings else note_stroke_paint)
            elif note.is_chain_note(0):
                if note.next_note:
                    start_x, start_y = width * note.position, height - self.compute_time_y(note.time)
                    end_x, end_y = width * note.next_note.position, height - self.compute_time_y(note.next_note.time)
                    canvas.drawLine(start_x, start_y, end_x, end_y, chain_connection_paint)
                chain_path.offset(width * note.position, height - self.compute_time_y(note.time))
                canvas.drawPath(chain_path, chain_paint)
                canvas.drawPath(chain_path,
                                note_bold_stroke_paint if note.time in coincident_timings else note_stroke_paint)
                chain_path.offset(-width * note.position, -(height - self.compute_time_y(note.time)))
            elif note.is_long_note() or note.is_long_chain_note():
                note_width = width * (note.width or 0) * self.config.width_scale if note.is_wide_note() else base_size * 2
                if note.next_note:
                    start_x, start_y = width * note.position, height - self.compute_time_y(note.time)
                    end_x, end_y = width * note.next_note.position, height - self.compute_time_y(note.next_note.time)
                    path = sk.Path()
                    path.moveTo(start_x - note_width / 2, start_y)
                    path.lineTo(start_x + note_width / 2, start_y)
                    path.lineTo(end_x + note_width / 2, end_y)
                    path.lineTo(end_x - note_width / 2, end_y)
                    path.close()
                    canvas.drawPath(path, charge_segment_paint if note.is_long_note() else long_chain_segment_paint)
                    canvas.drawPath(path, charge_segment_stroke_paint)
                if note.is_long_note() or (note.is_long_chain_note() and note.note_type in {NoteType.LONG_CHAIN_BEGIN, NoteType.LONG_CHAIN_END}):
                    charge_path = _create_charge_path(note_width, base_size) if note.is_long_note() else _create_chain_path(base_size)
                    charge_path.offset(width * note.position, height - self.compute_time_y(note.time))
                    canvas.drawPath(charge_path, charge_paint if note.is_long_note() else long_chain_paint)
                    canvas.drawPath(charge_path,
                                    note_bold_stroke_paint if note.time in coincident_timings else note_stroke_paint)
                    charge_path.offset(-width * note.position, -(height - self.compute_time_y(note.time)))
        # Note Beat Text Hint
        text_paint = sk.Paint(Color=0xffffffff)
        text_font = sk.Font()
        text_font.setSize(20)
        for time, split in analyze_beats(notes):
            y = height - self.compute_time_y(time)
            x = width + 10
            canvas.drawString(str(split), x, y + text_font.getMetrics().fDescent, text_font, text_paint)
        # Speed Change Text Hint
        text_font.setSize(16)
        for i in range(len(self.speed_changes)):
            y = height - self.compute_time_y(self.speed_changes[i].time)
            text = '{:g}x'.format(self.speed_changes[i].time_scale)
            canvas.drawString(text, 10, y + text_font.getMetrics().fDescent, text_font, text_paint)
        # BPM Change Text Hint
        for bpm_change in [x for x in self.chart.notes if x.note_type == NoteType.BPM_CHANGE]:
            y = height - self.compute_time_y(bpm_change.time)
            t = str(bpm_change.change_bpm)
            text_width = text_font.measureText(t)
            canvas.drawString(t, width - text_width - 10, y + text_font.getMetrics().fDescent, text_font, text_paint)
        # Chart Boundary Lines
        paint = sk.Paint(Color=0xffffffff)
        canvas.drawLine(0, 0, 0, height, paint)
        canvas.drawLine(width, 0, width, height, paint)
        image: sk.Image = surface.makeImageSnapshot()
        # Split chart to pages
        info_height = 40
        height_limit = self.config.page_height
        required_page = math.ceil(surface.height() / height_limit)
        required_width = required_page * surface.width()
        image_height = height_limit + self.config.top_margin + self.config.bottom_margin + info_height
        surface_2 = sk.Surface(required_width, image_height)
        canvas = surface_2.getCanvas()
        canvas.drawColor(0xff080403)
        for i in range(required_page):
            top_y, bottom_y = surface.height() - height_limit * (i + 1), surface.height() - height_limit * i
            src_rect = sk.Rect(0, top_y, surface.width(), bottom_y)
            dst_rect = sk.Rect(surface.width() * i, self.config.top_margin, surface.width() * (i + 1), self.config.top_margin + height_limit)
            canvas.drawImageRect(image, src_rect, dst_rect)
        # Draw Infomation
        renderer_info = 'Generated by chainbeet-chart-renderer'
        mirror_tip = ' // Mirror Chart ' if self.chart.is_mirror else ''
        if self.chart_name:
            text = '{} // BaseBPM: {} {} //  {}'.format(self.chart_name, self.chart.bpm, mirror_tip, renderer_info)
        else:
            text = 'BaseBPM: {}  // {} {}'.format(self.chart.bpm, mirror_tip, renderer_info)
        text_font = self.text_font or sk.Font()
        text_font.setSize(40)
        text_y = height_limit + self.config.top_margin + self.config.bottom_margin / 2 + 25
        canvas.drawString(text, self.config.width_extra / 2, text_y, text_font, text_paint)
        image = surface_2.makeImageSnapshot()
        return image
