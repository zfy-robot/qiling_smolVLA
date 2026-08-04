"""Scene builder for the drawer insert-close task preview.

This preview scene loads the warehouse base, then adds two aligned Sektion
cabinets and a single tomato soup can. The scripted drawer controller and
dataset recorder will be added separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import Articulation, ArticulationCfg, RigidObject, RigidObjectCfg
import isaaclab.sim as sim_utils
from isaaclab.sim import schemas

from s4_robot.simulation import (
    SceneBuildCfg,
    build_robot,
    configure_usdz_rigid_meshes,
    make_rgb_camera,
    make_wrist_cameras,
    spawn_background_and_table,
)


ISAAC_ROOT = Path("/home/zfy/isaacsim_assets/Assets/Isaac/5.1")
DRAWER_USD = ISAAC_ROOT / "Isaac/Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd"
YCB_OBJECTS = (
    ISAAC_ROOT / "Isaac/Props/YCB/Axis_Aligned/005_tomato_soup_can.usd",
)
DRAWER_YAW_180_QUAT = (0.0, 0.0, 0.0, 1.0)
DRAWER_X = 0.80
DRAWER_Z = 0.70
DRAWER_Y_OFFSET = 0.383
DRAWER_PLACEMENTS = (
    ("DrawerCabinet", (DRAWER_X, DRAWER_Y_OFFSET, DRAWER_Z)),
    ("DrawerCabinetSecondary", (DRAWER_X, -DRAWER_Y_OFFSET, DRAWER_Z)),
)
TOMATO_SOUP_CAN_POSITION = (0.54, -0.08, 1.16)
OBJECT_ROTATE_X_NEG_90_QUAT = (0.7071068, -0.7071068, 0.0, 0.0)
TOMATO_CAN_MASS_KG = 0.08
TOMATO_CAN_STATIC_FRICTION = 2.2
TOMATO_CAN_DYNAMIC_FRICTION = 1.8


@dataclass(frozen=True)
class DrawerAssetPlacement:
    name: str
    usd_path: Path
    position: tuple[float, float, float]
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    orientation: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


def _require_assets(paths: tuple[Path, ...]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing drawer task asset(s):\n  " + "\n  ".join(missing))


def _remove_stale_task_prims() -> None:
    """Remove stale task prims when iterating inside the same IsaacSim session."""
    try:
        import omni.usd
        from pxr import Sdf
    except Exception as exc:
        print(f"[WARN] could not import USD helpers for drawer cleanup: {exc}")
        return

    stage = omni.usd.get_context().get_stage()
    stale_paths = (
        "/World/CabinetTaskScene",
        "/World/DrawerTask",
        "/World/RecordTask",
        "/World/TaskTableVisual",
        "/World/TaskPlatform",
        "/World/RedBlock",
        "/World/BlueBlock",
        "/World/Plate",
    )
    removed: list[str] = []
    for path in stale_paths:
        prim = stage.GetPrimAtPath(path)
        if prim.IsValid():
            stage.RemovePrim(Sdf.Path(path))
            removed.append(path)
    if removed:
        print(f"[INFO] Removed stale task prims: {', '.join(removed)}", flush=True)


def _force_root_transform(
    prim_path: str,
    position: tuple[float, float, float],
    orientation: tuple[float, float, float, float],
    scale: tuple[float, float, float],
) -> None:
    """Author root xform ops after spawning to avoid asset-authored offsets winning."""
    try:
        import omni.usd
        from pxr import Gf, UsdGeom
    except Exception as exc:
        print(f"[WARN] could not force root transform for {prim_path}: {exc}")
        return

    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        print(f"[WARN] cannot force root transform; prim not found: {prim_path}")
        return

    xform = UsdGeom.Xformable(prim)
    for prop in list(prim.GetProperties()):
        if prop.GetName().startswith("xformOp:") or prop.GetName() == "xformOpOrder":
            prim.RemoveProperty(prop.GetName())
    xform.ClearXformOpOrder()
    translate_op = xform.AddTranslateOp(precision=UsdGeom.XformOp.PrecisionDouble)
    orient_op = xform.AddOrientOp(precision=UsdGeom.XformOp.PrecisionDouble)
    scale_op = xform.AddScaleOp(precision=UsdGeom.XformOp.PrecisionDouble)
    translate_op.Set(Gf.Vec3d(*position))
    orient_op.Set(
        Gf.Quatd(
            float(orientation[0]),
            Gf.Vec3d(float(orientation[1]), float(orientation[2]), float(orientation[3])),
        )
    )
    scale_op.Set(Gf.Vec3d(*scale))


def _bbox_z_range(prim_path: str) -> tuple[float, float] | None:
    try:
        import omni.usd
        from pxr import Usd, UsdGeom
    except Exception as exc:
        print(f"[WARN] could not compute bbox for {prim_path}: {exc}")
        return None

    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        print(f"[WARN] cannot compute bbox; prim not found: {prim_path}")
        return None

    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    bbox = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
    return float(bbox.GetMin()[2]), float(bbox.GetMax()[2])


def _bbox_min_z(prim_path: str) -> float | None:
    z_range = _bbox_z_range(prim_path)
    if z_range is None:
        return None
    return z_range[0]


def _bbox_max_z(prim_path: str) -> float | None:
    z_range = _bbox_z_range(prim_path)
    if z_range is None:
        return None
    return z_range[1]


def _align_bbox_bottom_z(
    prim_path: str,
    position: tuple[float, float, float],
    orientation: tuple[float, float, float, float],
    scale: tuple[float, float, float],
    bottom_z: float,
) -> tuple[float, float, float]:
    min_z = _bbox_min_z(prim_path)
    if min_z is None:
        return position
    dz = float(bottom_z) - min_z
    adjusted = (position[0], position[1], position[2] + dz)
    _force_root_transform(prim_path, adjusted, orientation, scale)
    print(
        f"[BOOT] aligned {prim_path} bbox bottom z: {min_z:.3f} -> {bottom_z:.3f} "
        f"root_z={adjusted[2]:.3f}",
        flush=True,
    )
    return adjusted


def _spawn_usd(
    prim_path: str,
    usd_path: Path,
    position: tuple[float, float, float],
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    orientation: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    *,
    kinematic: bool | None = None,
    bbox_bottom_z: float | None = None,
) -> tuple[float, float, float]:
    rigid_props = None if kinematic is None else schemas.RigidBodyPropertiesCfg(kinematic_enabled=kinematic)
    usd_cfg = sim_utils.UsdFileCfg(usd_path=str(usd_path), scale=scale, rigid_props=rigid_props)
    usd_cfg.func(prim_path, usd_cfg, translation=position, orientation=orientation)
    _force_root_transform(prim_path, position, orientation, scale)
    if bbox_bottom_z is not None:
        return _align_bbox_bottom_z(prim_path, position, orientation, scale, bbox_bottom_z)
    return position


def _object_placements() -> tuple[DrawerAssetPlacement, ...]:
    return (
        DrawerAssetPlacement(
            "TomatoSoupCan",
            YCB_OBJECTS[0],
            TOMATO_SOUP_CAN_POSITION,
            orientation=OBJECT_ROTATE_X_NEG_90_QUAT,
        ),
    )


def _spawn_dynamic_usd_object(item: DrawerAssetPlacement) -> RigidObject:
    """Spawn a graspable USD object with explicit rigid-body/contact settings."""
    prim_path = f"/World/DrawerTask/Objects/{item.name}"
    contact_material = sim_utils.RigidBodyMaterialCfg(
        static_friction=TOMATO_CAN_STATIC_FRICTION,
        dynamic_friction=TOMATO_CAN_DYNAMIC_FRICTION,
        restitution=0.0,
    )
    collision_props = schemas.CollisionPropertiesCfg(contact_offset=0.002, rest_offset=0.0005)
    rigid_props = schemas.RigidBodyPropertiesCfg(
        solver_position_iteration_count=32,
        solver_velocity_iteration_count=8,
        max_depenetration_velocity=0.20,
        linear_damping=0.35,
        angular_damping=0.45,
    )
    obj_cfg = RigidObjectCfg(
        prim_path=prim_path,
        init_state=RigidObjectCfg.InitialStateCfg(pos=item.position, rot=item.orientation),
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(item.usd_path),
            scale=item.scale,
            mass_props=schemas.MassPropertiesCfg(mass=TOMATO_CAN_MASS_KG),
            rigid_props=rigid_props,
            collision_props=collision_props,
        ),
    )
    obj = RigidObject(cfg=obj_cfg)
    configure_usdz_rigid_meshes(
        prim_path,
        schemas.MassPropertiesCfg(mass=TOMATO_CAN_MASS_KG),
        rigid_props,
        collision_props,
        contact_material,
    )
    print(
        f"[BOOT] configured graspable {item.name}: mass={TOMATO_CAN_MASS_KG:.3f}kg "
        f"friction=({TOMATO_CAN_STATIC_FRICTION:.1f},{TOMATO_CAN_DYNAMIC_FRICTION:.1f})",
        flush=True,
    )
    return obj


def _spawn_primary_drawer() -> Articulation:
    """Spawn the task cabinet as an IsaacLab articulation for tensor joint reset."""
    name, position = DRAWER_PLACEMENTS[0]
    drawer_cfg = ArticulationCfg(
        prim_path=f"/World/DrawerTask/{name}",
        spawn=sim_utils.UsdFileCfg(usd_path=str(DRAWER_USD)),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=position,
            rot=DRAWER_YAW_180_QUAT,
            joint_pos={".*": 0.0},
            joint_vel={".*": 0.0},
        ),
        actuators={
            "task_drawer": ImplicitActuatorCfg(
                joint_names_expr=["drawer_top_joint"],
                stiffness=0.0,
                damping=2.0,
                effort_limit_sim=500.0,
            ),
            "unused_cabinet_joints": ImplicitActuatorCfg(
                joint_names_expr=["drawer_bottom_joint", "door_left_joint", "door_right_joint"],
                stiffness=800.0,
                damping=80.0,
                effort_limit_sim=500.0,
            ),
        },
    )
    return Articulation(cfg=drawer_cfg)


def format_drawer_layout(cfg: SceneBuildCfg, drawer_top_z: float | None) -> str:
    objects = "\n".join(
        f"  {item.name}=({item.position[0]:.3f}, {item.position[1]:.3f}, {item.position[2]:.3f}) "
        f"asset={item.usd_path.name}"
        for item in _object_placements()
    )
    drawers = "\n".join(
        f"  {name}=({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}) asset={DRAWER_USD.name}"
        for name, pos in DRAWER_PLACEMENTS
    )
    drawer_top_text = "unknown" if drawer_top_z is None else f"{drawer_top_z:.3f}"
    return (
        "Drawer task layout:\n"
        f"  robot_base_z={cfg.robot_base_z:.3f}\n"
        f"  scene_usd={cfg.scene_usd}\n"
        f"  table_usd={cfg.table_usd}\n"
        f"{drawers}\n"
        f"  drawer_top_z={drawer_top_text}\n"
        f"{objects}"
    )


def build_scene(cfg: SceneBuildCfg) -> dict[str, object]:
    """Build the drawer task preview scene by loading each required asset."""
    _require_assets((cfg.scene_usd, DRAWER_USD, *YCB_OBJECTS))
    if cfg.table_usd is not None:
        _require_assets((cfg.table_usd,))

    _remove_stale_task_prims()
    spawn_background_and_table(cfg)

    print(f"[BOOT] loading drawers: {DRAWER_USD}", flush=True)
    primary_drawer = _spawn_primary_drawer()
    print("[BOOT] drawer articulation loaded: /World/DrawerTask/DrawerCabinet", flush=True)
    for name, position in DRAWER_PLACEMENTS[1:]:
        _spawn_usd(
            f"/World/DrawerTask/{name}",
            DRAWER_USD,
            position,
            orientation=DRAWER_YAW_180_QUAT,
            kinematic=None,
        )
        print(f"[BOOT] drawer loaded: /World/DrawerTask/{name}", flush=True)

    drawer_top_z = _bbox_max_z("/World/DrawerTask/DrawerCabinet")
    if drawer_top_z is not None:
        print(f"[BOOT] primary drawer bbox top z={drawer_top_z:.3f}", flush=True)

    dynamic_objects: list[RigidObject] = []
    named_objects: dict[str, RigidObject] = {}
    object_initial_poses: list[tuple[RigidObject, tuple[float, float, float], tuple[float, float, float, float]]] = []
    for item in _object_placements():
        print(f"[BOOT] loading drawer task object: {item.name} <- {item.usd_path.name}", flush=True)
        obj = _spawn_dynamic_usd_object(item)
        dynamic_objects.append(obj)
        named_objects["can"] = obj
        object_initial_poses.append((obj, item.position, item.orientation))

    camera = make_rgb_camera("/World/DebugFrontCamera", cfg)
    robot = build_robot(
        "/World/Robot",
        cfg.joint_stiffness,
        cfg.joint_damping,
        cfg.joint_effort_limit,
        cfg.robot_base_z,
    )
    wrist_cameras = make_wrist_cameras(cfg)
    print("[BOOT] drawer task scene objects constructed.", flush=True)
    return {
        "task_id": "drawer_insert_close",
        "task_description": "Open the drawer with the left hand, grasp the can with the right hand, put it into the drawer, and close the drawer.",
        "robot": robot,
        "drawer": primary_drawer,
        "camera": camera,
        "wrist_cameras": wrist_cameras,
        "dynamic_objects": dynamic_objects,
        "named_objects": named_objects,
        "object_initial_poses": object_initial_poses,
        "layout_text": format_drawer_layout(cfg, drawer_top_z),
    }
