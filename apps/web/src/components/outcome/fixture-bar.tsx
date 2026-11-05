"use client";

import { FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { GLOBAL_SCENARIOS, type GlobalScenario, getGlobalScenario, setGlobalScenario } from "@/lib/fixtures/transport";

/** Development-only control. Present only when the app runs on the fixture transport. */
export function FixtureBar() {
  const [scenario, setScenario] = useState<GlobalScenario>("healthy");
  useEffect(() => setScenario(getGlobalScenario()), []);

  return (
    <footer className="sticky bottom-0 z-30 border-t border-fixture/30 bg-shell">
      <div className="flex h-9 items-center gap-3 px-5 text-2xs max-sm:px-3">
        <FlaskConical aria-hidden className="size-3.5 text-fixture" />
        <span className="font-medium whitespace-nowrap text-fixture">Fixture mode.</span>
        <span className="min-w-0 truncate text-muted-foreground max-md:hidden">
          All data on screen is synthetic and labeled FIXTURE. Nothing here counts as live execution.
        </span>
        <label className="ml-auto flex min-w-0 items-center gap-2 text-muted-foreground">
          <span className="max-sm:sr-only">Scenario</span>
          <select
            value={scenario}
            onChange={(event) => {
              const next = event.target.value as GlobalScenario;
              setGlobalScenario(next);
              setScenario(next);
              window.location.reload();
            }}
            className="h-6 min-w-0 max-w-52 rounded-sm border border-input bg-raised px-1.5 text-2xs text-foreground"
          >
            {Object.entries(GLOBAL_SCENARIOS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </footer>
  );
}
