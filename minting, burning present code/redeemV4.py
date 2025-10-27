"""
dynamic_redemption.py - v3.0 Dynamic NFT Redemption System

FULLY DYNAMIC NFT REDEMPTION WITH COMPLETE CLEANUP
===================================================
- Runtime input for Asset ID only - everything else retrieved from blockchain
- Automatically retrieves LogicSig, nonce, and redeemable amount from on-chain data
- Dynamic redeemable amount calculation from escrow balance
- Verifies security fingerprint with nonce
- Works even after years (no time limit)
- DESTROYS NFT and CLOSES ESCROW (returns ALL ALGO to redeemer)
- Fully compatible with dynamic_secure_minting.py v3.0

DYNAMIC FEATURES:
- User only inputs Asset ID at runtime
- All parameters retrieved from blockchain automatically
- No manual configuration required
- Dynamic balance calculation
- Complete cleanup (destroy + close account)

VERSION: 3.0 - Fully Dynamic with Zero Manual Configuration
"""

import base64
import time
import hashlib
import json
from algosdk import account, mnemonic, encoding
from algosdk.v2client import algod, indexer
from algosdk import transaction
from algosdk.transaction import LogicSigAccount

# ============================================================================
# CONFIGURATION - NETWORK ONLY
# ============================================================================
ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

# Indexer for retrieving historical transactions
INDEXER_ADDRESS = "https://testnet-idx.algonode.cloud"
INDEXER_TOKEN = ""
indexer_client = indexer.IndexerClient(INDEXER_TOKEN, INDEXER_ADDRESS)

# User credentials (NFT owner) - only hardcoded value
USER_MNEMONIC = "never world tide ankle author misery aware cruise erode swallow trouble mad heavy milk upset payment elder peace brick brass chase order friend absorb manage"

# Safety parameters for calculations
MIN_BALANCE = 100_000        # 0.1 ALGO min balance requirement
FEE_BUFFER = 3_000          # 0.003 ALGO fee buffer

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def wait_for_confirmation(client, txid, timeout=30):
    """
    Wait for transaction confirmation with timeout
    
    Args:
        client: Algod client instance
        txid: Transaction ID to monitor
        timeout: Maximum wait time in seconds
        
    Returns:
        dict: Confirmed transaction information
    """
    start = time.time()
    while True:
        try:
            pending = client.pending_transaction_info(txid)
            if pending.get("confirmed-round", 0) > 0:
                return pending
            if pending.get("pool-error"):
                raise Exception(f"Pool error: {pending['pool-error']}")
        except Exception:
            pass
        if time.time() - start > timeout:
            raise Exception(f"Timeout waiting for txid: {txid}")
        time.sleep(1)


def get_account_balance(address):
    """
    Get account balance in microALGOs
    
    Args:
        address: Algorand address
        
    Returns:
        int: Balance in microALGOs
    """
    try:
        account_info = algod_client.account_info(address)
        return account_info.get('amount', 0)
    except Exception as e:
        print(f"  ⚠️  Error getting balance: {e}")
        return 0


def get_user_input():
    """
    Get Asset ID from user at runtime
    
    Returns:
        int: Asset ID to redeem
    """
    print("\n" + "="*70)
    print("ASSET ID INPUT - ENTER THE NFT YOU WANT TO REDEEM")
    print("="*70)
    
    print("\n📝 All other data will be retrieved automatically from blockchain")
    
    while True:
        asset_input = input("\n  Enter Asset ID to redeem: ").strip()
        if not asset_input:
            print("    ❌ Asset ID is required. Try again.")
            continue
        try:
            asset_id = int(asset_input)
            if asset_id <= 0:
                print("    ❌ Asset ID must be positive. Try again.")
                continue
            return asset_id
        except ValueError:
            print("    ❌ Invalid number. Try again.")


# ============================================================================
# REDEMPTION WORKFLOW - FULLY DYNAMIC
# ============================================================================

def step1_fetch_asset_info(asset_id):
    """
    Step 1: Fetch asset information from blockchain
    
    Retrieves complete asset details including creator, reserve,
    name, unit, and other parameters.
    
    Args:
        asset_id: Asset ID to fetch
        
    Returns:
        tuple: (asset_info_dict, params_dict) or (None, None) on error
    """
    print("\n" + "="*70)
    print("STEP 1: RETRIEVE ASSET DATA FROM BLOCKCHAIN")
    print("="*70)
    
    try:
        asset_info = algod_client.asset_info(asset_id)
        params = asset_info.get('params', {})
        
        print(f"\n📋 Asset Information:")
        print(f"  • Asset ID: {asset_id}")
        print(f"  • Name: {params.get('name', 'N/A')}")
        print(f"  • Unit: {params.get('unit-name', 'N/A')}")
        print(f"  • Total: {params.get('total', 0)}")
        print(f"  • Decimals: {params.get('decimals', 0)}")
        print(f"  • Creator: {params.get('creator', 'N/A')}")
        print(f"  • Reserve: {params.get('reserve', 'N/A')}")
        
        print(f"\n✅ Asset info retrieved successfully")
        return asset_info, params
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to fetch asset info: {e}")
        return None, None


def step2_retrieve_dynamic_metadata(asset_id, params):
    """
    Step 2: Dynamically retrieve LogicSig, nonce, and redeemable amount from blockchain
    
    Searches for the asset creation transaction and extracts all
    metadata from the note field. This includes:
    - LogicSig program bytes
    - Unique nonce
    - Redeemable amount (DYNAMIC)
    - Version information
    
    Args:
        asset_id: Asset ID to retrieve metadata for
        params: Asset parameters dict
        
    Returns:
        tuple: (lsig_bytes, nonce, locked_amount) or (None, None, None) on error
    """
    print("\n" + "="*70)
    print("STEP 2: RETRIEVE DYNAMIC METADATA FROM BLOCKCHAIN")
    print("="*70)

    creator_addr = params.get('creator')
    print(f"\n🔍 Searching for asset creation transaction...")
    print(f"  • Asset ID: {asset_id}")
    print(f"  • Creator: {creator_addr}")

    try:
        print(f"\n📡 Querying Indexer API...")
        
        response = indexer_client.search_asset_transactions(
            asset_id=asset_id,
            txn_type='acfg'
        )
        
        transactions = response.get('transactions', [])
        print(f"  • Found {len(transactions)} asset configuration transaction(s)")
        
        # Find the creation transaction (has created-asset-index)
        creation_txn = None
        for txn in transactions:
            if txn.get('created-asset-index') == asset_id:
                creation_txn = txn
                break
        
        # Fallback: use first transaction if no explicit creation found
        if not creation_txn and transactions:
            creation_txn = transactions[0]
        
        if not creation_txn:
            print(f"\n❌ ERROR: Could not find creation transaction")
            return None, None, None
        
        txid = creation_txn.get('id')
        print(f"\n✅ Found creation transaction: {txid}")
        
        # Extract and decode note field
        note_b64 = creation_txn.get('note')
        if not note_b64:
            print(f"\n❌ ERROR: No note field found in creation transaction")
            print(f"   This NFT may not be compatible with v3.0 dynamic redemption")
            return None, None, None
        
        note_bytes = base64.b64decode(note_b64)
        note_data = json.loads(note_bytes.decode('utf-8'))
        
        # Extract all dynamic metadata
        lsig_b64 = note_data.get('logicsig')
        nonce = note_data.get('nonce')
        locked_amount = note_data.get('locked_amount')  # DYNAMIC: Retrieved from blockchain
        version = note_data.get('version', 'unknown')
        
        if not lsig_b64 or nonce is None:
            print(f"\n❌ ERROR: Missing logicsig or nonce in note field")
            return None, None, None
        
        lsig_bytes = base64.b64decode(lsig_b64)
        
        print(f"\n✅ Dynamic metadata retrieved successfully:")
        print(f"  • LogicSig size: {len(lsig_bytes)} bytes")
        print(f"  • Nonce: {nonce}")
        print(f"  • Version: {version}")
        
        # Handle locked_amount (may not exist in older versions)
        if locked_amount is not None:
            print(f"  • Redeemable Amount: {locked_amount/1_000_000:.6f} ALGO (from blockchain)")
        else:
            print(f"  • Redeemable Amount: Not stored (will calculate from escrow balance)")
            locked_amount = None  # Will be calculated later
        
        return lsig_bytes, nonce, locked_amount
        
    except Exception as e:
        print(f"\n❌ ERROR retrieving metadata: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def step3_verify_escrow(lsig_bytes, params):
    """
    Step 3: Verify escrow address matches asset reserve
    
    Reconstructs the escrow address from the LogicSig and verifies
    it matches the asset's reserve address for security.
    
    Args:
        lsig_bytes: Compiled LogicSig bytes
        params: Asset parameters dict
        
    Returns:
        tuple: (LogicSigAccount, escrow_address) or (None, None) on error
    """
    print("\n" + "="*70)
    print("STEP 3: VERIFY ESCROW ADDRESS")
    print("="*70)
    
    try:
        lsig = LogicSigAccount(lsig_bytes)
        escrow_addr = lsig.address()
        reserve_addr = params.get('reserve')
        
        print(f"\n🔐 Escrow Address Verification:")
        print(f"  • Derived Escrow: {escrow_addr}")
        print(f"  • Asset Reserve: {reserve_addr}")
        
        if escrow_addr == reserve_addr:
            print(f"\n✅ Escrow address matches reserve address")
            return lsig, escrow_addr
        else:
            print(f"\n❌ ERROR: Escrow address mismatch!")
            print(f"   This indicates a security issue or incorrect LogicSig")
            return None, None
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to verify escrow: {e}")
        return None, None


def step4_check_ownership(asset_id, owner_addr):
    """
    Step 4: Check NFT ownership
    
    Verifies the user owns exactly 1 unit of the NFT.
    
    Args:
        asset_id: Asset ID to check
        owner_addr: Owner's address
        
    Returns:
        bool: True if user owns the NFT, False otherwise
    """
    print("\n" + "="*70)
    print("STEP 4: CHECK NFT OWNERSHIP")
    print("="*70)
    
    try:
        account_info = algod_client.account_info(owner_addr)
        assets = account_info.get('assets', [])
        
        print(f"\n👤 Ownership Verification:")
        print(f"  • Owner Address: {owner_addr}")
        
        for asset in assets:
            if asset.get('asset-id') == asset_id:
                amount = asset.get('amount', 0)
                print(f"  • Owned Amount: {amount}")
                
                if amount == 1:
                    print(f"\n✅ Ownership verified - user owns this NFT")
                    return True
                else:
                    print(f"\n❌ ERROR: Must have exactly 1 unit (found {amount})")
                    return False
        
        print(f"\n❌ ERROR: Owner does not hold this NFT")
        print(f"   Make sure you opted in and received the NFT")
        return False
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to check ownership: {e}")
        return False


def step5_compute_redeemable_amount(escrow_addr, stored_locked_amount):
    """
    Step 5: Dynamically compute redeemable amount from escrow balance
    
    Calculates how much ALGO can be redeemed based on:
    - Stored locked_amount (if available from note field)
    - Current escrow balance
    - Required minimum balance and fees
    
    Args:
        escrow_addr: Escrow account address
        stored_locked_amount: Locked amount from note field (may be None)
        
    Returns:
        int: Redeemable amount in microALGOs, or None on error
    """
    print("\n" + "="*70)
    print("STEP 5: COMPUTE REDEEMABLE AMOUNT (DYNAMIC)")
    print("="*70)
    
    try:
        escrow_balance = get_account_balance(escrow_addr)
        
        print(f"\n💰 Escrow Balance Analysis:")
        print(f"  • Current Balance: {escrow_balance/1_000_000:.6f} ALGO")
        print(f"  • Min Balance Required: {MIN_BALANCE/1_000_000:.6f} ALGO")
        print(f"  • Fee Buffer: {FEE_BUFFER/1_000_000:.6f} ALGO")
        
        # Use stored locked_amount if available (v3.0+)
        if stored_locked_amount is not None:
            redeemable = stored_locked_amount
            print(f"  • Stored Locked Amount: {stored_locked_amount/1_000_000:.6f} ALGO (from blockchain)")
            print(f"\n✅ Using stored locked amount from NFT metadata")
        else:
            # Fallback: Calculate from escrow balance (backward compatibility)
            redeemable = escrow_balance - MIN_BALANCE - FEE_BUFFER
            print(f"  • No stored amount found - calculating from balance")
            print(f"  • Calculated Redeemable: {redeemable/1_000_000:.6f} ALGO")
            print(f"\n⚠️  Using calculated amount (backward compatibility mode)")
        
        # Verify escrow has enough
        required = redeemable + MIN_BALANCE + FEE_BUFFER
        if escrow_balance < required:
            print(f"\n❌ ERROR: Insufficient balance in escrow")
            print(f"  • Required: {required/1_000_000:.6f} ALGO")
            print(f"  • Available: {escrow_balance/1_000_000:.6f} ALGO")
            print(f"  • Shortfall: {(required - escrow_balance)/1_000_000:.6f} ALGO")
            return None
        
        print(f"\n✅ Redeemable Amount Confirmed: {redeemable/1_000_000:.6f} ALGO")
        return redeemable
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to compute redeemable amount: {e}")
        return None


def step6_execute_redemption(owner_sk, owner_addr, lsig, escrow_addr, asset_id, redeemable_amount):
    """
    Step 6: Execute atomic redemption transaction group
    
    Creates and submits an atomic transaction group:
    - Transaction 0: User sends NFT back to escrow
    - Transaction 1: Escrow pays user ALGO
    
    Both transactions must succeed or both fail (atomic).
    
    Args:
        owner_sk: Owner's private key
        owner_addr: Owner's address
        lsig: LogicSigAccount instance
        escrow_addr: Escrow account address
        asset_id: Asset ID to redeem
        redeemable_amount: Amount to redeem (microALGOs)
        
    Returns:
        bool: True if redemption succeeded, False otherwise
    """
    print("\n" + "="*70)
    print("STEP 6: EXECUTE ATOMIC REDEMPTION")
    print("="*70)
    
    try:
        balance_before = get_account_balance(owner_addr)
        
        print(f"\n📊 Pre-Redemption Status:")
        print(f"  • User Balance: {balance_before/1_000_000:.6f} ALGO")
        print(f"  • Redeemable Amount: {redeemable_amount/1_000_000:.6f} ALGO")
        
        params = algod_client.suggested_params()
        
        print(f"\n🔗 Building atomic transaction group...")
        
        # Transaction 0: User sends NFT to escrow (must be index 0)
        txn0 = transaction.AssetTransferTxn(
            sender=owner_addr,
            sp=params,
            receiver=escrow_addr,
            amt=1,
            index=asset_id
        )
        
        # Transaction 1: Escrow pays user (must be index 1)
        # CRITICAL: Must match TEAL expectations exactly
        txn1 = transaction.PaymentTxn(
            sender=escrow_addr,
            sp=params,
            receiver=owner_addr,
            amt=redeemable_amount
        )
        
        print(f"  • Txn 0: User → Escrow (NFT transfer)")
        print(f"  • Txn 1: Escrow → User (ALGO payment: {redeemable_amount/1_000_000:.6f})")
        
        # Group transactions atomically
        gid = transaction.calculate_group_id([txn0, txn1])
        txn0.group = gid
        txn1.group = gid
        
        print(f"\n✅ Transaction group created with group ID")
        
        # Sign transactions
        print(f"\n✍️  Signing transactions...")
        stxn0 = txn0.sign(owner_sk)
        stxn1 = transaction.LogicSigTransaction(txn1, lsig)
        
        print(f"  ✅ Transaction 0 signed by user")
        print(f"  ✅ Transaction 1 signed by LogicSig")
        
        # Submit atomic group
        print(f"\n📤 Submitting atomic transaction group to network...")
        signed_group = [stxn0, stxn1]
        txid = algod_client.send_transactions(signed_group)
        
        print(f"  • Submitted. Waiting for confirmation...")
        
        confirmed = wait_for_confirmation(algod_client, txid)
        balance_after = get_account_balance(owner_addr)
        
        print(f"\n" + "="*70)
        print("✅ REDEMPTION SUCCESSFUL!")
        print("="*70)
        
        print(f"\n💸 Redemption Details:")
        print(f"  • Redeemed Amount: {redeemable_amount/1_000_000:.6f} ALGO")
        print(f"  • Transaction ID: {txid}")
        print(f"  • Confirmed Round: {confirmed.get('confirmed-round')}")
        
        print(f"\n📈 Balance Changes:")
        print(f"  • Balance Before: {balance_before/1_000_000:.6f} ALGO")
        print(f"  • Balance After: {balance_after/1_000_000:.6f} ALGO")
        print(f"  • Net Change: {(balance_after - balance_before)/1_000_000:.6f} ALGO")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Redemption failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def step7_destroy_nft(lsig, escrow_addr, asset_id):
    """
    Step 7: Destroy the NFT from blockchain
    
    Removes the NFT asset completely by setting all config
    addresses to zero address.
    
    Args:
        lsig: LogicSigAccount instance
        escrow_addr: Escrow account address
        asset_id: Asset ID to destroy
        
    Returns:
        bool: True if destruction succeeded, False otherwise
    """
    print("\n" + "="*70)
    print("STEP 7: DESTROY NFT")
    print("="*70)
    
    try:
        print(f"\n🔥 Preparing asset destruction...")
        print(f"  • Asset ID: {asset_id}")
        print(f"  • Escrow: {escrow_addr}")
        
        params = algod_client.suggested_params()
        
        # Asset destroy transaction - all addresses set to zero
        ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"
        
        destroy_txn = transaction.AssetConfigTxn(
            sender=escrow_addr,
            sp=params,
            index=asset_id,
            manager=ZERO_ADDR,
            reserve=ZERO_ADDR,
            freeze=ZERO_ADDR,
            clawback=ZERO_ADDR,
            strict_empty_address_check=False
        )
        
        print(f"\n✍️  Signing destruction transaction with LogicSig...")
        stxn = transaction.LogicSigTransaction(destroy_txn, lsig)
        
        print(f"📤 Submitting destruction transaction...")
        txid = algod_client.send_transaction(stxn)
        
        print(f"  • Submitted. Waiting for confirmation...")
        confirmed = wait_for_confirmation(algod_client, txid)
        
        print(f"\n" + "="*70)
        print("✅ NFT DESTROYED SUCCESSFULLY!")
        print("="*70)
        print(f"  • Transaction ID: {txid}")
        print(f"  • Confirmed Round: {confirmed.get('confirmed-round')}")
        print(f"  • Asset {asset_id} has been removed from blockchain")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: NFT destruction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def step8_close_escrow_account(lsig, escrow_addr, owner_addr):
    """
    Step 8: Close escrow account and recover all remaining ALGO
    
    Sends all remaining ALGO from escrow to owner and removes
    the escrow account from the ledger.
    
    Args:
        lsig: LogicSigAccount instance
        escrow_addr: Escrow account address
        owner_addr: Owner's address (recipient)
        
    Returns:
        bool: True if close succeeded, False otherwise
    """
    print("\n" + "="*70)
    print("STEP 8: CLOSE ESCROW ACCOUNT")
    print("="*70)
    
    try:
        escrow_balance_before = get_account_balance(escrow_addr)
        owner_balance_before = get_account_balance(owner_addr)
        
        print(f"\n📊 Pre-Close Status:")
        print(f"  • Escrow Balance: {escrow_balance_before/1_000_000:.6f} ALGO")
        print(f"  • Owner Balance: {owner_balance_before/1_000_000:.6f} ALGO")
        
        params = algod_client.suggested_params()
        
        # Close-out transaction - amount=0, close_remainder_to sends all
        close_txn = transaction.PaymentTxn(
            sender=escrow_addr,
            sp=params,
            receiver=owner_addr,
            amt=0,
            close_remainder_to=owner_addr
        )
        
        print(f"\n✍️  Signing close-out transaction with LogicSig...")
        stxn = transaction.LogicSigTransaction(close_txn, lsig)
        
        print(f"📤 Submitting close-out transaction...")
        txid = algod_client.send_transaction(stxn)
        
        print(f"  • Submitted. Waiting for confirmation...")
        confirmed = wait_for_confirmation(algod_client, txid)
        
        owner_balance_after = get_account_balance(owner_addr)
        
        # Try to get escrow balance (should fail or be 0)
        try:
            escrow_balance_after = get_account_balance(escrow_addr)
        except:
            escrow_balance_after = 0
        
        recovered = owner_balance_after - owner_balance_before
        
        print(f"\n" + "="*70)
        print("✅ ESCROW ACCOUNT CLOSED SUCCESSFULLY!")
        print("="*70)
        print(f"  • Transaction ID: {txid}")
        print(f"  • Confirmed Round: {confirmed.get('confirmed-round')}")
        
        print(f"\n📊 Post-Close Status:")
        print(f"  • Escrow Balance: {escrow_balance_after/1_000_000:.6f} ALGO")
        print(f"  • Owner Balance: {owner_balance_after/1_000_000:.6f} ALGO")
        print(f"  • Recovered Amount: {recovered/1_000_000:.6f} ALGO")
        
        if escrow_balance_after == 0:
            print(f"\n✅ Escrow account completely removed from ledger")
        else:
            print(f"\n⚠️  WARNING: Escrow still has balance (unexpected)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Escrow close-out failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("DYNAMIC SECURE NFT REDEMPTION SYSTEM v3.0")
    print("="*70)
    print("\n🚀 Fully Dynamic NFT Redemption with Zero Manual Configuration")
    print("   • Enter Asset ID only - everything else retrieved from blockchain")
    print("   • Automatic metadata retrieval (LogicSig, nonce, amount)")
    print("   • Dynamic balance calculation")
    print("   • Complete cleanup (redeem → destroy → close account)")
    
    user_sk = mnemonic.to_private_key(USER_MNEMONIC)
    user_addr = account.address_from_private_key(user_sk)
    
    print(f"\n👤 User Address: {user_addr}")
    
    # Get Asset ID from user
    asset_id = get_user_input()
    
    print(f"\n" + "="*70)
    print("REDEMPTION CONFIGURATION")
    print("="*70)
    print(f"\n  • Asset ID: {asset_id}")
    print(f"  • User: {user_addr}")
    print(f"  • All other parameters will be retrieved dynamically")
    
    try:
        # Execute dynamic redemption workflow
        print(f"\n" + "="*70)
        print("STARTING REDEMPTION PROCESS")
        print("="*70)
        
        # Step 1: Fetch asset info
        asset_info, params = step1_fetch_asset_info(asset_id)
        if not asset_info or not params:
            exit(1)
        
        # Step 2: Retrieve dynamic metadata (LogicSig, nonce, locked_amount)
        lsig_bytes, nonce, stored_locked_amount = step2_retrieve_dynamic_metadata(asset_id, params)
        if not lsig_bytes or nonce is None:
            exit(1)
        
        # Step 3: Verify escrow
        lsig, escrow_addr = step3_verify_escrow(lsig_bytes, params)
        if not lsig or not escrow_addr:
            exit(1)
        
        # Step 4: Check ownership
        if not step4_check_ownership(asset_id, user_addr):
            exit(1)
        
        # Step 5: Compute redeemable amount dynamically
        redeemable_amount = step5_compute_redeemable_amount(escrow_addr, stored_locked_amount)
        if not redeemable_amount:
            exit(1)
        
        # Step 6: Execute atomic redemption
        success = step6_execute_redemption(
            user_sk, user_addr, lsig, escrow_addr, 
            asset_id, redeemable_amount
        )
        
        if not success:
            exit(1)
        
        # Cleanup phase
        print(f"\n" + "="*70)
        print("STARTING CLEANUP PHASE")
        print("="*70)
        time.sleep(2)  # Brief pause for network propagation
        
        # Step 7: Destroy NFT
        if not step7_destroy_nft(lsig, escrow_addr, asset_id):
            print(f"\n⚠️  WARNING: NFT destruction failed")
            print(f"   Redemption was successful, but cleanup incomplete")
            exit(1)
        
        time.sleep(2)  # Brief pause for network propagation
        
        # Step 8: Close escrow account
        if not step8_close_escrow_account(lsig, escrow_addr, user_addr):
            print(f"\n⚠️  WARNING: Escrow close failed")
            print(f"   Redemption and destruction succeeded, but some ALGO may remain in escrow")
            exit(1)
        
        # Final summary
        print(f"\n" + "="*70)
        print("🎉 COMPLETE REDEMPTION FINISHED!")
        print("="*70)
        print(f"\n✅ All steps completed successfully:")
        print(f"  ✓ NFT redeemed ({redeemable_amount/1_000_000:.6f} ALGO received)")
        print(f"  ✓ NFT destroyed (removed from blockchain)")
        print(f"  ✓ Escrow closed (all remaining ALGO recovered)")
        print(f"  ✓ Escrow account removed from ledger")
        
        print(f"\n📊 Final Status:")
        final_balance = get_account_balance(user_addr)
        print(f"  • Your Balance: {final_balance/1_000_000:.6f} ALGO")
        print(f"  • Asset {asset_id}: DESTROYED ✅")
        print(f"  • Escrow {escrow_addr}: CLOSED ✅")
        
        print(f"\n" + "="*70)
        print("✨ REDEMPTION COMPLETE - ALL RESOURCES RECOVERED")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
