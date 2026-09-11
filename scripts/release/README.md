# Release artifact tools

Preview the eight selected public artifacts without copying data:

```bash
python scripts/release/prepare_modelscope_release.py
```

After reviewing the plan, build the upload tree. The output directory must be
empty. Large binary files are hard-linked when the filesystem permits it, so
staging does not normally consume a second copy of every checkpoint.

```bash
python scripts/release/prepare_modelscope_release.py --materialize
```

ModelScope credentials and download cache are kept under the ignored
`.s4/modelscope/` directory. The SDK's resumable upload tracker is
`release/staging/qiling_smolvla/.ms_upload_cache`; the staging tree is generated
and Git-ignored, while the original model/data sources remain untouched. Before
uploading, set the dataset repository to **public** in the ModelScope web
settings, then run:

```bash
scripts/release/modelscope_release.sh login
scripts/release/modelscope_release.sh check
scripts/release/modelscope_release.sh upload
```

`login` prompts for the token without placing it in shell history. `check`
refuses to continue unless the authenticated identity is valid, the repository
is public, and every staged file matches `SHA256SUMS`. `upload` uses the SDK
upload cache so the same command can resume an interrupted transfer. Run
`scripts/release/modelscope_release.sh logout` to remove the locally persisted
credential through the container; no host-side access to the credential file is
required.

Consumers download only one named set:

```bash
python scripts/release/pull_modelscope_artifacts.py sim_rollout \
  --revision <immutable-modelscope-commit>
```
