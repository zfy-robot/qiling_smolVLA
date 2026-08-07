# S4 SmolVLA IsaacLab

Clean project for collecting IsaacLab demonstrations with the S4 humanoid upper body, converting them to a LeRobotDataset, training SmolVLA, and evaluating the trained policy back in IsaacLab.

Reference repos stay read-only:

- `/home/zfy/smolVLA/lerobot`: upstream LeRobot and SmolVLA implementation.
- `/home/zfy/smolVLA/qi-studio-benchhub`: S4 production workflow reference.

This project is the only directory that should be edited for the local S4 IsaacLab pipeline.

## Directory Layout

```text
s4_smolvla_isaaclab/
├── configs/
│   ├── s4_bimanual_dataset.json      # active task/dataset/feature config
│   ├── smolvla_s4_bimanual.yaml      # active SmolVLA training config
│   └── tasks/                        # reusable per-task config templates
├── data/
│   ├── hdf5_schema.py                # canonical HDF5 field names
│   ├── dataset_writer.py             # HDF5 writer helpers
│   └── lerobot_conversion.py         # HDF5 -> LeRobotDataset
├── docs/
│   ├── ARCHITECTURE.md
│   ├── TASKS.md
│   └── WORKFLOW.md
├── s4_pipeline/
│   ├── config.py                     # typed config loader
│   └── paths.py                      # project/workspace paths
├── s4_robot/
│   ├── simulation.py                 # IsaacLab scene construction
│   ├── s4_robot_cfg.py               # robot joints/defaults/limits
│   ├── control_mapping.py            # active action -> robot joint targets
│   └── arm_control.py                # scripted arm/hand helpers
├── scripts/
│   ├── record_dataset.py             # IsaacLab scene/debug/scripted recording
│   ├── convert_lerobot.py            # LeRobotDataset conversion
│   ├── eval_policy.py                # online SmolVLA rollout
│   ├── preview_policy.py             # offline checkpoint preview
│   ├── visualize_policy.py           # offline policy/expert video
│   ├── record_parallel.py            # multi-process HDF5 recording
│   ├── pipeline_collect_convert_train.sh
│   ├── train_smolvla_local.sh        # lerobot-train wrapper
│   └── 0X_*.py / 1X_*.py             # compatibility wrappers/legacy entries
├── tasks/
│   ├── base.py                       # task metadata contract
│   ├── right_blue_cylinder_plate.py  # current validated task
│   └── drawer_insert_close.py        # next task placeholder
└── run.sh                            # stable command entrypoint
```

## Reusable Task Structure

Task-specific scene and control code should live behind the task registry in `tasks/`, while data conversion, SmolVLA training, and policy eval stay reusable. Inspect registered tasks:

```bash
bash run.sh list-tasks
```

Switch active configs:

```bash
bash run.sh activate-task right_blue_cylinder_plate
bash run.sh activate-task drawer_insert_close
```

The active config files remain `configs/s4_bimanual_dataset.json` and `configs/smolvla_s4_bimanual.yaml`, so the normal collect -> convert -> train commands do not change when the task changes. See [TASKS.md](docs/TASKS.md) for the new-task checklist.

After activation, `sim`, `record-hdf5`, and `eval-smolvla` all read the active task's `scene.scene_usd`, `scene.table_usd`, and `scene.table_top_z`. Conversion and training remain task-agnostic unless a task changes the state/action feature contract.

The drawer task has a scene preview and a YAML-driven scripted data-collection controller:

```bash
bash run.sh activate-task drawer_insert_close
bash run.sh sim --print-layout
```

This currently loads the base warehouse, adds two aligned Sektion cabinets and only `005_tomato_soup_can.usd`, removes stale old-task prims if present, and adds the S4 robot plus DebugFrontCamera. It intentionally does not load the old PackingTable or the other three YCB objects. Current placement is explicit: drawers at `(0.80, 0.383, 0.70)` and `(0.80, -0.400, 0.70)`, tomato can root `(0.56, -0.08, 1.16)`. The asymmetric Y spacing is intentional: the previous `+/-0.383m` placement left only `2.23mm` between cabinet collision bounds, causing the primary top drawer to collide with the secondary cabinet and stop reproducibly at `q=0.028929m`.

The tomato can is spawned as an IsaacLab `RigidObject`, not as a passive visual USD reference. It has explicit mass, rigid-body solver/damping settings, convex mesh collision, small contact/rest offsets, and high-friction material so the hand can physically grasp it. Its authored local Y axis becomes world Z after the spawn rotation, so `TOMATO_SOUP_CAN_SCALE = (1.0, 0.90, 1.0)` reduces only its world-space height to 90% while preserving the grasping diameter. The root scale applies to both rendering and collision geometry:

```text
mass = 0.08 kg
static_friction = 2.2
dynamic_friction = 1.8
restitution = 0.0
solver_position_iteration_count = 32
solver_velocity_iteration_count = 8
```

GUI preview mode renders without advancing physics. Use it for scene placement checks; drawer open/close should be implemented through the task controller instead of manually dragging articulation joints while the sim is running.
After a live arm-control command is received through `/tmp/s4_arm_control.json`, the preview starts stepping physics so joint targets and Pinocchio DLS TCP targets move the robot.
Drawer preview now uses the same PhysX joint-space gravity compensation path as the scripted cylinder task. The sim terminal prints `[SCENE] drawer preview gravity_compensation=...` on startup and `[ARMDBG] ... gravity_comp=max/mean` while a command is active. If the arm still feels soft, tune `--joint-stiffness`, `--joint-damping`, `--joint-effort-limit`, or `--gravity-comp-scale`.

To test drawer motion in preview, drive the drawer joint programmatically:

```bash
bash run.sh sim --print-layout --drawer-open --drawer-joint-filter drawer_top_joint --drawer-target 0.35
```

If the drawer moves in the wrong direction, rerun with `--drawer-target -0.35`.
This preview automatically uses CPU PhysX when driving the drawer, because
runtime articulation drive targets are rejected by PhysX direct GPU API.

`bash run.sh sim` now starts the interactive drawer-task debug view with both
TCP frames, the drawer-handle frame, wrist-camera frustums, and periodic TCP pose
logging enabled by default:

```bash
bash run.sh sim
```

The sim launcher uses frustum base depth `0.8`, base line width `8`, and the
global default scale `0.30`. Pass the corresponding CLI option after `sim` to
override a numeric value for one run. Dataset recording and evaluation do not
enable these debug overlays.

The log includes both world-frame and robot `base_link` TCP position,
quaternion `wxyz`, and XYZ Euler angles in degrees. The hand TCP estimates are
`left_wrist_yaw_link` / `right_wrist_yaw_link` plus the current wrist-frame
offset `(0, 0, -0.10)m`.

The debug frames are shown at `/World/Visuals/LeftHandTCP`,
`/World/Visuals/RightHandTCP`, and `/World/Visuals/DrawerHandleTop`. The handle
frame defaults to `/World/DrawerTask/DrawerCabinet/drawer_handle_frame`;
override it with `--drawer-handle-frame-prim <prim_path>` if the USD hierarchy
changes.

`--show-wrist-camera-frustums` draws the left/right wrist camera view ranges as
real USD geometry below each camera's `DebugFrustum` child: thin cylinders for
frustum edges and small spheres for each origin/corner. Left is cyan and right
is orange. Geometry is authored in camera-local OpenGL coordinates with `-Z`
forward, so it inherits the exact same Fabric parent transform as the rendered
camera and follows every wrist movement. The USD Stage panel may still show an
articulated link's initial authored transform; that does not affect the inherited
Fabric rendering. Use
`--wrist-camera-frustum-depth 0.45` to change the drawn range depth and
`--wrist-camera-frustum-line-width 5` to change the cylinder thickness while
tuning. The default `--wrist-camera-frustum-scale 0.30` uniformly scales the
depth, line lengths, line radii, and point radii to 30% of their base size
(70% smaller). A successful startup prints `[VIS] wrist camera frustums active`.
The geometry is created before the first simulation reset so Fabric includes it
in the live camera hierarchy. This flag is for interactive debugging; leave it
off during dataset recording.

To make the Stage transform inspector and built-in transform gizmos follow the
current robot pose, use `--live-usd-transforms`. This debug mode switches physics
to CPU and disables Fabric so PhysX synchronizes current transforms back to USD:

```bash
bash run.sh sim --show-wrist-camera-frustums --live-usd-transforms --print-tcp-pose
```

Do not use this mode for normal GPU data collection because it is slower.

For live joint tuning in the drawer preview, add `--keyboard-jog` and use
`[`/`]` to select a 26D arm/hand entry, `u`/`j` to increase/decrease it, `p` to
print it, and `r` to reset. For a reproducible right-arm target while the sim is
running:

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

Left arm and bimanual joint targets are also supported:

```bash
bash run.sh control test-left-arm --shoulder-pitch -0.40 --shoulder-roll 0.15 --elbow -0.90
bash run.sh control test-bimanual-arm \
  --left -0.40 0.15 0.00 -0.90 0.00 -0.20 0.05 \
  --right -0.40 -0.15 0.00 -0.90 0.00 -0.20 0.05
```

For TCP pose control, keep the drawer preview running and send targets in the
robot `base_link` frame. The current solver is a Pinocchio damped least-squares
fallback, because Pink/IsaacLab Pink hits Pinocchio C++ vector binding errors
inside this IsaacSim process. The command target is the TCP; internally the code
converts it to the wrist frame using the current `(0, 0, -0.10)m` TCP offset and
solves continuously while the command is active. It also adds a null-space home
posture bias, `dq = dq_task + (I - J#J) * k * (q_home - q)`, so redundant arm
motion tends to keep the elbows out and away from the body without directly
overwriting the TCP task. The current scripted TCP default is
`--tcp-posture-gain 0.05`; higher values can fight Cartesian tracking near the
cabinet.

```bash
bash run.sh control tcp-pose \
  --right-pos 0.45 -0.25 0.25 \
  --right-rpy 0.0 0.0 0.0

bash run.sh control tcp-pose \
  --left-pos 0.45 0.25 0.25 --left-rpy 0.0 0.0 0.0 \
  --right-pos 0.45 -0.25 0.25 --right-rpy 0.0 0.0 0.0
```

Recommended drawer TCP debug startup. These are the current defaults for the
posture bias, DLS damping and max joint delta, so the gain arguments are shown
only to make the active values explicit:

```bash
bash run.sh sim \
  --print-layout \
  --show-tcp-frames \
  --show-drawer-handle-frame \
  --print-tcp-pose \
  --tcp-posture-gain 0.05 \
  --tcp-ik-damping 0.08 \
  --tcp-max-joint-delta 0.040
```

Equivalent shorter command using defaults:

```bash
bash run.sh sim --print-layout --show-tcp-frames --show-drawer-handle-frame --print-tcp-pose
```

If the posture bias fights the TCP target too much, relaunch with
`--tcp-posture-gain 0.10` or `--tcp-posture-gain 0.05`.

The drawer insert-close scripted sequence is now config-driven:

```text
configs/tasks/drawer_insert_close.scripted.yaml
tasks/drawer_insert_close_controller.py
```

It controls left arm, right arm, left hand, and right hand independently through
one 26D contract:

```text
left_arm_7 + left_hand_6 + right_arm_7 + right_hand_6
```

The same YAML is also the single tuning surface for episode randomization and
anchor-relative motion. Its main sections are:

```text
randomization.can_xy.x_range/y_range        # default [-0.05, +0.05] m
randomization.drawer_initial_open.range     # default [0.00, 0.05] m
randomization.drawer_initial_open.target_open_m # fixed final opening, 0.18 m
hands.action_hold_seconds                    # default 1.0 s
targets.left_handle_transition_1.offset
targets.left_handle_transition_2.offset
targets.right_can_pregrasp.offset
targets.right_can_grasp.offset
```

All current target offsets use `offset_frame: base_link`, so each XYZ component
is along the robot base axes. Set `offset_frame: anchor` only when an offset
should rotate with the can/handle frame. The recorder samples a new can XY and
drawer opening for every attempt, pulls every episode to the configured fixed
`target_open_m`, reads the settled can pose from PhysX, then
resolves all phase targets once for that episode. The sampled values are stored
in each HDF5 demo's `episode_metadata` attribute.
The primary cabinet is an IsaacLab `Articulation`; its `drawer_top_joint` is
randomized through the tensor joint-state API without stopping the GPU timeline.

The configured sequence is: open both hands and wait, left approach/grasp/pull,
right pre-grasp/grasp/close/lift/place/release, concurrent right retreat/single
closed-hand drawer push, left-hand release, left lift, and home. Every
explicit hand open/close phase waits one simulated second.
Any TCP phase that reaches `max_steps` without reaching tolerance is discarded
and retried. Both position and quaternion angular error are checked (defaults:
`0.035m` and `0.55rad`); the angular threshold reflects the measured residual
near the cabinet and can be tightened per phase after pose calibration. The
default episode timeout is 300 wall-clock seconds.

The collection/control speed defaults are `target_alpha=0.32`,
`max_joint_step=0.050`, `tcp_max_joint_delta=0.050`, and
`hand_max_joint_step=0.015`. The final arm poses are configured under
`home_poses.left_arm/right_arm` in the task YAML. Home phases check actual arm
joint error against `home_poses.tolerance`; they no longer finish after
`min_steps` alone.

Manual hand commands while the sim is running:

```bash
bash run.sh control hand --side left open
bash run.sh control hand --side left close
bash run.sh control hand --side right open
bash run.sh control hand --side right close
bash run.sh control hand --side both open
```

Record drawer demonstrations:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh activate-task drawer_insert_close
bash run.sh record-hdf5 --num-episodes 10 --no-render
```

First tune one rendered episode, then collect headless with the same YAML:

```bash
bash run.sh record-hdf5 --num-episodes 1 --render \
  --output /tmp/drawer_tune.hdf5
bash run.sh record-hdf5 --num-episodes 100 --no-render
```

Drawer episodes are written only when the final live simulation state passes
both checks in `configs/tasks/drawer_insert_close.scripted.yaml -> success`:
the absolute top-drawer opening is below `0.040m`, and the can root height in
world coordinates satisfies `0.80m < z < 1.15m`. Can X/Y no longer affect
acceptance.
Failed attempts are discarded before HDF5 writing, reset, and retried, so
`--num-episodes N` means `N` accepted episodes.
Look for `[VERIFY]`, `[DISCARD]`, and `[ACCEPT]`.
Important collection events are colored on interactive terminals: cyan marks
episode/configuration events, blue marks phase changes, yellow marks progress
or retries, red marks discarded attempts, and green marks accepted episodes.
Use `--no-color-logs` to disable colors or `--color-logs` to force them.

During a drawer attempt, an interactive terminal displays a fixed dashboard
that refreshes in place. Unicode `█/░` bars show the current scripted `TASK`
and requested `DATA` episode progress. The panel includes episode/attempt,
phase/step, clock time, L/R TCP position and rotation errors, current episode
wall/simulation durations, buffered frame count, total collection duration,
ETA, completed attempts, accepted/failed counts, and acceptance rate. ETA is
estimated from elapsed time per accepted episode and remains unavailable until
the first success. A `GATES` row shows whether each TCP error participates in
phase completion and, when active, the live drawer opening versus its limit.
Redirected output uses the same information in one line
without ANSI clear-screen sequences. Configure refresh rate, panel size, bar
width, and four display thresholds under `logging.progress_dashboard` in the
drawer scripted YAML. Display thresholds do not change phase completion rules.
Event lines include a local `YYYY-MM-DD HH:MM:SS` timestamp. Interactive color
coding uses cyan for task/configuration, blue for phase transitions, yellow for
retry notices, red for timeout/discard/failure, and green for verification and
accepted/completed episodes. The timestamp is gray. Redirected logs remain
plain text unless `--color-logs` is explicitly requested.

Drawer target anchors are absolute states measured from the fully closed handle:

```text
drawer_handle_initial = drawer_handle_closed + opening_axis * randomized_initial_open
drawer_handle_open    = drawer_handle_closed + opening_axis * target_open_m
left_drawer_open TCP  = drawer_handle_open + left_drawer_open.offset
left_drawer_closed TCP= fixed base_link position [0.3550, 0.3725, 0.0660]
```

With `target_open_m: 0.18`, the desired final opening is 0.18m. If an episode
starts at 0.04m open, the pull command travels approximately 0.14m, not 0.18m.
`left_drawer_closed` supplies fallback IK metadata for the close and release
phases. The live close target is calculated from the measured TCP and drawer
opening. The final live-state filter separately requires
`abs(opening) < 0.040m` before writing the episode.
At phase entry, `close_drawer_from_current: true` locks the measured left TCP
Y/Z and orientation. `right_retreat_and_start_close` performs one fixed-duration
three-second push directly toward logical/mechanical zero with no overtravel.
Neither TCP error nor drawer opening gates the phase.
`left_open_hand` similarly uses
`hold_current_left_pose: true`, so releasing the handle cannot reintroduce a
vertical move toward the static fallback pose.
After release, `left_lift_after_release` resolves a target from
the live TCP pose with `left_offset_from_current: [-0.04, 0, 0.07]` in `base_link`, reaches that
clearance pose, and then returns directly to joint-space home. The previous
post-lift `left_final_close_push` phase has been removed. The lift orientation remains
configurable through `targets.left_lift_after_release.rpy` as an absolute
base_link RPY.

After the right hand releases the can, `right_retreat_and_start_close` resolves
its target from the measured right TCP pose and applies
`right_offset_from_current: [-0.10, -0.20, 0.0]` in `base_link`, while the closed
left hand performs the only close push. There is no standalone right-home or
second close phase. Neither TCP residual nor drawer opening gates this phase;
it runs for 360 physics steps. Initial randomization writes only the reset state
and never changes the asset's `[0.0, 0.4]m` mechanical limits. The top drawer
joint uses zero stiffness, damping, static friction, dynamic friction, and
viscous friction. The secondary cabinet is placed at `y=-0.400m`, leaving enough
collision clearance for the primary drawer to coast to its authored `0m` lower
limit after hand contact is lost.

To regression-test the drawer independently of the robot, can, and task state
machine, run:

```bash
bash run.sh sim --headless --drawer-coast-diagnostic
```

The diagnostic moves the can away, initializes the top drawer at `0.18m` with
`-0.15m/s`, and prints its position/velocity until it reaches exactly `0m`.

Per-phase motion speed can override global command smoothing with
`target_alpha` and `max_joint_step`. The final joint-space return phase uses:

```yaml
left_home:  {target_alpha: 0.20, max_joint_step: 0.025}
```

Reduce either value to return more slowly. Other phases inherit the global
`0.32/0.050`. Each `[PHASE]` log prints its effective speed.

Use a separate tuning file without editing Python:

```bash
bash run.sh record-hdf5 --num-episodes 1 --render --output /tmp/drawer_tune.hdf5 \
  --drawer-scripted-config configs/tasks/drawer_insert_close.scripted.yaml
```

Convert and train:

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot --root-path datasets/staging/s4_drawer_insert_close_v0 --overwrite
bash run.sh train-smolvla --overwrite-output
```

The HDF5 writer stores per-frame phase text at `obs/task_description`; the
converter forwards it to LeRobot's `task` field. See [TASKS.md](docs/TASKS.md)
for the full drawer phase list and tuning notes.

## Environments

Use `env_isaaclab` for IsaacSim/IsaacLab commands:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
```

Use `smolvla` for conversion, training, and offline checkpoint inspection:

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
```

`run.sh` switches to IsaacLab only for simulation/eval commands. Conversion and training intentionally use the current shell environment.

## Full Workflow

### 1. Check Config

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh inspect-config
```

### 2. Check IsaacLab Scene

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh sim --print-layout
```

`run.sh sim` now passes `--continuous` by default, so the IsaacSim window should stay open for visual inspection.

The local Isaac asset root is expected at `/home/zfy/isaacsim_assets/Assets/Isaac/5.1`. `run.sh` passes this path to IsaacLab through Kit settings for `persistent.isaac.asset_root.default/cloud/nvidia`, because the stock IsaacLab app files still default those settings to NVIDIA S3. It also overrides the IsaacSim asset browsers (`isaacsim.asset.browser`, `isaacsim.gui.content_browser`, and `omni.kit.browser.asset`) to local `file:/...` paths. To keep browsing responsive, the default Isaac folders are intentionally narrowed to `Isaac/Environments`, `Isaac/Props`, and `Isaac/Robots`; the huge `Isaac/IsaacLab` tree is not scanned by default. The scene and table paths below intentionally include the extra `/Isaac` subdirectory under that root:

```text
/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac/Environments/Simple_Warehouse/warehouse.usd
/home/zfy/isaacsim_assets/Assets/Isaac/5.1/Isaac/Props/PackingTable/packing_table.usd
```

If IsaacSim is opened manually outside this project, stale asset-browser caches or already-open windows can still show cloud URLs. Close all IsaacSim windows after changing these settings, then reopen. For selecting assets locally, prefer the Content Browser or file picker pointed at `/home/zfy/isaacsim_assets/Assets/Isaac/5.1`; cloud thumbnail warnings are not part of the project scene-loading path.

Default scene construction loads the warehouse background, the visual packing table, robot, one fixed large task platform, the red pill bottle, the blue cylinder, the plate, and the chest camera. The table body is kept, but the known clutter prim `/World/TaskTableVisual/container_h20` from the `PackingTable` asset is deactivated after loading.

The red task slot uses `assets/scenes/Pill_Bottle.usdz` directly. Its prim path and HDF5 key intentionally remain `/World/RecordTask/RedBlock` and `states/rigid_object/red_block/root_pose` for compatibility with the existing scripts. The asset is Y-up, so it is rotated into Isaac's Z-up frame and uniformly scaled to about the old red cylinder height. In this Isaac reference path the USDZ unit metadata is not relied on; the scale is applied against the raw authored bbox, currently `0.001103`, giving an approximate bottle size of `0.132 x 0.120 x 0.074m`. Its root and mesh collision properties use the same mass, rigid-body solver settings, collision offsets, and friction material as the blue cylinder.

Default camera pose:

```text
prim     = /World/DebugFrontCamera
mode     = explicit rpy
position = (0.10, 0.00, 1.80)
rpy_deg  = (0.00, -23.00, -90.00)
size     = 680x480
```

This matches the DebugFrontCamera pose tuned in the IsaacSim UI. In this default
mode, `--camera-eye` is the camera world position and `--camera-rpy-deg` is the
camera world orientation. `--camera-target` is ignored unless `--camera-look-at`
is explicitly passed.

The recorded LeRobot video `observation.images.chest_front_rgb` is converted directly from HDF5
`obs/chest_front_rgb`, which is captured by `/World/DebugFrontCamera`. If the camera pose is changed,
re-record or reconvert with `--overwrite`; an old mp4 under `datasets/lerobot_data/.../videos` will not update
by itself.

Two wrist cameras are also attached to the robot for future multi-view training:

```text
left  wrist camera = /World/Robot/left_wrist_yaw_link/LeftWristCamera
right wrist camera = /World/Robot/right_wrist_yaw_link/RightWristCamera
left  local pos    = (-0.0445941356, -0.0209877889, -0.1614989107)
left  quat wxyz    = (-0.1871460184, 0.6595136840, 0.6044971537, 0.4057108079)
right local pos    = ( 0.0438948230, -0.0197078601, -0.1638273481)
right quat wxyz    = (-0.1353444104, 0.6807588438, -0.5885558066, -0.4145495744)
default convention = ros
```

These defaults come from the measured real-robot transforms
`lh_hand_base_link -> camera` and `rh_hand_base_link -> camera`. IsaacSim merges
the fixed `*_hand_base_link` links into `left_wrist_yaw_link` and
`right_wrist_yaw_link`, so the code stores the composed
`wrist_yaw_link -> camera` transform above. The camera frame is treated as a ROS
optical camera frame (`+Z` forward), so the IsaacLab offset convention is `ros`.

Tune the mounting in `s4_robot/simulation.py`, or pass
`--left-wrist-camera-pos/--left-wrist-camera-quat-wxyz` and
`--right-wrist-camera-pos/--right-wrist-camera-quat-wxyz` at startup. For quick
manual UI experiments you can override with
`--left-wrist-camera-rpy-deg/--right-wrist-camera-rpy-deg`, but final data
collection should prefer the calibrated quaternion. Because the cameras are
fixed children of the wrist links, they remain static relative to each wrist; if
the wrist rotates, the camera rotates with it. HDF5 records them as
`obs/left_wrist_rgb` and `obs/right_wrist_rgb`; LeRobot conversion maps them to
`observation.images.left_wrist_rgb` and
`observation.images.right_wrist_rgb`. Current online eval still sends the chest
camera only; extend the policy server request before rolling out a checkpoint
trained with all three camera views.

Quick wrist-camera tuning example:

```bash
bash run.sh sim --print-layout \
  --show-wrist-camera-frustums \
  --left-wrist-camera-pos -0.0446 -0.0210 -0.1615 \
  --left-wrist-camera-quat-wxyz -0.1871 0.6595 0.6045 0.4057 \
  --right-wrist-camera-pos 0.0439 -0.0197 -0.1638 \
  --right-wrist-camera-quat-wxyz -0.1353 0.6808 -0.5886 -0.4145
```

Look-at camera control is only for debugging. Pass `--camera-look-at
--camera-target X Y Z` if you want the script to compute orientation from a
camera position and a target point.

To test a different look-at target:

```bash
bash run.sh sim --print-layout --camera-eye 0.10 0.0 1.80 --camera-rpy-deg 0.0 -23.0 -90.0
```

If startup fails while testing the table cleanup path, isolate the issue with:

```bash
bash run.sh sim --print-layout --no-clean-table-clutter
```

### 3. One-Command Pipeline

Use this when you want to collect demonstrations, convert them to LeRobotDataset, and train SmolVLA without manually running each stage:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh pipeline \
  --num-episodes 100 \
  --workers 4 \
  --no-render \
  --overwrite-dataset \
  --overwrite-output \
  --steps 50000 \
  --batch-size 4 \
  --save-freq 5000
```

The pipeline writes HDF5 data to a timestamped subdirectory under the configured staging root, converts exactly that new HDF5 file/directory, then starts `lerobot-train`. Use `--workers 1` for a single IsaacSim recorder, or start with `--workers 2/4` before trying 10 workers. For `--workers > 1`, the pipeline launches multiple direct `bash run.sh record-hdf5 ... --no-render` workers, matching the single-worker command path.

Useful pipeline options:

```bash
bash run.sh pipeline --help
bash run.sh pipeline --dry-run --num-episodes 100 --workers 4 --no-render
bash run.sh pipeline --clean-first --num-episodes 100 --workers 4 --overwrite-dataset --overwrite-output
bash run.sh pipeline --skip-record --hdf5-root-path /path/to/existing.hdf5 --overwrite-dataset --overwrite-output
```

`--clean-first` deletes generated HDF5 staging data, converted LeRobotDataset data, training outputs, and eval outputs before running. It does not delete `models/`.

Environment split is explicit:

```text
record stages:  env_isaaclab through IsaacLab/isaaclab.sh
convert/train:  /home/zfy/miniconda3/envs/smolvla
```

`--no-render` is translated to IsaacLab `--headless` at the outer `run.sh record-hdf5` launch layer, and `record-hdf5` launches `03_record_physics_dataset.py` directly so AppLauncher sees `--headless` before the simulation app starts. Parallel workers should not open IsaacSim UI windows.

After recording, the pipeline verifies that HDF5 files exist before conversion. After conversion, it verifies that the configured LeRobotDataset directory exists and is non-empty before training.

In record mode, once the requested episode count is written and the HDF5 file is closed, the worker exits immediately. This avoids IsaacSim headless shutdown hanging after successful recording.

Use `--dry-run` first if you want to confirm the exact HDF5 output root and Python paths before starting a long run.

### 4. Collect HDF5 Demonstrations

Default collection is the current right-hand blue-cylinder-to-plate scripted flow. The raw HDF5 still records full robot state and the full 26D active action for audit/debug, but the current training conversion exports only right arm + right hand.

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh record-hdf5 --num-episodes 50 --block blue
```

For batch collection, use headless/no-render mode. This disables the interactive IsaacSim UI window only. The
`/World/DebugFrontCamera` RTX sensor is still rendered every simulation step, so the recorded RGB video should
match the normal rendered mode aside from viewer/UI-only overlays:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

The default recorded camera size is `680x480` RGB. This resolution is written into HDF5 and then propagated into the LeRobotDataset video metadata during conversion. If you change it, recollect and reconvert before training so rollout/eval uses the same image geometry.
The left and right wrist cameras use the same resolution and frame rate as the chest camera.

To speed up collection, run multiple independent IsaacLab workers. Start with 2-4 workers before trying 10, because each worker is a full IsaacSim process:

```bash
bash run.sh record-parallel --num-episodes 100 --workers 4 --block blue
```

This writes multiple HDF5 files under the active staging directory. Convert the directory to merge them:

```bash
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_right_blue_cylinder_plate_v1 \
  --overwrite
```

Each episode has a wall-clock timeout. If one scripted attempt exceeds the
current default `300s`, that attempt is discarded, the scene is reset, and the
same episode index is retried. The final HDF5 still contains the requested
number of accepted episodes.

Drawer collection refreshes its dashboard at the YAML-configured interval (currently `0.5s`). `right_pregrasp_can` deliberately uses a `0.075m` coarse staging control tolerance; the following can-grasp phase uses its own `0.050m` contact tolerance. Dashboard indicator thresholds are separate and currently display `0.050m/0.500rad` for both arms.

All per-phase tuning poses are in `configs/tasks/drawer_insert_close.scripted.yaml` under `targets`. Change `offset: [x, y, z]` for the handle transition, can pre-grasp, can grasp/lift, or drawer placement targets; offsets are in robot `base_link` metres unless `offset_frame: anchor` is selected. `rpy` is in radians. `orientation_weight` controls how strongly IK preserves orientation (`1.0` hard, smaller values prioritize TCP position).

The left-hand handle approach uses three configurable points: `left_handle_transition_1`, `left_handle_transition_2`, and `left_handle_transition_3`. Their current offsets are `[-0.1435,-0.0230,0.0328]`, `[-0.0885,-0.0230,0.0578]`, and `[-0.0335,-0.0230,0.0828]`. Point 2 is the geometric midpoint of the two user-tuned poses; point 3 is the final pose held while the left hand closes.

The can-grasp target uses `offset=[-0.08,-0.05,-0.02]`, `rpy=[0,-0.9,0]`, `orientation_weight=0.25`, and a phase-only `0.050m` position tolerance. This is intentionally different from the coarse pre-grasp tolerance and was checked offline at both ends of the configured can x randomization range.

The imported articulation has 48 non-fixed joints: 38 independently driven joints and 10 hand mimic joints (`thumb_ip` plus four `dip` joints per hand). The mimic joints do not enter the 26D policy action; `control_mapping.py` deterministically derives their targets from the six controls per hand, and the actuator config applies the same PD gains as the active finger joints. This avoids both incomplete `38 != 48` coverage and loose zero-gain mimic joints. Drawer resets now move both hands to the YAML `left_open/right_open` targets during the settle period, before recording starts; `initial_open_hands` remains as a one-second stable hold for VLA timing. The handle phase budgets remain configurable in the YAML; `left_grasp_handle` is currently 500 steps because its final centimetres converge slowly.

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

Final success filtering is enabled by default before writing to HDF5. The recorder keeps only attempts where the
target cylinder finishes inside the plate area: default center XY distance is `<= 0.095m`
(`plate_radius - cylinder_radius`) and cylinder center height is within `[-0.02, 0.20]m` relative to the plate
center. Failed attempts are discarded and retried without increasing the saved episode count.

Scene load and every reset settle for `2.0s` of simulated time before the scripted task starts. Override only when debugging:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render --reset-settle-s 2.0
```

`record-hdf5` defaults to small blue-cylinder initial-position randomization:

```text
blue x/y offset ~ uniform(-0.03m, +0.03m)
```

Only the blue cylinder is randomized. The fixed task platform and plate do not move. The scripted grasp locks its approach/lower/grasp/lift anchors from the actual randomized cylinder pose at the start of each episode, then moves to the fixed plate pose, releases, waits briefly with the hand open, and ends.

During scripted grasp/place, the arm explicitly pauses before hand transitions:

```text
lower -> pre_close_hold -> close -> lift
place_lower -> pre_release_hold -> release -> done
```

The default pre-close and pre-release holds are `120` simulation steps, about `1s` at the current `120Hz` simulation rate. Arm motion also waits for the smoothed 6D right-hand command to finish closing before lift, and waits for the hand command to finish opening before ending. This gives SmolVLA clearer temporal labels, so it is less likely to close/open at the wrong time.

After release, there is no lift-away or retreat phase. Once the hand-open command has completed and `release_steps` has elapsed, the sequence enters `done/hold` at the release pose. This removes the previously unstable post-release Cartesian move from both manual visualization and HDF5 recording.

The default release point is slightly shifted to the robot-right side of the plate center:

```text
place_offset = [0.00m, -0.05m]
```

Override it when testing:

```bash
bash run.sh control grasp-block --place-y-offset -0.07
```

Default simulation logs are concise. Add `--verbose-status` to `sim` or `record-hdf5` only when debugging TCP/Jacobian/arm tracking details.

Override the range or seed when needed:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --randomize-blue-xy 0.04 --random-seed 7
```

Default output:

```text
/home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_right_blue_cylinder_plate_v1/s4_right_blue_cylinder_plate_scripted.hdf5
```

### 5. Convert to LeRobotDataset

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_right_blue_cylinder_plate_v1/s4_right_blue_cylinder_plate_scripted.hdf5 \
  --overwrite
```

The default `control_mode` is `right_only`, configured in [configs/s4_bimanual_dataset.json](/home/zfy/smolVLA/s4_smolvla_isaaclab/configs/s4_bimanual_dataset.json). Conversion slices:

```text
processed_actions[13:26] -> action: right_arm_7 + right_hand_6
obs/s4_active_joint_pos[13:26] -> observation.state: right_arm_7 + right_hand_6
```

Use `--control-mode bimanual` only when intentionally training a full 26D bimanual policy.

Default output:

```text
/home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/lerobot_data/s4_right_blue_cylinder_plate_v1
```

### 6. Train SmolVLA

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh train-smolvla --overwrite-output
```

Useful overrides:

```bash
bash run.sh train-smolvla --overwrite-output --steps 50000 --batch-size 8 --save-freq 5000
bash run.sh train-smolvla --resume
```

`--resume` restores the latest complete checkpoint through
`checkpoints/last`. It restores model weights, optimizer and scheduler state,
the saved training step, RNG state, and the dataset sampling offset. Resume is
only possible after at least one checkpoint has been written. If training is
interrupted between checkpoints, work after the latest saved checkpoint is
repeated.

The configured `steps` value is the final target step, not the number of extra
steps. For example, to continue a checkpoint saved at step 20000 until step
100000:

```bash
bash run.sh train-smolvla --resume --steps 100000
```

Do not combine `--resume` with `--overwrite-output`; the latter deletes the
checkpoint that resume needs.

Default output:

```text
/home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_right_v1
```

### 7. Offline Policy Preview

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh preview-smolvla \
  --num-frames 20 \
  --device cpu
```

Look at grouped error:

```text
group_mean_mae(LA/LH/RA/RH)=...
```

For the current right-hand-only dataset, `LA/LH` should be zero/empty and you should focus on `RA/RH`.

### 8. Offline Policy Visualization

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh visualize-smolvla \
  --episode-index 0 \
  --max-frames 360
```

This visualizes policy action vs expert action on recorded frames. It is not an online rollout.

### 9. Online IsaacLab Rollout

The rollout uses the same interface as the current drawer dataset and checkpoint:

- `observation.state`: 26D, ordered as left arm 7 + left hand 6 + right arm 7 + right hand 6.
- Visual observations: chest, left wrist, and right wrist RGB at `680x480`.
- `action`: 26D absolute joint targets in the same order as the state.
- Language: the 16 per-phase task descriptions stored in the LeRobot dataset.

The phase order and median phase durations are read from the converted dataset.
The SmolVLA action queue is reset at each phase boundary so the new language
instruction takes effect immediately. Rollout requests the upstream
`predict_action_chunk()` output without modifying LeRobot. By default it
replans every 25 policy frames and cross-fades only the previous/new chunks,
blends the first 8 frames at a language/phase transition, and linearly
interpolates each 20 Hz target over the six 120 Hz physics steps. With
`--steps 0`, one complete rollout uses the dataset-derived schedule (about 23
seconds of simulated task time, plus bounded state-gate extensions). The phase
durations stay equal to the training data so smoothing does not change the
language/action timing distribution.

Run the current 360K checkpoint with the Isaac Sim window visible:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --steps 0 \
  --policy-device cuda \
  --output-video outputs/eval/smolvla_drawer_rollout_360k.avi
```

To run without a GUI while still rendering all policy cameras and the rollout video:

```bash
bash run.sh eval-smolvla \
  --checkpoint outputs/train/smolvla_drawer_insert_close_v0/checkpoints/360000/pretrained_model \
  --steps 0 \
  --policy-device cuda \
  --headless \
  --no-randomize-task \
  --output-video outputs/eval/smolvla_drawer_rollout_360k_optimized.avi
```

The default video is an MJPG `.avi` containing chest, left-wrist, and
right-wrist views side by side. Use `--video-layout chest` for a smaller
chest-only video. `--no-randomize-task` fixes the can and drawer at their
nominal reset poses for a deterministic first test. The final log reports the
same drawer-opening and can-height success checks used by data collection.

Useful rollout controls are:

```text
--chunk-replan-frames 25           # request a fresh 50-step chunk every 1.25 s
--chunk-overlap-blend-frames 5     # cross-fade only adjacent chunks for 0.25 s
--phase-transition-blend-frames 8  # blend old/new phase commands for 0.4 s
--phase-state-gating               # arm/open-hand/drawer conditions at boundaries
--phase-max-extension-frames 20    # bounded extra wait, at most 1 s per phase
--phase-hand-close-min-progress 0.10 # contact-safe minimum closure evidence
```

Each rollout also writes `<video_stem>_actions.csv` and
`<video_stem>_actions.png`. The CSV records the raw chunk prediction, overlap-
fused target, bounded command, and measured 26D joint state at 20 Hz. The
plot shows raw frame-to-frame jumps, total smoothing correction, and command
endpoint tracking error for LA/LH/RA/RH. Each command is compared with the
actual state measured after its six 120 Hz interpolation steps. Grasp-close phases intentionally do not require
the hand to reach its free-space close target because contact with the handle
or can should stop the fingers early. Actuator stiffness and damping are left
unchanged while evaluating these policy-interface changes.

完整诊断流程、CSV 字段解释、问题定位表和逐项 A/B 命令见
[`docs/ROLLOUT_DIAGNOSTICS.md`](docs/ROLLOUT_DIAGNOSTICS.md)。

## Cleaning Generated Files

Preview what would be deleted:

```bash
bash run.sh clean-generated
```

Delete generated HDF5 staging data, converted LeRobotDataset data, training outputs, and eval outputs:

```bash
bash run.sh clean-generated --yes
```

This does not delete `models/`, so the local base SmolVLM weights are kept.

## Important Interface Rules

### Simulation And Dataset Timebase

The physics and arm-control loop runs at `120 Hz` (`dt=1/120 s`). Standard
collection records every 6 physics steps, so HDF5 observations/actions and the
converted LeRobotDataset run at `20 Hz` (`0.05 s` per sample). The task dataset
configs also declare `fps: 20`.

Online rollout keeps physics at `120 Hz` and advances the policy time axis every
6 steps (`20 Hz`). It linearly interpolates between adjacent policy targets at
120 Hz. Its diagnostic video also defaults to every 6 physics steps and is
encoded at `20 fps`, matching simulated time and the converted dataset videos.

These rates describe simulated time. Collection is not wall-clock paced:
headless Isaac Sim may run faster than real time and rendered collection may
run slower. Episode timeout uses wall-clock seconds, while YAML hand holds,
settling delays, and phase step budgets use simulated time.

`convert-lerobot` validates the HDF5 `record_fps` metadata against the active
task's dataset fps. For the default timebase, use:

```bash
bash run.sh record-hdf5 --num-episodes 100 --record-every-n 6 --no-render
```

The `--record-every-n 6` argument is now also the default. Recordings created
earlier by the direct command may contain `record_fps=120`; they must not be
silently converted as 20 fps data.

SmolVLA inference must follow the upstream LeRobot path:

```text
prepare_observation_for_inference
-> policy_preprocessor
-> policy.select_action
-> policy_postprocessor
-> 13D right-only action for the current v1 task
-> control_mapping.py
-> IsaacLab joint target
```

Do not hand-build token tensors or call `policy.select_action` directly without the checkpoint processors. The checkpoint uses `STATE=MEAN_STD` and `ACTION=MEAN_STD`; bypassing processors produces actions in the wrong space.

The hand mapping is not action normalization. It maps six policy hand controls to the many URDF hand joints:

```text
right_hand_6
-> rh_thumb_cmc_yaw, rh_thumb_cmc_pitch, rh_index_mcp_pitch, rh_middle_mcp_pitch, rh_ring_mcp_pitch, rh_pinky_mcp_pitch
-> mimic joints such as rh_index_dip = rh_index_mcp_pitch * 0.89
```

For a right-only checkpoint, online eval expands the 13D policy output into the existing 26D internal action buffer and only overwrites `right_arm/right_hand`. See [s4_robot/control_mapping.py](/home/zfy/smolVLA/s4_smolvla_isaaclab/s4_robot/control_mapping.py).

## Extending to a New Task

For a new task, keep the same flow:

1. Add or edit a task config in `configs/s4_bimanual_dataset.json`.
2. Add scripted collection logic or teleop collection under `scripts/04_record_bimanual_hdf5.py`.
3. Keep HDF5 field names compatible with `data/hdf5_schema.py`.
4. Convert to a new LeRobotDataset repo id.
5. Train to a new output directory.
6. Preview offline before online rollout.

More details are in [docs/ARCHITECTURE.md](/home/zfy/smolVLA/s4_smolvla_isaaclab/docs/ARCHITECTURE.md) and [docs/WORKFLOW.md](/home/zfy/smolVLA/s4_smolvla_isaaclab/docs/WORKFLOW.md).

## Drawer IK And Joint Validation

The drawer approach targets are configured in `configs/tasks/drawer_insert_close.scripted.yaml`. Their `orientation_weight` values are deliberately progressive (`0.20`, `0.35`, `0.60`) so early waypoints prioritize a smooth position approach instead of forcing the wrist to satisfy the final orientation immediately. The default `--tcp-posture-gain` is `0.05`; higher values can make the damped null-space term fight the TCP task near the cabinet.

The primary cabinet is an IsaacLab articulation. Its `drawer_top_joint` is passive (`stiffness=0`, `damping=0`) with zero configured joint friction, so it can move freely after hand contact is lost. Opening and closing use different completion rules:

- `pull_drawer` requires `drawer_open >= 0.08 m` for the current `0.18 m` target.
- `right_retreat_and_start_close` ignores TCP and drawer-distance residuals and applies one three-second close push.
- Final episode acceptance requires `abs(drawer_open) < 0.040 m` and the can root world height `0.80 m < z < 1.15 m`.

During a test, the dashboard shows only TCP errors by design. If a phase fails,
the subsequent `[DISCARD]` event retains the detailed failure reason needed for
diagnosis; drawer velocity, joint tracking, blocker names, and absolute
coordinates are not shown in the live dashboard.

The Pinocchio controller keeps IK solutions continuous across nearby scripted targets. At the first solve of every phase, the current 14 arm joints become that phase's null-space posture reference. The DLS inverse is used for the Cartesian task, while a separate Moore-Penrose inverse builds the null-space projector; this prevents damped-projector leakage from pulling the wrist toward `DEFAULT_POSE`. Joint increments are scaled as one vector and the resulting targets are restricted to URDF limits. This is important near drawer-handle poses, where several 7-DoF arm configurations can produce nearly the same TCP pose.
