"""Isaac Lab scene construction and reset utilities for S4 grasping debug."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import Articulation, ArticulationCfg, RigidObject, RigidObjectCfg
from isaaclab.sensors.camera import Camera, CameraCfg
from isaaclab.sim import PhysxCfg, SimulationCfg, SimulationContext, schemas
from isaaclab.sim.spawners.shapes import CuboidCfg, CylinderCfg

from .s4_robot_cfg import ALL_DRIVE_JOINTS, URDF_PATH, get_default_joint_positions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ISAAC_ASSET_ROOT = Path("/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac")
DEFAULT_SCENE_USD = ISAAC_ASSET_ROOT / "Environments" / "Simple_Warehouse" / "warehouse.usd"
DEFAULT_TABLE_USD = ISAAC_ASSET_ROOT / "Props" / "PackingTable" / "packing_table.usd"

BLOCK_CYLINDER_RADIUS = 0.035
BLOCK_CYLINDER_HEIGHT = 0.12
BLOCK_MASS = 0.08
TASK_PLATFORM_HEIGHT = 0.05
BLOCK_PLATFORM_SIZE = (0.11, 0.11, TASK_PLATFORM_HEIGHT)
PLATE_PLATFORM_SIZE = (0.30, 0.30, TASK_PLATFORM_HEIGHT)
TABLE_YAW_90_QUAT = (0.7071068, 0.0, 0.0, 0.7071068)


@dataclass(frozen=True)
class TaskLayout:
    """World-frame task coordinates.

    The robot is fixed at world origin. Positive X is the table direction.
    Keep all task objects around ``table_center_y`` so the visual table and
    physics objects do not drift into the robot feet area independently.
    """

    table_center_x: float = 0.82
    table_center_y: float = -0.2
    block_x: float = 0.50
    block_y_offset: float = 0.20
    plate_x: float = 0.50

    def task_surface_z(self, table_top_z: float) -> float:
        return table_top_z + TASK_PLATFORM_HEIGHT

    def red_platform_pos(self, table_top_z: float) -> np.ndarray:
        return np.array(
            [self.block_x, self.table_center_y + self.block_y_offset, table_top_z + TASK_PLATFORM_HEIGHT * 0.5],
            dtype=np.float32,
        )

    def blue_platform_pos(self, table_top_z: float) -> np.ndarray:
        return np.array(
            [self.block_x, self.table_center_y - self.block_y_offset, table_top_z + TASK_PLATFORM_HEIGHT * 0.5],
            dtype=np.float32,
        )

    def plate_platform_pos(self, table_top_z: float) -> np.ndarray:
        return np.array(
            [self.plate_x, self.table_center_y, table_top_z + TASK_PLATFORM_HEIGHT * 0.5],
            dtype=np.float32,
        )

    def red_block_pos(self, table_top_z: float) -> np.ndarray:
        surface_z = self.task_surface_z(table_top_z)
        return np.array(
            [self.block_x, self.table_center_y + self.block_y_offset, surface_z + BLOCK_CYLINDER_HEIGHT * 0.5],
            dtype=np.float32,
        )

    def blue_block_pos(self, table_top_z: float) -> np.ndarray:
        surface_z = self.task_surface_z(table_top_z)
        return np.array(
            [self.block_x, self.table_center_y - self.block_y_offset, surface_z + BLOCK_CYLINDER_HEIGHT * 0.5],
            dtype=np.float32,
        )

    def plate_pos(self, table_top_z: float) -> np.ndarray:
        return np.array([self.plate_x, self.table_center_y, self.task_surface_z(table_top_z) + 0.015], dtype=np.float32)


@dataclass(frozen=True)
class SceneBuildCfg:
    table_top_z: float
    joint_stiffness: float
    joint_damping: float
    joint_effort_limit: float
    robot_base_z: float = 1.08
    scene_usd: Path = DEFAULT_SCENE_USD
    table_usd: Path = DEFAULT_TABLE_USD
    table_visual_z: float = 0.0
    table_scale: float = 1.0
    layout: TaskLayout = TaskLayout()


def create_simulation_context(device: str) -> SimulationContext:
    sim = SimulationContext(
        SimulationCfg(
            device=device,
            dt=1.0 / 120.0,
            physx=PhysxCfg(
                enable_ccd=True,
                enable_stabilization=True,
                enable_external_forces_every_iteration=True,
                solve_articulation_contact_last=True,
                min_position_iteration_count=4,
                min_velocity_iteration_count=1,
                gpu_max_rigid_contact_count=2**23,
                gpu_max_rigid_patch_count=2**18,
            ),
        )
    )
    sim.set_camera_view([1.65, 0.0, 1.45], [0.82, 0.0, 0.78])
    return sim


def build_robot(
    prim_path: str,
    joint_stiffness: float,
    joint_damping: float,
    joint_effort_limit: float,
    robot_base_z: float,
) -> Articulation:
    robot_cfg = ArticulationCfg(
        prim_path=prim_path,
        spawn=sim_utils.UrdfFileCfg(
            asset_path=str(URDF_PATH.resolve()),
            fix_base=True,
            merge_fixed_joints=True,
            self_collision=False,
            articulation_props=schemas.ArticulationRootPropertiesCfg(
                enabled_self_collisions=False,
                solver_position_iteration_count=16,
                solver_velocity_iteration_count=2,
            ),
            joint_drive=sim_utils.UrdfFileCfg.JointDriveCfg(
                gains=sim_utils.UrdfFileCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=joint_stiffness,
                    damping=joint_damping,
                ),
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, robot_base_z),
            joint_pos={j: float(v) for j, v in zip(ALL_DRIVE_JOINTS, get_default_joint_positions(), strict=True)},
        ),
        actuators={
            "drive_joints": ImplicitActuatorCfg(
                joint_names_expr=list(ALL_DRIVE_JOINTS),
                stiffness=joint_stiffness,
                damping=joint_damping,
                effort_limit_sim=joint_effort_limit,
            ),
        },
    )
    return Articulation(cfg=robot_cfg)


def spawn_background_and_table(cfg: SceneBuildCfg) -> None:
    if not cfg.scene_usd.is_file():
        raise FileNotFoundError(f"Scene USD not found: {cfg.scene_usd}")
    if not cfg.table_usd.is_file():
        raise FileNotFoundError(f"Table USD not found: {cfg.table_usd}")

    scene_cfg = sim_utils.UsdFileCfg(usd_path=str(cfg.scene_usd))
    scene_cfg.func("/World/BackgroundScene", scene_cfg)

    table_cfg = sim_utils.UsdFileCfg(
        usd_path=str(cfg.table_usd),
        scale=(cfg.table_scale, cfg.table_scale, cfg.table_scale),
        rigid_props=schemas.RigidBodyPropertiesCfg(kinematic_enabled=True),
    )
    table_cfg.func(
        "/World/TaskTableVisual",
        table_cfg,
        translation=(cfg.layout.table_center_x, cfg.layout.table_center_y, cfg.table_visual_z),
        orientation=TABLE_YAW_90_QUAT,
    )


def spawn_physics_task_objects(cfg: SceneBuildCfg) -> dict[str, RigidObject]:
    contact_material = sim_utils.RigidBodyMaterialCfg(static_friction=2.0, dynamic_friction=1.6, restitution=0.0)
    collision_props = schemas.CollisionPropertiesCfg(contact_offset=0.002, rest_offset=0.0005)
    dynamic_rigid_props = schemas.RigidBodyPropertiesCfg(
        solver_position_iteration_count=24,
        solver_velocity_iteration_count=4,
        max_depenetration_velocity=0.25,
        linear_damping=0.25,
        angular_damping=0.35,
    )
    def make_platform_cfg(name: str, pos: np.ndarray, size: tuple[float, float, float]) -> RigidObjectCfg:
        return RigidObjectCfg(
            prim_path=f"/World/RecordTask/{name}",
            init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(float(x) for x in pos)),
            spawn=CuboidCfg(
                size=size,
                rigid_props=schemas.RigidBodyPropertiesCfg(
                    kinematic_enabled=True,
                    solver_position_iteration_count=16,
                    solver_velocity_iteration_count=2,
                ),
                collision_props=collision_props,
                physics_material=contact_material,
                visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.20, 0.20, 0.18)),
            ),
        )

    red_platform_cfg = make_platform_cfg(
        "RedPlatform",
        cfg.layout.red_platform_pos(cfg.table_top_z),
        BLOCK_PLATFORM_SIZE,
    )
    blue_platform_cfg = make_platform_cfg(
        "BluePlatform",
        cfg.layout.blue_platform_pos(cfg.table_top_z),
        BLOCK_PLATFORM_SIZE,
    )
    plate_platform_cfg = make_platform_cfg(
        "PlatePlatform",
        cfg.layout.plate_platform_pos(cfg.table_top_z),
        PLATE_PLATFORM_SIZE,
    )
    red_cfg = RigidObjectCfg(
        prim_path="/World/RecordTask/RedBlock",
        init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(float(x) for x in cfg.layout.red_block_pos(cfg.table_top_z))),
        spawn=CylinderCfg(
            radius=BLOCK_CYLINDER_RADIUS,
            height=BLOCK_CYLINDER_HEIGHT,
            mass_props=schemas.MassPropertiesCfg(mass=BLOCK_MASS),
            rigid_props=dynamic_rigid_props,
            collision_props=collision_props,
            physics_material=contact_material,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.05, 0.03)),
        ),
    )
    blue_cfg = RigidObjectCfg(
        prim_path="/World/RecordTask/BlueBlock",
        init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(float(x) for x in cfg.layout.blue_block_pos(cfg.table_top_z))),
        spawn=CylinderCfg(
            radius=BLOCK_CYLINDER_RADIUS,
            height=BLOCK_CYLINDER_HEIGHT,
            mass_props=schemas.MassPropertiesCfg(mass=BLOCK_MASS),
            rigid_props=dynamic_rigid_props,
            collision_props=collision_props,
            physics_material=contact_material,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.05, 0.22, 1.0)),
        ),
    )
    plate_cfg = RigidObjectCfg(
        prim_path="/World/RecordTask/Plate",
        init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(float(x) for x in cfg.layout.plate_pos(cfg.table_top_z))),
        spawn=CylinderCfg(
            radius=0.13,
            height=0.025,
            rigid_props=schemas.RigidBodyPropertiesCfg(
                kinematic_enabled=True,
                solver_position_iteration_count=16,
                solver_velocity_iteration_count=2,
            ),
            collision_props=collision_props,
            physics_material=contact_material,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.92, 0.92, 0.86)),
        ),
    )
    return {
        "red_platform": RigidObject(cfg=red_platform_cfg),
        "blue_platform": RigidObject(cfg=blue_platform_cfg),
        "plate_platform": RigidObject(cfg=plate_platform_cfg),
        "red": RigidObject(cfg=red_cfg),
        "blue": RigidObject(cfg=blue_cfg),
        "plate": RigidObject(cfg=plate_cfg),
    }


def build_scene(cfg: SceneBuildCfg) -> dict[str, object]:
    spawn_background_and_table(cfg)
    task_objects = spawn_physics_task_objects(cfg)
    camera = Camera(
        cfg=CameraCfg(
            prim_path="/World/DebugFrontCamera",
            update_period=0,
            height=480,
            width=640,
            data_types=["rgb"],
            spawn=sim_utils.PinholeCameraCfg(
                focal_length=18.0,
                focus_distance=1.2,
                horizontal_aperture=20.955,
                clipping_range=(0.05, 5.0),
            ),
        )
    )
    return {
        "robot": build_robot(
            "/World/Robot",
            cfg.joint_stiffness,
            cfg.joint_damping,
            cfg.joint_effort_limit,
            cfg.robot_base_z,
        ),
        "red_platform": task_objects["red_platform"],
        "blue_platform": task_objects["blue_platform"],
        "plate_platform": task_objects["plate_platform"],
        "red": task_objects["red"],
        "blue": task_objects["blue"],
        "plate": task_objects["plate"],
        "camera": camera,
    }


def write_object_pose(obj: RigidObject, pos: np.ndarray, device: str) -> None:
    pose = torch.tensor([[pos[0], pos[1], pos[2], 1.0, 0.0, 0.0, 0.0]], dtype=torch.float32, device=device)
    obj.write_root_pose_to_sim(pose)
    obj.write_root_velocity_to_sim(torch.zeros(1, 6, device=device))


def reset_scene(scene: dict[str, object], cfg: SceneBuildCfg, sim: SimulationContext) -> np.ndarray:
    robot: Articulation = scene["robot"]

    default_drive = get_default_joint_positions()
    init_pos = torch.zeros(1, robot.num_joints, device=sim.device)
    for drive_i, joint_name in enumerate(ALL_DRIVE_JOINTS):
        if joint_name in robot.joint_names:
            init_pos[0, robot.joint_names.index(joint_name)] = float(default_drive[drive_i])
    robot.write_joint_state_to_sim(init_pos, torch.zeros_like(init_pos))
    robot.reset()

    write_object_pose(scene["red_platform"], cfg.layout.red_platform_pos(cfg.table_top_z), sim.device)
    write_object_pose(scene["blue_platform"], cfg.layout.blue_platform_pos(cfg.table_top_z), sim.device)
    write_object_pose(scene["plate_platform"], cfg.layout.plate_platform_pos(cfg.table_top_z), sim.device)
    write_object_pose(scene["red"], cfg.layout.red_block_pos(cfg.table_top_z), sim.device)
    write_object_pose(scene["blue"], cfg.layout.blue_block_pos(cfg.table_top_z), sim.device)
    write_object_pose(scene["plate"], cfg.layout.plate_pos(cfg.table_top_z), sim.device)
    return init_pos[0].detach().cpu().numpy()


def reset_camera(camera: Camera, sim: SimulationContext) -> None:
    camera.set_world_poses_from_view(
        eyes=torch.tensor([[0.22, 0.0, 1.42]], device=sim.device),
        targets=torch.tensor([[0.86, 0.0, 0.78]], device=sim.device),
    )
    camera.reset()


def format_layout(cfg: SceneBuildCfg) -> str:
    red = cfg.layout.red_block_pos(cfg.table_top_z)
    blue = cfg.layout.blue_block_pos(cfg.table_top_z)
    plate = cfg.layout.plate_pos(cfg.table_top_z)
    red_platform = cfg.layout.red_platform_pos(cfg.table_top_z)
    blue_platform = cfg.layout.blue_platform_pos(cfg.table_top_z)
    plate_platform = cfg.layout.plate_platform_pos(cfg.table_top_z)
    return (
        "Task layout:\n"
        f"  robot_base_z={cfg.robot_base_z:.3f}\n"
        f"  task_surface_z={cfg.layout.task_surface_z(cfg.table_top_z):.3f}\n"
        f"  red_platform=({red_platform[0]:.3f}, {red_platform[1]:.3f}, {red_platform[2]:.3f}) "
        f"size=({BLOCK_PLATFORM_SIZE[0]:.3f}, {BLOCK_PLATFORM_SIZE[1]:.3f}, {BLOCK_PLATFORM_SIZE[2]:.3f})\n"
        f"  blue_platform=({blue_platform[0]:.3f}, {blue_platform[1]:.3f}, {blue_platform[2]:.3f}) "
        f"size=({BLOCK_PLATFORM_SIZE[0]:.3f}, {BLOCK_PLATFORM_SIZE[1]:.3f}, {BLOCK_PLATFORM_SIZE[2]:.3f})\n"
        f"  plate_platform=({plate_platform[0]:.3f}, {plate_platform[1]:.3f}, {plate_platform[2]:.3f}) "
        f"size=({PLATE_PLATFORM_SIZE[0]:.3f}, {PLATE_PLATFORM_SIZE[1]:.3f}, {PLATE_PLATFORM_SIZE[2]:.3f})\n"
        f"  table_center=({cfg.layout.table_center_x:.3f}, {cfg.layout.table_center_y:.3f})\n"
        f"  red_block=({red[0]:.3f}, {red[1]:.3f}, {red[2]:.3f})\n"
        f"  blue_block=({blue[0]:.3f}, {blue[1]:.3f}, {blue[2]:.3f})\n"
        f"  plate=({plate[0]:.3f}, {plate[1]:.3f}, {plate[2]:.3f})"
    )
