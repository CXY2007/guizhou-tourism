"""上传文件（评论配图等）的清理：只在没人再引用时删除磁盘文件，避免误删。"""
from __future__ import annotations

import os

from flask import current_app


def _abs_path(url: str):
    if not url or not isinstance(url, str) or not url.startswith("/static/"):
        return None
    relative = url[len("/static/"):]
    if ".." in relative or relative.startswith("/") or "\\" in relative:
        return None
    return os.path.join(current_app.static_folder, relative.replace("/", os.sep))


def is_file_unused(url: str) -> bool:
    """评论、景点图集、景点封面都没引用这个地址时才返回 True。"""
    from ..models import Attraction, AttractionImage, Comment

    return (
        Comment.query.filter_by(image_url=url).first() is None
        and AttractionImage.query.filter_by(image_url=url).first() is None
        and Attraction.query.filter_by(cover_image=url).first() is None
    )


def remove_file_if_unused(url: str) -> bool:
    path = _abs_path(url)
    if not path or not os.path.isfile(path):
        return False
    if not is_file_unused(url):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False
