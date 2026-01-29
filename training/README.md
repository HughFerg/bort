# Simpsons Character Detection Training

Train a YOLOv8 classifier to detect Simpsons characters.

## Quick Start (Docker)

```bash
# 1. Download dataset from Kaggle
#    Go to: https://www.kaggle.com/datasets/alexattia/the-simpsons-characters-dataset
#    Download and extract to: training/data/raw/simpsons_dataset/

# 2. Build training container
docker build -t simpsons-train .

# 3. Prepare dataset
docker run -v $(pwd)/data:/app/data simpsons-train python prepare_dataset.py --skip-download

# 4. Train model
docker run --gpus all -v $(pwd)/data:/app/data -v $(pwd)/runs:/app/runs simpsons-train

# 5. Copy trained model to app
cp runs/classify/train/weights/best.pt ../models/simpsons_classifier.pt
```

## Manual Setup (Python 3.11)

```bash
# Create environment
python3.11 -m venv train_env
source train_env/bin/activate

# Install dependencies
pip install ultralytics opencv-python-headless kaggle pillow tqdm

# Set Kaggle credentials (or download manually)
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key

# Prepare dataset
python prepare_dataset.py

# Train
python train.py train --epochs 30 --model n

# Test on an image
python train.py test runs/classify/train/weights/best.pt path/to/image.jpg
```

## Dataset Structure

After running `prepare_dataset.py`:

```
data/simpsons_yolo/
├── train/
│   ├── homer_simpson/
│   ├── marge_simpson/
│   ├── bart_simpson/
│   └── ...
├── val/
│   ├── homer_simpson/
│   └── ...
└── classes.txt
```

## Training Options

```bash
python train.py train \
    --data data/simpsons_yolo \
    --epochs 30 \
    --batch 32 \
    --imgsz 224 \
    --model n \      # n=nano, s=small, m=medium, l=large
    --device mps     # mps for Mac, 0 for CUDA GPU, cpu for CPU
```

## Model Sizes

| Model | Params | Speed | Accuracy |
|-------|--------|-------|----------|
| yolov8n-cls | 2.7M | Fastest | Good |
| yolov8s-cls | 6.4M | Fast | Better |
| yolov8m-cls | 17.0M | Medium | Great |
| yolov8l-cls | 37.5M | Slow | Best |

Recommend starting with `n` (nano) for testing, then `s` or `m` for production.

## Characters Included

The model trains on characters with 50+ images:
- homer_simpson, marge_simpson, bart_simpson, lisa_simpson, maggie_simpson
- abraham_grampa_simpson, apu_nahasapeemapetilon, barney_gumble
- charles_montgomery_burns, chief_wiggum, comic_book_guy
- edna_krabappel, groundskeeper_willie, krusty_the_clown
- lenny_leonard, milhouse_van_houten, moe_szyslak
- ned_flanders, nelson_muntz, principal_skinner, sideshow_bob

## Integration

After training, update `character_detection.py` to use the new model:

```python
from ultralytics import YOLO

model = YOLO("models/simpsons_classifier.pt")
results = model(image_path)
predictions = results[0].probs.top5  # Top 5 class indices
```
