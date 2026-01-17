# Simpsons Semantic Scene Search

A local search engine that lets you find Simpsons scenes by describing what's happening visually, powered by CLIP embeddings and vector search.

**Unlike subtitle search (Frinkiac), this searches what's actually happening in the frames.**

## Features

- **Semantic Search**: Natural language visual search ("homer eating donuts")
- **Character Detection**: Automatically tagged with character names
- **AI Captions**: BLIP-generated descriptions
- **Random Frame**: Discover random moments
- **Filters**: Filter by season and character
- **Manual Curation**: Admin delete for quality control (pre-release)
- **90s Retro UI**: Classic Simpsons color scheme

## Example Queries

- "Homer looking sad on the couch"
- "Bart writing on chalkboard"
- "Burns tenting fingers saying excellent"
- "Lisa playing saxophone alone"
- "Marge with blue hair in the kitchen"

## Architecture

```
┌──────────────────┐      ┌──────────────┐      ┌──────────────┐
│  Video Files     │──►   │   ffmpeg     │──►   │   Frames     │
│  (.mkv/.mp4)     │      │ (1 per 3s)   │      │   (.jpg)     │
└──────────────────┘      └──────────────┘      └──────────────┘
                                                         │
                                                         ▼
                          ┌──────────────────────────────┐
                          │      OpenCLIP Model          │
                          │   (ViT-B-32 embeddings)      │
                          └──────────────────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │        LanceDB               │
                          │   (vector similarity)        │
                          └──────────────────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │     FastAPI + Frontend       │
                          │   (search interface)         │
                          └──────────────────────────────┘
```

## Tech Stack

- **Frame extraction**: ffmpeg
- **Embeddings**: OpenCLIP (ViT-B-32 model)
- **Vector DB**: LanceDB
- **Backend**: FastAPI
- **Frontend**: Vanilla HTML/CSS/JS

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Build and run
docker-compose up --build

# Visit http://localhost:8000
```

See [DOCKER.md](DOCKER.md) for more details.

### Option 2: Local Development

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Extract and Index Frames

Point the indexer at your Simpsons episodes:

```bash
# Process all videos in a directory
python index.py --videos "/Users/hughferguson/Downloads/The Simpsons (1989-2018)"

# This will:
# 1. Extract 1 frame every 3 seconds from each video
# 2. Generate CLIP embeddings for each frame
# 3. Store in LanceDB for fast search
```

**Options:**

```bash
# Custom frame interval (extract every 5 seconds)
python index.py --videos /path/to/videos --interval 5

# Custom output directory
python index.py --videos /path/to/videos --frames ./my_frames

# Only index existing frames (skip extraction)
python index.py --index-only --frames ./data/frames
```

### 3. Run the Search Server

```bash
uvicorn search:app --reload
```

Open http://localhost:8000 in your browser.

## Project Structure

```
simpsons-search/
├── index.py              # Frame extraction + embedding pipeline
├── search.py             # FastAPI search server
├── frontend/
│   └── index.html        # Search UI
├── data/
│   ├── frames/           # Extracted frames (gitignored)
│   │   ├── The Simpsons - s08e01/
│   │   │   ├── frame_00001.jpg
│   │   │   ├── frame_00002.jpg
│   │   │   └── ...
│   │   └── ...
│   └── simpsons.lance/   # LanceDB vector database
├── requirements.txt
└── README.md
```

## Usage Examples

### Process a Single Episode

```python
from index import extract_frames, index_frames

# Extract frames
extract_frames(
    video_path="S01E01.mp4",
    output_dir="data/frames/S01E01",
    interval=3
)

# Index the frames
index_frames("data/frames")
```

### Search Programmatically

```python
import requests

response = requests.get(
    "http://localhost:8000/search",
    params={"q": "homer eating donuts", "limit": 10}
)

results = response.json()
for r in results:
    print(f"{r['episode']} @ {r['timestamp']}s - {r['score']:.2%} match")
```

### Get Database Stats

```bash
curl http://localhost:8000/stats
```

## Performance

| Episodes | Frames @ 3s | Disk (frames) | Index time* | DB size |
|----------|-------------|---------------|-------------|---------|
| 1 | ~420 | ~42 MB | ~3 min | ~1.6 MB |
| 1 season (13) | ~5,400 | ~540 MB | ~40 min | ~22 MB |
| 100 episodes | ~42,000 | ~4.2 GB | ~5 hrs | ~170 MB |
| All (~700) | ~294,000 | ~29 GB | ~35 hrs | ~1.2 GB |

*CPU-only. GPU is 5-10x faster.

## Configuration

### Frame Extraction Interval

Default is 3 seconds (20 frames per minute). Adjust based on your needs:

- **2 seconds**: Maximum coverage, 1.5x storage
- **3 seconds**: Good balance (recommended)
- **5 seconds**: Fewer frames, faster indexing, less storage
- **10 seconds**: Minimal frames, fastest indexing, least storage

### Search Results

Modify `search.py` to change default result count:

```python
@app.get("/search")
def search(
    q: str = Query(...),
    limit: int = Query(30, ge=1, le=100)  # Change default here
):
    ...
```

## API Reference

### `GET /search`

Search for frames matching a query.

**Parameters:**
- `q` (required): Natural language description
- `limit` (optional): Max results (1-100, default 20)

**Response:**
```json
[
  {
    "episode": "The Simpsons - s08e23",
    "frame": "frame_00042.jpg",
    "path": "/path/to/frame.jpg",
    "timestamp": 210,
    "score": 0.87,
    "image_url": "/frames/S08E23/frame_00042.jpg"
  }
]
```

### `GET /stats`

Get database statistics.

**Response:**
```json
{
  "total_frames": 3250,
  "episodes": 13,
  "frames_per_episode_avg": 250
}
```

## Troubleshooting

### "ffmpeg: command not found"

Install ffmpeg:
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`
- **Windows**: Download from https://ffmpeg.org

### "Database not found" error

Make sure you've run the indexing step first:

```bash
python index.py --videos /path/to/videos
```

### Slow indexing

- Use a GPU if available (10x faster)
- Increase `--interval` to extract fewer frames
- Process episodes in batches

### Poor search results

- Try more descriptive queries
- Check that frames were extracted correctly
- Consider reducing frame interval for better coverage

## Future Enhancements

- [ ] Add subtitle search (hybrid text + visual)
- [ ] Character detection and filtering
- [ ] Scene clustering (group consecutive frames)
- [ ] Caption generation with LLaVA
- [ ] GIF creation from results
- [ ] Better deduplication
- [ ] Multi-language support

## License

Personal/educational use. This tool doesn't distribute copyrighted content—it's BYOB (bring your own videos).

## Credits

Built with:
- [OpenCLIP](https://github.com/mlfoundations/open_clip) - Vision-language embeddings
- [LanceDB](https://lancedb.com/) - Vector database
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
