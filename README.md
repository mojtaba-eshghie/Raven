# Raven: Semantic Analysis of Revert-Inducing Invariants on Ethereum’s  

This repository contains code and documentation for a tool that automates the extraction, clustering, and analysis of invariants in Solidity smart contracts. The goal is to map invariant patterns to transaction failures, providing insights into why transactions revert and how smart contracts can be made more reliable.

## Project Overview

Smart contracts manage decentralized applications and finances on blockchain networks. However, vulnerabilities—such as reentrancy attacks—have led to severe financial losses. This project leverages invariant analysis to:
- Automatically extract invariants from a large dataset of Solidity smart contracts.
- Cluster and classify these invariants based on their semantic purpose.
- Analyze how different invariant patterns correlate with transaction reversions (e.g., due to failed `revert`, `require`, or `assert` statements).

## Research Questions

- **RQ1:** How can invariants be efficiently extracted and clustered from Solidity smart contracts at scale?
- **RQ2:** What are the primary factors behind transaction reversion in Ethereum smart contracts? Specifically, which invariants or invariant categories are most associated with reverted transactions, and what are their underlying characteristics?

## Analysis Objectives

In addition to the main research questions, the project aims to address the following:
- **Invariant Insights:** What information can be extracted from an analysis of invariants (e.g., gas usage implications)?
- **Reversion Causes:** What are the most common causes of transaction reversions in Ethereum and other EVM-based blockchains?
- **Revert-Inducing Conditions:** Can we identify the top revert-inducing invariants (e.g., a ranked list of conditions that lead to transaction reversions)?
- **Failure Patterns:** What are the prevalent reasons for transaction reversion in the wild—be it due to `revert`/`require`/`assert` failures, gas consumption issues, or other factors?
- **Effectiveness Ratio:** What is the ratio of effective invariants (those directly linked to transaction reversion events) to the total number of invariants used in contracts?
- **Temporal Trends:** How does the percentage of transactions failing due to out-of-gas issues compare to other failure reasons over time?
- **Contract-Level Analysis:** Which contracts are most prone to transaction reversions, both for out-of-gas issues and manual reversion triggers?

## Installation

To set up the project locally:

```bash
# Clone the repository
git clone https://github.com/mojtaba-eshghie/Failysis/
cd Failysis

# Install dependencies
pip install -r requirements.txt
```

## Strucutre
Failysis/
├── analysis/                # Plotting of results with generated plots
├── clustering/          # Scripts for invariant clustering after extraction
├── dataset_creation/          # Code to create the datasets
├── datasets/    # the datasets for clustering and results
├── ethereum_failed_transactions/       # the extracted hashes from Dune
├── finetuning/            # finetuning ReBERT
├── requirements.txt     # Python dependencies


## Usage
Please follow these steps to correctly use the pipeline:

1. Dataset Creation (optional): Use scripts in dataset_creation/ to process and prepare your initial contract data. For the thesis, the data exists already

2. Invariant Clustering: Run the scripts in clustering/ to group similar invariants based on semantics or structural features.

3. Model Fine-Tuning (Optional): use to finetune the ReBERT model.

4. Visualization: Generate plots and figures using analysis/plotting.ipynb. The resulting PDFs will appear in analysis/visualization/.



## Contact

For further questions or collaboration, please reach out to:
- **Student:** Melissa Rebecca Mazura (mazura@kth.se)
- **Supervisor:** Mojtaba Eshghie (eshghie@kth.se)
