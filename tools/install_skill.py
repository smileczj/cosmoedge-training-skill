#!/usr/bin/env python3
"""Install a verified release archive into an explicitly selected directory."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

from package_skill import (
    MANIFEST_NAME, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, SKILL_NAME,
    PackageError, portable_key, safe_relative_path, validate_payload,
)


def read_archive(archive_path: Path) -> tuple[dict[str, bytes], set[str]]:
    files = {}
    executable = set()
    names = set()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES + 1 or sum(m.file_size for m in members) > MAX_TOTAL_BYTES + MAX_FILE_BYTES:
            raise PackageError("归档超过文件数或展开体积限制")
        for member in members:
            safe_relative_path(member.filename)
            key = portable_key(member.filename)
            if key in names:
                raise PackageError("归档包含重复或冲突路径")
            names.add(key)
            prefix = SKILL_NAME + "/"
            if not member.filename.startswith(prefix):
                raise PackageError(f"归档必须位于单个 {SKILL_NAME} 目录内")
            name = member.filename[len(prefix):]
            safe_relative_path(name)
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if member.is_dir() or kind not in {0, stat.S_IFREG}:
                raise PackageError(f"归档不接受符号链接或特殊文件：{name}")
            if member.flag_bits & 1 or member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise PackageError("归档不接受加密或不支持的压缩格式")
            if member.file_size > MAX_FILE_BYTES:
                raise PackageError(f"归档文件过大：{name}")
            data = archive.read(member)
            if len(data) != member.file_size:
                raise PackageError(f"文件大小不匹配：{name}")
            files[name] = data
            if mode & stat.S_IXUSR:
                executable.add(name)
    try:
        raw_manifest = files.pop(MANIFEST_NAME)
        manifest = json.loads(raw_manifest)
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError("缺少有效的 MANIFEST.json") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("name") != SKILL_NAME:
        raise PackageError("不支持的包清单格式")
    records = manifest.get("files")
    if not isinstance(records, dict) or set(records) != set(files):
        raise PackageError("清单与归档文件不一致")
    for name, data in files.items():
        record = records[name]
        if not isinstance(record, dict) or type(record.get("size")) is not int or record["size"] != len(data):
            raise PackageError(f"清单大小不匹配：{name}")
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not hmac.compare_digest(digest, hashlib.sha256(data).hexdigest()):
            raise PackageError(f"SHA-256 校验失败：{name}")
    validate_payload(files)
    files[MANIFEST_NAME] = raw_manifest
    return files, executable


def install_archive(archive_path: Path, destination: Path) -> Path:
    files, executable = read_archive(archive_path)
    destination = destination.expanduser().absolute()
    if destination.is_symlink():
        raise PackageError("安装目录本身不能是符号链接")
    target = destination / SKILL_NAME
    if target.exists() or target.is_symlink():
        raise PackageError(f"安装位置已存在，拒绝覆盖：{target}")
    destination.mkdir(parents=True, exist_ok=True)
    # Materialize the complete verified package before reserving the final name.
    with tempfile.TemporaryDirectory(dir=destination, prefix=".skill-install-") as staging:
        staged = Path(staging)
        for name, data in files.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755 if name in executable else 0o644)
        # mkdir is exclusive: even concurrent installs cannot replace an existing directory.
        try:
            target.mkdir()
        except FileExistsError as exc:
            raise PackageError(f"安装位置已存在，拒绝覆盖：{target}") from exc
        try:
            for child in staged.iterdir():
                child.rename(target / child.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="将完整 Skill 包安装到明确指定的位置，不覆盖已有安装")
    parser.add_argument("archive", type=Path, help="package_skill.py 生成的 ZIP 文件")
    parser.add_argument("--dest", type=Path, required=True, help="Skill 安装父目录；会创建 cosmoedge-training 子目录")
    args = parser.parse_args()
    try:
        target = install_archive(args.archive.expanduser(), args.dest)
        print(f"安装完成：{target}\n请让 AI 助手重新发现 Skill，或明确读取其中的 SKILL.md。")
    except (PackageError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(1, f"安装失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
