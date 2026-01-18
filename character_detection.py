#!/usr/bin/env python3
"""
Improved character detection for The Simpsons using pre-trained models.

Supports multiple backends:
1. YOLOv8 classifier (best - trained on 20+ characters)
2. HuggingFace ViT (family members only)
3. CLIP zero-shot (fallback)

Requirements:
    pip install transformers torch pillow
    pip install ultralytics  # for YOLOv8
"""

import os
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

# Default path for trained YOLO model
YOLO_MODEL_PATH = Path(__file__).parent / "models" / "simpsons_classifier.pt"


class SimpsonsCharacterDetector:
    """
    Character detector using pre-trained ViT model and CLIP fallback.

    The ViT model is more accurate for main family members, while CLIP
    handles secondary characters.
    """

    # Extended character list beyond family members
    SECONDARY_CHARACTERS = [
        "Mr. Burns", "Smithers", "Ned Flanders", "Moe Szyslak", "Barney Gumble",
        "Chief Wiggum", "Apu", "Krusty the Clown", "Milhouse",
        "Nelson Muntz", "Principal Skinner", "Edna Krabappel", "Groundskeeper Willie",
        "Comic Book Guy", "Sideshow Bob", "Otto Mann", "Patty Bouvier", "Selma Bouvier",
        "Ralph Wiggum", "Martin Prince", "Grampa Simpson", "Santa's Little Helper",
        "Snowball", "Itchy", "Scratchy", "Troy McClure", "Lionel Hutz"
    ]

    def __init__(
        self,
        use_yolo: bool = True,
        use_vit: bool = True,
        use_clip_fallback: bool = True,
        yolo_model_path: str = None,
        device: str = None
    ):
        """
        Initialize character detection models.

        Args:
            use_yolo: Use trained YOLOv8 classifier (best accuracy)
            use_vit: Use pre-trained ViT model for family members
            use_clip_fallback: Use CLIP for secondary character detection
            yolo_model_path: Path to trained YOLO model
            device: Device to run models on (auto-detected if None)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.yolo_model = None
        self.yolo_names = []
        self.vit_model = None
        self.vit_processor = None
        self.clip_model = None
        self.clip_preprocess = None
        self.clip_tokenizer = None
        self.vit_labels = []

        # Try YOLO first (best accuracy if trained)
        if use_yolo:
            yolo_path = Path(yolo_model_path) if yolo_model_path else YOLO_MODEL_PATH
            self._load_yolo_model(yolo_path)

        # Fall back to ViT if no YOLO
        if use_vit and self.yolo_model is None:
            self._load_vit_model()

        # CLIP as final fallback
        if use_clip_fallback and self.yolo_model is None:
            self._load_clip_model()

    def _load_yolo_model(self, model_path: Path):
        """Load trained YOLOv8 classifier."""
        if not model_path.exists():
            print(f"YOLO model not found at {model_path}")
            return

        try:
            from ultralytics import YOLO

            print(f"Loading YOLO model: {model_path}...")
            self.yolo_model = YOLO(str(model_path))
            self.yolo_names = self.yolo_model.names
            print(f"  YOLO can detect {len(self.yolo_names)} characters")

        except ImportError:
            print("Warning: ultralytics not installed, skipping YOLO")
        except Exception as e:
            print(f"Warning: Could not load YOLO model: {e}")
            self.yolo_model = None

    def _load_vit_model(self):
        """Load the pre-trained ViT model for Simpsons family members."""
        try:
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            model_name = "DunnBC22/vit-base-patch16-224-in21k_Simpsons_Family_Members"
            print(f"Loading ViT model: {model_name}...")

            self.vit_processor = AutoImageProcessor.from_pretrained(model_name)
            self.vit_model = AutoModelForImageClassification.from_pretrained(model_name)
            self.vit_model.to(self.device)
            self.vit_model.eval()

            # Get label names from model config
            if hasattr(self.vit_model.config, 'id2label'):
                self.vit_labels = list(self.vit_model.config.id2label.values())
                print(f"  ViT can detect: {', '.join(self.vit_labels)}")
            else:
                self.vit_labels = ["Homer", "Marge", "Bart", "Lisa", "Maggie"]
                print(f"  ViT labels not found, using defaults: {', '.join(self.vit_labels)}")

        except Exception as e:
            print(f"Warning: Could not load ViT model: {e}")
            self.vit_model = None

    def _load_clip_model(self):
        """Load CLIP model for secondary character detection."""
        try:
            import open_clip

            print("Loading CLIP model for secondary characters...")
            self.clip_model, _, self.clip_preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32',
                pretrained='laion2b_s34b_b79k'
            )
            self.clip_tokenizer = open_clip.get_tokenizer('ViT-B-32')
            self.clip_model.to(self.device)
            self.clip_model.eval()

        except Exception as e:
            print(f"Warning: Could not load CLIP model: {e}")
            self.clip_model = None

    def detect_with_yolo(
        self,
        image_path: str,
        threshold: float = 0.3,
        max_chars: int = 5
    ) -> list[tuple[str, float]]:
        """
        Detect characters using trained YOLOv8 classifier.

        Args:
            image_path: Path to image file
            threshold: Minimum confidence threshold
            max_chars: Maximum characters to return

        Returns:
            List of (character_name, confidence) tuples
        """
        if self.yolo_model is None:
            return []

        results = self.yolo_model(image_path, verbose=False)

        detected = []
        for result in results:
            probs = result.probs
            if probs is None:
                continue

            # Get top predictions above threshold
            for idx, conf in zip(probs.top5, probs.top5conf):
                if conf.item() >= threshold:
                    name = self.yolo_names[idx]
                    # Clean up name (e.g., "homer_simpson" -> "Homer")
                    clean_name = self._clean_character_name(name)
                    detected.append((clean_name, conf.item()))

        return detected[:max_chars]

    def _clean_character_name(self, name: str) -> str:
        """Convert YOLO class name to display name."""
        # Map YOLO names to display names
        name_map = {
            "homer_simpson": "Homer",
            "marge_simpson": "Marge",
            "bart_simpson": "Bart",
            "lisa_simpson": "Lisa",
            "maggie_simpson": "Maggie",
            "abraham_grampa_simpson": "Grampa",
            "apu_nahasapeemapetilon": "Apu",
            "barney_gumble": "Barney",
            "charles_montgomery_burns": "Mr. Burns",
            "chief_wiggum": "Chief Wiggum",
            "comic_book_guy": "Comic Book Guy",
            "edna_krabappel": "Edna Krabappel",
            "groundskeeper_willie": "Groundskeeper Willie",
            "krusty_the_clown": "Krusty",
            "lenny_leonard": "Lenny",
            "milhouse_van_houten": "Milhouse",
            "moe_szyslak": "Moe",
            "ned_flanders": "Ned Flanders",
            "nelson_muntz": "Nelson",
            "principal_skinner": "Principal Skinner",
            "sideshow_bob": "Sideshow Bob",
        }
        return name_map.get(name, name.replace("_", " ").title())

    def detect_with_vit(self, image_path: str, threshold: float = 0.5) -> list[tuple[str, float]]:
        """
        Detect family members using ViT model.

        Args:
            image_path: Path to image file
            threshold: Minimum confidence threshold

        Returns:
            List of (character_name, confidence) tuples
        """
        if self.vit_model is None:
            return []

        image = Image.open(image_path).convert('RGB')
        inputs = self.vit_processor(image, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.vit_model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)[0]

        # Get characters above threshold
        detected = []
        for idx, prob in enumerate(probs):
            if prob.item() >= threshold:
                label = self.vit_labels[idx] if idx < len(self.vit_labels) else f"Class_{idx}"
                detected.append((label, prob.item()))

        return sorted(detected, key=lambda x: x[1], reverse=True)

    def detect_with_clip(
        self,
        image_path: str,
        characters: list[str] = None,
        threshold: float = 0.25,
        max_chars: int = 5
    ) -> list[tuple[str, float]]:
        """
        Detect characters using CLIP zero-shot classification.

        Args:
            image_path: Path to image file
            characters: List of character names to check (defaults to SECONDARY_CHARACTERS)
            threshold: Minimum confidence threshold
            max_chars: Maximum number of characters to return

        Returns:
            List of (character_name, confidence) tuples
        """
        if self.clip_model is None:
            return []

        if characters is None:
            characters = self.SECONDARY_CHARACTERS

        image = self.clip_preprocess(Image.open(image_path).convert('RGB')).unsqueeze(0).to(self.device)
        text = self.clip_tokenizer([f"a photo of {char}" for char in characters]).to(self.device)

        with torch.no_grad():
            image_features = self.clip_model.encode_image(image)
            text_features = self.clip_model.encode_text(text)

            image_features /= image_features.norm(dim=-1, keepdim=True)
            text_features /= text_features.norm(dim=-1, keepdim=True)

            similarity = (image_features @ text_features.T)[0]

        # Get top characters above threshold
        detected = []
        for idx, score in enumerate(similarity):
            if score.item() >= threshold:
                detected.append((characters[idx], score.item()))

        # Sort by confidence and limit
        detected = sorted(detected, key=lambda x: x[1], reverse=True)[:max_chars]

        # Filter to only include characters within reasonable range of top score
        if detected:
            top_score = detected[0][1]
            detected = [(char, score) for char, score in detected if top_score - score <= 0.1]

        return detected

    def detect(
        self,
        image_path: str,
        yolo_threshold: float = 0.3,
        vit_threshold: float = 0.4,
        clip_threshold: float = 0.25,
        max_chars: int = 5
    ) -> list[str]:
        """
        Detect all characters in an image.

        Priority: YOLO (if trained) > ViT (family members) > CLIP (fallback)

        Args:
            image_path: Path to image file
            yolo_threshold: Confidence threshold for YOLO model
            vit_threshold: Confidence threshold for ViT model
            clip_threshold: Confidence threshold for CLIP model
            max_chars: Maximum total characters to return

        Returns:
            List of detected character names
        """
        detected = {}

        # Try YOLO first (best if trained)
        if self.yolo_model is not None:
            yolo_results = self.detect_with_yolo(image_path, yolo_threshold, max_chars)
            for char, score in yolo_results:
                detected[char] = score
            # If YOLO found characters, return them
            if detected:
                sorted_chars = sorted(detected.items(), key=lambda x: x[1], reverse=True)[:max_chars]
                return [char for char, score in sorted_chars]

        # Fall back to ViT for family members
        if self.vit_model is not None:
            vit_results = self.detect_with_vit(image_path, vit_threshold)
            for char, score in vit_results:
                detected[char] = score

        # Then use CLIP for secondary characters
        if self.clip_model is not None:
            clip_results = self.detect_with_clip(image_path, threshold=clip_threshold, max_chars=max_chars)
            for char, score in clip_results:
                # Don't override ViT detections
                if char not in detected:
                    detected[char] = score

        # Sort by confidence and return names only
        sorted_chars = sorted(detected.items(), key=lambda x: x[1], reverse=True)[:max_chars]
        return [char for char, score in sorted_chars]


# Singleton instance for reuse
_detector = None


def get_detector() -> SimpsonsCharacterDetector:
    """Get or create the shared character detector instance."""
    global _detector
    if _detector is None:
        _detector = SimpsonsCharacterDetector()
    return _detector


def detect_characters(image_path: str, max_chars: int = 5) -> list[str]:
    """
    Convenience function to detect characters in an image.

    Args:
        image_path: Path to image file
        max_chars: Maximum characters to return

    Returns:
        List of detected character names
    """
    detector = get_detector()
    return detector.detect(image_path, max_chars=max_chars)


def main():
    """Test character detection on sample images."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python character_detection.py <image_path> [image_path2 ...]")
        sys.exit(1)

    detector = SimpsonsCharacterDetector()

    for image_path in sys.argv[1:]:
        if Path(image_path).exists():
            print(f"\n{image_path}:")
            characters = detector.detect(image_path)
            if characters:
                print(f"  Detected: {', '.join(characters)}")
            else:
                print("  No characters detected")
        else:
            print(f"File not found: {image_path}")


if __name__ == "__main__":
    main()
