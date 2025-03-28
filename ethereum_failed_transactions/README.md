## Failed Ethereum Transactions Dataset

**Target Block Range**: `0 - 22145000` (Mar-28-2025)



Breaking down the 32nd chunk into: 

```sql
-- Query 1 --
SELECT * FROM ethereum.transactions
WHERE block_number BETWEEN 21452961 AND 21625960
  AND success = FALSE;

-- Query 2 --
SELECT * FROM ethereum.transactions
WHERE block_number BETWEEN 21625961 AND 21798960
  AND success = FALSE;

-- Query 3 --
SELECT * FROM ethereum.transactions
WHERE block_number BETWEEN 21798961 AND 21971960
  AND success = FALSE;

-- Query 4 --
SELECT * FROM ethereum.transactions
WHERE block_number BETWEEN 21971961 AND 22145000
  AND success = FALSE;
```