"""Pure visual-selection constants and helpers."""

FINGER_LINK_TOKENS = ("thumb", "index", "middle", "ring", "pinky")
FINGER_BLUE_GRAY = (0.055, 0.12, 0.24)


def is_finger_visual_mesh_path(path: str) -> bool:
    """Return whether an imported robot mesh is a left/right finger visual."""
    normalized = path.lower()
    is_hand_link = any(f"/{side}_" in normalized for side in ("lh", "rh"))
    is_finger = any(token in normalized for token in FINGER_LINK_TOKENS)
    return is_hand_link and is_finger and "/visuals/" in normalized
