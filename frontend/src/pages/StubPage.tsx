import { EmptyState } from "../components/ui/EmptyState";
import { Button } from "../components/ui/Button";
import { useNavigate } from "react-router-dom";

export function StubPage({ title, description }: { title: string; description: string }) {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>
      <p className="mt-0.5 text-[12px] text-fm-muted">{description}</p>
      <div className="mt-4 rounded-fm border border-fm-border bg-fm-panel">
        <EmptyState
          title="Design system only — this page comes next"
          description="Shell, tokens, and components are live. Data wiring lands in the next step."
          action={<Button size="sm" onClick={() => navigate("/styleguide")}>Open styleguide</Button>}
        />
      </div>
    </div>
  );
}
