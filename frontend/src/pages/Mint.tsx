import React, { useState } from "react";
import algosdk from "algosdk";
import { useWallet } from "../context/WalletContext";

const Mint: React.FC = () => {
  const { walletAddress, peraWallet } = useWallet();
  const [assetName, setAssetName] = useState("");
  const [assetUnit, setAssetUnit] = useState("");
  const [algoAmount, setAlgoAmount] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>("");

  /**
   * Convert base64 msgpack string to algosdk.Transaction instance
   */
  const base64ToTxn = (b64Txn: string): algosdk.Transaction => {
    try {
      // Decode base64 to Uint8Array
      const binaryString = atob(b64Txn);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Decode msgpack to Transaction object
      return algosdk.decodeUnsignedTransaction(bytes);
    } catch (error) {
      console.error("Error decoding transaction:", error);
      throw new Error(`Failed to decode transaction: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  /**
   * Convert Uint8Array to base64 string
   */
  const uint8ToBase64 = (u8: Uint8Array): string => {
    let binary = "";
    for (let i = 0; i < u8.byteLength; i++) {
      binary += String.fromCharCode(u8[i]);
    }
    return btoa(binary);
  };

  const handleSubmit = async () => {
    if (!walletAddress) {
      alert("Connect wallet first!");
      return;
    }

    if (!assetName || !assetUnit || algoAmount <= 0) {
      alert("Please fill all fields with valid values!");
      return;
    }

    setLoading(true);
    setStatus("Preparing mint...");

    try {
      const payload = {
        creator_address: walletAddress,
        asset_name: assetName,
        asset_unit: assetUnit,
        locked_amount: Math.floor(algoAmount * 1_000_000), // Convert to microAlgos
      };

      // ===== STEP 1: Get funding transaction =====
      setStatus("Getting funding transaction...");
      const res1 = await fetch("http://localhost:8000/mint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res1.ok) {
        const errorData = await res1.json();
        throw new Error(errorData.detail || `Backend error: ${res1.status}`);
      }

      const data1 = await res1.json();
      console.log("Mint response:", data1);

      // ===== STEP 2: Sign and submit funding transaction =====
      setStatus("Please sign funding transaction in Pera Wallet...");
      const fundTxn = base64ToTxn(data1.funding_txn);
      
      // Correct format for Pera Wallet - array of transaction groups
      const txnsToSign = [[
        { txn: fundTxn, signers: [walletAddress] }
      ]];

      const signedFundTxns = await peraWallet.signTransaction(txnsToSign);
      
      // signedFundTxns is an array of Uint8Array
      // We only have one transaction, so get the first one
      const signedFundB64 = uint8ToBase64(signedFundTxns[0]);

      setStatus("Submitting funding transaction...");
      const fundSubmitRes = await fetch("http://localhost:8000/submit_funding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signed_txn: signedFundB64 }),
      });

      if (!fundSubmitRes.ok) {
        const errorData = await fundSubmitRes.json();
        throw new Error(errorData.detail || "Failed to submit funding transaction");
      }

      const fundSubmitData = await fundSubmitRes.json();
      console.log("Funding submitted:", fundSubmitData);

      // ===== STEP 3: Create NFT asset (backend creates via escrow) =====
      setStatus("Creating NFT asset...");
      const createRes = await fetch("http://localhost:8000/create_nft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ escrow_address: data1.escrow_address }),
      });

      if (!createRes.ok) {
        const errorData = await createRes.json();
        throw new Error(errorData.detail || "Failed to create NFT");
      }

      const createData = await createRes.json();
      console.log("NFT created:", createData);
      const assetId = createData.asset_id;

      // ===== STEP 4: Opt-in to receive NFT =====
      setStatus("Getting opt-in transaction...");
      const optinRes = await fetch("http://localhost:8000/optin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: assetId,
          creator_address: walletAddress,
        }),
      });

      if (!optinRes.ok) {
        const errorData = await optinRes.json();
        throw new Error(errorData.detail || "Failed to get opt-in transaction");
      }

      const optinData = await optinRes.json();
      console.log("Opt-in response:", optinData);

      // ===== STEP 5: Sign and submit opt-in transaction =====
      setStatus("Please sign opt-in transaction in Pera Wallet...");
      const optInTxn = base64ToTxn(optinData.optin_txn);
      
      const optInTxnsToSign = [[
        { txn: optInTxn, signers: [walletAddress] }
      ]];

      const signedOptInTxns = await peraWallet.signTransaction(optInTxnsToSign);
      const signedOptInB64 = uint8ToBase64(signedOptInTxns[0]);

      setStatus("Submitting opt-in transaction...");
      const optinSubmitRes = await fetch("http://localhost:8000/submit_optin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signed_txn: signedOptInB64 }),
      });

      if (!optinSubmitRes.ok) {
        const errorData = await optinSubmitRes.json();
        throw new Error(errorData.detail || "Failed to submit opt-in transaction");
      }

      const optinSubmitData = await optinSubmitRes.json();
      console.log("Opt-in submitted:", optinSubmitData);

      // ===== STEP 6: Transfer NFT from escrow to creator =====
      setStatus("Transferring NFT to your wallet...");
      const transferRes = await fetch("http://localhost:8000/transfer_nft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          escrow_address: data1.escrow_address,
          asset_id: assetId,
          receiver_address: walletAddress,
        }),
      });

      if (!transferRes.ok) {
        const errorData = await transferRes.json();
        throw new Error(errorData.detail || "Failed to transfer NFT");
      }

      const transferData = await transferRes.json();
      console.log("NFT transferred:", transferData);

      setStatus("Success! NFT minted and transferred!");
      alert(`🎉 NFT Minted Successfully!\n\nAsset ID: ${assetId}\nTransaction: ${transferData.txid}\n\nCheck your Pera Wallet!`);

      // Reset form
      setAssetName("");
      setAssetUnit("");
      setAlgoAmount(0);
      setStatus("");

    } catch (err) {
      console.error("Error during minting:", err);
      const errorMsg = err instanceof Error ? err.message : "Unknown error occurred";
      alert(`Minting failed: ${errorMsg}\n\nCheck console for details.`);
      setStatus(`Error: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto mt-12 p-8 bg-white rounded-xl shadow-md">
      <h1 className="text-2xl font-bold text-center mb-6">Mint Your Dynamic NFT</h1>

      {!walletAddress ? (
        <p className="text-center text-gray-700 mb-4">Connect your wallet first!</p>
      ) : (
        <div className="text-center mb-6 p-3 bg-green-50 rounded border border-green-200">
          <p className="text-sm text-gray-600">Connected Wallet</p>
          <p className="font-mono text-sm">
            {walletAddress.slice(0, 8)}...{walletAddress.slice(-6)}
          </p>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            NFT Name
          </label>
          <input
            type="text"
            placeholder="e.g., My Dynamic NFT"
            value={assetName}
            onChange={(e) => setAssetName(e.target.value)}
            className="w-full border border-gray-300 px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-green-500"
            disabled={loading}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Unit Name
          </label>
          <input
            type="text"
            placeholder="e.g., DYNFT"
            value={assetUnit}
            onChange={(e) => setAssetUnit(e.target.value.toUpperCase())}
            maxLength={8}
            className="w-full border border-gray-300 px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-green-500"
            disabled={loading}
          />
          <p className="text-xs text-gray-500 mt-1">Max 8 characters</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Amount to Lock (ALGO)
          </label>
          <input
            type="number"
            placeholder="e.g., 5"
            value={algoAmount || ""}
            onChange={(e) => setAlgoAmount(Number(e.target.value))}
            min="0.1"
            step="0.1"
            className="w-full border border-gray-300 px-3 py-2 rounded focus:outline-none focus:ring-2 focus:ring-green-500"
            disabled={loading}
          />
          <p className="text-xs text-gray-500 mt-1">
            Minimum: 0.1 ALGO (plus transaction fees)
          </p>
        </div>
      </div>

      {status && (
        <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
          <p className="text-sm text-blue-800">{status}</p>
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading || !walletAddress}
        className={`w-full mt-6 py-3 rounded-lg text-white font-semibold transition-colors ${
          loading || !walletAddress
            ? "bg-gray-400 cursor-not-allowed"
            : "bg-green-600 hover:bg-green-700"
        }`}
      >
        {loading ? "Processing..." : "Mint NFT"}
      </button>

      <div className="mt-6 p-4 bg-gray-50 rounded text-xs text-gray-600">
        <p className="font-semibold mb-2">How it works:</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>Fund a unique escrow account with your ALGO</li>
          <li>Escrow creates your NFT with embedded metadata</li>
          <li>NFT is transferred to your wallet</li>
          <li>Redeem anytime to unlock your locked ALGO</li>
        </ol>
      </div>
    </div>
  );
};

export default Mint;