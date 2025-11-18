# publish-model.py
from pathlib import Path
from sentence_transformers import SentenceTransformer

MODEL_DIR = Path(__file__).resolve().parent / "smartbert-contrastive"
assert MODEL_DIR.is_dir(), f"Model dir not found: {MODEL_DIR}"

model = SentenceTransformer(str(MODEL_DIR))
model.push_to_hub("MojtabaEshghie/RavenBERT", private=False,
                  commit_message="Initial RavenBERT upload")
print("✅ Pushed MojtabaEshghie/RavenBERT")
