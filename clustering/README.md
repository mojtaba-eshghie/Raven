# Clustering – Failysis

This folder contains the scripts used to cluster invariants for **Failysis**. It utilizes ReBERT, an embedding model created for invariants.

---

## File Overview

| File Name                | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| `clustering.ipynb`       | Clusters the entire dataset efficiently. |
| `clustering_results_all_metrics.csv` | Results of the clustering for this thesis.  |


---

## ReBERT

This project uses ReBERT, a customized embedding model. It is found in the smartBERT-contrastive folder, and was trained with the finetuning folder.

---


## Usage

### Run all experiments

To run all experiments, go through each step of the clutsering pipeline, by
To run all experiments, go through each step of the clutsering pipeline, by

1. Extracting Invariants and saving them to a file
2. Embed the dataset with the different embedding models
3. Cluster them for with and without error messages

This can be done automatically by following each step in the pipeline. The results for this thesis are in the experiments folder, as well as the experiments themselves, which can be found under `èxperiments`.


---

## Output
The output are two folders under experiments. Note that these can be replicated exactly due to seed settings in the clustering pipeline. 
