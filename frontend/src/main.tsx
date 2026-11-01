import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ThemeProvider } from "./lib/theme";

async function enableMocks() {
  if (import.meta.env.VITE_MOCK === "1") {
    const { worker } = await import("./mocks/browser");
    await worker.start();
  }
}

enableMocks().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </StrictMode>,
  );
});
