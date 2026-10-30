"""Command line: ``pupilread run``, ``pupilread prepare``, ``pupilread example``, ``pupilread config``, ``pupilread scripts``, ``pupilread guide``."""
from __future__ import annotations

import argparse
import os
import shutil
import sys


def main(argv=None) -> int:
    from . import __version__
    p = argparse.ArgumentParser(prog="pupilread", description="Pupillometry preprocessing for passage reading.")
    p.add_argument("--version", action="version", version=f"pupilread {__version__}")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run the whole pipeline and write the files for R")
    r.add_argument("path", nargs="?", default=None, help="sample report or folder of reports (omit with --cache)")
    r.add_argument("--config", help="YAML or JSON settings (default: the paper's primary choices)")
    r.add_argument("--out", help="output folder (default: pupilread_output next to the data)")
    r.add_argument("--cache", help="folder for per-reader prepared data (resumable)")
    pr_ = sub.add_parser("prepare", help="prepare every reader (stages 3.1-3.2) into a cache folder")
    pr_.add_argument("path")
    pr_.add_argument("--cache", required=True)
    pr_.add_argument("--config")
    ex = sub.add_parser("example", help="write synthetic example data")
    ex.add_argument("folder", nargs="?", default="pupilread_example")
    ex.add_argument("--readers", type=int, default=3)
    ex.add_argument("--items", type=int, default=4)
    sub.add_parser("config", help="print the default settings as YAML")
    sc = sub.add_parser("scripts", help="copy lmm.R, gamm.R and multiverse.R into a folder")
    sc.add_argument("folder", nargs="?", default=".")
    gd = sub.add_parser("guide", help="explain the functions of Table 1 in plain language")
    gd.add_argument("topic", nargs="?", default=None, help='a stage ("3.3") or a function ("baseline")')
    a = p.parse_args(argv)
    if a.cmd == "run":
        from .pipeline import run_pipeline
        run_pipeline(a.path, a.config, out=a.out, cache=a.cache)
    elif a.cmd == "prepare":
        from .pipeline import prepare_readers
        prepare_readers(a.path, a.config, cache=a.cache)
    elif a.cmd == "example":
        from .example import make_example
        info = make_example(a.folder, n_readers=a.readers, n_items=a.items)
        print(f"example data in {info['folder']} (design: {info['design']})")
    elif a.cmd == "config":
        from .pipeline import default_config_yaml
        sys.stdout.write(default_config_yaml())
    elif a.cmd == "scripts":
        from .export import R_SCRIPTS, r_script_path
        os.makedirs(a.folder, exist_ok=True)
        for s in R_SCRIPTS:
            shutil.copyfile(r_script_path(s), os.path.join(a.folder, s))
        print(f"copied {', '.join(R_SCRIPTS)} to {a.folder}")
    elif a.cmd == "guide":
        from .guide import guide
        guide(a.topic)
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
