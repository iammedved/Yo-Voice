import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class CudaEnvTests(unittest.TestCase):
    def test_search_dirs_include_nvidia_bin_subdirectory(self):
        from yo import cuda_env

        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "cublas"
            bindir = pkg / "bin"
            bindir.mkdir(parents=True)
            (bindir / "cublas64_12.dll").write_bytes(b"MZ")
            fake = types.SimpleNamespace(
                __path__=[str(pkg)],
                __file__=str(pkg / "__init__.py"),
            )
            with mock.patch.dict(sys.modules, {"nvidia.cublas.lib": fake}):
                dirs = cuda_env.cuda_search_dirs()
        self.assertIn(str(pkg), dirs)
        self.assertIn(str(bindir), dirs)

    def test_frozen_meipass_includes_cublas_bin(self):
        from yo import cuda_env

        with tempfile.TemporaryDirectory() as tmp:
            meipass = str(Path(tmp) / "internal")
            with mock.patch.object(sys, "frozen", True, create=True):
                with mock.patch.object(sys, "_MEIPASS", meipass, create=True):
                    dirs = cuda_env.cuda_search_dirs()
        self.assertIn(os.path.join(meipass, "nvidia", "cublas", "bin"), dirs)
        self.assertIn(os.path.join(meipass, "nvidia", "cuda_runtime", "bin"), dirs)
        self.assertIn(os.path.join(meipass, "ctranslate2"), dirs)

    def test_wanted_dlls_include_cublas12(self):
        from yo.cuda_env import WANTED_DLLS

        self.assertIn("cublas64_12.dll", WANTED_DLLS)
        self.assertIn("cublasLt64_12.dll", WANTED_DLLS)
        self.assertIn("cudart64_12.dll", WANTED_DLLS)

    def test_nvidia_cuda_binaries_collect_wheel_dlls(self):
        from yo.cuda_env import nvidia_cuda_binaries

        bins = nvidia_cuda_binaries()
        names = {Path(src).name for src, _dest in bins}
        if "cublas64_12.dll" not in names:
            self.skipTest("nvidia-cublas-cu12 wheel not installed")
        self.assertIn("cublasLt64_12.dll", names)
        self.assertIn("cudart64_12.dll", names)
        dests = {dest for _src, dest in bins}
        self.assertIn("nvidia/cublas/bin", dests)
        self.assertIn("nvidia/cuda_runtime/bin", dests)
        for src, _dest in bins:
            self.assertTrue(Path(src).is_file(), src)

    def test_setup_prepends_bin_to_path(self):
        from yo import cuda_env

        old = os.environ.get("PATH", "")
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "cublas"
            bindir = pkg / "bin"
            bindir.mkdir(parents=True)
            (bindir / "cublas64_12.dll").write_bytes(b"MZ")
            fake = types.SimpleNamespace(
                __path__=[str(pkg)],
                __file__=str(pkg / "__init__.py"),
            )
            try:
                with mock.patch.dict(sys.modules, {"nvidia.cublas.lib": fake}):
                    cuda_env.setup_cuda_libs()
                self.assertTrue(
                    os.environ.get("PATH", "").startswith(str(bindir))
                    or str(bindir) in os.environ.get("PATH", "").split(os.pathsep),
                )
            finally:
                os.environ["PATH"] = old

    def test_spec_collects_nvidia_cuda_binaries(self):
        spec = Path(__file__).resolve().parents[1].joinpath("packaging", "yo-voice.spec").read_text(
            encoding="utf-8"
        )
        self.assertIn("nvidia_cuda_binaries", spec)
        self.assertIn("_nvidia_cuda_binaries", spec)
        self.assertNotIn('"nvidia.cublas"', spec)

    def test_rthook_prepends_cuda_path(self):
        src = Path(__file__).resolve().parents[1].joinpath("packaging", "rthook_console.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_prepend_cuda_path", src)
        self.assertIn("nvidia/cublas/bin", src)
