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
│   ├── control_mapping.py            # 26D action -> robot joint targets
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

If startup fails while testing the table cleanup path, isolate the issue with:

```bash
bash run.sh sim --print-layout --no-clean-table-clutter
```

### 3. Collect HDF5 Demonstrations

Default collection is the current right-hand blue-cylinder-to-plate scripted flow:

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh record-hdf5 --num-episodes 50 --block blue
```

For batch collection, use headless/no-render mode. Camera frames are still recorded, but the interactive viewport is not rendered:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

Each episode has a wall-clock timeout. If one scripted attempt exceeds `500s`, that attempt is discarded, the scene is reset, and the same episode index is retried. The final HDF5 still contains the requested number of saved episodes.

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render --episode-timeout-s 500
```

`record-hdf5` defaults to small blue-cylinder initial-position randomization:

```text
blue x/y offset ~ uniform(-0.03m, +0.03m)
```

Only the blue cylinder is randomized. The fixed task platform and plate do not move. The scripted grasp locks its approach/lower/grasp/lift anchors from the actual randomized cylinder pose at the start of each episode, then moves to the fixed plate pose, releases, and retreats.

During scripted grasp/place, arm motion waits for the smoothed 6D right-hand command to finish closing before lift, and waits for the hand command to finish opening before retreat. This prevents the arm from moving away while the hand is still closing or releasing.

After release, the hand first lifts in world `-Y/+Z`, then retreats in world `-X/-Y/+Z`. This avoids dragging the little finger across the plate while the hand is still close to the rim.

The default release point is slightly shifted to the robot-right side of the plate center:

```text
place_offset = [0.00m, -0.05m]
```

Override it when testing:

```bash
bash run.sh control grasp-block --place-y-offset -0.07
```

Tune the first lift after opening:

```bash
bash run.sh control grasp-block --release-lift-y -0.05 --release-lift-z 0.18
```

Default simulation logs are concise. Add `--verbose-status` to `sim` or `record-hdf5` only when debugging TCP/Jacobian/arm tracking details.

Override the range or seed when needed:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --randomize-blue-xy 0.04 --random-seed 7
```

Default output:

```text
/home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5
```

### 4. Convert to LeRobotDataset

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5 \
  --overwrite
```

Default output:

```text
/home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/lerobot_data/s4_bimanual_red_blue_plate_v0
```

### 5. Train SmolVLA

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
/home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_bimanual_v0
```

### 6. Offline Policy Preview

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh preview-smolvla \
  --checkpoint /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --num-frames 20 \
  --device cpu
```

Look at grouped error:

```text
group_mean_mae(LA/LH/RA/RH)=...
```

For the current right-hand task, focus on `RA/RH`.

### 7. Offline Policy Visualization

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh visualize-smolvla \
  --checkpoint /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_bimanual_v0/checkpoints/050000/pretrained_model \
  --episode-index 0 \
  --max-frames 360
```

This visualizes policy action vs expert action on recorded frames. It is not an online rollout.

### 8. Online IsaacLab Rollout

Default online video is `.avi` with MJPG because OpenCV-generated `.mp4` was not reliably playable on this machine.

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh eval-smolvla \
  --checkpoint /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
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

## Important Interface Rules

SmolVLA inference must follow the upstream LeRobot path:

```text
prepare_observation_for_inference
-> policy_preprocessor
-> policy.select_action
-> policy_postprocessor
-> 26D action
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

See [s4_robot/control_mapping.py](/home/zfy/smolVLA/s4_smolvla_isaaclab/s4_robot/control_mapping.py).

## Extending to a New Task

For a new task, keep the same flow:

1. Add or edit a task config in `configs/s4_bimanual_dataset.json`.
2. Add scripted collection logic or teleop collection under `scripts/04_record_bimanual_hdf5.py`.
3. Keep HDF5 field names compatible with `data/hdf5_schema.py`.
4. Convert to a new LeRobotDataset repo id.
5. Train to a new output directory.
6. Preview offline before online rollout.

More details are in [docs/ARCHITECTURE.md](/home/zfy/smolVLA/s4_smolvla_isaaclab/docs/ARCHITECTURE.md) and [docs/WORKFLOW.md](/home/zfy/smolVLA/s4_smolvla_isaaclab/docs/WORKFLOW.md).
