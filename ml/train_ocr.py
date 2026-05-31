"""
ml/train_ocr.py
Fine-tune PaddleOCR for Nepal license plates and Devanagari bus route text.

Datasets:
  ./data/plates/      — plate images + label files (format: image_path\\ttext)
  ./data/route_text/  — bus route text images (Devanagari)

Output:
  ./models/plate_ocr/   — fine-tuned plate OCR model
  ./models/route_ocr/   — fine-tuned Devanagari route OCR model

Usage:
  python -m ml.train_ocr [--task plate|route|both] [--epochs 20]
"""
import argparse
import os
import json
from pathlib import Path


MODELS_DIR = Path("./models")
DATA_PLATE  = Path("./data/plates")
DATA_ROUTE  = Path("./data/route_text")


def prepare_label_file(data_dir: Path, output_path: Path):
    """
    Convert a simple TSV label file (image_path\\ttext) to
    PaddleOCR rec training format: image_path\\tjson_encoded_text.
    """
    src = data_dir / "labels.txt"
    if not src.exists():
        print(f"Warning: {src} not found. Creating synthetic label file.")
        # Create a minimal synthetic example
        imgs = list(data_dir.glob("*.jpg")) + list(data_dir.glob("*.png"))
        with open(output_path, "w", encoding="utf-8") as f:
            for img in imgs[:10]:
                f.write(f"{img.name}\t['text']\n")
        return

    with open(src, "r", encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:
        for line in f_in:
            parts = line.strip().split("\t", 1)
            if len(parts) == 2:
                img_path, text = parts
                f_out.write(f"{img_path}\t{json.dumps(text, ensure_ascii=False)}\n")


def train_plate_ocr(epochs: int = 20):
    """Fine-tune PaddleOCR recognition for Nepal plate format."""
    print("=" * 50)
    print("Training PaddleOCR for Nepal license plates")
    print("=" * 50)

    MODELS_DIR.mkdir(exist_ok=True)
    output_dir = MODELS_DIR / "plate_ocr"
    output_dir.mkdir(exist_ok=True)

    label_file = DATA_PLATE / "train_labels.txt"
    prepare_label_file(DATA_PLATE, label_file)

    # PaddleOCR fine-tuning via CLI (uses paddleocr's training pipeline)
    # Characters for Nepal plates: A-Z, a-z, 0-9, space
    char_list = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "

    config = {
        "Global": {
            "use_gpu": False,
            "epoch_num": epochs,
            "log_smooth_window": 20,
            "print_batch_step": 10,
            "save_model_dir": str(output_dir),
            "save_epoch_step": 5,
            "eval_batch_step": [0, 200],
            "cal_metric_during_train": True,
            "pretrained_model": None,
            "checkpoints": None,
            "character_dict_path": None,
            "character_type": "en",
            "max_text_length": 25,
        },
        "Train": {
            "dataset": {
                "name": "SimpleDataSet",
                "data_dir": str(DATA_PLATE),
                "label_file_list": [str(label_file)],
            },
            "loader": {"batch_size_per_card": 64, "num_workers": 4},
        }
    }

    config_path = DATA_PLATE / "plate_ocr_config.yml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Config written to {config_path}")
    print(f"To train: python -m paddle.distributed.launch --gpus '0' tools/train.py -c {config_path}")
    print(f"Output will be saved to: {output_dir}")

    # Without a real dataset we demonstrate the config generation
    print("\nPlate OCR training configuration created.")
    print("Provide images in ./data/plates/ with labels.txt to run full training.")


def train_route_ocr(epochs: int = 20):
    """Fine-tune PaddleOCR for Devanagari bus route text."""
    print("=" * 50)
    print("Training PaddleOCR for Devanagari route text")
    print("=" * 50)

    MODELS_DIR.mkdir(exist_ok=True)
    output_dir = MODELS_DIR / "route_ocr"
    output_dir.mkdir(exist_ok=True)

    label_file = DATA_ROUTE / "train_labels.txt"
    prepare_label_file(DATA_ROUTE, label_file)

    # Devanagari Unicode range: U+0900–U+097F
    devanagari_chars = "".join(chr(c) for c in range(0x0900, 0x0980))
    devanagari_chars += "–-/ "  # separator chars

    config = {
        "Global": {
            "use_gpu": False,
            "epoch_num": epochs,
            "save_model_dir": str(output_dir),
            "character_type": "devanagari",
            "max_text_length": 40,
            "lang": "ne",
        },
        "Train": {
            "dataset": {
                "name": "SimpleDataSet",
                "data_dir": str(DATA_ROUTE),
                "label_file_list": [str(label_file)],
            },
            "loader": {"batch_size_per_card": 32},
        }
    }

    config_path = DATA_ROUTE / "route_ocr_config.yml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Config written to {config_path}")
    print(f"Output will be saved to: {output_dir}")
    print("\nRoute OCR (Devanagari) training configuration created.")
    print("Provide bus front images in ./data/route_text/ with labels.txt to run full training.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PaddleOCR for Nepal")
    parser.add_argument("--task",   choices=["plate", "route", "both"], default="both")
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()

    if args.task in ("plate", "both"):
        train_plate_ocr(epochs=args.epochs)
    if args.task in ("route", "both"):
        train_route_ocr(epochs=args.epochs)
