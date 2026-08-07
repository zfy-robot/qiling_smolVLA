from pathlib import Path

import numpy as np
import pytest


def test_pyav_video_roundtrip(tmp_path: Path):
    av = pytest.importorskip("av")
    path = tmp_path / "smoke.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("libx264", rate=20)
        stream.width = 32
        stream.height = 24
        stream.pix_fmt = "yuv420p"
        for _ in range(2):
            frame = av.VideoFrame.from_ndarray(np.zeros((24, 32, 3), dtype=np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    with av.open(str(path)) as container:
        decoded = list(container.decode(video=0))
    assert len(decoded) == 2
    assert (decoded[0].height, decoded[0].width) == (24, 32)
