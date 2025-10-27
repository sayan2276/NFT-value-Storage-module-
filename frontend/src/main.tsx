import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
declare global {
  interface Window {
    Buffer: typeof Buffer;
    process: any;
  }
}


import { Buffer } from "buffer";
import process from "process";

window.Buffer = Buffer;
window.process = process;


createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
