"""
Utility helpers for LocalFiles storage operations.
"""

import os
import posixpath
import re
from pathlib import Path
from typing import Callable, Iterable, Optional

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.utils._os import safe_join

AUTO_ROOT_CANDIDATES: tuple[str, ...] = ('mydata', 'label-studio-data')

# 主平台用户名规则：小写字母开头，仅小写字母/数字/-
USERNAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')


def autodetect_local_files_root(
    base_dir: Optional[str] = None, candidates: Iterable[str] = AUTO_ROOT_CANDIDATES
) -> Optional[str]:
    """Return the first existing candidate directory relative to ``base_dir``."""
    search_root = Path(base_dir or os.getcwd())
    for candidate_name in candidates:
        candidate = (search_root / candidate_name).expanduser()
        if candidate.is_dir():
            return str(candidate.resolve())

    return None


def normalize_storage_path(raw_path: str | None) -> str | None:
    """Return a canonical representation for LocalFiles paths.

    We need consistent paths because permission checks compare the requested
    directory with storage.path prefixes. Users often enter trailing slashes or
    Windows separators; normalizing here prevents mismatches.
    """
    if raw_path is None:
        return None

    trimmed = raw_path.strip()
    if trimmed == '':
        return ''

    collapsed = trimmed.replace('\\', os.sep)
    normalized = os.path.normpath(collapsed)
    return normalized


def build_local_files_path(relative_path: str) -> str:
    """Map a ``/data/local-files/?d=`` value to a path under LOCAL_FILES_DOCUMENT_ROOT.

    Raises SuspiciousFileOperation when the value escapes the document root.
    """
    # Normalize the incoming relative path so we don't depend on trailing slashes
    normalized = posixpath.normpath(relative_path).lstrip('/')
    return safe_join(settings.LOCAL_FILES_DOCUMENT_ROOT, normalized)


def is_within_storage(directory: str, storage_path: str) -> bool:
    # SQL startswith is a plain string prefix: storage /data/ds would also match /data/ds-private
    root = storage_path.rstrip(os.sep)
    return directory == root or directory.startswith(root + os.sep)


def project_local_files_resolver(project) -> Callable[[str], Optional[str]]:
    """Build the SDK converter's Local Storage resolver for exports of ``project``.

    Uses the path rules of the /data/local-files/ view: nothing is readable while local files serving
    is off, otherwise only files under one of this project's Local Files storages.
    """
    # Imported lazily: this module is loaded by settings before the app registry is ready
    from io_storages.localfiles.models import LocalFilesImportStorage

    storage_paths = []
    if settings.LOCAL_FILES_SERVING_ENABLED:
        storage_paths = list(LocalFilesImportStorage.objects.filter(project=project).values_list('path', flat=True))

    def resolve(relative_path: str) -> Optional[str]:
        try:
            full_path = build_local_files_path(relative_path)
        except SuspiciousFileOperation:
            return None
        directory = os.path.normpath(os.path.dirname(full_path))
        if any(is_within_storage(directory, path) for path in storage_paths) and os.path.isfile(full_path):
            return full_path
        return None

    return resolve


def resolve_user_scoped_root(user) -> Optional[Path]:
    """返回用户可访问的本地文件根目录 ``/mnt/<username>/``。

    用户名必须满足主平台规则（小写字母开头，仅小写字母/数字/-），
    否则返回 ``None``，由调用方决定是拒绝（配置侧）还是跳过校验（读取侧）。
    """
    username = getattr(user, 'username', '') or ''
    if not USERNAME_RE.fullmatch(username):
        return None
    return (Path(settings.LOCAL_FILES_DOCUMENT_ROOT) / username).resolve()
