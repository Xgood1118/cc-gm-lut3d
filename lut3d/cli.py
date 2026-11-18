# -*- coding: utf-8 -*-
import argparse
import json
import lut3d as m


def main():
    ap = argparse.ArgumentParser(description="lut3d")
    ap.add_argument("path")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    lut = m.load_cube(a.path)
    c = m.apply_lut(lut, (0.25, 0.25, 0.25))
    print(json.dumps({"rgb": list(c)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
