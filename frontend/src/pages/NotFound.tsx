import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";

export function NotFound() {
  return (
    <div className="rounded-fm border border-fm-border bg-fm-panel">
      <EmptyState title="No such page" description="That route does not exist on this console." action={<Button asChild size="sm"><Link to="/dock">Back to Dock Live</Link></Button>} />
    </div>
  );
}
