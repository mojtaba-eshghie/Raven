
import os
import json
from pathlib import Path
import numpy as np
import pandas as pd
from typing import List, Optional
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler, normalize
from sklearn.cluster import KMeans, DBSCAN
import hdbscan
import matplotlib.pyplot as plt

ARTIFACTS_DIR = "artifacts"
Path(ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)

def _row_to_run_id(row: pd.Series) -> str:
    algo = row.get("algorithm", "unknown")
    model = row.get("model_name", row.get("embedding_name", "X"))
    metric = row.get("metric", "cosine")
    parts = [str(model), str(algo), str(metric)]
    # add common hyperparams if present
    for key in ["n_clusters", "eps", "min_samples", "min_cluster_size", "min_samples_hdb"]:
        if key in row and pd.notna(row[key]):
            parts.append(f"{key}={int(row[key]) if isinstance(row[key], (int, np.integer)) else row[key]}")
    return "_".join(parts).replace(" ", "")

def _fit_predict_with_row(algo: str, X, row: pd.Series):
    if algo.lower() == "kmeans":
        n_clusters = int(row.get("n_clusters", 8))
        model = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
        labels = model.fit_predict(X)
        return labels
    elif algo.lower() == "dbscan":
        eps = float(row.get("eps", 0.5))
        min_samples = int(row.get("min_samples", 5))
        model = DBSCAN(eps=eps, min_samples=min_samples, metric=row.get("metric","cosine"))
        labels = model.fit_predict(X)
        return labels
    elif algo.lower() == "hdbscan":
        from sklearn.preprocessing import normalize
        min_cluster_size = int(row.get("min_cluster_size", 10))
        min_samples = int(row.get("min_samples", min_cluster_size))
        metric = str(row.get("metric", "euclidean")).lower()
        if metric == "cosine":
            X_in = normalize(X)
            clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                                        min_samples=min_samples,
                                        metric="euclidean")
            return clusterer.fit_predict(X_in)
        else:
            clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                                        min_samples=min_samples,
                                        metric=metric)
            return clusterer.fit_predict(X)
    else:
        raise ValueError(f"Unsupported algorithm: {algo}")

def save_pca_for_best(
    X,
    results_df: pd.DataFrame,
    model_name: Optional[str] = None,
    sort_by: str = "combined_scores",
    top_k: int = 3,
    scale_before_pca: bool = True,
):
    """
    Re-runs clustering for the top-k rows (by `sort_by`) and saves PCA coords+labels and a PNG figure per run.
    Expects `results_df` rows to include columns: 'algorithm', hyperparameters, and ideally 'model_name'.
    """
    if results_df is None or len(results_df) == 0:
        raise ValueError("results_df is empty.")
    df = results_df.copy()
    if model_name is not None and "model_name" in df.columns:
        df = df[df["model_name"] == model_name]

    if sort_by not in df.columns:
        # fall back to silhouette if available, else any numeric score
        for candidate in ["silhouette", "calinski_harabasz", "pct_clustered"]:
            if candidate in df.columns:
                sort_by = candidate
                break

    df_sorted = df.sort_values(sort_by, ascending=False if sort_by != "davies_bouldin" else True)
    top = df_sorted.head(top_k)

    # prepare PCA
    X_prep = X
    if scale_before_pca:
        X_prep = StandardScaler(with_mean=False).fit_transform(X) if hasattr(X, "toarray") or hasattr(X, "A") else StandardScaler().fit_transform(X)
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(X_prep)

    saved = []
    for _, row in top.iterrows():
        algo = str(row.get("algorithm", ""))
        run_id = _row_to_run_id(row)
        labels = _fit_predict_with_row(algo, X, row)

        # Save dataframe of PCA coords + labels
        out_csv = Path(ARTIFACTS_DIR) / f"{run_id}_pca.csv"
        df_out = pd.DataFrame({
            "x": coords[:,0],
            "y": coords[:,1],
            "cluster": labels.astype(int)
        })
        df_out.to_csv(out_csv, index=False)

        # Save metadata
        out_meta = Path(ARTIFACTS_DIR) / f"{run_id}_meta.json"
        meta = row.to_dict()
        meta["run_id"] = run_id
        meta["pca_explained_variance_ratio"] = list(map(float, pca.explained_variance_ratio_))
        with open(out_meta, "w") as f:
            json.dump(meta, f, indent=2)

        # Save quick PNG
        out_png = Path(ARTIFACTS_DIR) / f"{run_id}_pca.png"
        import matplotlib.pyplot as plt
        plt.figure()
        scatter = plt.scatter(df_out["x"], df_out["y"], c=df_out["cluster"], s=6)
        plt.title(run_id)
        plt.xlabel("PCA 1")
        plt.ylabel("PCA 2")
        plt.tight_layout()
        plt.savefig(out_png, dpi=200)
        plt.close()

        saved.append({"run_id": run_id, "csv": str(out_csv), "png": str(out_png), "meta": str(out_meta)})

    return pd.DataFrame(saved)

def plot_saved_pca(run_id: str):
    """Convenience: reload a saved PCA CSV and plot it (for later/interactive use)."""
    csv_path = Path(ARTIFACTS_DIR) / f"{run_id}_pca.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No saved PCA CSV found for run_id={run_id} at {csv_path}")
    df = pd.read_csv(csv_path)
    plt.figure()
    plt.scatter(df["x"], df["y"], c=df["cluster"], s=6)
    plt.title(run_id)
    plt.xlabel("PCA 1")
    plt.ylabel("PCA 2")
    plt.tight_layout()
    plt.show()
