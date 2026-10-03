"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license."""

import os
from pathlib import Path

from core.utils.exceptions import extract_message
from django.core.exceptions import ValidationError as DjangoValidationError  # type: ignore[import]
from io_storages.localfiles.functions import resolve_user_scoped_root
from io_storages.localfiles.models import (
    LocalFilesExportStorage,
    LocalFilesImportStorage,
    normalize_storage_path,
)
from io_storages.serializers import ExportStorageSerializer, ImportStorageSerializer, StorageTypeField
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError  # type: ignore[import]


def _stringify_detail(detail):
    """Convert DRF/Django validation detail into plain strings for the UI."""
    if isinstance(detail, dict):
        return {key: _stringify_detail(value) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_stringify_detail(item) for item in detail]
    return str(detail)


def validate_local_path_user_scope(serializer, path):
    """限制 Local Files 的 path 必须在 /mnt/<username>/ 下（一人一目录，数据隔离）。

    访问依据为当前登录的 username（来自 SSO 中间件，request.user.username）。
    在 normalize_storage_path 之前调用，用 resolve 消除 .. 与符号链接逃逸。
    """
    request = serializer.context.get('request')
    user = getattr(request, 'user', None) if request else None
    if not user or not user.is_authenticated:
        raise PermissionDenied('未登录，无法配置本地文件路径')

    user_root = resolve_user_scoped_root(user)
    if user_root is None:
        raise PermissionDenied('当前用户名不合法，无法配置本地文件路径')

    target = Path(path).resolve()  # resolve 消除 .. 与符号链接逃逸
    if not (target == user_root or user_root in target.parents):
        raise PermissionDenied(f'无权访问该路径：本地文件路径必须以 {user_root} 开头')


class LocalFilesImportStorageSerializer(ImportStorageSerializer):
    type = StorageTypeField(default=os.path.basename(os.path.dirname(__file__)))

    class Meta:
        model = LocalFilesImportStorage
        fields = '__all__'

    def validate(self, data):
        # Validate local file path
        data = super(LocalFilesImportStorageSerializer, self).validate(data)
        if 'path' in data:
            if data['path']:
                validate_local_path_user_scope(self, data['path'])
            data['path'] = normalize_storage_path(data['path'])
        storage = LocalFilesImportStorage(**data)
        try:
            storage.validate_connection()
        except (DjangoValidationError, DRFValidationError) as exc:
            detail = getattr(exc, 'detail', getattr(exc, 'messages', str(exc)))
            raise DRFValidationError(_stringify_detail(detail))
        except Exception as exc:
            raise DRFValidationError(extract_message(exc))
        return data


class LocalFilesExportStorageSerializer(ExportStorageSerializer):
    type = StorageTypeField(default=os.path.basename(os.path.dirname(__file__)))

    class Meta:
        model = LocalFilesExportStorage
        fields = '__all__'

    def validate(self, data):
        # Validate local file path
        data = super(LocalFilesExportStorageSerializer, self).validate(data)
        if 'path' in data:
            if data['path']:
                validate_local_path_user_scope(self, data['path'])
            data['path'] = normalize_storage_path(data['path'])
        storage = LocalFilesExportStorage(**data)
        try:
            storage.validate_connection()
        except (DjangoValidationError, DRFValidationError) as exc:
            detail = getattr(exc, 'detail', getattr(exc, 'messages', str(exc)))
            raise DRFValidationError(_stringify_detail(detail))
        except Exception as exc:
            raise DRFValidationError(extract_message(exc))
        return data
