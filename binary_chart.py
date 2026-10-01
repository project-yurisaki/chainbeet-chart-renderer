"""Decode the CBNE envelope and CBTN v3 chart format used by master_v2.db."""

import hmac
import math
import struct
import zlib


_ROOT_KEY = bytes.fromhex(
    'e0f6a01c5ad8a15629b7436d1f7ede06e63fb1824e8ba0e455464917e5d6a6e8'
)
_MAX_PAYLOAD = 64 * 1024 * 1024
_GROUP_TYPES = {20, 21, 22, 30, 31, 32, 60, 61, 62}
_WIDE_CHARGE_TYPES = {50, 51, 52}
_VALUE_TYPES = {2, 3, 40}
_AUDIO_TYPES = {0, 1}
_NOTE_TYPES = _GROUP_TYPES | _WIDE_CHARGE_TYPES | _VALUE_TYPES | _AUDIO_TYPES | {10}


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def read(self, size: int) -> bytes:
        if size < 0 or size > self.remaining:
            raise ValueError(f'Truncated CBTN payload at byte {self.offset}')
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]

    def uint(self) -> int:
        value = 0
        for shift in range(0, 70, 7):
            byte = self.unpack('<B')
            if shift == 63 and byte > 1:
                raise ValueError('CBTN varint exceeds 64 bits')
            value |= (byte & 0x7f) << shift
            if not byte & 0x80:
                return value
        raise ValueError('Invalid CBTN varint')

    def sint(self) -> int:
        value = self.uint()
        value = (value >> 1) ^ -(value & 1)
        if not -(1 << 31) <= value < (1 << 31):
            raise ValueError('CBTN signed integer exceeds 32 bits')
        return value

    def number(self) -> float:
        value = self.unpack('<d')
        if not math.isfinite(value):
            raise ValueError('Non-finite CBTN number')
        return value


def _decrypt_cbne(data: bytes) -> bytes:
    if len(data) < 72:
        raise ValueError('Truncated CBNE envelope')
    magic, version, flags, header_size, algorithm, chart_id = struct.unpack_from(
        '<4sHHIIQ', data
    )
    if (magic, version, flags, header_size, algorithm) != (b'CBNE', 1, 0, 56, 1):
        raise ValueError('Unsupported CBNE header')
    size = struct.unpack_from('<I', data, 52)[0]
    if size > 128 * 1024 * 1024 or len(data) != 56 + size + 16:
        raise ValueError('Invalid CBNE ciphertext size')

    # JSON and unencrypted CBTN do not require the cryptography dependency.
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    keys = [
        hmac.digest(_ROOT_KEY, b'ChainBeeT/CBTN-ENC/v1/layer' + layer, 'sha256')
        for layer in (b'1', b'2')
    ]
    try:
        encrypted_chart = AESGCM(keys[1]).decrypt(data[40:52], data[56:], data[:56])
    except InvalidTag as exc:
        raise ValueError(f'CBNE authentication failed for chart {chart_id}') from exc
    # The client uses only the first eight bytes of the 16-byte nonce field.
    decryptor = Cipher(algorithms.AES(keys[0]), modes.CTR(data[24:32] + bytes(8))).decryptor()
    return decryptor.update(encrypted_chart) + decryptor.finalize()


def decode_blob(data: bytes | bytearray | memoryview) -> dict:
    """Return the legacy info/notes structure for a CBNE or CBTN binary chart.

    CBNE uses the chart key embedded in the MasterV2 client, independently of
    the SQLCipher database key. Authentication, lengths and CRC32 are checked
    before chart records are returned.
    """
    data = bytes(data)
    if data.startswith(b'CBNE'):
        data = _decrypt_cbne(data)
    if len(data) < 32 or not data.startswith(b'CBTN'):
        raise ValueError('Expected a CBNE envelope or CBTN chart')
    (_, version, flags, header_size, raw_size, stored_size, note_count,
     pair_count, string_count, checksum) = struct.unpack_from('<4sHHIIIIHHI', data)
    if version != 3 or flags not in (0, 1) or header_size != 32:
        raise ValueError('Unsupported CBTN header')
    if not 0 < raw_size <= _MAX_PAYLOAD or len(data) != 32 + stored_size:
        raise ValueError('Invalid CBTN payload size')
    if note_count > 4 * 1024 * 1024 or pair_count == 0:
        raise ValueError('Invalid CBTN record counts')
    payload = data[32:]
    if flags & 1:
        try:
            inflater = zlib.decompressobj()
            payload = inflater.decompress(payload, raw_size + 1)
        except zlib.error as exc:
            raise ValueError('Invalid CBTN zlib payload') from exc
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError('Invalid CBTN compressed payload size')
    if len(payload) != raw_size:
        raise ValueError('CBTN uncompressed size mismatch')
    if zlib.crc32(payload) != checksum:
        raise ValueError('CBTN CRC32 mismatch')

    reader = _Reader(payload)
    bpm = reader.number()
    delay = reader.unpack('<i')
    default_pair = reader.unpack('<H')
    reserved = reader.unpack('<H')
    directory_index = reader.unpack('<I')
    reserved |= reader.unpack('<I')
    if bpm <= 0 or reserved or default_pair >= pair_count:
        raise ValueError('Invalid CBTN chart metadata')
    pairs = [(reader.sint(), reader.sint()) for _ in range(pair_count)]
    strings = []
    total_string_size = 0
    for _ in range(string_count):
        size = reader.uint()
        total_string_size += size
        if total_string_size > 32 * 1024 * 1024:
            raise ValueError('CBTN string table exceeds size limit')
        strings.append(reader.read(size).decode('utf-8'))

    def string_at(index: int) -> str:
        if index >= len(strings):
            raise ValueError('Invalid CBTN string table index')
        return strings[index]

    directory = string_at(directory_index)
    if note_count > reader.remaining // 4:
        raise ValueError('CBTN note count exceeds payload size')
    notes = []
    beat = 0
    for _ in range(note_count):
        tag = reader.unpack('<B')
        note_type = tag & 0x7f
        if note_type not in _NOTE_TYPES:
            raise ValueError(f'Unsupported CBTN note type: {note_type}')
        pair_index = reader.uint() if tag & 0x80 else default_pair
        if pair_index >= len(pairs):
            raise ValueError('Invalid CBTN division table index')
        position_split, beat_split = pairs[pair_index]
        beat += reader.sint()
        if not -(1 << 31) <= beat < (1 << 31):
            raise ValueError('CBTN cumulative beat exceeds 32 bits')
        position_index, beat_index = reader.sint(), reader.sint()
        normalized_beat = beat
        if beat_split > 0:
            extra_beat, beat_index = divmod(beat_index, beat_split)
            normalized_beat += extra_beat
        if not -(1 << 31) <= normalized_beat < (1 << 31):
            raise ValueError('CBTN normalized beat exceeds 32 bits')
        is_meta = note_type in _AUDIO_TYPES | {2, 3}
        if beat_split < 1 or position_split < (1 if is_meta else 2):
            raise ValueError('Invalid CBTN note divisions')
        if not is_meta and not 0 <= position_index < position_split:
            raise ValueError('Invalid CBTN note position')
        note = [normalized_beat, position_split, beat_split, position_index, beat_index, note_type]
        if note_type in _AUDIO_TYPES:
            note.append(string_at(reader.uint()))
        elif note_type in _GROUP_TYPES:
            note.append(reader.sint())
        elif note_type in _WIDE_CHARGE_TYPES:
            note.extend((reader.sint(), reader.number()))
        elif note_type in _VALUE_TYPES:
            note.append(reader.number())
        notes.append(note)
    if reader.remaining:
        raise ValueError('Trailing bytes in CBTN payload')
    return {'info': {'bpm': bpm, 'delay': delay, 'dir': directory}, 'notes': notes}
