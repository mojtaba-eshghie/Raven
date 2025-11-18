# clustering/train_ravenbert_contrastive.py
import argparse, random, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sentence_transformers import SentenceTransformer, models, losses, InputExample
from torch.utils.data import DataLoader

def load_texts(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    # Prefer an existing combined column if present; otherwise build it
    if "combined" in df.columns:
        texts = df["combined"].astype(str).fillna("").str.strip().tolist()
    else:
        # Heuristics for column names
        pred_col = next((c for c in ["predicate","guard","invariant","text"] if c in df.columns), None)
        msg_col  = next((c for c in ["message","reason","error","revert_message","revert"] if c in df.columns), None)
        if pred_col is None:
            raise ValueError(f"No predicate-like column found. Columns: {list(df.columns)}")
        df[pred_col] = df[pred_col].astype(str).fillna("").str.strip()
        if msg_col and msg_col in df.columns:
            df[msg_col] = df[msg_col].astype(str).fillna("").str.strip()
            combined = df[pred_col] + np.where(df[msg_col] != "", " || " + df[msg_col], "")
        else:
            combined = df[pred_col]
        texts = (combined.str.replace(r"\s+", " ", regex=True)
                         .str.strip()).tolist()

    # De-dup & prune trivials
    texts = [t for t in dict.fromkeys(texts) if len(t) >= 3]
    if not texts:
        raise ValueError("No usable texts after cleaning.")
    return texts

def make_pairs(embs: np.ndarray, texts: list[str],
               tau_pos=0.80, tau_neg=0.20,
               top_k=10, max_pos_per_item=5, target_neg_ratio=1.0,
               seed=0):
    """
    embs must be L2-normalized. Cosine(sim) == dot product.
    Positives: neighbors with sim >= tau_pos (up to max_pos_per_item).
    Negatives: random pairs with sim <= tau_neg, sized to ~target_neg_ratio * #positives.
    """
    random.seed(seed)
    n = len(texts)
    # Nearest neighbors in cosine space; distances = 1 - cosine
    nn = NearestNeighbors(n_neighbors=min(top_k+1, n), metric="cosine", algorithm="brute")
    nn.fit(embs)
    distances, indices = nn.kneighbors(embs, return_distance=True)

    positives = []
    for i in range(n):
        count = 0
        for dist, j in zip(distances[i], indices[i]):
            if j == i:
                continue
            sim = 1.0 - float(dist)
            if sim >= tau_pos:
                positives.append((texts[i], texts[j], 1.0))
                count += 1
                if count >= max_pos_per_item:
                    break

    # Build negatives by rejection sampling on cosine ≤ tau_neg
    want_negs = int(len(positives) * target_neg_ratio)
    negatives = []
    if want_negs > 0:
        # quick helper for sim via dot product (embs already normalized)
        def sim(i, j): return float(np.dot(embs[i], embs[j]))
        tries, max_tries = 0, max(100000, want_negs * 20)
        while len(negatives) < want_negs and tries < max_tries:
            i = random.randrange(n)
            j = random.randrange(n)
            if i == j: 
                tries += 1; 
                continue
            if sim(i, j) <= tau_neg:
                negatives.append((texts[i], texts[j], 0.0))
            tries += 1

        # If the dataset is too dense (few very-low-sim pairs), fall back to random negatives
        while len(negatives) < want_negs:
            i = random.randrange(n)
            j = random.randrange(n)
            if i != j:
                negatives.append((texts[i], texts[j], 0.0))

    pairs = positives + negatives
    random.shuffle(pairs)
    return pairs, len(positives), len(negatives)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="finetuning_dataset.csv", help="Path to CSV")
    ap.add_argument("--base", default="web3se/SmartBERT-v2")
    ap.add_argument("--out",  default="clustering/ravenbert")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch",  type=int, default=16)
    ap.add_argument("--tau_pos", type=float, default=0.80)
    ap.add_argument("--tau_neg", type=float, default=0.20)
    ap.add_argument("--top_k",   type=int, default=10)
    ap.add_argument("--max_pos_per_item", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    texts = load_texts(args.csv)
    print(f"Loaded {len(texts)} unique texts")

    # Seed embeddings (L2-normalized) from base model
    base = SentenceTransformer(args.base)
    embs = base.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=True)

    # Build contrastive pairs (thresholded)
    pairs, n_pos, n_neg = make_pairs(
        embs, texts,
        tau_pos=args.tau_pos, tau_neg=args.tau_neg,
        top_k=args.top_k, max_pos_per_item=args.max_pos_per_item,
        target_neg_ratio=1.0, seed=args.seed
    )
    print(f"Pairs: {len(pairs)} = {n_pos} positives + {n_neg} negatives")

    # Trainable model = Transformer + mean-pooling + L2 normalize layer
    word = models.Transformer(args.base, max_seq_length=512)
    pool = models.Pooling(word.get_word_embedding_dimension(), pooling_mode_mean_tokens=True)
    norm = models.Normalize()  # L2-normalize final embeddings → cosine distance is proper
    model = SentenceTransformer(modules=[word, pool, norm])

    train_examples = [InputExample(texts=[a, b], label=label) for a, b, label in pairs]
    train_loader = DataLoader(train_examples, shuffle=True, batch_size=args.batch)
    train_loss = losses.CosineSimilarityLoss(model=model)  # labels in [0,1]

    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=args.epochs,
        warmup_steps=min(100, max(10, len(train_loader)//10)),
        output_path=args.out,
        show_progress_bar=True,
    )

    # Also save a .bin checkpoint to avoid safetensors issues on some setups
    word.auto_model.save_pretrained(f"{args.out}/0_Transformer", safe_serialization=False)
    word.tokenizer.save_pretrained(f"{args.out}/0_Transformer")

    # Write simple training summary
    Path(args.out).mkdir(parents=True, exist_ok=True)
    with open(Path(args.out) / "ravenbert_training_stats.json", "w") as f:
        json.dump({
            "base_model": args.base,
            "n_texts": len(texts),
            "pairs_total": len(pairs),
            "positives": n_pos, "negatives": n_neg,
            "tau_pos": args.tau_pos, "tau_neg": args.tau_neg,
            "top_k": args.top_k, "max_pos_per_item": args.max_pos_per_item,
            "epochs": args.epochs, "batch": args.batch
        }, f, indent=2)

    print(f"✅ Saved RavenBERT to: {args.out}")

if __name__ == "__main__":
    main()
