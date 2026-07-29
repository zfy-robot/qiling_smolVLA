"""
S4 38DOF 全尺寸人形机器人配置 (新版 linkerhand_o6 手)

基于 URDF: assets/my_robot/urdf/s4_40dof_merged.urdf

关节结构:
  下肢 (6 DOF × 2):   hip_roll → hip_yaw → hip_pitch → knee → foot_pitch → foot_roll
  上肢 (7 DOF × 2):   shoulder_pitch → shoulder_roll → shoulder_yaw → elbow → wrist_roll → wrist_pitch → wrist_yaw
  手部 (6 DOF × 2):   thumb_cmc_yaw/pitch, index/middle/ring/pinky_mcp_pitch
  手部 mimic (×10):   thumb_ip, index/middle/ring/pinky_dip (URDF multiplier 联动)
  固定关节 (×2):      lh_hand_mount, rh_hand_mount (wrist → hand_base_link)
"""

from pathlib import Path

# ----- 路径 -----
PROJECT_ROOT = Path(__file__).parent.parent
URDF_PATH = PROJECT_ROOT / "assets" / "my_robot" / "urdf" / "s4_40dof_merged.urdf"
MESHES_DIR = PROJECT_ROOT / "assets" / "my_robot" / "meshes"

# ============================================================
#  关节分组 & 名称
# ============================================================

# 左腿（从 base_link 向下）
LEFT_LEG_JOINTS = [
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_hip_pitch_joint",
    "left_knee_joint",
    "left_foot_pitch_joint",
    "left_foot_roll_joint",
]

# 右腿
RIGHT_LEG_JOINTS = [
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_hip_pitch_joint",
    "right_knee_joint",
    "right_foot_pitch_joint",
    "right_foot_roll_joint",
]

# 左臂（从 base_link 向外）
LEFT_ARM_JOINTS = [
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
]

# 右臂
RIGHT_ARM_JOINTS = [
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
]

# 左手（从 wrist_yaw 向外，经由 lh_hand_mount 固定关节）
LEFT_HAND_JOINTS = [
    "lh_thumb_cmc_yaw",
    "lh_thumb_cmc_pitch",
    "lh_index_mcp_pitch",
    "lh_middle_mcp_pitch",
    "lh_ring_mcp_pitch",
    "lh_pinky_mcp_pitch",
]

# 右手（从 wrist_yaw 向外，经由 rh_hand_mount 固定关节）
RIGHT_HAND_JOINTS = [
    "rh_thumb_cmc_yaw",
    "rh_thumb_cmc_pitch",
    "rh_index_mcp_pitch",
    "rh_middle_mcp_pitch",
    "rh_ring_mcp_pitch",
    "rh_pinky_mcp_pitch",
]

# Mimic 关节（URDF multiplier 联动，不可独立控制）
LEFT_HAND_MIMIC_JOINTS = [
    "lh_thumb_ip",
    "lh_index_dip",
    "lh_middle_dip",
    "lh_ring_dip",
    "lh_pinky_dip",
]
RIGHT_HAND_MIMIC_JOINTS = [
    "rh_thumb_ip",
    "rh_index_dip",
    "rh_middle_dip",
    "rh_ring_dip",
    "rh_pinky_dip",
]

# 固定关节 (wrist → hand_base_link)
FIXED_MOUNT_JOINTS = ["lh_hand_mount", "rh_hand_mount"]

# ---- 用于训练的关节分组 ----
# 初期抓取任务：只用上肢（右臂 7 + 右手 6 = 13 DOF）
UPPER_BODY_JOINTS = RIGHT_ARM_JOINTS + RIGHT_HAND_JOINTS

# 所有可驱动关节 (非mimic, 非固定)
ALL_DRIVE_JOINTS = (
    LEFT_LEG_JOINTS + RIGHT_LEG_JOINTS +
    LEFT_ARM_JOINTS + RIGHT_ARM_JOINTS +
    LEFT_HAND_JOINTS + RIGHT_HAND_JOINTS
)

# 驱动关节数 (= 12 legs + 14 arms + 12 hands = 38)
NUM_DOF = 38
UPPER_BODY_DOF = len(UPPER_BODY_JOINTS)  # 13

# ============================================================
#  默认姿态
# ============================================================

# 站立/初始姿态 (rad) — 上肢微抬，便于抓取
# 值根据 URDF 关节限位取中间安全位置
DEFAULT_POSE = {
    # 下肢 — 直立
    "left_hip_roll_joint": 0.0,
    "left_hip_yaw_joint": 0.0,
    "left_hip_pitch_joint": -0.2,
    "left_knee_joint": 0.3,
    "left_foot_pitch_joint": 0.0,
    "left_foot_roll_joint": 0.0,
    "right_hip_roll_joint": 0.0,
    "right_hip_yaw_joint": 0.0,
    "right_hip_pitch_joint": -0.2,
    "right_knee_joint": 0.3,
    "right_foot_pitch_joint": 0.0,
    "right_foot_roll_joint": 0.0,
    # 上肢 — 收在身体两侧并略抬肘，折肘避让桌面
    "left_shoulder_pitch_joint": -0.12,
    "left_shoulder_roll_joint": 0.28,
    "left_shoulder_yaw_joint": 0.0,
    "left_elbow_joint": -1.35,
    "left_wrist_roll_joint": 0.0,
    "left_wrist_pitch_joint": 0.0,
    "left_wrist_yaw_joint": 0.0,
    "right_shoulder_pitch_joint": -0.12,
    "right_shoulder_roll_joint": -0.28,
    "right_shoulder_yaw_joint": 0.0,
    "right_elbow_joint": -1.35,
    "right_wrist_roll_joint": 0.0,
    "right_wrist_pitch_joint": 0.0,
    "right_wrist_yaw_joint": 0.0,
    # 左手 (linkerhand_o6) — 微微张开
    "lh_thumb_cmc_yaw": 0.5,
    "lh_thumb_cmc_pitch": 0.2,
    "lh_index_mcp_pitch": 0.3,
    "lh_middle_mcp_pitch": 0.3,
    "lh_ring_mcp_pitch": 0.3,
    "lh_pinky_mcp_pitch": 0.3,
    # 右手 (linkerhand_o6) — 微微张开
    "rh_thumb_cmc_yaw": 0.5,
    "rh_thumb_cmc_pitch": 0.2,
    "rh_index_mcp_pitch": 0.3,
    "rh_middle_mcp_pitch": 0.3,
    "rh_ring_mcp_pitch": 0.3,
    "rh_pinky_mcp_pitch": 0.3,
}

# ============================================================
#  Isaac Lab ArticulationCfg 兼容配置
# ============================================================

def get_robot_usd_path() -> str:
    """返回 URDF 绝对路径 (Isaac Lab 可直接导入 URDF)"""
    return str(URDF_PATH.resolve())

def get_default_joint_positions():
    """返回默认姿态作为 numpy array (按 ALL_DRIVE_JOINTS 顺序)"""
    import numpy as np
    return np.array([DEFAULT_POSE[j] for j in ALL_DRIVE_JOINTS], dtype=np.float32)

def get_joint_limits():
    """从 URDF limit 解析关节限位"""
    import xml.etree.ElementTree as ET

    tree = ET.parse(str(URDF_PATH))
    root = tree.getroot()

    limits = {}
    for joint in root.iter("joint"):
        name = joint.get("name")
        limit_el = joint.find("limit")
        if limit_el is not None and name in ALL_DRIVE_JOINTS:
            lower = float(limit_el.get("lower", "-3.14"))
            upper = float(limit_el.get("upper", "3.14"))
            effort = float(limit_el.get("effort", "100"))
            velocity = float(limit_el.get("velocity", "10"))
            limits[name] = {
                "lower": lower,
                "upper": upper,
                "effort": effort,
                "velocity": velocity,
            }
    return limits

# ============================================================
#  打印关节信息（调试用）
# ============================================================

def print_joint_info():
    """打印所有驱动关节的信息"""
    limits = get_joint_limits()
    print(f"{'Joint':<35} {'Lower':>8} {'Upper':>8} {'Effort':>8} {'Vel':>8}")
    print("-" * 70)
    for j in ALL_DRIVE_JOINTS:
        lim = limits.get(j, {})
        print(f"{j:<35} {lim.get('lower', 0):8.3f} {lim.get('upper', 0):8.3f} "
              f"{lim.get('effort', 0):8.1f} {lim.get('velocity', 0):8.2f}")
    print(f"\n总计: {len(ALL_DRIVE_JOINTS)} 驱动关节")

if __name__ == "__main__":
    print(f"URDF: {URDF_PATH.resolve()}")
    print(f"Meshes: {MESHES_DIR.resolve()}")
    print()
    print_joint_info()
