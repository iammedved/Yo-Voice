import unittest
from unittest import mock

from yo.compute import choose_device, cpu_model_kwargs, cpu_thread_count, has_nvidia_name


class ChooseDeviceTests(unittest.TestCase):
    def test_auto_without_nvidia_is_cpu(self):
        self.assertEqual(choose_device("auto", 0), "cpu")

    def test_auto_with_nvidia_is_cuda(self):
        self.assertEqual(choose_device("auto", 1), "cuda")

    def test_forced_cuda_without_device_stays_on_cpu(self):
        self.assertEqual(choose_device("cuda", 0), "cpu")

    def test_forced_cpu_ignores_nvidia(self):
        self.assertEqual(choose_device("cpu", 2), "cpu")


class CpuThreadTests(unittest.TestCase):
    def test_ryzen_7_16_threads_uses_eight_cores(self):
        self.assertEqual(cpu_thread_count(16), 8)

    def test_eight_logical_leaves_two_free(self):
        self.assertEqual(cpu_thread_count(8), 6)

    def test_four_logical_leaves_headroom(self):
        self.assertEqual(cpu_thread_count(4), 2)

    def test_single_core(self):
        self.assertEqual(cpu_thread_count(1), 1)

    def test_cpu_kwargs_keep_one_model_copy(self):
        self.assertEqual(cpu_model_kwargs(16), {"cpu_threads": 8, "num_workers": 1})


class AdapterNameTests(unittest.TestCase):
    def test_radeon_is_not_nvidia(self):
        self.assertFalse(has_nvidia_name(["AMD Radeon 780M Graphics"]))

    def test_geforce_is_nvidia(self):
        self.assertTrue(has_nvidia_name(["NVIDIA GeForce RTX 4070 Ti", "AMD Radeon"]))


class AsrPickTests(unittest.TestCase):
    def test_engine_picks_cpu_when_probe_sees_no_cuda(self):
        from yo.asr import AsrEngine

        engine = AsrEngine(device="auto")
        with mock.patch("yo.asr.cuda_device_count", return_value=0):
            self.assertEqual(engine._pick_device(), "cpu")

    def test_engine_picks_cuda_when_probe_sees_a_device(self):
        from yo.asr import AsrEngine

        engine = AsrEngine(device="auto")
        with mock.patch("yo.asr.cuda_device_count", return_value=1):
            self.assertEqual(engine._pick_device(), "cuda")
