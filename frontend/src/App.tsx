import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { PasscodeDialog } from "./components/shell/PasscodeDialog";
import { Analytics } from "./pages/Analytics";
import { CaseDetail } from "./pages/CaseDetail";
import { Cases } from "./pages/Cases";
import { DockLive } from "./pages/DockLive";
import { Eval } from "./pages/Eval";
import { Landing } from "./pages/Landing";
import { NotFound } from "./pages/NotFound";
import { Policy } from "./pages/Policy";
import { Styleguide } from "./pages/Styleguide";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PasscodeDialog />
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route index element={<Landing />} />
          <Route element={<AppShell />}>
            <Route path="dock" element={<DockLive />} />
            <Route path="cases" element={<Cases />} />
            <Route path="cases/:poId" element={<CaseDetail />} />
            <Route path="policy" element={<Policy />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="eval" element={<Eval />} />
            <Route path="styleguide" element={<Styleguide />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
