# Architecture

This project follows the same high-level shape as the upstream LeRobot SmolVLA workflow, but keeps IsaacLab-specific robot and scene code local.

## Upstream LeRobot Flow

```text
robot.get_observation()
-> build_inference_frame / prepare_observation_for_inference
-> policy_preprocessor
-> SmolVLAPolicy.select_action
-> policy_postprocessor
-> make_robot_action
-> robot.send_action
```

## Local IsaacLab Flow

```text
IsaacLab robot joint state + chest RGB
-> prepare_observation_for_inference
-> policy_preprocessor
-> SmolVLAPolicy.select_action
-> policy_postprocessor
-> task action
-> s4_robot/control_mapping.py
-> IsaacLab joint position target
```

The final mapping step is local because the S4 IsaacLab robot is not a LeRobot built-in hardware class. The current v1 task trains a right-only 13D policy action (`right_arm_7 + right_hand_6`). Online eval expands that 13D output into the internal 26D active action buffer and only overwrites the right side.

## Data Contract

HDF5 episodes live under:

```text
data/demo_*
```

Required fields for conversion:

```text
processed_actions
states/articulation/robot/joint_position
obs/chest_front_rgb
obs/left_wrist_rgb
obs/right_wrist_rgb
```

Current LeRobot features:

```text
observation.state: 13D right_arm_7 + right_hand_6
observation.images.chest_front_rgb: 480x680 RGB video
observation.images.left_wrist_rgb: 480x680 RGB video
observation.images.right_wrist_rgb: 480x680 RGB video
action: 13D right_arm_7 + right_hand_6
```

The wrist camera streams are optional for older HDF5 files, but new scene
builders attach them under `left_wrist_yaw_link` and `right_wrist_yaw_link`.
Their default mount offset is defined in `s4_robot/simulation.py` and should be
tuned per robot/hand geometry before collecting final data.

Raw HDF5 still stores full joint positions and full 26D active actions for debugging. Conversion defaults to `control_mode=right_only` and slices `processed_actions[13:26]` plus `obs/s4_active_joint_pos[13:26]`.

## Action Layout

```text
LeRobot v1 right-only action:

```text
00:07 right_arm
07:13 right_hand
```

Internal/debug 26D active action:

```text
00:07 left_arm
07:13 left_hand
13:20 right_arm
20:26 right_hand
```

Each hand exposes six policy controls. `control_mapping.py` expands those controls into active and mimic URDF hand joints.

## Environment Split

`env_isaaclab`:

- IsaacSim/IsaacLab scene startup
- scripted control
- HDF5 recording
- online rollout shell

`smolvla`:

- LeRobotDataset conversion
- SmolVLA training
- checkpoint preview/visualization
- policy server subprocess used by online rollout

The online rollout uses a subprocess policy server so IsaacLab Python 3.11 and SmolVLA Python 3.12 do not share one interpreter.

## Files to Edit for New Tasks

Start with:

- `tasks/`
- `configs/tasks/<task_id>.dataset.json`
- `configs/tasks/<task_id>.smolvla.yaml`
- task-specific scene/controller modules

Then run:

```bash
bash run.sh activate-task <task_id>
bash run.sh inspect-config
```

The stable active config paths remain `configs/s4_bimanual_dataset.json` and
`configs/smolvla_s4_bimanual.yaml` so conversion/training commands do not need
to change for every task.

`record_dataset.py` and `eval_policy.py` must load the active project config
for scene/table paths. Do not hard-code `DEFAULT_SCENE_USD` or
`DEFAULT_TABLE_USD` in task-agnostic entrypoints; otherwise task activation
will appear to work while IsaacLab still runs the previous task scene.

Prefer semantic script names:

```text
scripts/record_dataset.py
scripts/convert_lerobot.py
scripts/eval_policy.py
scripts/preview_policy.py
scripts/record_parallel.py
scripts/pipeline_collect_convert_train.sh
```

The older numbered scripts are compatibility entrypoints only.

Avoid editing:

- `/home/zfy/smolVLA/lerobot`
- `/home/zfy/smolVLA/qi-studio-benchhub`

Those are references.
