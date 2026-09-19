# Local data storage

The Windows checkout stores large local datasets outside the source tree in
`../immune-repertoire-web-data/`. Directory junctions retain the original paths:

| Original path | External directory |
| --- | --- |
| `_reference/` | `../immune-repertoire-web-data/_reference/` |
| `test_data/` | `../immune-repertoire-web-data/test_data/` |
| `flask_app/data/results/` | `../immune-repertoire-web-data/results/` |

Existing local paths continue to work, including paths saved in task metadata.
New results also go to the external directory. No result files were deleted.
This relocation reduces data physically inside the checkout; it does not free
the equivalent amount of space on the drive. Folder-size tools that follow
junctions may still count the external data.

These directories are ignored by Git. Historical reference scripts and datasets
remain in the external directory and in earlier commits, but are no longer part
of the current Git index. Runtime reference databases under
`flask_app/data/reference_db/` remain in the project.

The one-time Windows migration can be previewed with:

```powershell
rtk proxy powershell -NoProfile -File scripts/relocate_local_data.ps1
```

Pass `-Apply` to execute after stopping analysis processes. The script moves
directories on the same drive and retains their original paths as junctions.
An existing matching junction is skipped. Do not copy these junctions as if they
were portable data: back up the external directory separately, and explicitly
mount/configure data paths when deploying to another machine or container.

For future cleanup, use the platform's task deletion action for unwanted
completed/failed tasks so its existing result cleanup updates task records as
well. No automatic expiry or intermediate-file deletion is enabled by this
migration. Git maintenance preserves existing history and linked worktrees;
history rewriting and force-pushing are separate operations.
