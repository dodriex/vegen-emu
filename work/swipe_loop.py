#!/usr/bin/env python3
"""Perform only timed touch gestures; do not read emulator screen content."""
import csv
import io
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone

from PIL import Image

ADB_CANDIDATES = [
    os.environ.get("VEGEN_EMU_ADB"),
    "adb",
    str(Path.home() / "Android" / "Sdk" / "platform-tools" / "adb"),
    str(Path.home() / "android" / "sdk" / "platform-tools" / "adb"),
    "/opt/android-sdk/platform-tools/adb",
    "/usr/lib/android-sdk/platform-tools/adb",
    "/home/micahboy/Documents/Codex/2026-09-10/vo/work/android/sdk/platform-tools/adb",
]
ADB = ""
ADB_HOST = os.environ.get("VEGEN_EMU_ADB_HOST", "127.0.0.1")
ADB_PORT = os.environ.get("VEGEN_EMU_ADB_PORT", "5038")
ADB_SERIAL = os.environ.get("VEGEN_EMU_ADB_SERIAL", "emulator-5554")
OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"
EVENTS = OUTPUTS / "veeglog.csv"
TOTALS = OUTPUTS / "veegtellingen.json"
RESET_REQUEST = OUTPUTS / "reset_tellingen.request"
FIELDS = ["tijd_utc", "richting", "resultaat", "links_totaal", "rechts_totaal",
          "interval_seconden", "kans_links", "start_monotonic"]
stopped = threading.Event()

SCREEN_HEIGHT = 2400
SCROLL_X = 540
SCROLL_TOP_MARGIN = 300
SCROLL_BOTTOM_MARGIN = 300
SCROLL_DURATION_MS = 504
SCROLL_PAUSE_SECONDS = 0.1
SCROLLS_TO_BOTTOM = [4, 6]
SCROLLS_TO_TOP = [4, 6]
WAIT_AFTER_SWIPE_SECONDS = [0.5, 0.75]
HORIZONTAL_Y = 1200
HORIZONTAL_DURATION_MS = 450
SCREEN_CHANGE_WAIT_SECONDS = 1.0
SCREEN_SAMPLE_SIZE = (72, 128)
SCREEN_PIXEL_DELTA = 80
SCREEN_CHANGE_THRESHOLD = 0.12
SCROLL_MOVE_THRESHOLD = 0.02


def stop(_signum, _frame):
    stopped.set()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def find_adb():
    for candidate in ADB_CANDIDATES:
        if not candidate:
            continue
        try:
            subprocess.run(
                [candidate, "version"],
                check=True,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        return candidate
    raise RuntimeError(
        "adb niet gevonden. Zet adb in PATH of stel VEGEN_EMU_ADB in naar platform-tools/adb."
    )


def adb_command(*args):
    return [ADB, "-H", ADB_HOST, "-P", ADB_PORT, "-s", ADB_SERIAL, *args]


def save_totals(left, right):
    data = {
        "bijgewerkt_utc": timestamp(),
        "succesvol_links": left,
        "succesvol_rechts": right,
        "succesvol_totaal": left + right,
        "kans_links_procent": [5, 6],
        "cyclus": "Na elke horizontale veeg 0.5-0.75 seconden wachten, eerst terug naar boven, daarna omlaag scrollen tot de bodemdetectie geen beweging meer ziet, daarna direct de volgende horizontale veeg.",
        "wachttijd_na_veeg_seconden": WAIT_AFTER_SWIPE_SECONDS,
        "scrolls_omhoog_per_cyclus": SCROLLS_TO_TOP,
        "scrolls_omlaag_per_cyclus": SCROLLS_TO_BOTTOM,
        "scroll_duur_ms": SCROLL_DURATION_MS,
        "scroll_bodem_drempel": SCROLL_MOVE_THRESHOLD,
        "schermwissel_controle": "Na de horizontale veeg wordt alleen een tijdelijke schermafdruk in geheugen vergeleken met een grove pixeldrempel; screenshots worden niet opgeslagen of bekeken.",
        "schermwissel_drempel": SCREEN_CHANGE_THRESHOLD,
        "adb_serial": ADB_SERIAL,
        "betekenis_succes": "ADB-veegopdracht voltooid met exitcode 0 en genoeg tijdelijke schermpixels veranderden na de horizontale veeg.",
    }
    temporary = TOTALS.with_suffix(".tmp")
    with temporary.open("w") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(TOTALS)


def append_event(left, right, direction, result, interval="", probability="", started=""):
    new_file = not EVENTS.exists()
    with EVENTS.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(FIELDS)
        writer.writerow([timestamp(), direction, result, left, right, interval, probability, started])
        handle.flush()
        os.fsync(handle.fileno())
    save_totals(left, right)


def load_totals():
    left = right = 0
    if EVENTS.exists():
        with EVENTS.open(newline="") as handle:
            for row in csv.DictReader(handle):
                left, right = int(row["links_totaal"]), int(row["rechts_totaal"])
    return left, right


def apply_pending_reset(left, right):
    if not RESET_REQUEST.exists():
        return left, right
    try:
        RESET_REQUEST.unlink()
    except FileNotFoundError:
        pass
    left = right = 0
    append_event(left, right, "reset", "succes", "", "", time.monotonic())
    print("counts_reset=succes left=0 right=0", flush=True)
    return left, right


def screen_sample():
    capture = subprocess.run(
        adb_command("exec-out", "screencap", "-p"),
        check=True, timeout=5, stdout=subprocess.PIPE,
    )
    with Image.open(io.BytesIO(capture.stdout)) as image:
        image = image.convert("RGB").resize(SCREEN_SAMPLE_SIZE)
        return image.tobytes()


def screen_change_ratio(before, after):
    changed = 0
    pixels = len(before) // 3
    for index in range(0, len(before), 3):
        delta = (
            abs(before[index] - after[index])
            + abs(before[index + 1] - after[index + 1])
            + abs(before[index + 2] - after[index + 2])
        )
        if delta >= SCREEN_PIXEL_DELTA:
            changed += 1
    return changed / pixels


def main():
    global ADB
    ADB = find_adb()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    OUTPUTS.mkdir(exist_ok=True)
    left, right = load_totals()
    left, right = apply_pending_reset(left, right)
    save_totals(left, right)
    wait_after_swipe = 0
    print(
        f"Started: after each swipe wait 0.5-0.75 seconds, reset upward, scroll down, then swipe; "
        f"left chance 5-6%; left={left} right={right}; adb={ADB}",
        flush=True,
    )
    while not stopped.is_set():
        if wait_after_swipe and stopped.wait(wait_after_swipe):
            break
        left, right = apply_pending_reset(left, right)
        probability = random.uniform(0.05, 0.06)
        direction = "links" if random.random() < probability else "rechts"
        wait_after_swipe = random.uniform(*WAIT_AFTER_SWIPE_SECONDS)
        x1, x2 = (900, 220) if direction == "links" else (220, 900)
        reset_count = random.randint(*SCROLLS_TO_TOP)
        scroll_count = random.randint(*SCROLLS_TO_BOTTOM)
        scroll_start_y = SCREEN_HEIGHT - SCROLL_BOTTOM_MARGIN
        scroll_end_y = SCROLL_TOP_MARGIN
        reset_start_y = SCROLL_TOP_MARGIN
        reset_end_y = SCREEN_HEIGHT - SCROLL_BOTTOM_MARGIN
        scroll_started = time.monotonic()
        try:
            for reset_number in range(reset_count):
                if stopped.is_set():
                    break
                subprocess.run(
                    adb_command(
                        "shell", "input", "touchscreen", "swipe", str(SCROLL_X), str(reset_start_y),
                        str(SCROLL_X), str(reset_end_y), str(SCROLL_DURATION_MS)
                    ),
                    check=True, timeout=5,
                )
                if reset_number + 1 < reset_count and stopped.wait(SCROLL_PAUSE_SECONDS):
                    break
            if stopped.is_set():
                break
            bottom_detected = False
            down_scrolls_done = 0
            last_scroll_change_ratio = None
            for scroll_number in range(scroll_count):
                if stopped.is_set():
                    break
                before_scroll_sample = screen_sample()
                subprocess.run(
                    adb_command(
                        "shell", "input", "touchscreen", "swipe", str(SCROLL_X), str(scroll_start_y),
                        str(SCROLL_X), str(scroll_end_y), str(SCROLL_DURATION_MS)
                    ),
                    check=True, timeout=5,
                )
                down_scrolls_done = scroll_number + 1
                after_scroll_sample = screen_sample()
                last_scroll_change_ratio = screen_change_ratio(before_scroll_sample, after_scroll_sample)
                if last_scroll_change_ratio < SCROLL_MOVE_THRESHOLD:
                    bottom_detected = True
                    break
                if scroll_number + 1 < scroll_count and stopped.wait(SCROLL_PAUSE_SECONDS):
                    break
            if stopped.is_set():
                break
            print(
                f"reset_up_repeated={reset_count} scroll_down_done={down_scrolls_done} "
                f"scroll_down_limit={scroll_count} bottom_detected={int(bottom_detected)} "
                f"last_scroll_change_ratio={last_scroll_change_ratio if last_scroll_change_ratio is not None else -1:.3f} "
                f"duration_ms={SCROLL_DURATION_MS} "
                f"planned_direction={direction} scroll_start={scroll_started:.3f}",
                flush=True,
            )
            before_swipe_sample = screen_sample()
            swipe_started = time.monotonic()
            subprocess.run(
                adb_command(
                    "shell", "input", "touchscreen", "swipe", str(x1), str(HORIZONTAL_Y),
                    str(x2), str(HORIZONTAL_Y), str(HORIZONTAL_DURATION_MS)
                ),
                check=True, timeout=5,
            )
            if stopped.wait(SCREEN_CHANGE_WAIT_SECONDS):
                break
            after_swipe_sample = screen_sample()
        except (subprocess.SubprocessError, OSError) as error:
            append_event(left, right, direction, "niet_bevestigd", wait_after_swipe, probability, scroll_started)
            print(f"Stopped after input failure: {error}", flush=True)
            return 1
        change_ratio = screen_change_ratio(before_swipe_sample, after_swipe_sample)
        if change_ratio < SCREEN_CHANGE_THRESHOLD:
            append_event(left, right, direction, "geen_schermwissel", wait_after_swipe, probability, swipe_started)
            print(
                f"direction={direction} not_counted=geen_schermwissel change_ratio={change_ratio:.3f} "
                f"left={left} right={right} "
                f"wait_after_swipe={wait_after_swipe:.3f} swipe_start={swipe_started:.3f}",
                flush=True,
            )
            continue
        left += direction == "links"
        right += direction == "rechts"
        append_event(left, right, direction, "succes", wait_after_swipe, probability, swipe_started)
        print(
            f"direction={direction} left={left} right={right} change_ratio={change_ratio:.3f} "
            f"wait_after_swipe={wait_after_swipe:.3f} swipe_start={swipe_started:.3f}",
            flush=True,
        )
    print(f"Stopped: left={left} right={right}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
