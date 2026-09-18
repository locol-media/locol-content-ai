"""Path helpers for reading the YAML config directories.

The config root comes from LOCOL_CONFIG_LOCATION (see config_manager.get_config_root),
so it is operator-controlled rather than request-controlled. These helpers keep the
reads confined to that root anyway, so a symlink or unexpected entry planted inside a
config directory cannot pull in a file from elsewhere on the filesystem.
"""

import os


def resolve_within(root: str, filename: str) -> str:
    """
    Join filename onto root and return the resolved absolute path.

    Raises ValueError if the result escapes root (via .., an absolute path, or a
    symlink pointing outside).
    """
    resolved_root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(resolved_root, filename))

    if candidate != resolved_root and not candidate.startswith(resolved_root + os.sep):
        raise ValueError(f"Path {filename!r} resolves outside of {root!r}")

    return candidate


def list_yaml_files(directory: str) -> list:
    """
    Return the resolved paths of every .yaml/.yml file directly inside directory.

    Entries that resolve outside directory are skipped with a warning rather than
    aborting the whole sync.
    """
    resolved_root = os.path.realpath(directory)
    paths = []

    for filename in sorted(os.listdir(resolved_root)):
        if not (filename.endswith(".yaml") or filename.endswith(".yml")):
            continue
        try:
            file_path = resolve_within(resolved_root, filename)
        except ValueError as e:
            print(f"Skipping config entry outside of {directory}: {e}")
            continue
        if os.path.isfile(file_path):
            paths.append(file_path)

    return paths
