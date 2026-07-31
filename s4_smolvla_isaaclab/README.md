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
│   └── smolvla_s4_bimanual.yaml      # local SmolVLA training config
├── data/
│   ├── hdf5_schema.py                # canonical HDF5 field names
│   ├── dataset_writer.py             # HDF5 writer helpers
│   └── lerobot_conversion.py         # HDF5 -> LeRobotDataset
├── docs/
│   ├── ARCHITECTURE.md
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
│   ├── 03_record_physics_dataset.py  # IsaacLab scene/debug/scripted control
│   ├── 04_record_bimanual_hdf5.py    # scripted HDF5 data collection
│   ├── 05_convert_hdf5_to_lerobot.py # LeRobotDataset conversion
│   ├── 06_eval_smolvla_in_isaaclab.py# online SmolVLA rollout
│   ├── 07_preview_smolvla_policy.py  # offline checkpoint preview
│   ├── 08_visualize_smolvla_policy.py# offline policy/expert video
│   ├── 09_smolvla_policy_server.py   # smolvla env policy server
│   └── train_smolvla_local.sh        # lerobot-train wrapper
└── run.sh                            # stable command entrypoint
```

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

Default scene construction loads the warehouse background, the visual packing table, robot, one fixed large task platform, the red/blue cylinders, the plate, and the chest camera. The table body is kept, but the known clutter prim `/World/TaskTableVisual/container_h20` from the `PackingTable` asset is deactivated after loading.

Default camera pose:

```text
prim     = /World/DebugFrontCamera
mode     = look_at
eye      = (0.18, -0.62, 1.42)
target   = (0.52, -0.12, 0.98)
size     = 680x480
```

The recorded LeRobot video `observation.images.chest_front_rgb` is converted directly from HDF5
`obs/chest_front_rgb`, which is captured by `/World/DebugFrontCamera`. If the camera pose is changed,
re-record or reconvert with `--overwrite`; an old mp4 under `datasets/lerobot_data/.../videos` will not update
by itself.

RPY camera control is only for debugging. Pass `--no-camera-look-at --camera-rpy-deg R P Y` if you need to test
an explicit rotation; the default data path should stay in look-at mode.

To test a different look-at target:

```bash
bash run.sh sim --print-layout --camera-look-at --camera-target 0.52 -0.12 0.98
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
