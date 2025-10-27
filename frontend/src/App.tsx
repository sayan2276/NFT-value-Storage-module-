import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import { WalletProvider } from "./context/WalletContext";

// Pages
import Home from "./pages/Home";
import Mint from "./pages/Mint";
import Redeem from "./pages/Redeem";
import Docs from "./pages/Docs";

const App: React.FC = () => {
  return (
    <WalletProvider>
      
      <Router>
        <Navbar />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/mint" element={<Mint />} />
          <Route path="/redeem" element={<Redeem />} />
          <Route path="/docs" element={<Docs />} />
        </Routes>
      </Router>
    </WalletProvider>
  );
};

export default App;
