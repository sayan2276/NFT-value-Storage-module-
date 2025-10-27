import time
import json
import base64
from algosdk import  transaction, account, logic
from algosdk.v2client import algod
from algosdk.transaction import LogicSig, AssetConfigTxn, AssetTransferTxn, PaymentTxn, LogicSigTransaction

from hashlib import sha256

ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

ZERO_ADDR = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAY5HFKQ"

def create_unique_escrow_teal(min_payout, nonce):
    teal_source = f"""
#pragma version 6
// Only allow minimum payout
txn CloseRemainderTo
global ZeroAddress
==
txn Fee
int 1000
<=
&&

// Store nonce in the scratch slot (optional, for fingerprint)
int {nonce}
pop
"""
    return teal_source


def compile_teal_to_lsig(client, teal_src):
    compile_response = client.compile(teal_src)
    lsig_bytes = base64.b64decode(compile_response['result'])
    lsig = LogicSig(lsig_bytes)
    return lsig, lsig_bytes


def compute_security_fingerprint(lsig_bytes, asset_name, asset_unit, locked_amt, escrow_addr, nonce):
    data = lsig_bytes + asset_name.encode() + asset_unit.encode() + str(locked_amt).encode() + escrow_addr.encode() + str(nonce).encode()
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

def create_funding_txn(creator_addr, escrow_addr, fund_amt):
    params = algod_client.suggested_params()
    txn = transaction.PaymentTxn(
        sender=creator_addr,
        sp=params,
        receiver=escrow_addr,
        amt=fund_amt
    )
    return txn

def create_optin_txn(asset_id, creator_addr):
    params = algod_client.suggested_params()
    txn = transaction.AssetTransferTxn(
        sender=creator_addr,
        sp=params,
        receiver=creator_addr,
        amt=0,
        index=asset_id
    )
    return txn

def create_nft_txn(lsig, lsig_bytes, fingerprint, asset_name, asset_unit, nonce, locked_amount):
    escrow_addr = lsig.address()
    params = algod_client.suggested_params()
    note_data = {
        "logicsig": base64.b64encode(lsig_bytes).decode(),
        "nonce": nonce,
        "locked_amount": locked_amount,
        "version": "v3.0-dynamic",
        "created_at": int(time.time())
    }
    note_bytes = json.dumps(note_data).encode('utf-8')
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
        url="v3.0-dynamic",
        decimals=0,
        metadata_hash=fingerprint,
        note=note_bytes,
        strict_empty_address_check=False
    )
    lstx = LogicSigTransaction(acfg, lsig)
    return lstx

def create_escrow_transfer_txn(lsig, asset_id, receiver_addr):
    params = algod_client.suggested_params()
    xfer = transaction.AssetTransferTxn(
        sender=lsig.address(),
        sp=params,
        receiver=receiver_addr,
        amt=1,
        index=asset_id
    )
    lstx = LogicSigTransaction(xfer, lsig)
    return lstx

def wait_for_confirmation(client, txid, timeout=60):
    start_time = time.time()
    while True:
        try:
            tx_info = client.pending_transaction_info(txid)
            if tx_info.get('confirmed-round', 0) > 0:
                return tx_info
        except Exception:
            pass
        if time.time() - start_time > timeout:
            raise Exception("Transaction not confirmed in time")
        time.sleep(2)
