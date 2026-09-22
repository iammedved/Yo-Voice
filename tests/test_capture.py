import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from yo.capture import (
    NO_MIC_HINT,
    capture_microphone_update,
    has_microphone,
    list_capture_devices,
    listen_capture_plan,
    parse_pactl_sources,
    portaudio_name_at,
    preferred_portaudio_device,
    resolve_portaudio_device,
)


PULSE_USB_HEADSET = """
Source #52
	State: SUSPENDED
	Name: alsa_input.usb-1532_Razer_Barracuda_X.mono-fallback
	Description: Razer Barracuda X Моно
	Monitor of Sink: n/a
	Properties:
		device.class = "sound"
		media.class = "Audio/Source"
		alsa.card = "1"
		alsa.device = "0"
	Ports:
		analog-input-mic: Microphone (type: Mic, priority: 8700, availability unknown)
	Active Port: analog-input-mic
	Formats:
		pcm
"""

PULSE_JACKS_UNPLUGGED = """
Source #54
	State: SUSPENDED
	Name: alsa_input.pci-0000_00_1f.3.analog-stereo
	Description: Built-in Audio Analog Stereo
	Monitor of Sink: n/a
	Properties:
		device.class = "sound"
		media.class = "Audio/Source"
		alsa.card = "0"
		alsa.device = "0"
	Ports:
		analog-input-front-mic: Front Microphone (type: Mic, priority: 8500, availability group: Legacy 1, not available)
		analog-input-rear-mic: Rear Microphone (type: Mic, priority: 8200, availability group: Legacy 2, not available)
		analog-input-linein: Line In (type: Line, priority: 8100, availability group: Legacy 3, not available)
	Active Port: analog-input-front-mic
	Formats:
		pcm
"""

PULSE_ONLY_MONITORS = """
Source #51
	State: SUSPENDED
	Name: alsa_output.usb-headset.analog-stereo.monitor
	Description: Monitor of Headset
	Monitor of Sink: alsa_output.usb-headset.analog-stereo
	Properties:
		device.class = "monitor"
		media.class = "Audio/Sink"
	Ports:
		analog-output: Analog Output (type: Analog, priority: 9900, availability unknown)
	Active Port: analog-output
	Formats:
		pcm
"""

PULSE_USB_PLUS_DEAD_JACK = PULSE_USB_HEADSET + PULSE_JACKS_UNPLUGGED + PULSE_ONLY_MONITORS


class PactlSourceTests(unittest.TestCase):
    def test_usb_headset_counts_as_microphone(self):
        sources = parse_pactl_sources(PULSE_USB_HEADSET)
        self.assertEqual(len(sources), 1)
        self.assertTrue(has_microphone(pactl_text=PULSE_USB_HEADSET))

    def test_unplugged_analog_jacks_are_not_a_microphone(self):
        self.assertFalse(has_microphone(pactl_text=PULSE_JACKS_UNPLUGGED))

    def test_loopback_monitors_are_not_a_microphone(self):
        self.assertFalse(has_microphone(pactl_text=PULSE_ONLY_MONITORS))

    def test_empty_list_is_not_a_microphone(self):
        self.assertFalse(has_microphone(pactl_text=""))

    def test_usb_is_found_even_if_onboard_jacks_are_empty(self):
        self.assertTrue(has_microphone(pactl_text=PULSE_USB_PLUS_DEAD_JACK))


class PortAudioFallbackTests(unittest.TestCase):
    def test_ignores_pipewire_default_and_hdmi(self):
        devices = [
            {"name": "default", "max_input_channels": 64},
            {"name": "pipewire", "max_input_channels": 64},
            {"name": "HDA NVidia: HDMI 0 (hw:0,3)", "max_input_channels": 0},
            {"name": "Monitor of Speakers", "max_input_channels": 2},
        ]
        self.assertFalse(has_microphone(pactl_text=None, devices=devices))

    def test_usb_capture_device_counts(self):
        devices = [
            {"name": "default", "max_input_channels": 64},
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
        ]
        self.assertTrue(has_microphone(pactl_text=None, devices=devices))

    def test_prefers_usb_hw_device_not_pipewire_default(self):
        devices = [
            {"name": "HDA NVidia: HDMI 0 (hw:0,3)", "max_input_channels": 0},
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "HDA Intel PCH: ALC897 Analog (hw:2,0)", "max_input_channels": 2},
            {"name": "pipewire", "max_input_channels": 64},
            {"name": "default", "max_input_channels": 64},
        ]
        self.assertEqual(
            preferred_portaudio_device(pactl_text=PULSE_USB_PLUS_DEAD_JACK, devices=devices),
            1,
        )

    def test_no_usable_source_has_no_preferred_device(self):
        devices = [
            {"name": "pipewire", "max_input_channels": 64},
            {"name": "default", "max_input_channels": 64},
        ]
        self.assertIsNone(
            preferred_portaudio_device(pactl_text=PULSE_JACKS_UNPLUGGED, devices=devices)
        )

    def test_saved_name_selects_headset_not_index(self):
        devices = [
            {"name": "HDA NVidia: HDMI 0 (hw:0,3)", "max_input_channels": 0},
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "HDA Intel PCH: ALC897 Analog (hw:2,0)", "max_input_channels": 2},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        self.assertEqual(
            resolve_portaudio_device(
                "Razer Barracuda X: USB Audio (hw:1,0)",
                pactl_text=PULSE_USB_PLUS_DEAD_JACK,
                devices=devices,
            ),
            1,
        )

    def test_empty_name_falls_back_to_auto(self):
        devices = [
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        self.assertEqual(
            resolve_portaudio_device(
                "",
                pactl_text=PULSE_USB_HEADSET,
                devices=devices,
            ),
            preferred_portaudio_device(pactl_text=PULSE_USB_HEADSET, devices=devices),
        )

    def test_missing_saved_name_falls_back_to_auto(self):
        devices = [
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        self.assertEqual(
            resolve_portaudio_device(
                "USB Headset That Was Unplugged",
                pactl_text=PULSE_USB_HEADSET,
                devices=devices,
            ),
            0,
        )

    def test_list_skips_monitors_and_dead_jacks(self):
        devices = [
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "Monitor of Speakers", "max_input_channels": 2},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        listed = list_capture_devices(pactl_text=PULSE_USB_PLUS_DEAD_JACK, devices=devices)
        names = [item["id"] for item in listed]
        labels = " ".join(item["label"] for item in listed)
        self.assertEqual(names, ["Razer Barracuda X: USB Audio (hw:1,0)"])
        self.assertIn("Razer", labels)
        self.assertNotIn("Monitor of Speakers", names)

    def test_list_hides_pulse_dead_analog_jack(self):
        devices = [
            {"name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
            {"name": "HDA Intel PCH: ALC897 Analog (hw:0,0)", "max_input_channels": 2},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        listed = list_capture_devices(pactl_text=PULSE_USB_PLUS_DEAD_JACK, devices=devices)
        names = [item["id"] for item in listed]
        self.assertEqual(names, ["Razer Barracuda X: USB Audio (hw:1,0)"])
        self.assertNotIn("HDA Intel PCH: ALC897 Analog (hw:0,0)", names)

    def test_saved_name_follows_headset_when_hw_index_moves(self):
        devices = [
            {"name": "HDA NVidia: HDMI 0 (hw:0,3)", "max_input_channels": 0},
            {"name": "Razer Barracuda X: USB Audio (hw:2,0)", "max_input_channels": 1},
            {"name": "pipewire", "max_input_channels": 64},
        ]
        self.assertEqual(
            resolve_portaudio_device(
                "Razer Barracuda X: USB Audio (hw:1,0)",
                pactl_text=PULSE_USB_HEADSET,
                devices=devices,
            ),
            1,
        )

    def test_capture_stores_live_name_not_numeric_index(self):
        devices = [
            {"index": 7, "name": "Razer Barracuda X: USB Audio (hw:1,0)", "max_input_channels": 1},
        ]
        self.assertEqual(portaudio_name_at(7, devices=devices), "Razer Barracuda X: USB Audio (hw:1,0)")
        self.assertEqual(
            capture_microphone_update("", "Razer Barracuda X: USB Audio (hw:1,0)"),
            "Razer Barracuda X: USB Audio (hw:1,0)",
        )
        self.assertIsNone(
            capture_microphone_update(
                "Razer Barracuda X: USB Audio (hw:1,0)",
                "Razer Barracuda X: USB Audio (hw:1,0)",
            )
        )
        self.assertEqual(
            capture_microphone_update(
                "Razer Barracuda X: USB Audio (hw:1,0)",
                "Razer Barracuda X: USB Audio (hw:2,0)",
            ),
            "Razer Barracuda X: USB Audio (hw:2,0)",
        )
        src = (Path(__file__).resolve().parents[1] / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def _start_capture") : src.index("def _sync_mic")]
        self.assertIn("capture_microphone_update", body)

    def test_windows_skips_mapper_mix_and_line_in(self):
        devices = [
            {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi_name": "MME"},
            {"name": "Primary Sound Capture Driver", "max_input_channels": 2, "hostapi_name": "Windows DirectSound"},
            {"name": "Stereo Mix (Realtek HD Audio)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
            {"name": "Line In (Realtek HD Audio)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
            {"name": "Microphone (Realtek High Definition Audio)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
            {"name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "Windows WASAPI"},
        ]
        with patch("yo.capture.sys.platform", "win32"):
            listed = list_capture_devices(pactl_text=None, devices=devices)
        names = [item["id"] for item in listed]
        self.assertIn("Microphone (Realtek High Definition Audio)", names)
        self.assertIn("Микрофон (Razer Barracuda X)", names)
        self.assertNotIn("Microsoft Sound Mapper - Input", names)
        self.assertNotIn("Primary Sound Capture Driver", names)
        self.assertNotIn("Stereo Mix (Realtek HD Audio)", names)
        self.assertNotIn("Line In (Realtek HD Audio)", names)

    def test_candidates_try_wasapi_then_mme_same_name(self):
        from yo.capture import capture_candidate_indices

        devices = [
            {"index": 1, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "MME"},
            {"index": 7, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "Windows DirectSound"},
            {"index": 15, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
        ]
        with patch("yo.capture.sys.platform", "win32"):
            idxs = capture_candidate_indices("", devices=devices)
        self.assertEqual(idxs[0], 15)
        self.assertIn(1, idxs)
        self.assertIn(7, idxs)

    def test_candidates_follow_the_selected_microphone_name(self):
        from yo.capture import capture_candidate_indices

        devices = [
            {"index": 1, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "MME"},
            {"index": 8, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "Windows DirectSound"},
            {"index": 18, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
            {"index": 19, "name": "Микрофон (Realtek HD Audio Mic input)", "max_input_channels": 2, "hostapi_name": "Windows WDM-KS"},
            {"index": 20, "name": "Microphone (Realtek High Definition Audio)", "max_input_channels": 2, "hostapi_name": "Windows WASAPI"},
            {"index": 27, "name": "Микрофон (Razer Barracuda X)", "max_input_channels": 1, "hostapi_name": "Windows WDM-KS"},
        ]
        with patch("yo.capture.sys.platform", "win32"):
            barra = capture_candidate_indices("Микрофон (Razer Barracuda X)", devices=devices)
            realtek = capture_candidate_indices("Микрофон (Realtek HD Audio Mic input)", devices=devices)
            listed = list_capture_devices(pactl_text=None, devices=devices)
        self.assertEqual(barra[0], 18)
        self.assertEqual(barra, [18, 1, 8, 27])
        self.assertNotIn(19, barra)
        self.assertNotIn(20, barra)
        self.assertEqual(realtek, [19])
        names = [item["id"] for item in listed]
        self.assertIn("Микрофон (Razer Barracuda X)", names)
        self.assertIn("Микрофон (Realtek HD Audio Mic input)", names)
        self.assertIn("Microphone (Realtek High Definition Audio)", names)


class ListenPlanTests(unittest.TestCase):
    def test_hint_text_is_exact(self):
        self.assertEqual(NO_MIC_HINT, "подключите микрофон")

    def test_no_mic_skips_capture_and_shows_hint(self):
        plan = listen_capture_plan(False)
        self.assertFalse(plan["start_capture"])
        self.assertTrue(plan["mic_missing"])
        self.assertEqual(plan["hint"], "подключите микрофон")

    def test_mic_present_starts_capture_and_keeps_waves(self):
        plan = listen_capture_plan(True)
        self.assertTrue(plan["start_capture"])
        self.assertFalse(plan["mic_missing"])
        self.assertIsNone(plan["hint"])

    def test_launch_probes_microphone_before_hotkey(self):
        src = (Path(__file__).resolve().parents[1] / "yo" / "app.py").read_text(encoding="utf-8")
        start = src.index("def start_background")
        body = src[start : src.index("def start_listen")]
        self.assertLess(body.index("self._sync_mic()"), body.index("self._restart_hotkey()"))


if __name__ == "__main__":
    unittest.main()
