import React, { useEffect, useState } from "react";
import { useWallet } from "../context/WalletContext";
import algosdk from "algosdk";

interface NFTAsset {
  assetId: number;
  name: string;
  unitName: string;
  amount: number;
}

const Redeem: React.FC = () => {
  const { walletAddress } = useWallet();
  const [nfts, setNfts] = useState<NFTAsset[]>([]);
  const [selectedNFT, setSelectedNFT] = useState<NFTAsset | null>(null);

  // Fetch NFTs from wallet
  useEffect(() => {
    const fetchNFTs = async () => {
      if (!walletAddress) return;

      try {
        const algodClient = new algosdk.Algodv2("", "https://testnet-api.algonode.cloud", "");
        const accountInfo = await algodClient.accountInformation(walletAddress).do();

        // // Filter for NFTs (1 unit, 0 decimals)
        // const assets = accountInfo.assets
        //   ?.filter(a => a.amount === 1 && a['params']?.decimals === 0)
        //   .map(a => ({
        //     assetId: a['asset-id'],
        //     name: a['params']?.name || "NFT",
        //     unitName: a['params']?.unit_name || "NFT",
        //     amount: a.amount
        //   })) || [];

        // setNfts(assets);
      } catch (err) {
        console.error("Error fetching NFTs:", err);
      }
    };

    fetchNFTs();
  }, [walletAddress]);

  const handleBurn = () => {
    if (!selectedNFT) {
      alert("Select an NFT to burn");
      return;
    }

    alert(`Burn NFT with Asset ID: ${selectedNFT.assetId}`);
    // Backend / blockchain logic will go here later
  };

  return (
    <div className="min-h-screen bg-gray-900 p-8">
      <h1 className="text-3xl text-amber-50 font-bold mb-6">Redeem / Burn NFT</h1>

      {!walletAddress ? (
        <p className="text-red-500">Connect your wallet to view NFTs.</p>
      ) : nfts.length === 0 ? (
        <p className="text-gray-700 text-xl">No redeemable NFTs found in your wallet.</p>
      ) : (
        <div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 mb-6">
            {nfts.map(nft => (
              <div
                key={nft.assetId}
                className={`p-4 border rounded-lg cursor-pointer transition ${
                  selectedNFT?.assetId === nft.assetId
                    ? "border-blue-600 bg-blue-100"
                    : "border-gray-300 hover:bg-gray-100"
                }`}
                onClick={() => setSelectedNFT(nft)}
              >
                <h2 className="font-semibold">{nft.name}</h2>
                <p className="text-sm text-gray-600">Unit: {nft.unitName}</p>
                <p className="text-sm text-gray-600">Amount: {nft.amount}</p>
                <p className="text-sm text-gray-500">Asset ID: {nft.assetId}</p>
              </div>
            ))}
          </div>

          <button
            onClick={handleBurn}
            className="bg-red-600 text-white px-6 py-2 rounded hover:bg-red-700 transition"
          >
            Burn Selected NFT
          </button>
        </div>
      )}
    </div>
  );
};

export default Redeem;
