import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// One self-hosted variable font (weight 100-900, width 62-125%): no request to Google Fonts,
// which is better for privacy and keeps the Content Security Policy strict.
import "@fontsource-variable/archivo/wdth.css";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
