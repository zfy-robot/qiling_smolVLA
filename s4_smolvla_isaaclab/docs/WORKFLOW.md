# Workflow

This is the repeatable loop for a task.

## 1. Define the Task

Start from the task registry:

```bash
bash run.sh list-tasks
```

Activate the task you want to run:

```bash
bash run.sh activate-task right_blue_cylinder_plate
```

This copies the registered task configs from `configs/tasks/` into the stable active paths:

```text
configs/s4_bimanual_dataset.json
configs/smolvla_s4_bimanual.yaml
```

For a genuinely different task, create a new `task_id`, dataset repo id, staging path, LeRobot dataset path, and training output dir. The next planned task is registered as `drawer_insert_close`; its scene/controller implementation is still a placeholder.

## 2. Verify Simulation

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh sim --print-layout
```

Check:

- Robot starts stable.
- Camera sees the task.
- Isaac asset root is local. `run.sh` overrides IsaacLab Kit settings to `/home/zfy/isaacsim_assets/Assets/Isaac/5.1`; the default scene/table files are under that root's `Isaac/...` subdirectory.
- IsaacSim asset-browser folders are also overridden to local `file:/home/zfy/isaacsim_assets/Assets/Isaac/5.1/...` folders when launched through this project. This covers `isaacsim.asset.browser`, `isaacsim.gui.content_browser`, and `omni.kit.browser.asset`. Defaults are narrowed to `Isaac/Environments`, `Isaac/Props`, and `Isaac/Robots` instead of scanning the whole `Isaac` or `Isaac/IsaacLab` tree, because local thumbnail validation on those large trees can still take a long time. If the GUI still logs `https://omniverse-content-production...` thumbnail warnings, close all existing IsaacSim windows and restart; an already-open window keeps its old browser model/cache.
- Default recorded camera is `/World/DebugFrontCamera` in look-at mode: `eye=(0.18, -0.62, 1.42)` -> `target=(0.52, -0.12, 0.98)`, `680x480`.
- Object/platform heights are correct.
- The visual packing table is loaded, but table clutter/crates should not appear. The cleanup keeps the table body and deactivates known clutter prims such as `container_h20`, crates, and corrugated boxes.
- No visual debug arrows are enabled unless requested.

## 3. One-Command Pipeline

For the normal collect -> convert -> train run:

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

The pipeline writes HDF5 to a timestamped staging subdirectory, converts that exact file/directory into the configured LeRobotDataset, then launches `train-smolvla`. For `--workers > 1`, it starts multiple direct `bash run.sh record-hdf5 ... --no-render` workers, so the parallel path uses the same no-window command path as the single-worker test.

Useful variants:

```bash
bash run.sh pipeline --help
bash run.sh pipeline --dry-run --num-episodes 100 --workers 4 --no-render
bash run.sh pipeline --clean-first --num-episodes 100 --workers 4 --overwrite-dataset --overwrite-output
bash run.sh pipeline --skip-record --hdf5-root-path /path/to/existing.hdf5 --overwrite-dataset --overwrite-output
```

Use the split stages below when debugging one stage at a time.

Environment split:

```text
record stages:  env_isaaclab through IsaacLab/isaaclab.sh
convert/train:  /home/zfy/miniconda3/envs/smolvla
```

`--no-render` is converted to IsaacLab `--headless` before each worker starts, and `record-hdf5` launches the real IsaacLab script directly so AppLauncher receives `--headless` before the app starts. `record-parallel` should not create IsaacSim UI windows.

The pipeline checks that HDF5 files exist after recording and that the LeRobotDataset output exists and is non-empty after conversion.

Recording workers exit immediately after closing the completed HDF5 file. This intentionally bypasses occasional IsaacSim headless shutdown hangs after data has already been written.

`--dry-run` prints the timestamped HDF5 output root and the SmolVLA Python/`lerobot-train` paths without starting collection or training.

## 4. Collect Demonstrations

```bash
bash run.sh record-hdf5 --num-episodes 50 --block blue
```

For faster batch collection:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

For higher throughput, run multiple independent IsaacLab workers:

```bash
bash run.sh record-parallel --num-episodes 100 --workers 4 --block blue
```

Each worker writes a separate `.hdf5` file in the active staging directory. Convert the staging directory, not one file, to merge all workers:

```bash
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_right_blue_cylinder_plate_v1 \
  --overwrite
```

Do not start with `--workers 10` unless 2-4 workers are stable; 10 full IsaacSim processes can run out of GPU memory.

`--no-render` runs the IsaacLab scene headless while still rendering and recording `/World/DebugFrontCamera`
observations. It should remove the UI window, not disable RGB sensor rendering.

Episode timeout is enabled by default:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

If one attempt exceeds the timeout, its buffered frames are discarded, the scene is reset, and the same episode index is retried. This keeps the final saved episode count equal to `--num-episodes`.

Final success filtering is also enabled by default. Before an episode is written, the recorder checks that the
target cylinder center is inside the plate area: default `xy_dist <= 0.095m` and
`z_above_plate` in `[-0.02, 0.20]m`. Failed attempts are discarded and retried.

Scene load and every reset settle for `2.0s` of simulated time before the scripted task starts:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render --reset-settle-s 2.0
```

Default collection is scripted. The current training target is still the blue cylinder. The red task slot is a fixed pill bottle loaded directly from `assets/scenes/Pill_Bottle.usdz`, while the blue cylinder starts with per-episode x/y randomization:

```text
uniform(-0.03m, +0.03m)
```

Only the blue cylinder is randomized. The red bottle, fixed task platform, and plate stay fixed. The scripted grasp reads the actual randomized cylinder pose before planning approach/lower/grasp/lift, so the hand target follows the true object position. For future VR/teleop data, keep the same HDF5 field names so conversion and training stay unchanged. The red bottle still writes to the legacy `red_block` HDF5 key for script compatibility.

The scripted state machine waits for the smoothed 6D right-hand command to finish closing before lift, and waits for the hand command to finish opening before ending.

It also inserts explicit pauses before each hand transition:

```text
lower -> pre_close_hold -> close
place_lower -> pre_release_hold -> release
```

These pauses are part of the training data and are intended to make the open/close timing easier for SmolVLA to learn.
The defaults are `pre_close_hold_steps=120` and `pre_release_hold_steps=120`, about `1s` at `120Hz`.

The release target is the plate center plus `place_offset=[0.00m, -0.05m]` in world/base coordinates. Negative Y is robot-right in the current layout. To move the release point farther right during manual testing:

```bash
bash run.sh control grasp-block --place-y-offset -0.07
```

After release, there is no lift-away or retreat phase. Once the hand-open command has completed and `release_steps` has elapsed, the sequence enters `done/hold` at the release pose. This keeps manual visualization and HDF5 recording on the same simplified scripted path and avoids the previously unstable post-release Cartesian move.

Default RGB camera recording is `680x480`. Conversion reads the real frame shape from HDF5 and writes that shape to the LeRobotDataset video feature, so data collection, conversion, training, and eval stay aligned after recollection.

Camera debugging note: LeRobot videos are not rendered from the viewport during conversion. They are encoded from
the HDF5 array `obs/chest_front_rgb`, which is written by the IsaacLab `Camera` sensor at `/World/DebugFrontCamera`.
If `datasets/lerobot_data/.../videos/.../file-000.mp4` shows an old or wrong angle, rebuild that LeRobotDataset
from a freshly recorded HDF5 using `bash run.sh convert-lerobot --root-path ... --overwrite`.

New recordings also store wrist-camera RGB arrays:

```text
obs/left_wrist_rgb  -> observation.images.left_wrist_rgb
obs/right_wrist_rgb -> observation.images.right_wrist_rgb
```

Both sensors are fixed under the corresponding wrist yaw link and use the same
`680x480` resolution as the chest camera. The default mount comes from the
real-robot hand-eye calibration matrices `lh_hand_base_link -> camera` and
`rh_hand_base_link -> camera`. Since IsaacSim merges those hand base links into
the wrist yaw links, `s4_robot/simulation.py` stores the composed
`wrist_yaw_link -> camera` transforms:

```text
left  pos=(-0.0445941356, -0.0209877889, -0.1614989107)
left  quat_wxyz=(-0.1871460184, 0.6595136840, 0.6044971537, 0.4057108079)
right pos=( 0.0438948230, -0.0197078601, -0.1638273481)
right quat_wxyz=(-0.1353444104, 0.6807588438, -0.5885558066, -0.4145495744)
convention=ros
```

Override with `--left-wrist-camera-pos/--left-wrist-camera-quat-wxyz` and
`--right-wrist-camera-pos/--right-wrist-camera-quat-wxyz` for calibrated data.
RPY overrides are still available for quick UI tuning, but should not replace
the measured quaternion defaults without a new calibration.

The canonical defaults live only in `s4_robot/simulation.py`. Simulation,
recording, and evaluation CLI arguments default to `None` and inherit those
constants; command-line values are temporary per-run overrides.

Logs are concise by default. Add `--verbose-status` only when you need detailed TCP/Jacobian/arm tracking diagnostics.

Useful overrides:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --randomize-blue-xy 0.04 --random-seed 7
```

## 5. Convert

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_right_blue_cylinder_plate_v1/s4_right_blue_cylinder_plate_scripted.hdf5 \
  --overwrite
```

Do not split the HDF5 path across shell lines unless the line ends with `\`.

Default conversion is right-only:

```text
HDF5 processed_actions[13:26] -> LeRobot action 13D
HDF5 obs/s4_active_joint_pos[13:26] -> LeRobot observation.state 13D
```

Only pass `--control-mode bimanual` when deliberately training the old full 26D action policy.

## 6. Train

```bash
bash run.sh train-smolvla --overwrite-output
```

For more data:

```bash
bash run.sh train-smolvla --overwrite-output --steps 50000 --batch-size 4 --save-freq 5000
```

Training is performed by upstream `lerobot-train`; this project only passes local paths and policy parameters.

## 7. Offline Check

```bash
bash run.sh preview-smolvla \
  --num-frames 20 \
  --device cpu
```

For the current right-arm task, inspect `right_arm` and `right_hand` MAE.

## 8. Online Rollout

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh eval-smolvla \
  --steps 840 \
  --policy-device cuda \
  --policy-every-n-steps 0 \
  --output-video /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/eval/smolvla_rollout.avi
```

If the video does not open, keep the `.avi` suffix. The writer uses MJPG for `.avi`; `.mp4` uses OpenCV `mp4v`, which may not be playable depending on local codecs.

## 9. Interpret Hand Logs

```text
raw_policy RH=[...]
desired RH=[...]
RH_tracking cmd=[...] actual=[...] max_err=...
```

- `raw_policy` changes but `cmd` does not: action filtering/clipping issue.
- `cmd` changes but `actual` does not: hand mapping or actuator issue.
- `cmd` and `actual` track but task fails: policy/data/contact issue.

## 10. When to Retrain

Retrain when:

- You add more demos.
- You regenerate the LeRobotDataset.
- You change task text.
- You change fps or action/state dimensions.
- You change camera key or image resolution.

Do not retrain only because preview/eval code was fixed. That fix changes inference usage, not checkpoint weights.

## 11. Drawer Episode Acceptance

The drawer recorder validates the physical end state before writing HDF5:

- `abs(drawer_top_joint) < 0.015m`
- the can root world height satisfies `0.80m < z < 1.15m` (X/Y are not checked)

Tune both criteria in
`configs/tasks/drawer_insert_close.scripted.yaml -> success`. The can bounds
are relative to `drawer_handle_current` and use `base_link` XYZ axes. A failed
attempt prints `[DISCARD]`, resets the scene, and retries the same
episode number. Therefore `--num-episodes 100` produces 100 accepted demos,
not 100 attempts.

## 12. Clean Generated Files

Dry run:

```bash
bash run.sh clean-generated
```

Actually remove generated staging HDF5, converted LeRobotDataset, training outputs, and eval outputs:

```bash
bash run.sh clean-generated --yes
```

The command intentionally keeps `models/`.
