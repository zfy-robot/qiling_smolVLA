# Task Modules

This project is organized so task-specific work is separated from the reusable data and training pipeline.

## Stable Pipeline

These stages should stay mostly unchanged across tasks:

```text
IsaacLab scripted/teleop rollout
-> HDF5 writer
-> HDF5 to LeRobotDataset conversion
-> SmolVLA training
-> offline preview / online rollout eval
```

The current stable commands are:

```bash
bash run.sh list-tasks
bash run.sh activate-task right_blue_cylinder_plate
bash run.sh inspect-config
bash run.sh sim --print-layout
bash run.sh record-hdf5 --num-episodes 10 --block blue --no-render
bash run.sh convert-lerobot --root-path <hdf5-file-or-dir> --overwrite
bash run.sh train-smolvla --overwrite-output
bash run.sh eval-smolvla --steps 840 --policy-device cuda
```

## Task Registry

Registered task metadata lives in:

```text
tasks/
├── base.py
├── right_blue_cylinder_plate.py
├── drawer_insert_close.py
└── __init__.py
```

Each task declares:

- `task_id`
- human-readable description
- dataset config path
- training config path
- state/action dimensions
- scene builder target
- scripted controller target

Use `bash run.sh list-tasks` to inspect the registry.

## Task Configs

Task-specific configs live under:

```text
configs/tasks/
├── right_blue_cylinder_plate.dataset.json
├── right_blue_cylinder_plate.smolvla.yaml
├── drawer_insert_close.dataset.json
└── drawer_insert_close.smolvla.yaml
```

The active stable config paths remain:

```text
configs/s4_bimanual_dataset.json
configs/smolvla_s4_bimanual.yaml
```

Activate a task by copying the registered task configs into those stable paths:

```bash
bash run.sh activate-task right_blue_cylinder_plate
bash run.sh activate-task drawer_insert_close
```

This keeps existing conversion/training scripts simple while allowing different task configs.

The active dataset config is also the source of truth for scene loading during
recording and online rollout. `record-hdf5`, `sim`, and `eval-smolvla` read
`scene.scene_usd`, `scene.table_usd`, and `scene.table_top_z` from
`configs/s4_bimanual_dataset.json` after `activate-task`. This prevents a new
task from accidentally collecting data in the old cylinder scene.

## Adding a New Task

For a new task, create:

```text
tasks/<task_id>.py
configs/tasks/<task_id>.dataset.json
configs/tasks/<task_id>.smolvla.yaml
```

Then register the task in `tasks/__init__.py`.

Task-specific implementation should be isolated to:

- scene loading and object placement
- scripted collection controller or teleop adapter
- success criteria
- optional extra state/action dimensions

Do not fork conversion/training unless the data contract changes. If the policy still controls `right_arm_7 + right_hand_6`, keep:

```text
control_mode = right_only
observation.state shape = [13]
action shape = [13]
```

If the next task needs drawer joint state in the policy observation, update:

- task dataset config `features`
- HDF5 writer fields
- `data/lerobot_conversion.py`
- online eval observation packing

## Drawer Insert Close Task

Current target:

```text
left hand opens drawer
-> right hand grasps tomato can
-> right hand places can in drawer
-> right hand opens
-> left hand closes drawer
-> both arms return home
```

The task is now configured as a 26D bimanual policy contract:

```text
observation.state = left_arm_7 + left_hand_6 + right_arm_7 + right_hand_6
action            = left_arm_7 + left_hand_6 + right_arm_7 + right_hand_6
```

Per-frame task text is written to HDF5 at `obs/task_description` and converted
to the LeRobot `task` field. This keeps phase-specific language available for
SmolVLA while preserving the same conversion/training scripts.

The scripted drawer sequence lives in:

```text
configs/tasks/drawer_insert_close.scripted.yaml
tasks/drawer_insert_close_controller.py
```

Tune phase targets in YAML, not in Python. Each phase can specify independent
left/right TCP targets in robot `base_link`, independent left/right hand
targets (`open`, `close`, `hold`, or explicit 6D values), optional home-arm
targets, `min_steps`, `max_steps`, and a TCP distance `tolerance`.

The drawer task now uses named episode anchors rather than fixed world poses:

```text
can                    settled randomized can pose
drawer_handle_initial  handle pose at this episode's randomized opening
drawer_handle_open     handle pose at the fixed configured target opening
drawer_handle_closed   fully closed handle pose
```

Edit `randomization` to tune can XY ranges and initial drawer opening. Edit the
named entries under `targets` to tune the two left-handle transition offsets,
right-can pre-grasp/grasp offsets, lift, placement, and close target. Current
offsets are in `base_link`; `offset_frame: anchor` is available for local-frame
offsets. `hands.action_hold_seconds: 1.0` is automatically applied to every
phase that issues an open/close command.

Each episode records its sampled `can_xy_offset`, `drawer_initial_open_m`, and
scripted config path in the HDF5 demo attribute `episode_metadata`. A controller
phase timeout marks the attempt failed, discards its buffer, resets the scene,
and samples another attempt so failed trajectories are not counted.

The current YAML starts from the manually tested poses:

```bash
bash run.sh control tcp-pose --left-pos 0.32 0.36 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control tcp-pose --left-pos 0.36 0.36 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control hand --side left close
bash run.sh control tcp-pose --left-pos 0.36 0.30 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control tcp-pose --right-pos 0.50 -0.15 0.25 --right-rpy 0.0 -1.5 0.0 --left-pos 0.36 0.30 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control tcp-pose --right-pos 0.54 -0.13 0.16 --right-rpy 0.0 -1.5 0.0 --left-pos 0.32 0.36 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control hand --side right close
bash run.sh control tcp-pose --right-pos 0.44 0.10 0.18 --right-rpy 0.0 -1.5 1.5 --left-pos 0.32 0.36 0.10 --left-rpy -1.5 0.0 1.5
bash run.sh control hand --side right open
```

For hand-only testing while holding the current arm pose:

```bash
bash run.sh control hand --side left open
bash run.sh control hand --side left close
bash run.sh control hand --side right open
bash run.sh control hand --side right close
bash run.sh control hand --side both open
```

## Drawer Scene Preview

Activate the drawer preview scene with:

```bash
bash run.sh activate-task drawer_insert_close
bash run.sh sim --print-layout
```

The scene builder currently loads the base warehouse, then adds the Sektion
cabinet and one tomato soup can. It does not load the old PackingTable, the
PackingTable clutter, or the old cylinder/plate task objects. It also removes
stale legacy task prims such as `/World/TaskTableVisual`, `/World/RecordTask`,
and `/World/DrawerTask` when iterating inside one IsaacSim session.

Default recording camera for this task is the DebugFrontCamera pose tuned in
the IsaacSim UI:

```text
position = (0.10, 0.00, 1.80)
rpy_deg  = (0.00, -23.00, -90.00)
mode     = explicit rpy, not look-at
```

`--camera-target` is ignored in this default mode. It is only used when
`--camera-look-at` is explicitly passed.

Loaded drawer asset:

```text
/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac/Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd
```

Loaded object:

```text
005_tomato_soup_can.usd
```

Current preview placement:

```text
primary drawer = (0.80, 0.383, 0.70)
secondary drawer = (0.80, -0.383, 0.70)
TomatoSoupCan root = (0.56, -0.08, 1.16)
TomatoSoupCan orientation = rotate -90 deg about X
```

The drawer USD is loaded without overriding its rigid-body settings. Do not set
the cabinet root to kinematic, otherwise PhysX cannot create the drawer joints.
The tomato can is an IsaacLab `RigidObject` with explicit mass, convex mesh
collisions, contact offsets, damping and high-friction material. This is
required for physical grasping; do not change it back to a passive USD visual
reference. Current can settings are `mass=0.08kg`, `static_friction=2.2`,
`dynamic_friction=1.8`, `restitution=0.0`,
`solver_position_iteration_count=32`, and `solver_velocity_iteration_count=8`.
If the visual/collision origin proves inconvenient, adjust the placement
constants in `tasks/drawer_insert_close_scene.py`.

In GUI preview mode the script keeps the app rendering but does not advance
physics. This is intentional for scene placement/debugging: advancing physics
while editing drawer joints in the UI can trigger IsaacSim warnings such as
`Updating joint local poses in articulations is not supported after simulation
start`. Dynamic drawer open/close will be handled by the task controller instead
of manual UI dragging.

Once a live arm-control command is received through `/tmp/s4_arm_control.json`,
the preview starts stepping physics so the commanded joint or Pinocchio DLS TCP target
actually moves the robot.

To verify that the Sektion drawer articulation can move, use the programmatic
drive preview:

```bash
bash run.sh sim --print-layout --drawer-open --drawer-joint-filter drawer_top_joint --drawer-target 0.35
```

This scans joints under `/World/DrawerTask/DrawerCabinet`, prints the detected
joint paths, applies a USD Physics drive to the matching joint, and then steps
physics so the drawer can move. If the drawer moves in the wrong direction, use
the same command with a negative target, for example `--drawer-target -0.35`.
Do not edit the joint local pose from the property panel after physics starts;
that is the operation which triggers IsaacSim's unsupported local-pose warning.

When `--drawer-open` is used, the script forces the SimulationContext physics
device to CPU if the CLI device is CUDA. PhysX direct GPU API rejects runtime
articulation `setDriveTarget()` calls, which is why drawer-drive preview cannot
use the same GPU physics path as the cylinder grasp task.

For choosing a good arm pose around the drawer handle, print both hand TCP poses
and the drawer handle frame:

```bash
bash run.sh sim \
  --print-layout \
  --show-tcp-frames \
  --show-drawer-handle-frame \
  --show-wrist-camera-frustums \
  --print-tcp-pose \
  --tcp-print-period 0.5
```

This prints both world-frame and robot `base_link` TCP position, quaternion in
`wxyz` order, and XYZ extrinsic Euler angles in degrees. The TCP is estimated
from `left_wrist_yaw_link`/`right_wrist_yaw_link` plus the current wrist-frame
offset `(0, 0, -0.10)m`. Use the quaternion for code and the Euler values for
quick manual pose tuning.

The visual debug frames are:

```text
/World/Visuals/LeftHandTCP
/World/Visuals/RightHandTCP
/World/Visuals/DrawerHandleTop
```

The drawer handle frame defaults to:

```text
/World/DrawerTask/DrawerCabinet/drawer_handle_frame
```

If a saved scene changes the hierarchy, override it with
`--drawer-handle-frame-prim <prim_path>`. If the full path is not valid, the
script also searches the stage by the leaf name, for example
`drawer_handle_frame`.

The wrist camera frustums are drawn as real USD geometry under each camera's
`DebugFrustum` child: thin cylinders for frustum edges and small spheres for each
origin/corner. Their coordinates are local to `LeftWristCamera` and
`RightWristCamera`, with the same OpenGL `-Z` optical axis as the image. They
therefore inherit each camera's current Fabric transform and follow wrist motion
without copying world transforms back into USD. Do not use the USD Stage
transform inspector to validate an articulated camera while Fabric is enabled:
it may still show the authored initial link transform. Left is cyan and right is
orange. Change the drawn range with
`--wrist-camera-frustum-depth <meters>`; this only affects the debug drawing,
not camera capture. The default `--wrist-camera-frustum-scale 0.30` uniformly
reduces depth, line lengths, line radii, and point radii by 70%. A successful startup prints
`[VIS] wrist camera frustums active`.

The frustum children are created before the first `SimulationContext.reset()` so
Fabric discovers them together with the camera hierarchy. Leave the visualization
flag off while recording datasets. If the built-in Stage transform inspector must
also show live link transforms, add `--live-usd-transforms`; this uses CPU PhysX
without Fabric and is intended only for interactive coordinate debugging.

For live arm tuning in this drawer preview, the required frame and frustum
overlays are now defaults of the `sim` launcher:

```bash
bash run.sh sim
```

Add `--keyboard-jog` only when keyboard joint tuning is needed. Add
`--live-usd-transforms` only when the Stage inspector itself must track current
link transforms; it switches to the slower CPU/no-Fabric debug mode.

Keyboard jog controls:

```text
[ / ]  select the previous/next 26D arm/hand control entry
u / j  increase/decrease the selected entry
r      reset the 26D action to default
p      print the selected entry
```

For reproducible right-arm joint targets, keep the sim running and send:

```bash
bash run.sh control test-right-arm \
  --shoulder-pitch -0.40 \
  --shoulder-roll -0.15 \
  --shoulder-yaw 0.00 \
  --elbow -0.90 \
  --wrist-roll 0.10 \
  --wrist-pitch -0.20 \
  --wrist-yaw 0.05
```

Left arm, bimanual joint targets, and TCP pose targets are also supported:

```bash
bash run.sh control test-left-arm --shoulder-pitch -0.40 --shoulder-roll 0.15 --elbow -0.90

bash run.sh control test-bimanual-arm \
  --left -0.40 0.15 0.00 -0.90 0.00 -0.20 0.05 \
  --right -0.40 -0.15 0.00 -0.90 0.00 -0.20 0.05

bash run.sh control tcp-pose \
  --left-pos 0.45 0.25 0.25 --left-rpy 0.0 0.0 0.0 \
  --right-pos 0.45 -0.25 0.25 --right-rpy 0.0 0.0 0.0
```

`tcp-pose` targets are expressed in the robot `base_link` frame. The drawer
preview solves both wrist frames with the local Pinocchio damped least-squares
fallback, not Pink's Python task solver. Pink was avoided because this IsaacSim
process cannot safely convert several Pinocchio C++ vector return types used by
Pink internals. The solver converts TCP targets to wrist-frame targets with the
current `(0, 0, -0.10)m` offset and then applies the resulting left/right arm
joint targets through the same joint position controller used elsewhere.

The TCP IK also applies a null-space posture bias:

```text
dq = dq_task + (I - J#J) * k * (q_home - q)
```

This keeps redundant motion closer to `DEFAULT_POSE`, which currently means
elbows stay more outside/away from the body while the TCP task remains primary.
The default is `--tcp-posture-gain 0.30`. Use lower values such as `0.10` or
`0.05` while launching `run.sh sim` if the posture bias reduces TCP tracking
near hard poses.

Current recommended drawer TCP debug launch:

```bash
bash run.sh sim \
  --print-layout \
  --show-tcp-frames \
  --show-drawer-handle-frame \
  --print-tcp-pose
```

The equivalent explicit launch is:

```bash
bash run.sh sim \
  --print-layout \
  --show-tcp-frames \
  --show-drawer-handle-frame \
  --print-tcp-pose \
  --tcp-posture-gain 0.30 \
  --tcp-ik-damping 0.08 \
  --tcp-max-joint-delta 0.025
```

The saved `assets/scenes/cabinet_task.usd` experiment was reverted because it
loaded as an empty task scene in IsaacLab. Keep using explicit Python asset
loading until the saved USD reference paths are fixed.

Scripted recording uses the same YAML controller as the visual sequence:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh activate-task drawer_insert_close
bash run.sh record-hdf5 --num-episodes 10 --no-render --episode-timeout-s 120
```

The default HDF5 path is:

```text
datasets/staging/s4_drawer_insert_close_v0/drawer_insert_close_scripted.hdf5
```

Convert and train from the `smolvla` environment:

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot --root-path datasets/staging/s4_drawer_insert_close_v0 --overwrite
bash run.sh train-smolvla --overwrite-output
```

Current limitation: the first drawer scripted recorder records camera, 26D
state/action, TCP poses, and phase text. It does not yet add explicit drawer
joint state or object pose to `observation.state`; add those only if image +
arm/hand state is insufficient.
