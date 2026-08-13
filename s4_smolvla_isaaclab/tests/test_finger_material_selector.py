from s4_robot.visuals import is_finger_visual_mesh_path


def test_finger_material_selector_includes_both_hands_and_all_digits():
    for side in ("lh", "rh"):
        for digit in ("thumb", "index", "middle", "ring", "pinky"):
            path = f"/World/Robot/{side}_{digit}_proximal/visuals/mesh_0"
            assert is_finger_visual_mesh_path(path)


def test_finger_material_selector_excludes_palms_wrists_and_collisions():
    assert not is_finger_visual_mesh_path("/World/Robot/lh_hand_base_link/visuals/mesh_0")
    assert not is_finger_visual_mesh_path("/World/Robot/right_wrist_yaw_link/visuals/mesh_0")
    assert not is_finger_visual_mesh_path("/World/Robot/rh_index_distal/collisions/mesh_0")
    assert not is_finger_visual_mesh_path("/World/Robot/left_index_link/visuals/mesh_0")
