from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from algosdk.v2client import algod
from algosdk import transaction, encoding
from algosdk.transaction import LogicSig, LogicSigTransaction
import base64
import time
import json
import logging
from typing import Dict, Any
from hashlib import sha256

# ===== Algorand Client =====
ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== FastAPI App =====
app = FastAPI(title="Algorand NFT Minting Service", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Pydantic Models =====
class MintRequest(BaseModel):
    creator_address: str
    asset_name: str
    asset_unit: str
    locked_amount: int  # in microAlgos

class SignedTxn(BaseModel):
    signed_txn: str  # base64 signed txn

class OptInRequest(BaseModel):
    asset_id: int
    creator_address: str

class CreateNFTRequest(BaseModel):
    escrow_address: str

class TransferNFTRequest(BaseModel):
    escrow_address: str
    asset_id: int
    receiver_address: str

# ===== In-memory storage =====
# In production, use a database
pending_escrows: Dict[str, Dict[str, Any]] = {}

# ===== Helper Functions =====

def create_escrow_teal(nonce: int) -> str:
    """
    Creates a simple escrow TEAL program that:
    - Prevents closing account to other addresses
    - Enforces reasonable fee limits
    - Includes a unique nonce for fingerprinting
    """
    teal_source = f"""#pragma version 6
// Ensure account isn't closed to another address
txn CloseRemainderTo
global ZeroAddress
==

// Ensure reasonable fee
txn Fee
int 1000
<=
&&

// Unique nonce for this escrow
int {nonce}
pop
"""
    return teal_source


def compile_teal_to_lsig(teal_src: str) -> tuple[LogicSig, bytes]:
    """Compile TEAL source to LogicSig"""
    try:
        resp = algod_client.compile(teal_src)
        lsig_bytes = base64.b64decode(resp['result'])
        lsig = LogicSig(lsig_bytes)
        return lsig, lsig_bytes
    except Exception as e:
        logger.error(f"TEAL compilation failed: {e}")
        raise HTTPException(status_code=500, detail=f"TEAL compilation error: {str(e)}")


def txn_to_b64(txn) -> str:
    """
    Convert Algorand transaction to base64-encoded msgpack.
    """
    try:
        encoded = encoding.msgpack_encode(txn)
        
        if isinstance(encoded, bytes):
            return base64.b64encode(encoded).decode('utf-8')
        elif isinstance(encoded, str):
            # Already base64 encoded
            return encoded
        else:
            raise TypeError(f"Unexpected encoding type: {type(encoded)}")
            
    except Exception as e:
        logger.error(f"Transaction encoding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transaction encoding error: {str(e)}")


def compute_security_fingerprint(
    lsig_bytes: bytes,
    asset_name: str,
    asset_unit: str,
    locked_amt: int,
    escrow_addr: str,
    nonce: int
) -> tuple[bytes, dict]:
    """
    Compute a SHA-256 fingerprint combining all NFT parameters.
    This is stored in the NFT's metadata_hash field.
    """
    data = (
        lsig_bytes +
        asset_name.encode('utf-8') +
        asset_unit.encode('utf-8') +
        str(locked_amt).encode('utf-8') +
        escrow_addr.encode('utf-8') +
        str(nonce).encode('utf-8')
    )
    fingerprint = sha256(data).digest()
    
    fingerprint_data = {
        "logicsig_sha256": sha256(lsig_bytes).hexdigest(),
        "logicsig_size": len(lsig_bytes),
        "asset_name": asset_name,
        "asset_unit": asset_unit,
        "locked_amount": locked_amt,
        "escrow_address": escrow_addr,
        "nonce": nonce,
        "version": "v3.0-dynamic"
    }
    
    return fingerprint, fingerprint_data


def wait_for_confirmation(client: algod.AlgodClient, txid: str, timeout: int = 60) -> dict:
    """Wait for transaction confirmation"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            info = client.pending_transaction_info(txid)
            if info.get("confirmed-round", 0) > 0:
                logger.info(f"Transaction {txid} confirmed in round {info['confirmed-round']}")
                return info
        except Exception as e:
            logger.debug(f"Waiting for confirmation: {e}")
        time.sleep(2)
    
    raise HTTPException(
        status_code=408,
        detail=f"Transaction {txid} not confirmed within {timeout} seconds"
    )


# ===== API Endpoints =====

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Algorand Dynamic NFT Minting",
        "version": "3.0",
        "network": "testnet"
    }


@app.post("/mint")
def mint(request: MintRequest):
    """
    Step 1: Create escrow and return funding transaction.
    Frontend signs and submits this transaction.
    """
    try:
        # Validate inputs
        if request.locked_amount < 100_000:  # Minimum 0.1 ALGO
            raise HTTPException(status_code=400, detail="Minimum locked amount is 0.1 ALGO")
        
        if len(request.asset_unit) > 8:
            raise HTTPException(status_code=400, detail="Unit name max 8 characters")
        
        # Create unique nonce
        nonce = int(time.time() * 1000)
        
        # Compile escrow
        teal_src = create_escrow_teal(nonce)
        lsig, lsig_bytes = compile_teal_to_lsig(teal_src)
        escrow_addr = lsig.address()
        
        logger.info(f"Created escrow {escrow_addr} for creator {request.creator_address}")
        
        # Create funding transaction (user → escrow)
        params = algod_client.suggested_params()
        fund_txn = transaction.PaymentTxn(
            sender=request.creator_address,
            sp=params,
            receiver=escrow_addr,
            amt=request.locked_amount
        )
        
        fund_txn_b64 = txn_to_b64(fund_txn)
        
        # Store pending escrow data
        pending_escrows[escrow_addr] = {
            "lsig": lsig,
            "lsig_bytes": lsig_bytes,
            "asset_name": request.asset_name,
            "asset_unit": request.asset_unit,
            "locked_amount": request.locked_amount,
            "creator_address": request.creator_address,
            "nonce": nonce,
            "funded": False,
            "asset_id": None
        }
        
        logger.info(f"Stored pending escrow: {escrow_addr}")
        
        return {
            "escrow_address": escrow_addr,
            "funding_txn": fund_txn_b64,
            "nonce": nonce,
            "message": "Sign and submit this funding transaction"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit_funding")
def submit_funding(signed: SignedTxn):
    """
    Step 2: Submit signed funding transaction to network.
    """
    try:
        # Decode base64 to bytes
        tx_bytes = base64.b64decode(signed.signed_txn)
        
        # Submit the raw transaction bytes directly
        txid = algod_client.send_raw_transaction(tx_bytes)
        
        logger.info(f"Funding transaction submitted: {txid}")
        
        # Wait for confirmation
        tx_info = wait_for_confirmation(algod_client, txid)
        
        # Decode the signed transaction to get receiver
        signed_txn = encoding.msgpack_decode(tx_bytes)
        receiver = encoding.encode_address(signed_txn.transaction.receiver)
        
        # Mark escrow as funded
        if receiver in pending_escrows:
            pending_escrows[receiver]["funded"] = True
            logger.info(f"Escrow {receiver} marked as funded")
        else:
            logger.warning(f"Escrow {receiver} not found in pending_escrows")
        
        return {
            "txid": txid,
            "confirmed_round": tx_info.get("confirmed-round"),
            "receiver": receiver,
            "message": "Funding confirmed"
        }
        
    except Exception as e:
        logger.error(f"Submit funding error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/create_nft")
def create_nft(request: CreateNFTRequest):
    """
    Step 3: Create NFT asset from escrow account.
    This is signed by the escrow's LogicSig.
    """
    try:
        escrow_addr = request.escrow_address
        
        if escrow_addr not in pending_escrows:
            raise HTTPException(status_code=404, detail="Escrow not found")
        
        escrow_data = pending_escrows[escrow_addr]
        
        if not escrow_data.get("funded"):
            raise HTTPException(status_code=400, detail="Escrow not funded yet")
        
        lsig = escrow_data["lsig"]
        lsig_bytes = escrow_data["lsig_bytes"]
        asset_name = escrow_data["asset_name"]
        asset_unit = escrow_data["asset_unit"]
        locked_amount = escrow_data["locked_amount"]
        nonce = escrow_data["nonce"]
        
        # Compute security fingerprint
        fingerprint, fingerprint_data = compute_security_fingerprint(
            lsig_bytes, asset_name, asset_unit, locked_amount, escrow_addr, nonce
        )
        
        # Create note with embedded data
        note_data = {
            "logicsig": base64.b64encode(lsig_bytes).decode('utf-8'),
            "nonce": nonce,
            "locked_amount": locked_amount,
            "version": "v3.0-dynamic",
            "created_at": int(time.time()),
            "fingerprint_data": fingerprint_data
        }
        note_bytes = json.dumps(note_data, indent=2).encode('utf-8')
        
        # Create asset configuration transaction
        params = algod_client.suggested_params()
        acfg = transaction.AssetConfigTxn(
            sender=escrow_addr,
            sp=params,
            total=1,
            default_frozen=False,
            unit_name=asset_unit,
            asset_name=asset_name,
            manager=escrow_addr,
            reserve=escrow_addr,
            freeze=ZERO_ADDR,
            clawback=ZERO_ADDR,
            url="https://algorand-dynamic-nft.example.com",
            decimals=0,
            metadata_hash=fingerprint,
            note=note_bytes,
            strict_empty_address_check=False
        )
        
        # Sign with LogicSig
        lstx = LogicSigTransaction(acfg, lsig)
        
        # Submit transaction
        txid = algod_client.send_transaction(lstx)
        logger.info(f"NFT creation transaction submitted: {txid}")
        
        # Wait for confirmation
        tx_info = wait_for_confirmation(algod_client, txid)
        
        # Extract asset ID
        asset_id = tx_info.get("asset-index")
        if not asset_id:
            raise HTTPException(status_code=500, detail="Asset ID not found in transaction info")
        
        # Store asset ID
        pending_escrows[escrow_addr]["asset_id"] = asset_id
        
        logger.info(f"NFT created with asset ID: {asset_id}")
        
        return {
            "txid": txid,
            "asset_id": asset_id,
            "confirmed_round": tx_info.get("confirmed-round"),
            "escrow_address": escrow_addr,
            "message": "NFT asset created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create NFT error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optin")
def optin(request: OptInRequest):
    """
    Step 4: Generate opt-in transaction for creator.
    Frontend signs and submits this.
    """
    try:
        params = algod_client.suggested_params()
        
        # Create opt-in transaction (0 amount transfer to self)
        optin_txn = transaction.AssetTransferTxn(
            sender=request.creator_address,
            sp=params,
            receiver=request.creator_address,
            amt=0,
            index=request.asset_id
        )
        
        optin_txn_b64 = txn_to_b64(optin_txn)
        
        logger.info(f"Created opt-in txn for asset {request.asset_id}, creator {request.creator_address}")
        
        return {
            "optin_txn": optin_txn_b64,
            "asset_id": request.asset_id,
            "message": "Sign this opt-in transaction"
        }
        
    except Exception as e:
        logger.error(f"Opt-in error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit_optin")
def submit_optin(signed: SignedTxn):
    """
    Step 5: Submit signed opt-in transaction.
    """
    try:
        tx_bytes = base64.b64decode(signed.signed_txn)
        txid = algod_client.send_raw_transaction(tx_bytes)
        
        logger.info(f"Opt-in transaction submitted: {txid}")
        
        # Wait for confirmation
        tx_info = wait_for_confirmation(algod_client, txid)
        
        return {
            "txid": txid,
            "confirmed_round": tx_info.get("confirmed-round"),
            "message": "Opt-in confirmed"
        }
        
    except Exception as e:
        logger.error(f"Submit opt-in error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transfer_nft")
def transfer_nft(request: TransferNFTRequest):
    """
    Step 6: Transfer NFT from escrow to creator.
    This is signed by the escrow's LogicSig.
    """
    try:
        escrow_addr = request.escrow_address
        
        if escrow_addr not in pending_escrows:
            raise HTTPException(status_code=404, detail="Escrow not found")
        
        escrow_data = pending_escrows[escrow_addr]
        lsig = escrow_data["lsig"]
        
        # Create transfer transaction
        params = algod_client.suggested_params()
        xfer_txn = transaction.AssetTransferTxn(
            sender=escrow_addr,
            sp=params,
            receiver=request.receiver_address,
            amt=1,
            index=request.asset_id
        )
        
        # Sign with LogicSig
        lstx = LogicSigTransaction(xfer_txn, lsig)
        
        # Submit transaction
        txid = algod_client.send_transaction(lstx)
        logger.info(f"NFT transfer transaction submitted: {txid}")
        
        # Wait for confirmation
        tx_info = wait_for_confirmation(algod_client, txid)
        
        logger.info(f"NFT {request.asset_id} transferred to {request.receiver_address}")
        
        return {
            "txid": txid,
            "confirmed_round": tx_info.get("confirmed-round"),
            "asset_id": request.asset_id,
            "receiver": request.receiver_address,
            "message": "NFT transferred successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transfer NFT error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/escrow/{escrow_address}")
def get_escrow_info(escrow_address: str):
    """
    Get information about an escrow account.
    """
    if escrow_address not in pending_escrows:
        raise HTTPException(status_code=404, detail="Escrow not found")
    
    escrow_data = pending_escrows[escrow_address]
    
    return {
        "escrow_address": escrow_address,
        "asset_name": escrow_data["asset_name"],
        "asset_unit": escrow_data["asset_unit"],
        "locked_amount": escrow_data["locked_amount"],
        "creator_address": escrow_data["creator_address"],
        "nonce": escrow_data["nonce"],
        "funded": escrow_data.get("funded", False),
        "asset_id": escrow_data.get("asset_id")
    }


@app.post("/redeem")
def redeem_nft(request: TransferNFTRequest):
    """
    Redeem NFT: Burn the NFT and return locked ALGO to owner.
    This requires the NFT holder to initiate.
    """
    try:
        escrow_addr = request.escrow_address
        
        if escrow_addr not in pending_escrows:
            raise HTTPException(status_code=404, detail="Escrow not found")
        
        escrow_data = pending_escrows[escrow_addr]
        lsig = escrow_data["lsig"]
        locked_amount = escrow_data["locked_amount"]
        
        params = algod_client.suggested_params()
        
        # Transaction 1: Transfer NFT back to escrow (burn)
        burn_txn = transaction.AssetTransferTxn(
            sender=request.receiver_address,
            sp=params,
            receiver=escrow_addr,
            amt=1,
            index=request.asset_id
        )
        
        # Transaction 2: Pay locked ALGO to redeemer
        payout_txn = transaction.PaymentTxn(
            sender=escrow_addr,
            sp=params,
            receiver=request.receiver_address,
            amt=locked_amount - 2000  # Deduct fees
        )
        
        # Group transactions
        gid = transaction.calculate_group_id([burn_txn, payout_txn])
        burn_txn.group = gid
        payout_txn.group = gid
        
        # Sign payout with LogicSig
        lstx_payout = LogicSigTransaction(payout_txn, lsig)
        
        # Return burn transaction for user to sign
        burn_txn_b64 = txn_to_b64(burn_txn)
        
        return {
            "burn_txn": burn_txn_b64,
            "message": "Sign the burn transaction to complete redemption",
            "payout_amount": locked_amount - 2000
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Redeem error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)