from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from numuw.storage_backends import get_rename

if TYPE_CHECKING:
    from django.db import models


def get_path(instance: models.Model, filename: str) -> str:
    """
    Generates a path for uploading a file by appending the filename to a predefined directory.
    """
    return get_rename("chat_files/", filename)


def validate_file_extension(value: File):
    """
    Validates the file extension of an uploaded file against a list of supported extensions.
    """
    import os
    ext = os.path.splitext(value.name)[1]  # Extracts the file extension
    if ext.lower() not in settings.CHAT_FILE_EXTENSIONS:
        raise ValidationError("Unsupported file extension.")
