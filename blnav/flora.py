"""flora.bin (FLR2) reader and writer.

File layout (all little-endian):

  0x00  char[4]  magic = "FLR2"
  0x04  u32      total_size  = file_length - 8  (counts bytes from offset 8 onward)
  0x08  u32      record_count

  Per record (variable length, repeated record_count times):
    u32      name_len
    char[name_len]  name  (ASCII, no null terminator)
    u32      kind          small integer 0-14; purpose opaque, preserved verbatim
    f32[12]  matrix        3x4 rotation+scale matrix, row-major
                           (3 rows × 4 floats; the 4th column is either 0.0 or
                           FLT_MAX 0x7F7FFFFF in some scenes — preserved verbatim)
    f32[3]   position      world-space XYZ in metres
    f32[5]   extra         typically all 1.0f; elements [1..4] carry an RGBA
                           colour tint in some scenes (range [0, 1])

Empty file: magic + total_size=4 + record_count=0 (12 bytes total).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"FLR2"
_RECORD_PAYLOAD = 84   # u32 kind (4) + f32[12] matrix (48) + f32[3] pos (12) + f32[5] extra (20)


@dataclass
class FloraRecord:
    name: str
    kind: int                # u32; small int 0–14; opaque, preserved verbatim
    matrix: list[float]      # 12 floats, 3x4 row-major rotation/scale
    position: list[float]    # 3 floats: world X, Y, Z in metres
    extra: list[float]       # 5 floats: typically all 1.0; [1..4] = RGBA tint


@dataclass
class Flora:
    records: list[FloraRecord] = field(default_factory=list)

    @classmethod
    def load(cls, path: str) -> "Flora":
        try:
            return cls.load_bytes(open(path, "rb").read())
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc

    def to_bytes(self) -> bytes:
        parts: list[bytes] = []
        for rec in self.records:
            name_b = rec.name.encode("ascii")
            parts.append(struct.pack("<I", len(name_b)))
            parts.append(name_b)
            payload = struct.pack("<I", rec.kind)
            payload += struct.pack("<12f", *rec.matrix)
            payload += struct.pack("<3f", *rec.position)
            payload += struct.pack("<5f", *rec.extra)
            parts.append(payload)
        body = b"".join(parts)
        # total_size counts the record_count u32 plus all record bytes
        total_size = 4 + len(body)
        return MAGIC + struct.pack("<II", total_size, len(self.records)) + body

    @classmethod
    def load_bytes(cls, data: bytes) -> "Flora":
        """Parse FLR2 data from an in-memory bytes object."""
        if data[:4] != MAGIC:
            raise ValueError(f"bad magic {data[:4]!r}")
        total_size = struct.unpack_from("<I", data, 4)[0]
        if total_size != len(data) - 8:
            raise ValueError(
                f"total_size={total_size} != len(data)-8={len(data)-8}"
            )
        record_count = struct.unpack_from("<I", data, 8)[0]

        records: list[FloraRecord] = []
        offset = 12
        for i in range(record_count):
            (name_len,) = struct.unpack_from("<I", data, offset)
            offset += 4
            name = data[offset : offset + name_len].decode("ascii")
            offset += name_len
            kind, = struct.unpack_from("<I", data, offset)
            matrix = list(struct.unpack_from("<12f", data, offset + 4))
            position = list(struct.unpack_from("<3f", data, offset + 52))
            extra = list(struct.unpack_from("<5f", data, offset + 64))
            offset += _RECORD_PAYLOAD
            records.append(FloraRecord(name, kind, matrix, position, extra))

        if offset != len(data):
            raise ValueError(f"{len(data) - offset} trailing bytes")

        return cls(records)

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.to_bytes())
