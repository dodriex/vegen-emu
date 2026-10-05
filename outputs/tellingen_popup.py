#!/usr/bin/env python3
"""Live popup for swipe counts.

Reads only veegtellingen.json from this output directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import ttk


TOTALS = Path(__file__).resolve().with_name("veegtellingen.json")
RESET_REQUEST = Path(__file__).resolve().with_name("reset_tellingen.request")
SWIPE_LOOP = Path(__file__).resolve().parent.parent / "work" / "swipe_loop.py"
REFRESH_MS = 1000


def read_totals() -> dict[str, object]:
    with TOTALS.open() as handle:
        return json.load(handle)


def write_totals(data: dict[str, object]) -> None:
    temporary = TOTALS.with_suffix(".tmp")
    with temporary.open("w") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(TOTALS)


def format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def left_percentage(left: object, total: object) -> str:
    try:
        left_number = int(left)
        total_number = int(total)
    except (TypeError, ValueError):
        return "-"
    if total_number <= 0:
        return "0.0%"
    return f"{left_number / total_number * 100:.1f}%"


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )


def systemd_run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemd-run", "--user", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )


def service_names() -> list[str]:
    result = systemctl("list-units", "--type=service", "--all", "--no-legend", "--no-pager")
    names = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            names.append(parts[0])
    return names


def find_emulator_service() -> str | None:
    for name in service_names():
        if "android-emulator" in name and name.endswith(".service"):
            return name
    return None


def swipe_service_from_emulator(emulator_service: str) -> str:
    suffix = emulator_service.removeprefix("android-emulator-")
    return f"android-swipe-{suffix}"


def find_swipe_service() -> str | None:
    names = service_names()
    for name in names:
        if name.startswith("android-swipe-") and name.endswith(".service"):
            return name
    emulator_service = find_emulator_service()
    if emulator_service:
        return swipe_service_from_emulator(emulator_service)
    return None


def is_service_active(service: str | None) -> bool:
    if not service:
        return False
    return systemctl("is-active", service, check=False).stdout.strip() == "active"


def start_swipe_service() -> str:
    service = find_swipe_service()
    emulator_service = find_emulator_service()
    if service and is_service_active(service):
        return f"Loopt al: {service}"
    if service:
        started = systemctl("start", service, check=False)
        if started.returncode == 0:
            return f"Gestart: {service}"
    if not emulator_service:
        raise RuntimeError("Geen user-service met android-emulator gevonden.")
    service = swipe_service_from_emulator(emulator_service)
    unit = service.removesuffix(".service")
    systemd_run(
        f"--unit={unit}",
        "--description=Android swipes with live counts",
        f"--property=BindsTo={emulator_service}",
        f"--property=After={emulator_service}",
        f"--property=PartOf={emulator_service}",
        "--property=Restart=no",
        "--property=KillMode=mixed",
        "--property=TimeoutStopSec=7",
        "/usr/bin/python3",
        "-u",
        str(SWIPE_LOOP),
    )
    return f"Gestart: {service}"


def stop_swipe_service() -> str:
    service = find_swipe_service()
    if not service:
        raise RuntimeError("Geen swipe-service gevonden.")
    stopped = systemctl("stop", service, check=False)
    if stopped.returncode != 0:
        message = stopped.stderr.strip() or stopped.stdout.strip() or "Onbekende systemctl-fout."
        raise RuntimeError(message)
    return f"Gestopt: {service}"


class CountsPopup:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Veegtellingen live")
        self.root.geometry("420x380")
        self.root.minsize(380, 340)
        self.root.attributes("-topmost", True)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("Count.TLabel", font=("TkDefaultFont", 30, "bold"))
        style.configure("Label.TLabel", font=("TkDefaultFont", 11))
        style.configure("Status.TLabel", font=("TkDefaultFont", 9))

        outer = ttk.Frame(root, padding=18)
        outer.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer.columnconfigure((0, 1), weight=1)

        ttk.Label(outer, text="Live veegtellingen", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        self.left_var = tk.StringVar(value="-")
        self.right_var = tk.StringVar(value="-")
        self.total_var = tk.StringVar(value="-")
        self.left_percent_var = tk.StringVar(value="-")
        self.service_var = tk.StringVar(value="Service: zoeken...")
        self.updated_var = tk.StringVar(value="Bijgewerkt: -")
        self.status_var = tk.StringVar(value="Wachten op tellingen...")

        self._count_block(outer, "Links", self.left_var, 1, 0)
        self._count_block(outer, "Rechts", self.right_var, 1, 1)

        ttk.Separator(outer).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 10))
        ttk.Label(outer, textvariable=self.total_var, style="Count.TLabel").grid(
            row=4, column=0, sticky="w"
        )
        ttk.Label(outer, text="Totaal succesvol", style="Label.TLabel").grid(
            row=4, column=1, sticky="e"
        )
        ttk.Separator(outer).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 10))
        ttk.Label(outer, textvariable=self.left_percent_var, style="Count.TLabel").grid(
            row=6, column=0, sticky="w"
        )
        ttk.Label(outer, text="Percentage links", style="Label.TLabel").grid(
            row=6, column=1, sticky="e"
        )
        controls = ttk.Frame(outer)
        controls.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        controls.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(controls, text="Start", command=self.start_service).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(controls, text="Stop", command=self.stop_service).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(controls, text="Reset", command=self.reset_counts).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )
        ttk.Label(outer, textvariable=self.service_var, style="Status.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )
        ttk.Label(outer, textvariable=self.updated_var, style="Status.TLabel").grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        self.refresh()

    def _count_block(self, parent: ttk.Frame, label: str, var: tk.StringVar, row: int, col: int) -> None:
        frame = ttk.Frame(parent, padding=(0, 18, 0, 0))
        frame.grid(row=row, column=col, sticky="nsew")
        ttk.Label(frame, textvariable=var, style="Count.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=label, style="Label.TLabel").grid(row=1, column=0, sticky="w")

    def refresh(self) -> None:
        try:
            data = read_totals()
        except (OSError, json.JSONDecodeError) as error:
            self.status_var.set(f"Kan tellingen nog niet lezen: {error}")
        else:
            left = data.get("succesvol_links")
            right = data.get("succesvol_rechts")
            total = data.get("succesvol_totaal")
            updated = data.get("bijgewerkt_utc")

            self.left_var.set(format_value(left))
            self.right_var.set(format_value(right))
            self.total_var.set(format_value(total))
            self.left_percent_var.set(left_percentage(left, total))
            self.updated_var.set(f"Bijgewerkt: {format_value(updated)}")
            self.status_var.set("Live aan het volgen")
        self.refresh_service_status()

        self.root.after(REFRESH_MS, self.refresh)

    def refresh_service_status(self) -> None:
        try:
            service = find_swipe_service()
            active = is_service_active(service)
        except (subprocess.SubprocessError, OSError) as error:
            self.service_var.set(f"Service: onbekend ({error})")
            return
        if not service:
            self.service_var.set("Service: geen android-emulator gevonden")
            return
        state = "actief" if active else "gestopt"
        self.service_var.set(f"Service: {state} ({service})")

    def start_service(self) -> None:
        try:
            message = start_swipe_service()
        except (RuntimeError, subprocess.SubprocessError, OSError) as error:
            self.status_var.set(f"Start mislukt: {error}")
            self.refresh_service_status()
            return
        self.status_var.set(message)
        self.refresh_service_status()

    def stop_service(self) -> None:
        try:
            message = stop_swipe_service()
        except (RuntimeError, subprocess.SubprocessError, OSError) as error:
            self.status_var.set(f"Stop mislukt: {error}")
            self.refresh_service_status()
            return
        self.status_var.set(message)
        self.refresh_service_status()

    def reset_counts(self) -> None:
        try:
            data = read_totals()
        except (OSError, json.JSONDecodeError):
            data = {}
        data["succesvol_links"] = 0
        data["succesvol_rechts"] = 0
        data["succesvol_totaal"] = 0
        data["bijgewerkt_utc"] = "reset aangevraagd"
        data["reset_status"] = "De service zet zijn interne tellers bij de volgende cyclus op nul."
        try:
            write_totals(data)
            RESET_REQUEST.write_text("reset\n")
        except OSError as error:
            self.status_var.set(f"Reset mislukt: {error}")
            return
        self.left_var.set("0")
        self.right_var.set("0")
        self.total_var.set("0")
        self.left_percent_var.set("0.0%")
        self.updated_var.set("Bijgewerkt: reset aangevraagd")
        self.status_var.set("Reset aangevraagd")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a live popup with swipe counts.")
    parser.add_argument("--once", action="store_true", help="Print the current counts and exit.")
    args = parser.parse_args()

    if args.once:
        data = read_totals()
        print(
            f"links={data.get('succesvol_links')} "
            f"rechts={data.get('succesvol_rechts')} "
            f"totaal={data.get('succesvol_totaal')} "
            f"links_pct={left_percentage(data.get('succesvol_links'), data.get('succesvol_totaal'))}"
        )
        return 0

    root = tk.Tk()
    CountsPopup(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
