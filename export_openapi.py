import json
from pathlib import Path
import sys

# Ensure video-broll-engine is in sys.path
root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.main import app

out_path = root / "openapi.json"
schema = app.openapi()
out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
print(f"Exported OpenAPI specification ({len(schema.get('paths', {}))} endpoints) to {out_path}")
