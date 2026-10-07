"""Enumerate permitted table names without eagerly reading every file's size."""
import os

TABLE_SUFFIXES = ('.csv', '.tsv', '.txt', '.csv.gz', '.tsv.gz', '.xlsx')


def directory_table_names(root):
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            # Match os.walk's default treatment of unreadable subdirectories.
            continue
        with entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, prefix + entry.name + "/"))
                elif entry.name.lower().endswith(TABLE_SUFFIXES):
                    yield prefix + entry.name
