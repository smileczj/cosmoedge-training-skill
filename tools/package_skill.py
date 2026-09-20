#!/usr/bin/env python3
"""Validate and package the self-contained Skill using only the standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
from urllib.parse import unquote, urlsplit
import zipfile


SKILL_NAME = "cosmoedge-training"
MANIFEST_NAME = "MANIFEST.json"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_FILES = 1000
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".safetensors", ".bmodel", ".rknn", ".nn", ".ckpt", ".bin"}
IGNORED_NAMES = {".DS_Store", "__pycache__"}


class PackageError(ValueError):
    """An invalid source package or archive."""


def safe_relative_path(name: str) -> PurePosixPath:
    """Accept a portable relative file path, without normalization surprises."""
    if not name or "\\" in name or ":" in name or any(ord(c) < 32 for c in name):
        raise PackageError(f"不安全的包内路径：{name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")):
        raise PackageError(f"不安全的包内路径：{name!r}")
    if any(p.endswith((".", " ")) for p in path.parts):
        raise PackageError(f"不兼容的包内路径：{name!r}")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
    if any(p.split(".")[0].upper() in reserved for p in path.parts):
        raise PackageError(f"包内路径使用了系统保留名称：{name!r}")
    return path


def portable_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _frontmatter(text: str) -> None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PackageError("SKILL.md 缺少 YAML frontmatter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise PackageError("SKILL.md frontmatter 未结束") from exc
    values = {}
    for index, line in enumerate(lines[1:end], 1):
        match = re.match(r"^(name|description):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if key in values:
            raise PackageError(f"SKILL.md 重复字段：{key}")
        value = value.strip()
        if value in {"|", ">", "|-", ">-"}:
            continuation = []
            for following in lines[index + 1:end]:
                if following and not following.startswith((" ", "\t")):
                    break
                continuation.append(following.strip())
            value = " ".join(continuation).strip()
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        values[key] = value
    if values.get("name") != SKILL_NAME:
        raise PackageError(f"SKILL.md name 必须为 {SKILL_NAME}")
    description = values.get("description", "")
    if not description or description in {"null", "~"} or len(description) > 1024:
        raise PackageError("SKILL.md description 必须有实际说明，且不超过 1024 字符")


def _scan_text(name: str, text: str) -> None:
    rules = {
        "未完成的脚手架占位符": r"\bTODO\b|\[INSERT[_ ]|\[PLACEHOLDER\]",
        "本机个人绝对路径": r"/(?:Users|home)/[^\s/<]+|/var/folders/|[A-Za-z]:[\\/]Users[\\/]",
        "私钥": r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
        "访问令牌": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{24,})\b",
        "带凭据的 URL": r"https?://[^\s/@:]+:[^\s/@]+@",
    }
    for reason, pattern in rules.items():
        if re.search(pattern, text):
            raise PackageError(f"{name} 包含{reason}，请移除后打包")
    assignments = re.finditer(
        r"(?im)\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*([^\s,;]+)", text
    )
    for match in assignments:
        value = match.group(1).strip("\"'")
        if value and not value.startswith(("<", "${", "$", "os.environ", "os.getenv")) and value.upper() not in {
            "NONE", "NULL", "REDACTED", "YOUR_TOKEN", "YOUR_API_KEY", "YOUR_PASSWORD", "***"
        }:
            raise PackageError(f"{name} 包含疑似凭据赋值，请使用安全输入或清晰的占位符")


def _check_link(source: str, target: str, files: dict[str, bytes]) -> None:
    target = target.strip()
    if target.startswith("<"):
        target = target[1:target.find(">")]
    else:
        target = target.split()[0] if target else ""
    target = target.replace("\\ ", " ")
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https", "mailto"} or not target or target.startswith("#"):
        return
    if parsed.scheme or parsed.netloc:
        raise PackageError(f"{source} 包含不支持的资源链接：{target}")
    decoded = unquote(parsed.path)
    if not decoded:
        return
    if decoded.startswith(("/", "\\")) or "\\" in decoded:
        raise PackageError(f"{source} 包含绝对资源路径：{target}")
    parts = list(PurePosixPath(source).parent.parts)
    for part in decoded.split("/"):
        if part == "..":
            if not parts:
                raise PackageError(f"{source} 的链接越出 Skill：{target}")
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    relative = "/".join(parts)
    if relative not in files and not any(p.startswith(relative + "/") for p in files):
        raise PackageError(f"{source} 链接的文件不存在：{target}")


def validate_payload(files: dict[str, bytes]) -> None:
    if "SKILL.md" not in files or "LICENSE" not in files:
        raise PackageError("包必须包含 SKILL.md 和 LICENSE")
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise PackageError("Skill 包文件过多或体积过大；数据与权重应单独管理")
    seen = set()
    for name, data in files.items():
        path = safe_relative_path(name)
        key = portable_key(name)
        if key in seen:
            raise PackageError(f"包内路径在其他文件系统上会冲突：{name}")
        seen.add(key)
        if path.suffix.lower() in WEIGHT_SUFFIXES or len(data) > MAX_FILE_BYTES:
            raise PackageError(f"不要在 Skill 中分发模型权重或过大文件：{name}")
        if any(p == ".git" or p.startswith(".env") or p in {"id_rsa", "id_ed25519", "credentials.json"} for p in path.parts):
            raise PackageError(f"包包含私有运行文件：{name}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            if path.suffix.lower() in {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".sh"}:
                raise PackageError(f"文本文件必须为 UTF-8：{name}") from None
            continue
        _scan_text(name, text)
        if path.suffix.lower() == ".md":
            # Verify local files/resources; anchors and external availability are separate concerns.
            for match in re.finditer(r"\]\((<[^>]+>|[^)]+)\)", text):
                _check_link(name, match.group(1), files)
            for match in re.finditer(r"(?m)^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", text):
                _check_link(name, match.group(1), files)
        if path.suffix.lower() in {".md", ".html"}:
            for match in re.finditer(r"\b(?:src|href)=[\"']([^\"']+)[\"']", text):
                _check_link(name, match.group(1), files)
    try:
        _frontmatter(files["SKILL.md"].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PackageError("SKILL.md 必须为 UTF-8") from exc


def collect_payload(repo_root: Path) -> tuple[dict[str, bytes], set[str]]:
    source = repo_root / "skills" / SKILL_NAME
    if source.is_symlink() or not source.is_dir():
        raise PackageError(f"缺少真实 Skill 目录：{source}")
    files = {}
    executable = set()
    total_bytes = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(p in IGNORED_NAMES or p.endswith((".pyc", ".pyo")) for p in relative.parts):
            continue
        if path.is_symlink():
            raise PackageError(f"Skill 中不接受符号链接：{relative}")
        if path.is_dir():
            continue
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise PackageError(f"不支持的文件类型或大小：{relative}")
        total_bytes += path.stat().st_size
        if total_bytes > MAX_TOTAL_BYTES or len(files) >= MAX_FILES - 1:
            raise PackageError("Skill 源目录文件过多或体积过大")
        name = relative.as_posix()
        if name == MANIFEST_NAME:
            raise PackageError(f"{name} 由打包器从仓库生成，请勿放入 Skill 源目录")
        files[name] = path.read_bytes()
        if path.stat().st_mode & stat.S_IXUSR:
            executable.add(name)
    license_path = repo_root / "LICENSE"
    if license_path.is_symlink() or not license_path.is_file() or license_path.stat().st_size > MAX_FILE_BYTES:
        raise PackageError("仓库必须包含普通文件 LICENSE")
    root_license = license_path.read_bytes()
    if "LICENSE" in files and files["LICENSE"] != root_license:
        raise PackageError("Skill 目录 LICENSE 与仓库根 LICENSE 不一致，请同步后再发布")
    files["LICENSE"] = root_license
    validate_payload(files)
    return files, executable


def build_package(repo_root: Path, output: Path) -> dict:
    files, executable = collect_payload(repo_root)
    manifest = {
        "format": 1,
        "name": SKILL_NAME,
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in sorted(files.items())},
    }
    files[MANIFEST_NAME] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".skill-", suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(f"{SKILL_NAME}/{name}", date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if name in executable else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并打包完整 CosmoEdge 训练 Skill")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1], help="源仓库目录")
    parser.add_argument("--output", type=Path, help="ZIP 输出位置；默认 dist/cosmoedge-training.zip")
    parser.add_argument("--check", action="store_true", help="只检查，不生成文件")
    args = parser.parse_args()
    root = args.repo_root.expanduser().resolve()
    try:
        if args.check:
            files, _ = collect_payload(root)
            print(f"检查通过：{len(files)} 个文件，包含 LICENSE，内部资源完整。")
        else:
            output = args.output.expanduser().absolute() if args.output else root / "dist" / f"{SKILL_NAME}.zip"
            manifest = build_package(root, output)
            print(f"已打包：{output}\n包含 {len(manifest['files'])} 个文件及 SHA-256 清单。")
    except (PackageError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"打包失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
