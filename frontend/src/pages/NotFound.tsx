import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";

export function NotFound() {
  return (
    <section className="mt-6 grid overflow-hidden rounded-fm-xl bg-fm-panel md:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col justify-center p-12 max-md:p-8">
        <p className="text-[15px] font-semibold text-fm-muted">Page not found</p>
        <h1 className="mt-3 max-w-[14ch] text-[48px] font-bold leading-[1.04] tracking-[-0.034em] max-sm:text-[36px]">Nothing was delivered here.</h1>
        <p className="mt-4 max-w-[40ch] text-[17px] leading-relaxed text-fm-muted">That address is not part of FourthMatch. The dock, the cases and the policy are one click away.</p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Button asChild size="xl" variant="accent"><Link to="/dock">Go to the dock</Link></Button>
          <Link to="/cases" className="text-[17px] text-fm-accent-text hover:underline underline-offset-4">Open cases ›</Link>
        </div>
      </div>
      <img src="/media/scn1_clean_f1.webp" alt="An empty stretch of the receiving dock floor" width={1280} height={720} className="h-full min-h-[280px] w-full object-cover" />
    </section>
  );
}
