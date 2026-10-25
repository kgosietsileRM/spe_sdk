"""Interactive traffic-spatial CLI for the stand-alone SPE demo.

The script installs and runs from its own virtual environment. It reads media
keys from ``../assets/link.json`` and never imports from the SDK source tree.

Usage::

    .\\run.ps1
    spe_demo sources
    spe_demo use hd
    spe_demo analyze 80
"""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

import core
import cv2

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


class Session:
    """Mutable state for one interactive CLI session."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.links = core.load_links()
        self.source_key: str | None = None
        self.source_path: Path | None = None
        self.info: core.VideoInfo | None = None
        self.rows = args.rows
        self.columns = args.columns
        self.mode = args.mode
        self.url = args.url
        self.model = args.model
        self.confidence = args.confidence
        self.sample_fps = args.fps
        self.max_frames = args.frames
        self.last: core.AnalysisResult | None = None
        self.last_overlay: Any = None

    def choose(self, key: str) -> None:
        self.source_path = core.resolve_media(key, self.links)
        self.info = core.probe(self.source_path)
        self.source_key = key
        print(
            f"{key}: {self.source_path.name} "
            f"({self.info.width}x{self.info.height}, {self.info.fps:.2f} fps, "
            f"{self.info.total_frames} frames)"
        )

    def analyze(self) -> core.AnalysisResult:
        if self.source_path is None:
            raise RuntimeError("Select a source first: use <key>")
        if self.info is None:
            self.info = core.probe(self.source_path)

        def keep_overlay(
            _frame_index: int,
            annotated: Any,
            _spatial: list[dict[str, Any]],
            _occupancy: dict[str, Any],
            _lanes: dict[str, Any],
        ) -> None:
            self.last_overlay = annotated

        print(
            f"analyzing {self.source_key} in {self.mode} mode, "
            f"{self.max_frames} frames at {self.sample_fps:g} fps..."
        )
        result = core.analyze(
            self.source_path,
            mode=self.mode,
            max_frames=self.max_frames,
            sample_fps=self.sample_fps,
            rows=self.rows,
            columns=self.columns,
            url=self.url,
            model=self.model,
            confidence=self.confidence,
            on_frame=keep_overlay,
        )
        self.last = result
        print_summary(result.report)
        return result


def print_summary(report: dict[str, Any]) -> None:
    source = report["source"]
    print(f"\nsource     : {Path(source['path']).name} ({source['width']}x{source['height']})")
    print(f"mode       : {report['mode']}   sampled: {report['sampled_frames']} frames")
    occupancy = report["occupancy"]
    print(f"active     : {occupancy['active_tracks']} tracked object(s)")
    print(f"{'lane':<6}{'queue':>7}{'occupied':>10}{'crossings':>11}")
    print("-" * 34)
    for lane, stats in report["lanes"].items():
        print(f"{lane:<6}{stats['queue']:>7}{stats['occupancy']:>10}{stats['crossings']:>11}")
    zones = occupancy["zones"]
    if zones:
        busiest = max(zones.items(), key=lambda item: item[1]["occupancy"])
        print(f"busiest    : {busiest[0]} ({busiest[1]['occupancy']} object(s))")
    print(f"tracks     : {len(report['tracks'])}")


def command_sources(session: Session) -> None:
    print("available media keys from assets/link.json:")
    for key, value in session.links.items():
        remote = value.startswith(("http://", "https://"))
        suffix = "remote" if remote else value
        print(f"  {key:<8} {suffix}")


def command_info(session: Session) -> None:
    if session.source_path is None:
        print("no source selected")
        return
    print(json.dumps(core.probe(session.source_path).to_dict(), indent=2))


def command_report(session: Session, argument: str) -> None:
    if session.last is None:
        print("run analyze first")
        return
    target = Path(argument) if argument else OUTPUT_DIR / "report.json"
    core.save_report(session.last.report, target)
    print(f"wrote {target}")


def command_overlay(session: Session, argument: str) -> None:
    if session.last is None or session.last_overlay is None:
        print("run analyze first")
        return
    target = Path(argument) if argument else OUTPUT_DIR / "overlay.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), session.last_overlay):
        print(f"could not write {target}")
        return
    print(f"wrote {target}")


def print_help() -> None:
    print(
        "\ncommands:\n"
        "  sources                     list media keys\n"
        "  use <key>                   select media (hd, fullHd, online, ...)\n"
        "  info                        show source metadata\n"
        "  grid <rows> <columns>       change the calibrated grid\n"
        "  mode <local|server>         switch detection backend\n"
        "  server <url> [model]        configure the SPE server\n"
        "  analyze [frames] [fps]      run the analytics pipeline\n"
        "  report [path]               save the last report as JSON\n"
        "  overlay [path]              save the last annotated frame\n"
        "  help                        show this help\n"
        "  quit                        exit\n"
    )


def run_command(session: Session, line: str) -> bool:
    parts = [part.strip("'\"") for part in shlex.split(line, posix=False)]
    if not parts:
        return True
    command, arguments = parts[0].lower(), parts[1:]
    if command in {"quit", "exit"}:
        return False
    if command in {"help", "?"}:
        print_help()
    elif command == "sources":
        command_sources(session)
    elif command == "use":
        if not arguments:
            print("usage: use <key>")
        else:
            session.choose(arguments[0])
    elif command == "info":
        command_info(session)
    elif command == "grid":
        if len(arguments) != 2:
            print("usage: grid <rows> <columns>")
        else:
            session.rows, session.columns = int(arguments[0]), int(arguments[1])
            print(f"grid set to {session.rows}x{session.columns}")
    elif command == "mode":
        if not arguments or arguments[0] not in {"local", "server"}:
            print("usage: mode <local|server>")
        else:
            session.mode = arguments[0]
            print(f"detection mode: {session.mode}")
    elif command == "server":
        if not arguments:
            print("usage: server <url> [model]")
        else:
            session.url = arguments[0]
            if len(arguments) > 1:
                session.model = arguments[1]
            print(f"server: {session.url} model={session.model}")
    elif command == "analyze":
        if arguments:
            session.max_frames = int(arguments[0])
        if len(arguments) > 1:
            session.sample_fps = float(arguments[1])
        try:
            session.analyze()
        except Exception as error:
            print(f"analysis failed: {error}")
    elif command == "report":
        command_report(session, arguments[0] if arguments else "")
    elif command == "overlay":
        command_overlay(session, arguments[0] if arguments else "")
    else:
        print(f"unknown command {command!r}; type help")
    return True


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Media key to select at startup.")
    parser.add_argument("--mode", choices=("local", "server"), default="local")
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--model", default="model-a")
    parser.add_argument("--confidence", type=float, default=0.4)
    parser.add_argument("--rows", type=int, default=core.DEFAULT_ROWS)
    parser.add_argument("--columns", type=int, default=core.DEFAULT_COLUMNS)
    parser.add_argument("--frames", type=int, default=80)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("commands", nargs="*", help="Optional commands to run before the prompt.")
    return parser.parse_known_args()


COMMANDS = {
    "sources",
    "use",
    "info",
    "grid",
    "mode",
    "server",
    "analyze",
    "report",
    "overlay",
    "help",
    "?",
    "quit",
    "exit",
}


def split_commands(tokens: list[str]) -> list[str]:
    """Group scripted tokens into command lines at known command words."""
    groups: list[str] = []
    current: list[str] = []
    for token in tokens:
        if token.lower() in COMMANDS and current:
            groups.append(" ".join(current))
            current = [token]
        else:
            current.append(token)
    if current:
        groups.append(" ".join(current))
    return groups


def main() -> int:
    args, unknown = parse_args()
    session = Session(args)
    if args.source:
        session.choose(args.source)
    scripted = [*args.commands, *unknown]
    if scripted:
        for line in split_commands(scripted):
            if not run_command(session, line):
                break
        return 0
    print("SPE traffic CLI - type 'help' for commands")
    while True:
        try:
            line = input("spe> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            if not run_command(session, line):
                break
        except (KeyError, ValueError, RuntimeError) as error:
            print(f"error: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
