// src/context/WalletContext.tsx
import React, { createContext, useContext, useState, type ReactNode, useEffect } from "react";
import { PeraWalletConnect } from "@perawallet/connect";

const peraWallet = new PeraWalletConnect();

interface WalletContextProps {
  walletAddress: string | null;
  peraWallet: PeraWalletConnect;
  connectWallet: () => Promise<void>;
  disconnectWallet: () => void;
}

const WalletContext = createContext<WalletContextProps>({
  walletAddress: null,
  peraWallet,
  connectWallet: async () => {},
  disconnectWallet: () => {},
});

export const WalletProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [walletAddress, setWalletAddress] = useState<string | null>(null);

  // ✅ Auto reconnect session on refresh
  useEffect(() => {
    peraWallet.reconnectSession().then((accounts) => {
      if (accounts.length) {
        setWalletAddress(accounts[0]);
      }
    });

    peraWallet.connector?.on("disconnect", () => setWalletAddress(null));
  }, []);

  const connectWallet = async () => {
    try {
      const accounts = await peraWallet.connect();
      if (accounts.length) setWalletAddress(accounts[0]);
    } catch (err) {
      console.error("Wallet connection failed:", err);
    }
  };

  const disconnectWallet = () => {
    peraWallet.disconnect();
    setWalletAddress(null);
  };

  return (
    <WalletContext.Provider value={{ walletAddress, peraWallet, connectWallet, disconnectWallet }}>
      {children}
    </WalletContext.Provider>
  );
};

export const useWallet = () => useContext(WalletContext);
