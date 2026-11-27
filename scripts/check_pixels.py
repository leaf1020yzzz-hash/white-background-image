#!/usr/bin/env python3
"""Verify opaque white backgrounds and registered protected pixels."""

import argparse
import json
import sys

from PIL import Image, ImageChops, ImageOps


def open_registered_image(path):
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image)


def load_mask(path, size):
    with Image.open(path) as image:
        if image.size != size or image.mode not in ("1", "L"):
            raise ValueError(f"{path}: use a same-size binary grayscale mask")
        mask = image.convert("L")
    counts = mask.histogram()
    if sum(counts[1:255]) or not counts[255]:
        raise ValueError(f"{path}: use only 0 and 255, with at least one selected pixel")
    return mask


def count_different(image, reference, mask):
    red, green, blue = ImageChops.difference(image, reference).split()
    difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return sum(ImageChops.multiply(difference, mask).histogram()[1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="final product image")
    parser.add_argument("--size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--background-mask", help="white selects known background")
    parser.add_argument("--baseline", help="same-canvas original or approved image")
    parser.add_argument("--lock-mask", help="white selects protected pixels")
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.lock_mask):
        parser.error("--baseline and --lock-mask must be used together")

    try:
        image = open_registered_image(args.image)
        rgba = image.convert("RGBA")
        rgb = rgba.convert("RGB")
        width, height = image.size
        corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))
        white = (255, 255, 255)
        result = {
            "size": image.size,
            "opaque": rgba.getchannel("A").getextrema() == (255, 255),
            "white_corners": all(rgb.getpixel(point) == white for point in corners),
        }
        passed = result["opaque"] and result["white_corners"]
        if args.size:
            result["size_matches"] = image.size == tuple(args.size)
            passed &= result["size_matches"]
        if args.background_mask:
            mask = load_mask(args.background_mask, image.size)
            result["nonwhite_background_pixels"] = count_different(
                rgb, Image.new("RGB", image.size, white), mask
            )
            passed &= result["nonwhite_background_pixels"] == 0
        if args.baseline:
            baseline = open_registered_image(args.baseline)
            if baseline.size != image.size:
                raise ValueError("baseline and result must have the same registered size")
            mask = load_mask(args.lock_mask, image.size)
            result["icc_profiles_match"] = (
                baseline.info.get("icc_profile") == image.info.get("icc_profile")
            )
            result["changed_protected_rgb_pixels"] = count_different(
                rgb, baseline.convert("RGB"), mask
            )
            passed &= result["icc_profiles_match"] and result["changed_protected_rgb_pixels"] == 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"Cannot verify pixels: {error}\n")

    result["passed"] = passed
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
