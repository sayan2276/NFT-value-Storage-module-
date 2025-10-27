Dynamic Secure NFT Minting/rdeem System v4.0 
Overview

mintV4.py implements a fully dynamic, secure NFT minting system on Algorand TestNet, enabling runtime configuration of all NFT parameters. Each NFT gets a unique escrow account, stores all metadata on-chain, and includes a cryptographic security fingerprint to prevent tampering.

This script supports the complete NFT lifecycle: mint → verify → opt-in → transfer → redeem/destroy.

Features

Fully Dynamic: User inputs NFT name, unit, and redeemable ALGO at runtime.

Unique Escrow per NFT: Nonce-based LogicSig ensures each NFT has a unique escrow account.

Complete On-Chain Metadata: All parameters, including LogicSig bytes, nonce, and redeemable amount, are stored in the note field.

Security Fingerprint: SHA-256 fingerprint prevents fake NFTs, parameter tampering, or LogicSig substitution.

Redemption Support: No time limit for redemption; supports NFT destruction and account close-out.

Verification Tools: Automatic mint verification against the expected fingerprint.

How It Works

Runtime Input: User provides NFT details (name, unit, redeemable ALGO).

Escrow Creation: A unique LogicSig escrow account is generated and funded.

Fingerprint Generation: Security fingerprint computed using NFT parameters and LogicSig bytes.

Minting: NFT is minted with the metadata hash as the fingerprint and the note field storing full metadata.

Verification: Script verifies NFT parameters and fingerprint against on-chain data.

Opt-In & Transfer: User opts in to the NFT, and escrow transfers ownership.

Tech Stack

Language: Python

Algorand SDK: py-algorand-sdk

Smart Contracts: PyTeal (LogicSig v6)

Blockchain: Algorand TestNet

Setup

Install dependencies:

pip install py-algorand-sdk pyteal


Update creator mnemonic in the script:

CREATOR_MNEMONIC = "your 25-word mnemonic here"


Run the script:

python mintV4.py


Enter NFT details when prompted.

Minting Workflow
Step	Description
1	Create & Fund Escrow – Unique LogicSig with nonce and funding.
2	Compute Fingerprint – Generate cryptographic fingerprint.
3	Mint NFT – Store metadata and fingerprint on-chain.
4	Verify Mint – Confirm asset parameters & fingerprint.
5	Opt-In & Transfer – User opts in, escrow transfers NFT.
Security Features

Unique escrow per NFT (nonce-based)

LogicSig stored on-chain for full transparency

Redeemable amount encoded dynamically

Metadata hash embedded as fingerprint

Supports NFT destruction & account close-out

No expiry for redemption




`redeemV4.py` is a **fully dynamic NFT redemption script** for Algorand that allows users to redeem NFTs and recover all underlying ALGO automatically. It is the successor to `dynamic_redemption.py v3.0`, adding further robustness and automation.  

---

## ⚡ Features

- **Fully Dynamic** – Only requires the NFT Asset ID at runtime; all other parameters (LogicSig, escrow, redeemable amount) are retrieved from the blockchain automatically.  
- **Automatic Metadata Retrieval** – Fetches LogicSig, nonce, redeemable amount, and version info from the NFT creation transaction.  
- **Dynamic Redeemable Amount** – Calculates redeemable ALGO from escrow balance, respecting minimum balance and fee requirements.  
- **Security Verified** – Verifies that the LogicSig escrow address matches the asset reserve for security.  
- **Ownership Check** – Confirms the user owns the NFT before redeeming.  
- **Atomic Redemption** – Executes an atomic transaction group:  
  1. User sends NFT to escrow  
  2. Escrow pays user the redeemable ALGO  
- **Cleanup Included** – After redemption:  
  - Destroys the NFT (removes it from the blockchain)  
  - Closes the escrow account and returns remaining ALGO to the user  
- **Backward Compatible** – Can handle NFTs without stored `locked_amount`, calculating the redeemable amount from escrow.  
- **Time-Unlimited** – Works even years after minting.  

---

## 📦 Requirements

- Python 3.10+
- [Algorand Python SDK](https://pypi.org/project/py-algorand-sdk/)
  
```bash


🛠️ Workflow Steps

Fetch Asset Info – Retrieve NFT details from Algorand blockchain.

Retrieve Metadata – Fetch LogicSig, nonce, redeemable amount from creation transaction.

Verify Escrow – Ensure the LogicSig escrow address matches the asset reserve.

Check Ownership – Confirm the user owns exactly 1 NFT unit.

Compute Redeemable Amount – Use stored locked amount or calculate from escrow balance.

Execute Atomic Redemption – NFT → Escrow, Escrow → User ALGO.

Destroy NFT – Completely remove NFT from the blockchain.

Close Escrow – Recover all remaining ALGO and remove escrow account.

✅ Security Considerations

Escrow address verification ensures funds are sent only to the intended user.

Minimum balance and fee buffers are enforced to prevent transaction failures.

Atomic transactions guarantee either complete redemption or rollback.
🛠️ Workflow Steps

Fetch Asset Info – Retrieve NFT details from Algorand blockchain.

Retrieve Metadata – Fetch LogicSig, nonce, redeemable amount from creation transaction.

Verify Escrow – Ensure the LogicSig escrow address matches the asset reserve.

Check Ownership – Confirm the user owns exactly 1 NFT unit.

Compute Redeemable Amount – Use stored locked amount or calculate from escrow balance.

Execute Atomic Redemption – NFT → Escrow, Escrow → User ALGO.

Destroy NFT – Completely remove NFT from the blockchain.

Close Escrow – Recover all remaining ALGO and remove escrow account.

✅ Security Considerations

Escrow address verification ensures funds are sent only to the intended user.

Minimum balance and fee buffers are enforced to prevent transaction failures.

Atomic transactions guarantee either complete redemption or rollback.


Future Goals

Holding Rewards: Users holding NFTs will receive ALGO rewards over time.

Dynamic Value Growth: NFT value increases automatically after every transaction.

Enhanced Metadata: Introduce interactive and evolving NFT properties.

MainNet Launch: Deploy on Algorand MainNet for real-world usage.
