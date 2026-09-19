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

旧 Windows 一次性迁移脚本已移除。既有目录联接和外置数据仍保留，不能作为 Linux 部署路径复制；迁移时单独备份数据并恢复到 Docker 数据卷。

清理结果仍应通过平台任务与资产生命周期执行。
