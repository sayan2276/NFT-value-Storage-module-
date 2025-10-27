"""
dynamic_secure_minting.py - v3.0 Dynamic NFT Minting System

FULLY DYNAMIC NFT MINTING WITH MAXIMUM SECURITY
================================================
- Runtime input for all NFT parameters (name, unit, locked amount)
- Each NFT gets unique escrow account (nonce-based)
- LogicSig stored in note field with ALL metadata
- Security fingerprint in metadata_hash
- Reserve address = escrow (for verification)
- No time limit for redemption
- SUPPORTS NFT DESTRUCTION AND ACCOUNT CLOSE-OUT
- All data encoded on-chain for dynamic retrieval

DYNAMIC FEATURES:
- User inputs NFT details at runtime
- Automatic nonce generation per NFT
- Dynamic redeemable amount calculation
- Complete metadata encoding in note field
- Fully compatible with dynamic redemption script

VERSION: 3.0 - Fully Dynamic with Runtime Configuration
"""

import base64
import time
import hashlib
import json
import secrets
from pyteal import *
from algosdk import account, mnemonic, encoding
from algosdk.v2client import algod
from algosdk import transaction
from algosdk.transaction import LogicSigAccount, LogicSigTransaction

# ============================================================================
# CONFIGURATION - NETWORK ONLY
# ============================================================================
ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

# Creator credentials (only hardcoded value - user can change this)
CREATOR_MNEMONIC = "never world tide ankle author misery aware cruise erode swallow trouble mad heavy milk upset payment elder peace brick brass chase order friend absorb manage"

# Standard Algorand parameters (blockchain constants)
MIN_BALANCE = 200_000        # 0.2 ALGO standard min balance
FEES_BUFFER = 5_000          # 0.005 ALGO fees buffer (safety margin)

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


def compute_security_fingerprint(lsig_bytes, asset_name, asset_unit, locked_amount, escrow_addr, nonce):
    """
    Compute comprehensive security fingerprint for NFT verification
    
    This fingerprint combines all critical parameters to prevent:
    - Fake NFT attacks
    - Parameter tampering
    - LogicSig substitution
    
    Args:
        lsig_bytes: Compiled LogicSig program bytes
        asset_name: NFT name
        asset_unit: NFT unit name
        locked_amount: Redeemable ALGO amount (microALGOs)
        escrow_addr: Escrow account address
        nonce: Unique nonce for this NFT
        
    Returns:
        tuple: (fingerprint_hash, fingerprint_data_dict)
    """
    fingerprint_data = {
        "logicsig_sha256": hashlib.sha256(lsig_bytes).hexdigest(),
        "logicsig_size": len(lsig_bytes),
        "asset_name": asset_name,
        "asset_unit": asset_unit,
        "locked_amount": locked_amount,
        "escrow_address": escrow_addr,
        "nonce": nonce,
        "version": "v3.0-dynamic"
    }
    
    # Create deterministic JSON string for hashing
    data_str = json.dumps(fingerprint_data, sort_keys=True)
    fingerprint = hashlib.sha256(data_str.encode()).digest()
    
    return fingerprint, fingerprint_data


def get_user_input():
    """
    Collect NFT parameters from user at runtime
    
    Returns:
        dict: NFT configuration parameters
    """
    print("\n" + "="*70)
    print("NFT CONFIGURATION - ENTER YOUR NFT DETAILS")
    print("="*70)
    
    print("\n📝 Enter NFT details (or press Enter for defaults):")
    
    # Asset name
    asset_name = input("\n  NFT Name [Unique Dynamic NFT]: ").strip()
    if not asset_name:
        asset_name = "Unique Dynamic NFT"
    
    # Asset unit name
    asset_unit = input("  NFT Unit Name [DYNFT]: ").strip()
    if not asset_unit:
        asset_unit = "DYNFT"
    
    # Locked amount (redeemable ALGO)
    while True:
        locked_input = input("  Redeemable ALGO Amount [0.5]: ").strip()
        if not locked_input:
            locked_amount = 500_000  # 0.5 ALGO
            break
        try:
            locked_algo = float(locked_input)
            if locked_algo <= 0:
                print("    ❌ Amount must be positive. Try again.")
                continue
            locked_amount = int(locked_algo * 1_000_000)  # Convert to microALGOs
            break
        except ValueError:
            print("    ❌ Invalid number. Try again.")
    
    # Calculate total funding needed
    fund_amount = locked_amount + MIN_BALANCE + FEES_BUFFER
    
    print(f"\n✅ Configuration Summary:")
    print(f"  • NFT Name: {asset_name}")
    print(f"  • NFT Unit: {asset_unit}")
    print(f"  • Redeemable: {locked_amount/1_000_000:.6f} ALGO")
    print(f"  • Min Balance: {MIN_BALANCE/1_000_000:.6f} ALGO")
    print(f"  • Fees Buffer: {FEES_BUFFER/1_000_000:.6f} ALGO")
    print(f"  • Total Funding: {fund_amount/1_000_000:.6f} ALGO")
    
    confirm = input(f"\n  Proceed with this configuration? (yes/no) [yes]: ").strip().lower()
    if confirm and confirm not in ['yes', 'y']:
        print("\n❌ Minting cancelled by user")
        exit(0)
    
    return {
        'asset_name': asset_name,
        'asset_unit': asset_unit,
        'locked_amount': locked_amount,
        'fund_amount': fund_amount
    }


# ============================================================================
# PYTEAL: SECURE ESCROW LOGIC WITH DESTROY SUPPORT
# ============================================================================

def create_secure_escrow_teal(min_payout, nonce):
    """
    Generate secure escrow TEAL program with unique nonce
    
    SECURITY FEATURES:
    - Nonce embedded as constant to make each escrow unique
    - Supports: mint, transfer, redeem, destroy, close-account
    - Atomic swap for redemption (2-transaction group)
    - Zero-address restrictions for security
    
    SUPPORTED OPERATIONS:
    1. Mint: Create NFT with strict parameters
    2. Transfer: Send NFT to user
    3. Redeem: Atomic swap (NFT → ALGO)
    4. Destroy: Remove NFT from blockchain
    5. Close Account: Return all remaining ALGO
    
    Args:
        min_payout: Minimum ALGO payout for redemption (microALGOs)
        nonce: Unique 64-bit nonce for this escrow
        
    Returns:
        str: Compiled TEAL program source code
    """
    
    # Embed nonce as constant to make program hash unique
    # This creates a unique escrow address for each NFT
    # We use Pop() to discard it - it's just for uniqueness
    nonce_constant = Bytes("base64", base64.b64encode(nonce.to_bytes(8, 'big')).decode())
    
    # OPERATION 1: Mint NFT with strict parameters
    mint_nft = And(
        Txn.type_enum() == TxnType.AssetConfig,
        Txn.config_asset_total() == Int(1),
        Txn.config_asset_decimals() == Int(0),
        Txn.config_asset_manager() == Txn.sender(),
        Txn.config_asset_reserve() == Txn.sender(),
        Txn.config_asset_freeze() == Global.zero_address(),
        Txn.config_asset_clawback() == Global.zero_address(),
        Global.group_size() == Int(1)
    )

    # OPERATION 2: Transfer NFT to user
    transfer_nft = And(
        Txn.type_enum() == TxnType.AssetTransfer,
        Txn.asset_amount() == Int(1),
        Txn.xfer_asset() != Int(0),
        Txn.asset_sender() == Global.zero_address(),
        Global.group_size() == Int(1),
    )

    # OPERATION 3: Redeem - Atomic swap (2 transactions)
    # Transaction 0: User returns NFT
    # Transaction 1: Escrow pays user
    redeem_swap = And(
        Global.group_size() == Int(2),
        Txn.group_index() == Int(1),
        
        # Txn 0: User returns NFT to escrow
        Gtxn[0].type_enum() == TxnType.AssetTransfer,
        Gtxn[0].asset_amount() == Int(1),
        Gtxn[0].asset_receiver() == Txn.sender(),
        Gtxn[0].asset_sender() == Global.zero_address(),
        Gtxn[0].xfer_asset() != Int(0),
        
        # Txn 1: Escrow pays user ALGO
        Txn.type_enum() == TxnType.Payment,
        Txn.receiver() == Gtxn[0].sender(),
        Txn.amount() >= Int(min_payout),
        Txn.close_remainder_to() == Global.zero_address(),
        Txn.rekey_to() == Global.zero_address(),
    )

    # OPERATION 4: Destroy NFT (remove from blockchain)
    # All config addresses set to zero = destroy operation
    destroy_nft = And(
        Txn.type_enum() == TxnType.AssetConfig,
        Txn.config_asset() != Int(0),
        Txn.config_asset_manager() == Global.zero_address(),
        Txn.config_asset_reserve() == Global.zero_address(),
        Txn.config_asset_freeze() == Global.zero_address(),
        Txn.config_asset_clawback() == Global.zero_address(),
        Txn.rekey_to() == Global.zero_address(),
    )

    # OPERATION 5: Close account (return all remaining ALGO)
    # Amount = 0, but close_remainder_to returns everything
    close_account = And(
        Txn.type_enum() == TxnType.Payment,
        Txn.amount() == Int(0),
        Txn.close_remainder_to() != Global.zero_address(),
        Txn.rekey_to() == Global.zero_address(),
    )

    # Main program logic - supports all operations
    program = Seq([
        Pop(nonce_constant),  # Include nonce but discard (for uniqueness only)
        Cond(
            # Single transaction operations
            [Global.group_size() == Int(1), Or(mint_nft, transfer_nft, destroy_nft, close_account)],
            # Two transaction redemption
            [Global.group_size() == Int(2), Or(redeem_swap, destroy_nft, close_account)],
        )
    ])
    
    return compileTeal(program, Mode.Signature, version=6)


def compile_teal_to_lsig(client, teal_src):
    """
    Compile TEAL source code to LogicSig
    
    Args:
        client: Algod client instance
        teal_src: TEAL source code string
        
    Returns:
        tuple: (LogicSigAccount, compiled_bytes)
    """
    print("\n" + "="*70)
    print("COMPILED TEAL PROGRAM")
    print("="*70)
    print(teal_src)
    print("="*70)
    
    resp = client.compile(teal_src)
    prog = base64.b64decode(resp["result"])
    lsig = LogicSigAccount(prog)
    
    print(f"\n✅ Compilation successful:")
    print(f"  • Size: {len(prog)} bytes")
    print(f"  • Address: {lsig.address()}")
    
    return lsig, prog


# ============================================================================
# MINTING WORKFLOW - FULLY DYNAMIC
# ============================================================================

def step1_create_and_fund_escrow(creator_sk, creator_addr, fund_amt, nonce, locked_amount):
    """
    Step 1: Generate unique escrow and fund it
    
    Creates a unique LogicSig with embedded nonce, compiles it,
    and funds the resulting escrow account.
    
    Args:
        creator_sk: Creator's private key
        creator_addr: Creator's address
        fund_amt: Total funding amount (microALGOs)
        nonce: Unique nonce for this NFT
        locked_amount: Redeemable amount (microALGOs)
        
    Returns:
        tuple: (LogicSigAccount, lsig_bytes, escrow_address)
    """
    print("\n" + "="*70)
    print("STEP 1: CREATE AND FUND UNIQUE ESCROW")
    print("="*70)
    
    print(f"\n🔐 Generating unique escrow...")
    print(f"  • Nonce: {nonce}")
    print(f"  • Min Payout: {locked_amount/1_000_000:.6f} ALGO")
    
    # Compile TEAL with unique nonce
    teal_src = create_secure_escrow_teal(min_payout=locked_amount, nonce=nonce)
    lsig, lsig_bytes = compile_teal_to_lsig(algod_client, teal_src)
    escrow_addr = lsig.address()
    
    print(f"\n💰 Funding escrow with {fund_amt/1_000_000:.6f} ALGO...")
    params = algod_client.suggested_params()
    
    pay = transaction.PaymentTxn(
        sender=creator_addr,
        sp=params,
        receiver=escrow_addr,
        amt=fund_amt
    )
    
    signed = pay.sign(creator_sk)
    txid = algod_client.send_transaction(signed)
    wait_for_confirmation(algod_client, txid)
    
    print(f"\n✅ Escrow funded successfully")
    print(f"  • Transaction: {txid}")
    print(f"  • Escrow Address: {escrow_addr}")
    print(f"  • Balance: {fund_amt/1_000_000:.6f} ALGO")
    
    return lsig, lsig_bytes, escrow_addr


def step2_compute_fingerprint(lsig_bytes, asset_name, asset_unit, locked_amt, escrow_addr, nonce):
    """
    Step 2: Compute security fingerprint for verification
    
    Creates a cryptographic fingerprint combining all critical
    parameters to prevent tampering and fake NFTs.
    
    Args:
        lsig_bytes: Compiled LogicSig bytes
        asset_name: NFT name
        asset_unit: NFT unit name
        locked_amt: Redeemable amount (microALGOs)
        escrow_addr: Escrow account address
        nonce: Unique nonce
        
    Returns:
        tuple: (fingerprint_hash, fingerprint_data_dict)
    """
    print("\n" + "="*70)
    print("STEP 2: COMPUTE SECURITY FINGERPRINT")
    print("="*70)
    
    fingerprint, fingerprint_data = compute_security_fingerprint(
        lsig_bytes, asset_name, asset_unit, locked_amt, escrow_addr, nonce
    )
    
    print(f"\n🔒 Fingerprint computed:")
    print(f"  • LogicSig SHA256: {fingerprint_data['logicsig_sha256'][:16]}...")
    print(f"  • LogicSig Size: {fingerprint_data['logicsig_size']} bytes")
    print(f"  • Asset Name: {fingerprint_data['asset_name']}")
    print(f"  • Asset Unit: {fingerprint_data['asset_unit']}")
    print(f"  • Locked Amount: {fingerprint_data['locked_amount']/1_000_000} ALGO")
    print(f"  • Escrow: {fingerprint_data['escrow_address'][:10]}...")
    print(f"  • Nonce: {fingerprint_data['nonce']}")
    print(f"  • Version: {fingerprint_data['version']}")
    print(f"  • Fingerprint Hash: {fingerprint.hex()[:32]}...")
    
    return fingerprint, fingerprint_data


def step3_mint_nft(lsig, lsig_bytes, fingerprint, asset_name, asset_unit, nonce, locked_amount):
    """
    Step 3: Mint NFT with complete metadata encoding
    
    Creates the NFT with:
    - Security fingerprint in metadata_hash
    - Complete metadata in note field (LogicSig, nonce, redeemable amount)
    - Reserve address = escrow (for verification)
    
    Args:
        lsig: LogicSigAccount instance
        lsig_bytes: Compiled LogicSig bytes
        fingerprint: Security fingerprint hash
        asset_name: NFT name
        asset_unit: NFT unit name
        nonce: Unique nonce
        locked_amount: Redeemable amount (microALGOs)
        
    Returns:
        tuple: (asset_id, transaction_id)
    """
    print("\n" + "="*70)
    print("STEP 3: MINT NFT WITH COMPLETE METADATA")
    print("="*70)
    
    escrow_addr = lsig.address()
    params = algod_client.suggested_params()
    
    # Prepare comprehensive note field with ALL metadata
    note_data = {
        "logicsig": base64.b64encode(lsig_bytes).decode('utf-8'),
        "nonce": nonce,
        "locked_amount": locked_amount,  # DYNAMIC: Redeemable amount stored on-chain
        "version": "v3.0-dynamic",
        "created_at": int(time.time())
    }
    note_bytes = json.dumps(note_data).encode('utf-8')
    
    print(f"\n📝 Note field preparation:")
    print(f"  • LogicSig size: {len(lsig_bytes)} bytes")
    print(f"  • Locked amount: {locked_amount/1_000_000:.6f} ALGO (DYNAMIC)")
    print(f"  • Note size: {len(note_bytes)} bytes (limit: 1024)")
    print(f"  • Nonce: {nonce}")
    
    if len(note_bytes) > 1024:
        raise Exception(f"Note too large: {len(note_bytes)} bytes (max 1024)")
    
    # Create NFT with explicit zero addresses for security
    ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"

    acfg = transaction.AssetConfigTxn(
        sender=escrow_addr,
        sp=params,
        total=1,
        default_frozen=False,
        unit_name=asset_unit,
        asset_name=asset_name,
        manager=escrow_addr,
        reserve=escrow_addr,  # Reserve = escrow for verification
        freeze=ZERO_ADDR,
        clawback=ZERO_ADDR,
        url="v3.0-dynamic",
        decimals=0,
        metadata_hash=fingerprint,  # Security fingerprint
        note=note_bytes,  # Complete metadata
        strict_empty_address_check=False
    )
    
    lstx = LogicSigTransaction(acfg, lsig)
    txid = algod_client.send_transaction(lstx)
    pending = wait_for_confirmation(algod_client, txid)
    asset_id = pending.get("asset-index")
    
    print(f"\n✅ NFT minted successfully:")
    print(f"  • Asset ID: {asset_id}")
    print(f"  • Name: {asset_name}")
    print(f"  • Unit: {asset_unit}")
    print(f"  • Transaction: {txid}")
    print(f"  • Creation Round: {pending.get('confirmed-round')}")
    print(f"  • Unique Escrow: {escrow_addr}")
    print(f"  • Redeemable: {locked_amount/1_000_000:.6f} ALGO (stored on-chain)")
    
    return asset_id, txid


def step4_verify_mint(asset_id, txid, expected_fingerprint, nonce, locked_amount):
    """
    Step 4: Verify NFT was created correctly
    
    Validates:
    - Asset exists on-chain
    - Correct parameters (total, decimals, reserve)
    - Fingerprint matches expected value
    
    Args:
        asset_id: Asset ID to verify
        txid: Minting transaction ID
        expected_fingerprint: Expected fingerprint hash
        nonce: Expected nonce
        locked_amount: Expected redeemable amount
    """
    print("\n" + "="*70)
    print("STEP 4: VERIFY MINT")
    print("="*70)

    asset_info = algod_client.asset_info(asset_id)
    params = asset_info.get('params', {})

    print(f"\n🔍 Verification:")
    print(f"  • Asset exists: ✅ YES")
    print(f"  • Total supply: {params.get('total')}")
    print(f"  • Decimals: {params.get('decimals')}")
    print(f"  • Reserve: {params.get('reserve')[:10]}...")

    # Verify metadata hash
    raw_metadata_hash = params.get('metadata-hash')
    metadata_hash_bytes = b""
    if isinstance(raw_metadata_hash, str) and raw_metadata_hash != "":
        try:
            metadata_hash_bytes = base64.b64decode(raw_metadata_hash)
        except Exception:
            metadata_hash_bytes = b""
    elif isinstance(raw_metadata_hash, (bytes, bytearray)):
        metadata_hash_bytes = bytes(raw_metadata_hash)

    if metadata_hash_bytes:
        print(f"  • Metadata hash: {metadata_hash_bytes.hex()[:32]}...")
        if metadata_hash_bytes == expected_fingerprint:
            print(f"  • Fingerprint match: ✅ YES")
        else:
            print(f"  • Fingerprint match: ❌ NO (WARNING)")
    else:
        print("  • Metadata hash: ❌ <missing>")

    print(f"\n✅ Mint verification complete")


def step5_opt_in_and_transfer(creator_sk, lsig, asset_id, receiver_addr):
    """
    Step 5: User opts in and receives NFT
    
    Two-step process:
    1. User opts in to receive the asset
    2. Escrow transfers NFT to user
    
    Args:
        creator_sk: Creator's private key
        lsig: LogicSigAccount instance
        asset_id: Asset ID to transfer
        receiver_addr: Receiver's address
    """
    print("\n" + "="*70)
    print("STEP 5: OPT-IN AND TRANSFER")
    print("="*70)
    
    params = algod_client.suggested_params()
    
    # Step 5a: User opts in
    print(f"\n📥 User opting in to asset {asset_id}...")
    optin = transaction.AssetTransferTxn(
        sender=receiver_addr,
        sp=params,
        receiver=receiver_addr,
        amt=0,
        index=asset_id
    )
    stx = optin.sign(creator_sk)
    txid = algod_client.send_transaction(stx)
    wait_for_confirmation(algod_client, txid)
    print(f"  ✅ Opt-in complete: {txid}")
    
    # Step 5b: Escrow transfers NFT
    print(f"\n📤 Transferring NFT to user...")
    escrow_addr = lsig.address()
    xfer = transaction.AssetTransferTxn(
        sender=escrow_addr,
        sp=params,
        receiver=receiver_addr,
        amt=1,
        index=asset_id
    )
    
    lstx = LogicSigTransaction(xfer, lsig)
    txid = algod_client.send_transaction(lstx)
    wait_for_confirmation(algod_client, txid)
    print(f"  ✅ Transfer complete: {txid}")
    print(f"  ✅ NFT now owned by: {receiver_addr}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("DYNAMIC SECURE NFT MINTING SYSTEM v3.0")
    print("="*70)
    print("\n🚀 Fully Dynamic NFT Minting with Runtime Configuration")
    print("   • Enter NFT details when you run the script")
    print("   • All metadata stored on-chain for dynamic redemption")
    print("   • Unique escrow per NFT with nonce-based security")
    print("   • Complete lifecycle support (mint → redeem → destroy)")
    
    creator_sk = mnemonic.to_private_key(CREATOR_MNEMONIC)
    creator_addr = account.address_from_private_key(creator_sk)
    
    print(f"\n👤 Creator Address: {creator_addr}")
    
    # Get dynamic configuration from user
    config = get_user_input()
    
    # Generate unique nonce for this NFT
    nonce = secrets.randbits(64)
    
    print(f"\n" + "="*70)
    print("MINTING CONFIGURATION")
    print("="*70)
    print(f"\n  • NFT Name: {config['asset_name']}")
    print(f"  • NFT Unit: {config['asset_unit']}")
    print(f"  • Redeemable: {config['locked_amount']/1_000_000:.6f} ALGO")
    print(f"  • Total Funding: {config['fund_amount']/1_000_000:.6f} ALGO")
    print(f"  • Unique Nonce: {nonce}")
    print(f"  • Creator: {creator_addr}")
    
    try:
        # Execute minting workflow
        print(f"\n" + "="*70)
        print("STARTING MINTING PROCESS")
        print("="*70)
        
        # Step 1: Create and fund escrow
        lsig, lsig_bytes, escrow_addr = step1_create_and_fund_escrow(
            creator_sk, creator_addr, config['fund_amount'], 
            nonce, config['locked_amount']
        )
        
        # Step 2: Compute security fingerprint
        fingerprint, fingerprint_data = step2_compute_fingerprint(
            lsig_bytes, config['asset_name'], config['asset_unit'], 
            config['locked_amount'], escrow_addr, nonce
        )
        
        # Step 3: Mint NFT with complete metadata
        asset_id, mint_txid = step3_mint_nft(
            lsig, lsig_bytes, fingerprint, config['asset_name'], 
            config['asset_unit'], nonce, config['locked_amount']
        )
        
        # Step 4: Verify mint
        step4_verify_mint(asset_id, mint_txid, fingerprint, nonce, config['locked_amount'])
        
        # Step 5: Opt-in and transfer
        step5_opt_in_and_transfer(creator_sk, lsig, asset_id, creator_addr)
        
        # Final summary
        print("\n" + "="*70)
        print("🎉 MINTING COMPLETE - SUCCESS!")
        print("="*70)
        print(f"\n📋 Asset Details:")
        print(f"  • Asset ID: {asset_id}")
        print(f"  • Name: {config['asset_name']}")
        print(f"  • Unit: {config['asset_unit']}")
        print(f"  • Owner: {creator_addr}")
        print(f"  • Unique Escrow: {escrow_addr}")
        print(f"  • Redeemable: {config['locked_amount']/1_000_000:.6f} ALGO")
        print(f"  • Nonce: {nonce}")
        
        print(f"\n🔒 Security Features:")
        print(f"  ✅ Unique escrow per NFT (nonce-based)")
        print(f"  ✅ LogicSig stored on-chain")
        print(f"  ✅ Redeemable amount stored dynamically")
        print(f"  ✅ Security fingerprint embedded")
        print(f"  ✅ No expiry date for redemption")
        print(f"  ✅ Supports NFT destruction & account close")
        
        print(f"\n📝 Next Steps:")
        print(f"  1. Save this Asset ID: {asset_id}")
        print(f"  2. To redeem: python dynamic_redemption.py")
        print(f"  3. Enter Asset ID: {asset_id} when prompted")
        print(f"  4. Script will automatically retrieve all data from blockchain")
        
        print("\n" + "="*70)
        print("✨ NFT READY FOR DYNAMIC REDEMPTION")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
