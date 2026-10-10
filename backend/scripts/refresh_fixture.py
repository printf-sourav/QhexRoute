from __future__ import annotations

import argparse

from backend.app.graph.osm_refresh import refresh_fixture


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh a local Q-HexRoute GraphML fixture with OSMnx.")
    parser.add_argument("place", help="Place query understood by OSMnx, for example 'Bengaluru, Karnataka, India'")
    parser.add_argument("output", help="Destination GraphML path")
    parser.add_argument("--dist", type=int, default=1500, help="Street network radius in metres")
    args = parser.parse_args()
    print(refresh_fixture(args.place, args.output, args.dist))


if __name__ == "__main__":
    main()
