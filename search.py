#!/usr/bin/env python3
"""
FastAPI backend for Simpsons Scene Search.

Provides a REST API for searching frames by natural language descriptions
using CLIP embeddings and vector similarity search.
"""

import os
import secrets
import time
from datetime import datetime
from pathlib import Path

import lancedb
import open_clip
import torch
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Admin authentication
security = HTTPBasic()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# External CDN for images (if hosting frames on R2/S3)
# If set, images are served from CDN instead of locally
IMAGE_CDN_URL = os.environ.get("IMAGE_CDN_URL", "").rstrip("/")


def get_image_urls(episode: str, frame: str) -> dict:
    """Generate image URLs, using CDN if configured."""
    if IMAGE_CDN_URL:
        # CDN structure: {CDN_URL}/frames/{episode}/{frame}
        return {
            "thumb_url": f"{IMAGE_CDN_URL}/thumbnails/{episode}/{frame.rsplit('.', 1)[0]}_thumb.webp",
            "image_url": f"{IMAGE_CDN_URL}/frames/{episode}/{frame}"
        }
    else:
        # Local paths
        return {
            "thumb_url": f"/thumbs/{episode}/{frame}",
            "image_url": f"/frames/{episode}/{frame}"
        }


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify admin credentials for protected endpoints."""
    if not ADMIN_PASSWORD:
        # No password set - allow access (development mode)
        return True

    # Use secrets.compare_digest to prevent timing attacks
    password_correct = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        ADMIN_PASSWORD.encode("utf-8")
    )

    if not password_correct:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

app = FastAPI(
    title="Simpsons Scene Search",
    description="Search Simpsons frames by natural language descriptions",
    version="1.0.0"
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Stats cache with TTL
_stats_cache = {"data": None, "timestamp": 0}
STATS_CACHE_TTL = 600  # 10 minutes


def _compute_stats():
    """Compute database statistics."""
    import re
    count = table.count_rows()
    dummy_vector = [0.0] * 512
    all_frames = table.search(dummy_vector).limit(count).to_list()
    episodes = set(r["episode"] for r in all_frames)
    unique_episodes = len(episodes)

    seasons = set()
    for ep in episodes:
        match = re.search(r's(\d+)e', ep, re.I)
        if match:
            seasons.add(int(match.group(1)))

    return {
        "total_frames": count,
        "episodes": unique_episodes,
        "frames_per_episode_avg": count / unique_episodes if unique_episodes > 0 else 0,
        "seasons": sorted(seasons)
    }


# Precompute stats on startup
print("Precomputing stats...")
_stats_cache["data"] = _compute_stats()
_stats_cache["timestamp"] = time.time()
print(f"✓ Stats ready: {_stats_cache['data']['total_frames']} frames")

# Search logging
SEARCH_LOG_PATH = Path("data/search_log.tsv")


def log_search(query: str, mode: str, results_count: int, ip: str = ""):
    """Append search query to log file."""
    try:
        timestamp = datetime.now().isoformat()
        # TSV format: timestamp, query, mode, results_count, ip
        line = f"{timestamp}\t{query}\t{mode}\t{results_count}\t{ip}\n"
        with open(SEARCH_LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass  # Don't let logging errors break searches


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


@app.get("/test-delete")
def test_delete():
    """Serve the delete test page."""
    return FileResponse("test_delete.html")


@app.get("/legal")
def legal():
    """Return legal disclaimer and copyright information."""
    return {
        "disclaimer": (
            "This is a fan-made research/educational tool. "
            "The Simpsons and all related content are trademarks of and copyrighted by "
            "20th Television and The Walt Disney Company. "
            "This site is not affiliated with or endorsed by the copyright holders."
        ),
        "fair_use": (
            "Content is used under fair use doctrine (17 U.S.C. Section 107) for "
            "non-commercial, educational, and research purposes. This transformative use "
            "provides a search and indexing service, not streaming or distribution of full episodes."
        ),
        "takedown": (
            "For DMCA takedown requests or other legal inquiries, please contact the site administrator."
        ),
        "similar_projects": [
            "Frinkiac (frinkiac.com)",
            "Morbotron (morbotron.com)"
        ]
    }


@app.get("/search")
@limiter.limit("60/minute")
def search(
    request: Request,
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return"),
    mode: str = Query("visual", description="Search mode: 'visual' or 'quote'"),
    season: str = Query(None, description="Comma-separated season codes to filter (e.g., 's01,s02')")
):
    """
    Search for frames matching the query.

    Args:
        q: Natural language description (e.g., "homer eating donuts")
        limit: Maximum number of results (1-100)
        mode: Search mode - 'visual' uses CLIP embeddings, 'quote' prioritizes caption matches
        season: Optional comma-separated season codes to filter results

    Returns:
        List of matching frames with metadata and similarity scores
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Parse season filter
    season_filters = set()
    if season:
        season_filters = set(s.strip().lower() for s in season.split(','))

    try:
        query_lower = q.lower()
        query_words = set(query_lower.split())

        if mode == "quote":
            # Quote mode: use CLIP embedding but with heavy caption boosting
            query_embedding = embed_text(q)
            results = table.search(query_embedding).limit(limit * 10).to_list()

            # Filter by season if specified
            if season_filters:
                results = [r for r in results if any(sf in r["episode"].lower() for sf in season_filters)]

            # Score by caption match with heavy boosting
            scored_results = []
            for r in results:
                caption = r.get("caption", "").lower()
                base_score = max(0.0, 1 - r["_distance"] / 2)

                # Count word matches and check for phrase match
                word_matches = sum(1 for word in query_words if word in caption)
                phrase_match = query_lower in caption

                # Heavy boost for caption matches in quote mode
                if phrase_match:
                    score = 0.95
                elif word_matches > 0:
                    score = min(0.9, base_score + (word_matches * 0.2))
                else:
                    score = base_score * 0.3  # Penalize non-matches heavily

                scored_results.append({**r, "_score": score})

            # Sort by score descending
            scored_results.sort(key=lambda x: x["_score"], reverse=True)
            results = scored_results[:limit]

            # Log the search
            log_search(q, mode, len(results), request.client.host if request.client else "")

            return [{
                "episode": r["episode"],
                "frame": r["frame"],
                "path": r["path"],
                "timestamp": r["timestamp"],
                "score": r["_score"],
                **get_image_urls(r["episode"], r["frame"])
            } for r in results]

        else:
            # Visual mode: use CLIP embeddings with hybrid boosting
            query_embedding = embed_text(q)
            # Get more results for re-ranking (more if filtering by season)
            fetch_limit = limit * 10 if season_filters else limit * 3
            results = table.search(query_embedding).limit(fetch_limit).to_list()

            # Filter by season if specified
            if season_filters:
                results = [r for r in results if any(sf in r["episode"].lower() for sf in season_filters)]

            # Hybrid search: boost results where caption or characters match query terms
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

            # Log the search
            log_search(q, mode, len(results), request.client.host if request.client else "")

            return [{
                "episode": r["episode"],
                "frame": r["frame"],
                "path": r["path"],
                "timestamp": r["timestamp"],
                "score": max(0.0, min(1.0, 1 - r["_distance"] / 2)),  # Scale: distance 0=1.0, distance 2=0.0
                **get_image_urls(r["episode"], r["frame"])
            } for r in results]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
@limiter.limit("30/minute")
def stats(request: Request, refresh: bool = False):
    """Get database statistics (cached, precomputed on startup)."""
    global _stats_cache
    now = time.time()

    # Return cached data if valid and not forcing refresh
    if not refresh and _stats_cache["data"] and (now - _stats_cache["timestamp"]) < STATS_CACHE_TTL:
        return _stats_cache["data"]

    try:
        result = _compute_stats()

        # Update cache
        _stats_cache["data"] = result
        _stats_cache["timestamp"] = now

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/random")
@limiter.limit("30/minute")
def random_frame(request: Request):
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
            **get_image_urls(result["episode"], result["frame"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/similar")
@limiter.limit("30/minute")
def similar_frames(
    request: Request,
    path: str = Query(..., description="Path to the source frame"),
    limit: int = Query(12, ge=1, le=50, description="Number of similar frames to return")
):
    """
    Find frames similar to a given frame.

    Args:
        path: Path to the source frame
        limit: Maximum number of results (1-50)

    Returns:
        List of similar frames with similarity scores
    """
    try:
        # Find the source frame by path using filter
        source_results = table.search().where(f"path = '{path}'", prefilter=True).limit(1).to_list()

        if not source_results:
            raise HTTPException(status_code=404, detail=f"Source frame not found: {path}")

        source_frame = source_results[0]

        # Search using the source frame's embedding
        results = table.search(source_frame["vector"]).limit(limit + 1).to_list()

        # Filter out the source frame itself
        results = [r for r in results if r["path"] != path][:limit]

        return [{
            "episode": r["episode"],
            "frame": r["frame"],
            "path": r["path"],
            "timestamp": r["timestamp"],
            "score": max(0.0, min(1.0, 1 - r["_distance"] / 2)),
            **get_image_urls(r["episode"], r["frame"])
        } for r in results]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/frame/delete")
def delete_frame(
    path: str = Query(..., description="Path to the frame to delete"),
):
    """
    Delete a frame from the index.

    Args:
        path: Full path to the frame (e.g., "data/frames/The Simpsons - s01e01/frame_00123.jpg")

    Returns:
        Success message with deleted frame info
    """
    try:
        print(f"[DELETE] Received path: {path}")
        # Delete the frame from the table using SQL-like filter
        table.delete(f"path = '{path}'")
        print(f"[DELETE] Successfully deleted: {path}")

        return {
            "success": True,
            "message": f"Deleted frame: {path}",
            "path": path
        }
    except Exception as e:
        print(f"[DELETE] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete frame: {str(e)}")


@app.get("/frames/{episode}/{frame}")
def get_frame(episode: str, frame: str):
    """Serve frame images with aggressive caching headers."""
    frame_path = Path(f"data/frames/{episode}/{frame}")
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")

    return FileResponse(
        frame_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Vary": "Accept-Encoding"
        }
    )


@app.get("/thumbs/{episode}/{frame}")
def get_thumbnail(episode: str, frame: str):
    """Serve thumbnail images with aggressive caching headers."""
    # Convert frame.jpg to frame_thumb.webp
    thumb_name = frame.rsplit('.', 1)[0] + "_thumb.webp"
    thumb_path = Path(f"data/thumbnails/{episode}/{thumb_name}")

    # Fall back to full-res if thumbnail doesn't exist
    if not thumb_path.exists():
        frame_path = Path(f"data/frames/{episode}/{frame}")
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="Frame not found")
        return FileResponse(
            frame_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Vary": "Accept-Encoding"
            }
        )

    return FileResponse(
        thumb_path,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Vary": "Accept-Encoding"
        }
    )


if Path("frontend").exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
