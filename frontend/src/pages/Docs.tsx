import React from "react";

const Docs: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8">
      {/* Hero Section */}
      <section className="text-center py-12">
        <h1 className="text-4xl font-bold mb-4 text-blue-400">Project Documentation</h1>
        <p className="text-gray-300 max-w-2xl mx-auto">
          Find all the guides, references, and resources to get started with our Dynamic NFT Platform.
          Learn how to mint, redeem, and manage NFTs securely on Algorand.
        </p>
      </section>

      {/* Docs Section */}
      <section className="py-12 max-w-4xl mx-auto">
        <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition mb-6">
          <h2 className="text-2xl font-semibold text-blue-400 mb-2">Getting Started</h2>
          <p className="text-gray-300">
            Step-by-step guide on setting up your wallet, connecting it to the platform, and creating your first NFT.
          </p>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition mb-6">
          <h2 className="text-2xl font-semibold text-blue-400 mb-2">Redeem & Burn</h2>
          <p className="text-gray-300">
            Instructions on redeeming redeemable assets from NFTs and securely burning NFTs from your wallet.
          </p>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg shadow hover:shadow-lg transition mb-6">
          <h2 className="text-2xl font-semibold text-blue-400 mb-2">Advanced Features</h2>
          <p className="text-gray-300">
            Learn about escrow accounts, metadata encoding, and security fingerprints embedded in NFTs.
          </p>
        </div>

        {/* Button to get docs */}
        <div className="text-center mt-8">
          <a
            href="/path-to-your-docs.pdf" // Replace with your actual docs link
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block bg-blue-500 text-white font-semibold px-6 py-3 rounded-lg hover:bg-blue-600 transition"
          >
            Get Docs Here
          </a>
        </div>
      </section>
    </div>
  );
};

export default Docs;
