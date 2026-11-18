import argparse, json, sys
from pathlib import Path

from .demo import demo_sequence
from .export import to_payload
from .transcripts import analyze, load_dir, rep_scorecard


def main(argv=None):
    p = argparse.ArgumentParser(prog="salesintel")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze a directory of transcripts")
    a.add_argument("dir", type=Path)
    sub.add_parser("export-sequence", help="print the demo sequence as a modeled JSON payload")
    args = p.parse_args(argv)
    if args.cmd == "analyze":
        results = [analyze(c) for c in load_dir(args.dir)]
        json.dump({"calls": results, "scorecard": rep_scorecard(results)}, sys.stdout, indent=2)
    else:
        json.dump(to_payload(demo_sequence()), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
