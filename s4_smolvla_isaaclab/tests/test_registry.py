from tasks import TASK_REGISTRY, get_task_spec


def test_drawer_task_registered_with_26d_contract():
    task = get_task_spec("drawer_insert_close")
    assert TASK_REGISTRY[task.task_id] is task
    assert task.data.state_dim == task.data.action_dim == 26
    assert task.data.schema_version == "s4_bimanual_v1"
    assert task.dataset_config.is_file()
    assert task.train_config.is_file()
