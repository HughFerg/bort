#!/usr/bin/env python3
"""
Train YOLOv8 classifier on Simpsons characters.

Usage:
    python train.py                    # Train with defaults
    python train.py --epochs 50        # Custom epochs
    python train.py --resume           # Resume from last checkpoint
"""

import argparse
from pathlib import Path


def train(
    data_dir: str = "data/simpsons_yolo",
    epochs: int = 30,
    batch_size: int = 32,
    img_size: int = 224,
    model_size: str = "n",  # n, s, m, l, x
    resume: bool = False,
    device: str = ""  # auto-detect
):
    """
    Train YOLOv8 classification model.

    Args:
        data_dir: Path to prepared dataset
        epochs: Number of training epochs
        batch_size: Batch size (reduce if OOM)
        img_size: Input image size
        model_size: Model size (n=nano, s=small, m=medium, l=large, x=xlarge)
        resume: Resume from last checkpoint
        device: Device to train on (auto-detect if empty)
    """
    from ultralytics import YOLO

    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {data_path}. "
            "Run prepare_dataset.py first."
        )

    # Load model
    model_name = f"yolov8{model_size}-cls.pt"
    print(f"Loading model: {model_name}")

    if resume:
        # Find last checkpoint
        runs_dir = Path("runs/classify")
        if runs_dir.exists():
            train_dirs = sorted(runs_dir.glob("train*"))
            if train_dirs:
                last_weights = train_dirs[-1] / "weights" / "last.pt"
                if last_weights.exists():
                    print(f"Resuming from: {last_weights}")
                    model = YOLO(str(last_weights))
                else:
                    print("No checkpoint found, starting fresh")
                    model = YOLO(model_name)
            else:
                model = YOLO(model_name)
        else:
            model = YOLO(model_name)
    else:
        model = YOLO(model_name)

    # Train
    print(f"\nTraining on: {data_path}")
    print(f"Epochs: {epochs}, Batch size: {batch_size}, Image size: {img_size}")

    results = model.train(
        data=str(data_path),
        epochs=epochs,
        batch=batch_size,
        imgsz=img_size,
        device=device or None,
        patience=10,  # Early stopping
        save=True,
        plots=True,
        verbose=True
    )

    # Print results
    print("\n" + "=" * 50)
    print("Training complete!")
    print("=" * 50)

    # Find best model
    runs_dir = Path("runs/classify")
    train_dirs = sorted(runs_dir.glob("train*"))
    if train_dirs:
        best_model = train_dirs[-1] / "weights" / "best.pt"
        print(f"\nBest model saved to: {best_model}")
        print(f"\nTo use in your app, copy to:")
        print(f"  cp {best_model} ../models/simpsons_classifier.pt")

    return results


def export_model(model_path: str, format: str = "onnx"):
    """Export trained model to different format."""
    from ultralytics import YOLO

    model = YOLO(model_path)
    model.export(format=format)
    print(f"Exported to {format} format")


def test_model(model_path: str, image_path: str):
    """Test model on a single image."""
    from ultralytics import YOLO

    model = YOLO(model_path)
    results = model(image_path)

    for result in results:
        probs = result.probs
        top5 = probs.top5
        top5_conf = probs.top5conf

        print("\nTop 5 predictions:")
        for idx, conf in zip(top5, top5_conf):
            class_name = result.names[idx]
            print(f"  {class_name}: {conf:.2%}")


def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 Simpsons classifier")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Train command
    train_parser = subparsers.add_parser("train", help="Train model")
    train_parser.add_argument("--data", default="data/simpsons_yolo", help="Dataset directory")
    train_parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    train_parser.add_argument("--batch", type=int, default=32, help="Batch size")
    train_parser.add_argument("--imgsz", type=int, default=224, help="Image size")
    train_parser.add_argument("--model", default="n", choices=["n", "s", "m", "l", "x"], help="Model size")
    train_parser.add_argument("--resume", action="store_true", help="Resume training")
    train_parser.add_argument("--device", default="", help="Device (cpu, 0, mps)")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export model")
    export_parser.add_argument("model", help="Model path")
    export_parser.add_argument("--format", default="onnx", help="Export format")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test model")
    test_parser.add_argument("model", help="Model path")
    test_parser.add_argument("image", help="Image path")

    args = parser.parse_args()

    if args.command == "train" or args.command is None:
        train(
            data_dir=getattr(args, "data", "data/simpsons_yolo"),
            epochs=getattr(args, "epochs", 30),
            batch_size=getattr(args, "batch", 32),
            img_size=getattr(args, "imgsz", 224),
            model_size=getattr(args, "model", "n"),
            resume=getattr(args, "resume", False),
            device=getattr(args, "device", "")
        )
    elif args.command == "export":
        export_model(args.model, args.format)
    elif args.command == "test":
        test_model(args.model, args.image)


if __name__ == "__main__":
    main()
