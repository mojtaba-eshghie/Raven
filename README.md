#   Failysis: Failure Analysis of Ethereum Transctions at a Large Scale 

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

## Usage

### Command-line Script

Analyze a failed transaction by providing its hash:

```bash
python analyze_transaction.py <transaction_hash>
```

### TODO: Python Module

Import the analysis function into your Python scripts:

```python
from invariant_analyzer import analyze_failed_transaction

result = analyze_failed_transaction('0xYourTransactionHash')
print(result)
```

The function returns a dictionary with:
- **failure_reason:** The root cause of the transaction failure.
- **failure_invariant:** The specific revert/require/assert condition that triggered the failure.
- **failure_message:** The accompanying message (if available), or fallback information if data is missing.

## Contact

For further questions or collaboration, please reach out to:
- **Student:** Melissa Rebecca Mazura (mazura@kth.se)
- **Supervisor:** Mojtaba Eshghie (eshghie@kth.se)
