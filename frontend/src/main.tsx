import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { IS_MOCK } from "./lib/demo";
import { ThemeProvider } from "./lib/theme";

async function enableMocks() {
  if (IS_MOCK) {
    const { worker } = await import("./mocks/browser");
    await worker.start({ quiet: true });
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
