"""
ml/train_detector.py
Fine-tune YOLOv8 on a Nepal-specific vehicle dataset.

Dataset expected at: ./data/vehicles/
Structure (YOLO format):
  data/vehicles/
    images/train/   *.jpg
    images/val/     *.jpg
    labels/train/   *.txt
    labels/val/     *.txt
    data.yaml

Classes: car, motorcycle, bus, microbus, truck, van, tractor, rickshaw, plate

Usage:
  python -m ml.train_detector [--epochs 50] [--imgsz 640] [--batch 16]
"""
import argparse
import os
import yaml
from pathlib import Path


CLASSES = ["car", "motorcycle", "bus", "microbus", "truck", "van", "tractor", "rickshaw", "plate"]

DATA_DIR   = Path("./data/vehicles")
MODELS_DIR = Path("./models")


def create_data_yaml():
    """Create data.yaml for YOLO training if it doesn't exist."""
    yaml_path = DATA_DIR / "data.yaml"
    if not yaml_path.exists():
        config = {
            "path":  str(DATA_DIR.resolve()),
            "train": "images/train",
            "val":   "images/val",
            "nc":    len(CLASSES),
            "names": CLASSES,
        }
        yaml_path.write_text(yaml.dump(config, default_flow_style=False))
        print(f"Created {yaml_path}")
    return str(yaml_path)


def train(epochs: int = 50, imgsz: int = 640, batch: int = 16, device: str = "cpu"):
    from ultralytics import YOLO

    MODELS_DIR.mkdir(exist_ok=True)

    yaml_path = create_data_yaml()

    print(f"Loading base model yolov8n.pt ...")
    model = YOLO("yolov8n.pt")

    print(f"Starting training: epochs={epochs}, imgsz={imgsz}, batch={batch}, device={device}")
    results = model.train(
        data=yaml_path,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project="./runs/detect",
        name="nepal_vehicles",
        augment=True,
        degrees=5.0,       # rotation ±5°
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        hsv_v=0.4,         # brightness
        blur=0.01,
        save=True,
        exist_ok=True,
    )

    # Copy best model
    best_path = Path("./runs/detect/nepal_vehicles/weights/best.pt")
    if best_path.exists():
        import shutil
        dest = MODELS_DIR / "vehicle_detector.pt"
        shutil.copy(best_path, dest)
        print(f"Best model saved to {dest}")

    # Print mAP50
    val_results = model.val()
    map50 = val_results.box.map50
    print(f"\n{'='*40}")
    print(f"Training complete. mAP50 = {map50:.4f}")
    print(f"{'='*40}")
    return map50


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLOv8 vehicle detector")
    parser.add_argument("--epochs",  type=int, default=50)
    parser.add_argument("--imgsz",   type=int, default=640)
    parser.add_argument("--batch",   type=int, default=16)
    parser.add_argument("--device",  default="cpu", help="cpu / 0 / 0,1")
    args = parser.parse_args()

    train(epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device)
