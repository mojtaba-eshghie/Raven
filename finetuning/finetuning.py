import pandas as pd
import numpy as np
import random
from sklearn.metrics.pairwise import cosine_similarity
import torch
from sentence_transformers import SentenceTransformer, models, losses, InputExample
from torch.utils.data import DataLoader

def finetuning(texts):
    def embedding_model(texts, model_name):
        tokenizer = SentenceTransformer(model_name)
        embeddings = tokenizer.encode(texts, convert_to_numpy=True, show_progress_bar=True)
        return embeddings

    model_name = "web3se/SmartBERT-v2"
    embeddings = embedding_model(texts, model_name)

    sim_matrix = cosine_similarity(embeddings)

    top_k = 3
    positive_pairs = []
    for idx, sims in enumerate(sim_matrix):
        # top_k similar excluding self
        similar_idx = sims.argsort()[::-1][1:top_k+1]
        for sim_idx in similar_idx:
            positive_pairs.append((texts[idx], texts[sim_idx], 1.0))

    num_negatives = len(positive_pairs)
    all_indices = list(range(len(texts)))
    negative_pairs = []
    for _ in range(num_negatives):
        i, j = random.sample(all_indices, 2)
        negative_pairs.append((texts[i], texts[j], 0.0))

    all_pairs = positive_pairs + negative_pairs
    random.shuffle(all_pairs)
    train_examples = [InputExample(texts=[a,b], label=label) for a,b,label in all_pairs]

    print(f"Generated {len(train_examples)} pairs: {len(positive_pairs)} positives and {len(negative_pairs)} negatives")

    word_embedding_model = models.Transformer(model_name, max_seq_length=512)
    pooling_model = models.Pooling(
        word_embedding_model.get_word_embedding_dimension(),
        pooling_mode_cls_token=False,
        pooling_mode_mean_tokens=True
    )
    model = SentenceTransformer(modules=[word_embedding_model, pooling_model])

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
    train_loss = losses.CosineSimilarityLoss(model=model)

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=1,
        warmup_steps=100,
        output_path="./smartbert-contrastive"
    )

    print("Training finished and model saved to ./smartbert-contrastive")


def main():
    df = pd.read_csv("../../finetuned_dataset.csv")
    texts = df["combined"].astype(str).tolist()
    finetuning(texts)

if __name__ == main:
    main()