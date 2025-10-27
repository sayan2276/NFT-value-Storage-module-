// src/components/Navbar.tsx
import React from "react";
import { Link } from "react-router-dom";
import { useWallet } from "../context/WalletContext";
import { PeraWalletConnect } from "@perawallet/connect";

const peraWallet = new PeraWalletConnect();

const Navbar: React.FC = () => {
  const { walletAddress, setWalletAddress } = useWallet();


  const connectWallet = async () => {
    try {
      const accounts = await peraWallet.connect();
      if (accounts.length) {
        setWalletAddress(accounts[0]);
      }

      // Listen for disconnect
      peraWallet.connector?.on("disconnect", () => setWalletAddress(null));
    } catch (error) {
      console.error("Wallet connection failed:", error);
    }
  };

  const disconnectWallet = async () => {
    try {
      await peraWallet.disconnect();
      setWalletAddress(null);
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <nav className="bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
      <div className="flex space-x-6 font-semibold">
        <Link to="/">Home</Link>
        <Link to="/mint">Mint</Link>
        <Link to="/redeem">Redeem</Link>
        <Link to="/docs">Docs</Link>
      </div>
      <div>
        {walletAddress ? (
          <button
            onClick={disconnectWallet}
            className="bg-white text-blue-600 px-4 py-2 rounded hover:bg-gray-100 transition"
          >
            {walletAddress.slice(0, 6)}...{walletAddress.slice(-4)}
          </button>
        ) : (
          <button
            onClick={connectWallet}
            className="bg-white text-blue-600 px-4 py-2 rounded hover:bg-gray-100 transition"
          >
            Connect Wallet
          </button>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
