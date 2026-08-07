import base64

import numpy as np

from scripts.policy_server import _image_array_from_payload


def test_json_image_payload_roundtrip():
    image = np.arange(4 * 5 * 3, dtype=np.uint8).reshape(4, 5, 3)
    payload = {"shape": list(image.shape), "b64": base64.b64encode(image.tobytes()).decode("ascii")}
    decoded = _image_array_from_payload(payload)
    assert np.array_equal(decoded, image)
    assert decoded.flags.writeable
