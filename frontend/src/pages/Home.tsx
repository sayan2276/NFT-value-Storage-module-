import React from "react";

const Home: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
      {/* Hero Section */}
      <section className="text-center py-12">
        <h1 className="text-5xl font-bold mb-4 text-blue-400">Dynamic NFT Platform</h1>
        <p className="text-lg max-w-2xl mx-auto text-gray-300">
          Mint, redeem, and manage fully dynamic NFTs securely on Algorand. <br/>
          Now storing algos in NFT is made possible on ALgorand
        </p>
      </section>

      {/* Features Section */}
      <section className="py-12">
        <h2 className="text-3xl font-semibold mb-8 text-center text-blue-300">Key Features</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">Fully Dynamic Minting</h3>
            <p className="text-gray-300">
              NFTs are created at runtime with user-defined parameters like name, unit, and redeemable amount.
            </p>
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">Secure Escrow Accounts</h3>
            <p className="text-gray-300">
              Each NFT is linked to a unique escrow account for security and verification.
            </p>
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">Redeem & Burn</h3>
            <p className="text-gray-300">
              NFT holders can redeem their assets or burn NFTs safely with full on-chain verification.
            </p>
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">On-Chain Metadata</h3>
            <p className="text-gray-300">
              All NFT metadata, including redeemable amounts and fingerprints, is stored directly on-chain.
            </p>
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">Dynamic Redemption</h3>
            <p className="text-gray-300">
              Redeem assets anytime; no time limits or expiration. Fully dynamic workflow supported.
            </p>
          </div>

          <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition">
            <h3 className="text-xl font-bold mb-2 text-blue-400">User Friendly</h3>
            <p className="text-gray-300">
              Simple UI for minting, redeeming, and viewing NFTs with wallet integration.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
