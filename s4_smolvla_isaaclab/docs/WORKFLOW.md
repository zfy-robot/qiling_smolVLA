# Workflow

This is the repeatable loop for a task.

## 1. Define the Task

Edit:

```text
configs/s4_bimanual_dataset.json
configs/smolvla_s4_bimanual.yaml
```

Use a new dataset repo id and output dir when starting a genuinely different task.

## 2. Verify Simulation

```bash
conda activate env_isaaclab
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh sim --print-layout
```

Check:

- Robot starts stable.
- Camera sees the task.
- Object/platform heights are correct.
- The visual packing table is loaded, but table clutter/crates should not appear. The cleanup keeps the table body and deactivates known clutter prims such as `container_h20`, crates, and corrugated boxes.
- No visual debug arrows are enabled unless requested.

## 3. Collect Demonstrations

```bash
bash run.sh record-hdf5 --num-episodes 50 --block blue
```

For faster batch collection:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render
```

`--no-render` runs the IsaacLab scene headless while still recording camera observations.

Episode timeout is enabled by default:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --no-render --episode-timeout-s 500
```

If one attempt exceeds the timeout, its buffered frames are discarded, the scene is reset, and the same episode index is retried. This keeps the final saved episode count equal to `--num-episodes`.

Default collection is scripted. The blue cylinder starts with per-episode x/y randomization:

```text
uniform(-0.03m, +0.03m)
```

Only the blue cylinder is randomized. The fixed task platform and plate stay fixed. The scripted grasp reads the actual randomized cylinder pose before planning approach/lower/grasp/lift, so the hand target follows the true object position. For future VR/teleop data, keep the same HDF5 field names so conversion and training stay unchanged.

The scripted state machine waits for the smoothed 6D right-hand command to finish closing before lift, and waits for the hand command to finish opening before retreat.

The release target is the plate center plus `place_offset=[0.00m, -0.05m]` in world/base coordinates. Negative Y is robot-right in the current layout. To move the release point farther right during manual testing:

```bash
bash run.sh control grasp-block --place-y-offset -0.07
```

After release, the retreat anchor is the actual TCP position when the hand finishes opening. The hand first lifts in world `-Y/+Z`, then retreats in world `-X/-Y/+Z`, which corresponds to robot-right/back/up in the current task layout.

Tune the first lift after opening:

```bash
bash run.sh control grasp-block --release-lift-y -0.05 --release-lift-z 0.18
```

Logs are concise by default. Add `--verbose-status` only when you need detailed TCP/Jacobian/arm tracking diagnostics.

Useful overrides:

```bash
bash run.sh record-hdf5 --num-episodes 100 --block blue --randomize-blue-xy 0.04 --random-seed 7
```

## 4. Convert

```bash
conda activate smolvla
cd /home/zfy/smolVLA/s4_smolvla_isaaclab
bash run.sh convert-lerobot \
  --root-path /home/zfy/smolVLA/s4_smolvla_isaaclab/datasets/staging/s4_bimanual_red_blue_plate_v0/s4_right_blue_cylinder_plate_scripted.hdf5 \
  --overwrite
```

Do not split the HDF5 path across shell lines unless the line ends with `\`.

## 5. Train

```bash
bash run.sh train-smolvla --overwrite-output
```

For more data:

```bash
bash run.sh train-smolvla --overwrite-output --steps 50000 --batch-size 4 --save-freq 5000
```

Training is performed by upstream `lerobot-train`; this project only passes local paths and policy parameters.

## 6. Offline Check

```bash
bash run.sh preview-smolvla \
  --checkpoint /home/zfy/smolVLA/s4_smolvla_isaaclab/outputs/train/smolvla_s4_bimanual_v0/checkpoints/020000/pretrained_model \
  --num-frames 20 \
  --device cpu
```

For the current right-arm task, inspect `right_arm` and `right_hand` MAE.

## 7. Online Rollout

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

If the video does not open, keep the `.avi` suffix. The writer uses MJPG for `.avi`; `.mp4` uses OpenCV `mp4v`, which may not be playable depending on local codecs.

## 8. Interpret Hand Logs

```text
raw_policy RH=[...]
desired RH=[...]
RH_tracking cmd=[...] actual=[...] max_err=...
```

- `raw_policy` changes but `cmd` does not: action filtering/clipping issue.
- `cmd` changes but `actual` does not: hand mapping or actuator issue.
- `cmd` and `actual` track but task fails: policy/data/contact issue.

## 9. When to Retrain

Retrain when:

- You add more demos.
- You regenerate the LeRobotDataset.
- You change task text.
- You change fps or action/state dimensions.
- You change camera key or image resolution.

Do not retrain only because preview/eval code was fixed. That fix changes inference usage, not checkpoint weights.
