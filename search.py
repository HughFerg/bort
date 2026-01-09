#!/usr/bin/env python3
"""
FastAPI backend for Simpsons Scene Search.

Provides a REST API for searching frames by natural language descriptions
using CLIP embeddings and vector similarity search.
"""

from pathlib import Path

import lancedb
import open_clip
import torch
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Simpsons Scene Search",
    description="Search Simpsons frames by natural language descriptions",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Loading CLIP model...")
model, _, preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32',
    pretrained='laion2b_s34b_b79k'
)
tokenizer = open_clip.get_tokenizer('ViT-B-32')
model.eval()

print("Connecting to LanceDB...")
db_path = "data/simpsons.lance"
if not Path(db_path).exists():
    raise RuntimeError(
        f"Database not found at {db_path}. "
        "Run 'python index.py --videos <path>' first to create the index."
    )

db = lancedb.connect(db_path)
table = db.open_table("frames")

print("✓ Ready to search!")


def embed_text(query: str) -> list[float]:
    """Generate CLIP embedding for text query."""
    text = tokenizer([query])
    with torch.no_grad():
        embedding = model.encode_text(text)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding[0].tolist()


@app.get("/")
def root():
    """Serve the frontend."""
    return FileResponse("frontend/index.html")


@app.get("/search")
def search(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return")
):
    """
    Search for frames matching the query.

    Args:
        q: Natural language description (e.g., "homer eating donuts")
        limit: Maximum number of results (1-100)

    Returns:
        List of matching frames with metadata and similarity scores
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        query_embedding = embed_text(q)
        # Get more results for re-ranking
        results = table.search(query_embedding).limit(limit * 3).to_list()

        # Hybrid search: boost results where caption or characters match query terms
        query_lower = q.lower()
        query_words = set(query_lower.split())

        for r in results:
            caption = r.get("caption", "").lower()
            characters = r.get("characters", "").lower()

            # Boost score if caption contains query words
            caption_matches = sum(1 for word in query_words if word in caption)
            if caption_matches > 0:
                # Clamp multiplier to minimum 0.1 to avoid negative distances
                multiplier = max(0.1, 1 - 0.15 * caption_matches)
                r["_distance"] = r["_distance"] * multiplier

            # Strong boost if character name matches query
            character_matches = sum(1 for word in query_words if word in characters)
            if character_matches > 0:
                # Clamp multiplier to minimum 0.1 to avoid negative distances
                multiplier = max(0.1, 1 - 0.3 * character_matches)
                r["_distance"] = r["_distance"] * multiplier

        # Re-sort by adjusted distance and take top results
        results = sorted(results, key=lambda x: x["_distance"])[:limit]

        return [{
            "episode": r["episode"],
            "frame": r["frame"],
            "path": r["path"],
            "timestamp": r["timestamp"],
            "caption": r.get("caption", ""),
            "characters": r.get("characters", ""),
            "score": max(0.0, min(1.0, 1 - r["_distance"])),  # Clamp score to [0, 1]
            "image_url": f"/frames/{r['episode']}/{r['frame']}"
        } for r in results]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
def stats():
    """Get database statistics."""
    try:
        count = table.count_rows()
        # Get all episodes using a dummy search
        dummy_vector = [0.0] * 512
        all_frames = table.search(dummy_vector).limit(count).to_list()
        unique_episodes = len(set(r["episode"] for r in all_frames))

        return {
            "total_frames": count,
            "episodes": unique_episodes,
            "frames_per_episode_avg": count / unique_episodes if unique_episodes > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/random")
def random_frame():
    """Get a random frame from the database."""
    try:
        import random

        # Get a sample of frames using a dummy search
        count = table.count_rows()
        if count == 0:
            raise HTTPException(status_code=404, detail="No frames in database")

        # Pick a random offset
        random_offset = random.randint(0, max(0, count - 1))

        # Use a dummy vector search to get frames, then skip to random offset
        dummy_vector = [0.0] * 512  # CLIP ViT-B-32 embedding size
        results = table.search(dummy_vector).limit(1).offset(random_offset).to_list()

        if not results:
            raise HTTPException(status_code=404, detail="No frame found")

        result = results[0]

        return {
            "episode": result["episode"],
            "frame": result["frame"],
            "path": result["path"],
            "timestamp": result["timestamp"],
            "caption": result.get("caption", ""),
            "characters": result.get("characters", ""),
            "image_url": f"/frames/{result['episode']}/{result['frame']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/frame")
def delete_frame(path: str = Query(..., description="Path to the frame to delete")):
    """
    Delete a frame from the index.

    Args:
        path: Full path to the frame (e.g., "data/frames/The Simpsons - s01e01/frame_00123.jpg")

    Returns:
        Success message with deleted frame info
    """
    try:
        # Delete the frame from the table using SQL-like filter
        table.delete(f"path = '{path}'")

        return {
            "success": True,
            "message": f"Deleted frame: {path}",
            "path": path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete frame: {str(e)}")


if Path("data/frames").exists():
    app.mount("/frames", StaticFiles(directory="data/frames"), name="frames")

if Path("frontend").exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
