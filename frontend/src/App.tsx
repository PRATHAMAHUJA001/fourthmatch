import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { CaseDetail } from "./pages/CaseDetail";
import { Cases } from "./pages/Cases";
import { Styleguide } from "./pages/Styleguide";
import { StubPage } from "./pages/StubPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/styleguide" replace />} />
            <Route path="styleguide" element={<Styleguide />} />
            <Route path="dock" element={<StubPage title="Dock Live" description="Receiving-dock video, SAM tracks, live pipeline." />} />
            <Route path="cases" element={<Cases />} />
            <Route path="cases/:poId" element={<CaseDetail />} />
            <Route path="policy" element={<StubPage title="Policy" description="Company receiving policy, compiled to checkable rules." />} />
            <Route path="analytics" element={<StubPage title="Analytics" description="Holds, variance, and vendor patterns. All numbers computed in Python." />} />
            <Route path="eval" element={<StubPage title="Eval" description="Agent accuracy against ground truth. Counts only from SAM tracks." />} />
            <Route path="*" element={<StubPage title="Not found" description="That route doesn't exist." />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
