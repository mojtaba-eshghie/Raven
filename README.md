#  Raven: Mining Defensive Patterns in Ethereum via Semantic Transaction Revert Invariants Categories 

Raven treats **failed Ethereum transactions** as a *positive* signal of working on-chain defenses.

It (1) aligns reverted executions to verified source, (2) extracts the exact guard predicates (`require`, `assert`, `if (...) revert/throw`) that caused the revert, (3) embeds them with a fine-tuned model (**RavenBERT**), and (4) clusters them by **semantic intent** (e.g., access control, slippage safeguards, replay prevention, allow/ban lists, etc.).

This repo contains all code and artifacts to:

- collect and label **failed Ethereum transactions**,
- extract **revert-inducing invariants**,
- fine-tune **RavenBERT** via contrastive learning,
- run a **grid search** over encoders + clustering algorithms,
- reproduce the **figures and tables** in the paper.

---

## Paper, Model, and Dataset

- 📄 **Paper**: TBD 
- 🧠 **Model – RavenBERT**  
  BERT-family encoder fine-tuned contrastively on revert-inducing invariants from 100k failed transactions:  
  <https://huggingface.co/MojtabaEshghie/RavenBERT>
- 📊 **Dataset – raven-dataset**  
  Sampled failed Ethereum transactions with extracted invariants and metadata:  
  <https://huggingface.co/datasets/MojtabaEshghie/raven-dataset>

Raven’s experiments (in this repo) use:

- a **fine-tuning set** of 100k failed transactions (1,932 unique invariants), and  
- an **evaluation set** of 20k failed transactions (727 unique invariants, June 2024 – March 2025).

---

## High-Level Research Questions

Raven is built and evaluated around three questions:

- **RQ1 – Intrinsic Quality.**  
  Does Raven generate **compact, well-separated** invariant clusters (Silhouette, S\_Dbw)?

- **RQ2 – Coverage vs. Quality.**  
  What fraction of invariants are clustered (vs. noise), and how does this trade off against quality across different encoders and clustering algorithms?

- **RQ3 – Semantic Meaningfulness.**  
  Are the resulting clusters **meaningful and distinct** under expert review, and do they surface invariant categories **missing from prior catalogs**?

---


## Project Structure

```bash
Raven/
├── analysis/                    # Plotting and visualization of results
│   ├── plotting.ipynb          
│   └── visualization/          
├── clustering/                  # Invariant clustering pipeline
│   ├── clustering.ipynb        
│   ├── experiments/            # Clustering results 
│   ├── artifacts_*/            # Generated clustering artifacts
│   └── ravenbert/              
├── dataset_creation/            # Scripts for dataset extraction
│   ├── analyze_transaction.py  # Transaction-level analysis
│   └── ethereum_src.py         # Ethereum data extraction utilities
├── datasets/                    # Training and evaluation datasets
│   ├── finetuning_dataset.parquet    # 100k transactions for fine-tuning
│   ├── test_dataset.parquet          # 20k transactions for evaluation
│   └── cluster_*.csv                 # Clustering results and mappings
├── finetuning/                  # RavenBERT fine-tuning scripts
│   ├── train_ravenbert_contrastive.py
│   └── checkpoints/            # Model checkpoints
└── ethereum_failed_transactions/ # Raw failed transaction hashes
```

## Cite Raven
```bibtex
TBD
```
