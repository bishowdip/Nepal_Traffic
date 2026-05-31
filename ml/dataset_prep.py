"""
ml/dataset_prep.py
Dataset preparation utilities for Nepal Traffic AI.

Generates synthetic training data and organizes real images into YOLO format.
"""
import os
import random
import json
from pathlib import Path
from datetime import date, timedelta


DATA_DIR = Path("./data")


def generate_synthetic_plate_images(output_dir: Path, count: int = 200):
    """
    Generate synthetic Nepal license plate images using PIL.
    Useful as a data-augmentation seed before real plates are collected.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow not installed. Skipping synthetic plate generation.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    labels = []

    district_codes = ["Ba", "Ko", "La", "Bha", "Ka", "Chi", "Ra", "Su", "Mo", "Pa"]
    letters = ["Ka", "Kha", "Ga", "Gha", "Cha", "Ja", "Ta", "Da", "Pa", "Ba", "Ma", "Ra", "Sa"]

    for i in range(count):
        dc     = random.choice(district_codes)
        series = random.randint(1, 9)
        letter = random.choice(letters)
        number = random.randint(1, 9999)
        text   = f"{dc} {series} {letter} {str(number).zfill(4)}"

        # White background, black text (standard Nepal plate style)
        img = Image.new("RGB", (280, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw border
        draw.rectangle([2, 2, 277, 77], outline=(0, 0, 0), width=3)

        # Draw text (best effort without custom font)
        draw.text((20, 18), text, fill=(0, 0, 0))

        # Random augmentations
        if random.random() < 0.3:
            from PIL import ImageFilter
            img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.5)))

        filename = f"plate_{i:04d}.jpg"
        img.save(output_dir / filename)
        labels.append(f"{filename}\t{text}")

    label_file = output_dir / "labels.txt"
    label_file.write_text("\n".join(labels), encoding="utf-8")
    print(f"Generated {count} synthetic plate images in {output_dir}")
    print(f"Labels written to {label_file}")


def generate_yolo_dataset_structure():
    """Create the YOLO dataset directory structure."""
    for split in ("train", "val"):
        (DATA_DIR / "vehicles" / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "vehicles" / "labels"  / split).mkdir(parents=True, exist_ok=True)

    readme = DATA_DIR / "vehicles" / "README.txt"
    readme.write_text(
        "Place training images in images/train/ and images/val/\n"
        "Place corresponding YOLO label files in labels/train/ and labels/val/\n\n"
        "YOLO label format (one box per line):\n"
        "  class_id cx cy width height\n"
        "  (all normalized 0-1)\n\n"
        "Class IDs:\n"
        "  0=car 1=motorcycle 2=bus 3=microbus 4=truck 5=van 6=tractor 7=rickshaw 8=plate\n"
    )
    print("YOLO dataset structure created at ./data/vehicles/")


def split_dataset(image_dir: Path, ratio: float = 0.8):
    """
    Split images in image_dir into train/val sets.
    Copies/symlinks to YOLO structure.
    """
    import shutil
    images = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png"))
    random.shuffle(images)
    split_idx = int(len(images) * ratio)
    train_imgs = images[:split_idx]
    val_imgs   = images[split_idx:]

    for split, imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_out = DATA_DIR / "vehicles" / "images" / split
        lbl_out = DATA_DIR / "vehicles" / "labels" / split
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        for img in imgs:
            shutil.copy(img, img_out / img.name)
            label = img.with_suffix(".txt")
            if label.exists():
                shutil.copy(label, lbl_out / label.name)

    print(f"Split: {len(train_imgs)} train, {len(val_imgs)} val")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["synthetic", "structure", "split"], default="structure")
    parser.add_argument("--count",  type=int, default=200, help="Number of synthetic images")
    parser.add_argument("--source", type=str, default="./data/raw", help="Source dir for split")
    args = parser.parse_args()

    if args.action == "synthetic":
        generate_synthetic_plate_images(DATA_DIR / "plates", args.count)
    elif args.action == "structure":
        generate_yolo_dataset_structure()
    elif args.action == "split":
        split_dataset(Path(args.source))
