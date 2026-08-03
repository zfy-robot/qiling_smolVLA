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

This currently loads the base warehouse, adds two aligned Sektion cabinets and only `005_tomato_soup_can.usd`, removes stale old-task prims if present, and adds the S4 robot plus DebugFrontCamera. It intentionally does not load the old PackingTable or the other three YCB objects. Current placement is explicit: drawers at `(0.80, 0.383, 0.70)` and `(0.80, -0.383, 0.70)`, tomato can root `(0.56, -0.08, 1.16)`.

The tomato can is spawned as an IsaacLab `RigidObject`, not as a passive visual USD reference. It has explicit mass, rigid-body solver/damping settings, convex mesh collision, small contact/rest offsets, and high-friction material so the hand can physically grasp it:

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

To tune arm poses for pulling the drawer handle, print both hand TCP poses and
the drawer handle frame:

```bash
bash run.sh sim \
  --print-layout \
  --show-tcp-frames \
  --show-drawer-handle-frame \
  --print-tcp-pose \
  --tcp-print-period 0.5
```

The log includes both world-frame and robot `base_link` TCP position,
quaternion `wxyz`, and XYZ Euler angles in degrees. The hand TCP estimates are
`left_wrist_yaw_link` / `right_wrist_yaw_link` plus the current wrist-frame
offset `(0, 0, -0.10)m`.

The debug frames are shown at `/World/Visuals/LeftHandTCP`,
`/World/Visuals/RightHandTCP`, and `/World/Visuals/DrawerHandleTop`. The handle
frame defaults to `/World/DrawerTask/DrawerCabinet/drawer_handle_frame`;
override it with `--drawer-handle-frame-prim <prim_path>` if the USD hierarchy
changes.

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
overwriting the TCP task. The default is now `--tcp-posture-gain 0.30`, matching
the current reach-controller posture default. Lower it if TCP tracking gets
worse.

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
  --tcp-posture-gain 0.30 \
  --tcp-ik-damping 0.08 \
  --tcp-max-joint-delta 0.025
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
bash run.sh record-hdf5 --num-episodes 10 --no-render --episode-timeout-s 120
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

Each episode has a wall-clock timeout. If one scripted attempt exceeds `120s`, that attempt is discarded, the scene is reset, and the same episode index is retried. The final HDF5 still contains the requested number of saved episodes.

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render --episode-timeout-s 120
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

Default online video is `.avi` with MJPG because OpenCV-generated `.mp4` was not reliably playable on this machine.

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh eval-smolvla \
  --steps 840 \
  --policy-device cuda \
  --policy-every-n-steps 0 \
  --output-video /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/eval/smolvla_rollout.avi
```

The rollout log prints:

```text
raw_policy RH=[...]
desired RH=[...]
RH_tracking cmd=[...] actual=[...] max_err=...
```

Use this to distinguish policy-output problems from hand actuator/mapping problems.

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
