"""Прогресс загрузки Whisper без сети и без микрофона."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# До импорта huggingface_hub, чтобы случайный вызов не начал качать 0.8 ГБ.
_PREV_OFFLINE = os.environ.get("HF_HUB_OFFLINE")
os.environ["HF_HUB_OFFLINE"] = "1"

from yo.asr import RU_TURBO_CT2
from yo.fetchprog import (
    WHISPER_REPO,
    PrefetchError,
    RemoteFile,
    download_whisper_file,
    percent,
    prefetch_whisper,
    remote_byte_size,
    select_whisper_files,
    weights_ready,
    whisper_cache_dir,
)

_ENV_KEYS = ("HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HUB_DISABLE_XET")


def _restore_offline() -> None:
    if _PREV_OFFLINE is None:
        os.environ.pop("HF_HUB_OFFLINE", None)
    else:
        os.environ["HF_HUB_OFFLINE"] = _PREV_OFFLINE


unittest.addModuleCleanup(_restore_offline)


def _write_cached(cache: Path, filename: str, size: int, revision: str = "main") -> Path:
    from huggingface_hub.file_download import repo_folder_name

    folder = cache / repo_folder_name(repo_id=WHISPER_REPO, repo_type="model")
    path = folder / "snapshots" / revision
    for part in filename.split("/"):
        path = path / part
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if revision != "main":
        ref = folder / "refs" / "main"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(revision, encoding="ascii")
    return path


class PercentTests(unittest.TestCase):
    def test_boundaries(self):
        total = 819108016
        self.assertEqual(percent(0, total), 1)
        self.assertEqual(percent(0, 0), 1)
        self.assertEqual(percent(5, 0), 1)
        self.assertEqual(percent(total // 2, total), 50)
        self.assertEqual(percent(200, 400), 50)
        self.assertEqual(percent(total - 1, total), 99)
        self.assertEqual(percent(399, 400), 99)
        self.assertEqual(percent(total, total), 100)
        self.assertEqual(percent(400, 400), 100)
        self.assertEqual(percent(total + 1, total), 100)
        self.assertEqual(percent(1, 10_000), 1)

    def test_never_zero_and_hundred_only_when_complete(self):
        total = 100
        for done in range(0, 150):
            value = percent(done, total)
            self.assertGreaterEqual(value, 1)
            self.assertLessEqual(value, 100)
            if done < total:
                self.assertLess(value, 100)
            else:
                self.assertEqual(value, 100)
        self.assertNotEqual(percent(0, 400), 0)
        self.assertNotEqual(percent(399, 400), 100)


class RemoteSizeTests(unittest.TestCase):
    def test_lfs_size_not_git_pointer(self):
        entry = SimpleNamespace(path="ct2_int8_float16/model.bin", size=134, lfs=SimpleNamespace(size=814054531))
        self.assertEqual(remote_byte_size(entry), 814054531)

    def test_plain_file_uses_size(self):
        entry = SimpleNamespace(path="ct2_int8_float16/config.json", size=2487, lfs=None)
        self.assertEqual(remote_byte_size(entry), 2487)


class SelectFilesTests(unittest.TestCase):
    def test_only_ct2_files_faster_whisper_reads(self):
        files = [
            RemoteFile(".gitattributes", 1519),
            RemoteFile("README.md", 6478),
            RemoteFile("ct2_int8_float16/card.png", 50),
            RemoteFile("ct2_int8_float16/.gitattributes", 10),
            RemoteFile("ct2-int16/model.bin", 100),
            RemoteFile("model.safetensors", 3_000_000_000),
            RemoteFile("tokenizer.json", 100),
            RemoteFile("ct2_int8_float16/config.json", 2487),
            RemoteFile("ct2_int8_float16/model.bin", 814),
            RemoteFile("ct2_int8_float16/preprocessor_config.json", 372),
            RemoteFile("ct2_int8_float16/tokenizer.json", 100),
            RemoteFile("ct2_int8_float16/vocabulary.json", 100),
        ]
        selected = select_whisper_files(files)
        self.assertEqual(
            [item.path for item in selected],
            [
                f"{RU_TURBO_CT2}/config.json",
                f"{RU_TURBO_CT2}/model.bin",
                f"{RU_TURBO_CT2}/preprocessor_config.json",
                f"{RU_TURBO_CT2}/tokenizer.json",
                f"{RU_TURBO_CT2}/vocabulary.json",
            ],
        )
        self.assertNotIn(3_000_000_000, [item.size for item in selected])


class CacheDirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_hf_hub_cache_wins(self):
        os.environ["HF_HUB_CACHE"] = str(Path(self.tmp.name) / "explicit")
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(Path(self.tmp.name) / "legacy")
        os.environ["HF_HOME"] = str(Path(self.tmp.name) / "home")
        self.assertEqual(whisper_cache_dir(), Path(self.tmp.name) / "explicit")

    def test_legacy_hub_cache_then_hf_home(self):
        os.environ.pop("HF_HUB_CACHE", None)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(Path(self.tmp.name) / "legacy")
        os.environ["HF_HOME"] = str(Path(self.tmp.name) / "home")
        self.assertEqual(whisper_cache_dir(), Path(self.tmp.name) / "legacy")

    def test_hf_home_hub_without_touching_xdg(self):
        os.environ.pop("HF_HUB_CACHE", None)
        os.environ.pop("HUGGINGFACE_HUB_CACHE", None)
        os.environ["HF_HOME"] = str(Path(self.tmp.name) / "home")
        with patch("yo.paths.xdg_cache", side_effect=AssertionError("xdg")):
            self.assertEqual(whisper_cache_dir(), Path(self.tmp.name) / "home" / "hub")

    def test_default_is_app_hf_home_hub(self):
        os.environ.pop("HF_HUB_CACHE", None)
        os.environ.pop("HUGGINGFACE_HUB_CACHE", None)
        os.environ.pop("HF_HOME", None)
        root = Path(self.tmp.name) / "yo-voice"
        with patch("yo.paths.xdg_cache", return_value=root):
            self.assertEqual(whisper_cache_dir(), root / "hf" / "hub")
        self.assertEqual(os.environ["HF_HOME"], str(root / "hf"))


class PrefetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        self.addCleanup(self._restore)
        os.environ["HF_HUB_CACHE"] = str(self.cache)
        os.environ.pop("HUGGINGFACE_HUB_CACHE", None)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_already_present_skips_download(self):
        files = (
            RemoteFile(f"{RU_TURBO_CT2}/config.json", 4),
            RemoteFile(f"{RU_TURBO_CT2}/model.bin", 8),
        )
        revision = "ab" * 20
        for item in files:
            _write_cached(self.cache, item.path, item.size, revision=revision)
        calls = []
        with (
            patch("yo.fetchprog.remote_whisper_files", return_value=files) as remote,
            patch("yo.fetchprog.download_whisper_file") as download,
        ):
            result = prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)), now=None)
        remote.assert_called_once()
        download.assert_not_called()
        self.assertEqual(calls, [(12, 12, "check")])
        self.assertTrue(result.already_present)
        self.assertEqual(result.total_bytes, 12)
        self.assertEqual(result.cache_dir, self.cache)
        self.assertEqual(result.model_dir.name, RU_TURBO_CT2)
        self.assertIsNone(result.checked_at)
        self.assertEqual(percent(calls[-1][0], calls[-1][1]), 100)

    def test_progress_increases_and_final_is_complete(self):
        config = f"{RU_TURBO_CT2}/config.json"
        weights = f"{RU_TURBO_CT2}/model.bin"
        sizes = {config: 1000, weights: 3000}
        listed = (
            RemoteFile("model.safetensors", 50_000),
            RemoteFile(".gitattributes", 20),
            RemoteFile(f"{RU_TURBO_CT2}/card.jpg", 30),
            RemoteFile(config, sizes[config]),
            RemoteFile(weights, sizes[weights]),
        )

        def fake_download(filename, *, cache_dir, tqdm_class, force=False):
            size = sizes[filename]
            bar = tqdm_class(total=size, initial=0, desc=filename)
            with bar:
                first = size // 2
                bar.update(first)
                bar.update(size - first)
            _write_cached(Path(cache_dir), filename, size)
            return filename

        calls = []
        with (
            patch("yo.fetchprog.remote_whisper_files", return_value=listed),
            patch("yo.fetchprog.download_whisper_file", side_effect=fake_download) as download,
        ):
            result = prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)), now=12.5)
        self.assertEqual([call.args[0] for call in download.call_args_list], [config, weights])
        self.assertTrue(all(call.kwargs["force"] is False for call in download.call_args_list))
        self.assertEqual(download.call_args_list[0].kwargs["cache_dir"], self.cache)
        dones = [done for done, _total, phase in calls if phase == "download"]
        self.assertGreaterEqual(len(dones), 2)
        self.assertTrue(all(later > earlier for earlier, later in zip(dones, dones[1:])))
        self.assertTrue(all(done < 4000 for done in dones))
        self.assertTrue(all(total == 4000 for _done, total, _phase in calls))
        self.assertTrue(all(phase == "download" for *_rest, phase in calls[:-1]))
        self.assertEqual(calls[-1], (4000, 4000, "check"))
        self.assertEqual(percent(calls[-1][0], calls[-1][1]), 100)
        self.assertTrue(all(percent(done, total) < 100 for done, total, phase in calls if phase == "download"))
        self.assertFalse(result.already_present)
        self.assertEqual(result.files, (config, weights))
        self.assertEqual(result.checked_at, 12.5)
        self.assertEqual(result.model_dir.name, RU_TURBO_CT2)

    def test_size_mismatch_redownloads_that_file(self):
        config = f"{RU_TURBO_CT2}/config.json"
        weights = f"{RU_TURBO_CT2}/model.bin"
        files = (RemoteFile(config, 6), RemoteFile(weights, 10))
        _write_cached(self.cache, config, 6)
        _write_cached(self.cache, weights, 3)

        def fake_download(filename, *, cache_dir, tqdm_class, force=False):
            self.assertTrue(force)
            bar = tqdm_class(total=10, initial=0)
            bar.update(4)
            bar.update(6)
            _write_cached(Path(cache_dir), filename, 10)
            return filename

        calls = []
        with (
            patch("yo.fetchprog.remote_whisper_files", return_value=files),
            patch("yo.fetchprog.download_whisper_file", side_effect=fake_download) as download,
        ):
            result = prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)))
        self.assertEqual(download.call_count, 1)
        self.assertEqual(download.call_args.args[0], weights)
        self.assertFalse(result.already_present)
        self.assertEqual(calls[-1][2], "check")
        self.assertEqual(percent(calls[-1][0], calls[-1][1]), 100)

    def test_failed_download_raises_and_does_not_report_100(self):
        weights = f"{RU_TURBO_CT2}/model.bin"
        files = (RemoteFile(weights, 250),)

        def fake_download(filename, *, cache_dir, tqdm_class, force=False):
            bar = tqdm_class(total=250, initial=0)
            with bar:
                bar.update(250)
            raise ConnectionError("reset")

        calls = []
        with (
            patch("yo.fetchprog.remote_whisper_files", return_value=files),
            patch("yo.fetchprog.download_whisper_file", side_effect=fake_download),
        ):
            with self.assertRaises(PrefetchError) as caught:
                prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)))
        self.assertIsInstance(caught.exception.__cause__, ConnectionError)
        self.assertIn("скачать", str(caught.exception))
        self.assertNotIn("reset", str(caught.exception))
        self.assertGreater(len(calls), 0)
        self.assertTrue(all(phase == "download" for _done, _total, phase in calls))
        self.assertTrue(all(percent(done, total) < 100 for done, total, _phase in calls))
        self.assertTrue(all(done < total for done, total, _phase in calls))

    def test_metadata_failure_raises_without_progress(self):
        calls = []
        with (
            patch("yo.fetchprog.remote_whisper_files", side_effect=TimeoutError("timed out")),
            patch("yo.fetchprog.download_whisper_file") as download,
        ):
            with self.assertRaises(PrefetchError) as caught:
                prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)))
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertIn("сеть", str(caught.exception))
        self.assertEqual(calls, [])
        download.assert_not_called()

    def test_metadata_failure_keeps_complete_local_weights(self):
        revision = "cd" * 20
        names = (
            f"{RU_TURBO_CT2}/config.json",
            f"{RU_TURBO_CT2}/preprocessor_config.json",
            f"{RU_TURBO_CT2}/tokenizer.json",
            f"{RU_TURBO_CT2}/vocabulary.json",
        )
        for name in names:
            _write_cached(self.cache, name, 4, revision=revision)
        _write_cached(self.cache, f"{RU_TURBO_CT2}/model.bin", 8, revision=revision)
        calls = []
        with (
            patch("yo.fetchprog._MIN_WEIGHTS", 8),
            patch("yo.fetchprog.remote_whisper_files", side_effect=TimeoutError("timed out")) as remote,
            patch("yo.fetchprog.download_whisper_file") as download,
        ):
            result = prefetch_whisper(lambda done, total, phase: calls.append((done, total, phase)))
        remote.assert_called_once()
        download.assert_not_called()
        self.assertTrue(result.already_present)
        self.assertEqual(calls, [(result.total_bytes, result.total_bytes, "check")])
        self.assertEqual(percent(calls[-1][0], calls[-1][1]), 100)
        self.assertGreaterEqual(result.total_bytes, 8)

    def test_weights_ready_reads_disk_and_does_not_call_hub(self):
        revision = "ef" * 20
        names = (
            f"{RU_TURBO_CT2}/config.json",
            f"{RU_TURBO_CT2}/preprocessor_config.json",
            f"{RU_TURBO_CT2}/tokenizer.json",
            f"{RU_TURBO_CT2}/vocabulary.json",
        )
        for name in names:
            _write_cached(self.cache, name, 3, revision=revision)
        self.assertFalse(weights_ready())
        _write_cached(self.cache, f"{RU_TURBO_CT2}/model.bin", 9, revision=revision)
        with (
            patch("yo.fetchprog._MIN_WEIGHTS", 8),
            patch("yo.fetchprog.remote_whisper_files", side_effect=AssertionError("hub")) as remote,
        ):
            self.assertTrue(weights_ready())
        remote.assert_not_called()

    def test_download_helper_passes_tqdm_and_cache(self):
        marker = type("Marker", (), {})
        with patch("huggingface_hub.hf_hub_download", return_value="cached") as hub:
            returned = download_whisper_file(
                f"{RU_TURBO_CT2}/model.bin",
                cache_dir=self.cache,
                tqdm_class=marker,
                force=True,
            )
        self.assertEqual(returned, "cached")
        self.assertIs(hub.call_args.kwargs["tqdm_class"], marker)
        self.assertEqual(hub.call_args.kwargs["cache_dir"], str(self.cache))
        self.assertTrue(hub.call_args.kwargs["force_download"])
        self.assertEqual(hub.call_args.args[0], WHISPER_REPO)
        self.assertEqual(hub.call_args.args[1], f"{RU_TURBO_CT2}/model.bin")
        self.assertEqual(WHISPER_REPO, "coriollon/whisper-large-v3-turbo-russian")
