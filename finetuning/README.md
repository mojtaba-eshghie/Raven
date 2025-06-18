# Finetuning SmartBERT with Contrastive Learning

This script fine-tunes the `web3se/SmartBERT-v2` model using a contrastive learning approach on your dataset of texts. The goal is to generate embeddings where semantically similar sentences are closer in vector space.

---

## Overview

The finetuning process works as follows:

- Compute embeddings of all texts with the pretrained SmartBERT-v2.
- Build a similarity matrix using cosine similarity.
- Select top-k (3) most similar texts as positive pairs.
- Generate an equal number of random negative pairs.
- Train the model with contrastive loss (`CosineSimilarityLoss`) to pull positives closer and push negatives apart.
- Save the fine-tuned model to `./smartbert-contrastive`.

---

## Input / Output Files

- **Input:**
  - A CSV file containing your dataset of texts. Prepare the input via the preprocessing pipeline in the clustering folder.
  - Thesis input file: `finetuned_dataset.csv`. This file was created using the dataset creation pipeline with a different random seed.

- **ReBERT:**
  - The fine-tuned SentenceTransformer model saved in the folder: `./smartbert-contrastive`

---

## How to Run

Run the finetuning script:

```bash
python finetune_script.py
