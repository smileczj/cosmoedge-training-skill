"""Behavioral checks for portable, complete and non-destructive Skill installation."""

import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_skill import MANIFEST_NAME, SKILL_NAME, PackageError, build_package, collect_payload
from install_skill import install_archive


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repository"
        self.skill = self.repo / "skills" / SKILL_NAME
        (self.skill / "references").mkdir(parents=True)
        (self.skill / "assets").mkdir()
        (self.repo / "LICENSE").write_text("Example test license\n", encoding="utf-8")
        (self.skill / "SKILL.md").write_text(
            "---\nname: cosmoedge-training\ndescription: Assist model training.\n---\n"
            "[Read](references/guide.md)\n[Template](assets/task.md)\n", encoding="utf-8"
        )
        (self.skill / "references/guide.md").write_text("[Template](../assets/task.md)\n", encoding="utf-8")
        (self.skill / "assets/task.md").write_text("# Task\nDescribe the actual objective.\n", encoding="utf-8")
        self.archive = self.root / "release.zip"

    def package(self):
        return build_package(self.repo, self.archive)

    def rewrite(self, change):
        with zipfile.ZipFile(self.archive) as source:
            members = [(info, source.read(info)) for info in source.infolist()]
        with zipfile.ZipFile(self.archive, "w") as target:
            for info, data in members:
                target.writestr(info, change(info.filename, data))

    def test_fresh_install_is_self_contained_and_preserves_every_resource(self):
        manifest = self.package()
        destination = self.root / "new-machine" / "skills"
        installed = install_archive(self.archive, destination)
        self.assertEqual(installed, destination / SKILL_NAME)
        for name, record in manifest["files"].items():
            data = (installed / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
        self.assertEqual((installed / "references/../assets/task.md").read_text(), (self.skill / "assets/task.md").read_text())
        self.assertTrue((installed / "LICENSE").is_file())
        self.assertTrue((installed / MANIFEST_NAME).is_file())

    def test_matching_source_license_is_packaged_once_and_preserved(self):
        license_bytes = (self.repo / "LICENSE").read_bytes()
        (self.skill / "LICENSE").write_bytes(license_bytes)
        self.package()
        with zipfile.ZipFile(self.archive) as archive:
            name = f"{SKILL_NAME}/LICENSE"
            self.assertEqual(archive.namelist().count(name), 1)
            self.assertEqual(archive.read(name), license_bytes)
        installed = install_archive(self.archive, self.root / "skills")
        self.assertEqual((installed / "LICENSE").read_bytes(), license_bytes)

    def test_different_source_license_blocks_release(self):
        (self.skill / "LICENSE").write_text("Different license or outdated notice\n")
        with self.assertRaises(PackageError):
            self.package()
        self.assertFalse(self.archive.exists())

    def test_direct_directory_install_contains_the_repository_license(self):
        repository = Path(__file__).resolve().parents[1]
        copied = self.root / "direct-install" / SKILL_NAME
        shutil.copytree(repository / "skills" / SKILL_NAME, copied)
        self.assertEqual((copied / "LICENSE").read_bytes(), (repository / "LICENSE").read_bytes())
        self.assertTrue((copied / "SKILL.md").is_file())
        self.assertTrue((copied / "references/data-and-labels.md").is_file())

    def test_existing_install_is_untouched(self):
        self.package()
        destination = self.root / "skills"
        existing = destination / SKILL_NAME
        existing.mkdir(parents=True)
        sentinel = existing / "my-customization.md"
        sentinel.write_text("keep this")
        with self.assertRaises(PackageError):
            install_archive(self.archive, destination)
        self.assertEqual(sentinel.read_text(), "keep this")
        self.assertEqual(list(existing.iterdir()), [sentinel])

    def test_failed_install_rolls_back_its_new_directory(self):
        self.package()
        destination = self.root / "skills"
        with mock.patch.object(Path, "rename", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                install_archive(self.archive, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_archive_is_reproducible_for_unchanged_sources(self):
        self.package()
        first = self.archive.read_bytes()
        self.package()
        self.assertEqual(self.archive.read_bytes(), first)

    def test_missing_resource_and_escape_are_rejected_before_writing(self):
        for link in ("../missing.md", "../../../outside.md", "/private/local.md"):
            with self.subTest(link=link):
                (self.skill / "references/guide.md").write_text(f"[Read]({link})\n")
                with self.assertRaises(PackageError):
                    self.package()
                self.assertFalse(self.archive.exists())

    def test_symlink_outside_skill_is_never_followed(self):
        secret = self.root / "outside.txt"
        secret.write_text("outside")
        (self.skill / "references/private.md").symlink_to(secret)
        with self.assertRaises(PackageError):
            self.package()

    def test_frontmatter_and_publication_hygiene(self):
        original = (self.skill / "SKILL.md").read_text()
        for bad in (
            original.replace("name: cosmoedge-training", "name: another-skill"),
            original.replace("description: Assist model training.", "description: ''"),
            original + "\n[TODO: fill this]\n",
            original + "\n/Users/example/private/work\n",
            original + "\npassword=do-not-publish\n",
        ):
            with self.subTest(text=bad[-45:]):
                (self.skill / "SKILL.md").write_text(bad)
                with self.assertRaises(PackageError):
                    self.package()

    def test_weights_are_excluded_even_when_small(self):
        (self.skill / "assets/weights.onnx").write_bytes(b"small test model")
        with self.assertRaises(PackageError):
            self.package()

    def test_tampering_leaves_no_install(self):
        self.package()
        self.rewrite(lambda name, data: data + b"modified" if name.endswith("assets/task.md") else data)
        destination = self.root / "skills"
        with self.assertRaises(PackageError):
            install_archive(self.archive, destination)
        self.assertFalse(destination.exists())

    def test_unlisted_file_is_not_installed(self):
        self.package()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(f"{SKILL_NAME}/unlisted.py", "print('unexpected')")
        with self.assertRaises(PackageError):
            install_archive(self.archive, self.root / "skills")

    def test_invalid_manifest_digest_is_rejected_cleanly(self):
        self.package()
        def change(name, data):
            if name.endswith(MANIFEST_NAME):
                manifest = json.loads(data)
                manifest["files"]["SKILL.md"]["sha256"] = "错误摘要"
                return json.dumps(manifest).encode()
            return data
        self.rewrite(change)
        with self.assertRaises(PackageError):
            install_archive(self.archive, self.root / "skills")

    def test_portable_case_collision_is_rejected(self):
        # Use an archive so the fixture works on case-insensitive filesystems too.
        self.package()
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(f"{SKILL_NAME}/SKILL.MD", b"collision")
        with self.assertRaises(PackageError):
            install_archive(self.archive, self.root / "skills")

    def test_dangerous_archive_members_are_rejected(self):
        for name in ("../escaped", f"{SKILL_NAME}/../../escaped", "/absolute", f"{SKILL_NAME}\\escaped", f"{SKILL_NAME}/CON.txt"):
            with self.subTest(name=name):
                self.package()
                with zipfile.ZipFile(self.archive, "a") as archive:
                    archive.writestr(name, b"bad")
                with self.assertRaises(PackageError):
                    install_archive(self.archive, self.root / "skills")
                self.assertFalse((self.root / "escaped").exists())

    def test_archive_symlink_is_rejected(self):
        self.package()
        with zipfile.ZipFile(self.archive, "a") as archive:
            entry = zipfile.ZipInfo(f"{SKILL_NAME}/outside")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, "../../outside")
        with self.assertRaises(PackageError):
            install_archive(self.archive, self.root / "skills")

    def test_cli_requires_explicit_destination(self):
        self.package()
        script = Path(__file__).resolve().parents[1] / "tools/install_skill.py"
        result = subprocess.run([sys.executable, str(script), str(self.archive)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "skills").exists())

    def test_repository_package_installs_from_an_unrelated_directory(self):
        repository = Path(__file__).resolve().parents[1]
        build_package(repository, self.archive)
        destination = self.root / "unrelated" / "skills"
        script = repository / "tools/install_skill.py"
        result = subprocess.run(
            [sys.executable, str(script), str(self.archive), "--dest", str(destination)],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = destination / SKILL_NAME
        expected, _ = collect_payload(repository)
        self.assertEqual({p.relative_to(installed).as_posix() for p in installed.rglob("*") if p.is_file()}, set(expected) | {MANIFEST_NAME})
        for name, data in expected.items():
            self.assertEqual((installed / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
