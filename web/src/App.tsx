import { NavLink, Route, Routes } from "react-router-dom";

import { Cases } from "./routes/Cases";
import { CaseStudy } from "./routes/CaseStudy";
import { Landing } from "./routes/Landing";
import { Simulator } from "./routes/Simulator";

function BrandMark() {
  // Three descending bars: leverage paid down over a hold. Small enough to read
  // as a logo, literal enough to mean something.
  return (
    <svg className="brand-mark" viewBox="0 0 22 22" aria-hidden="true">
      <rect x="1" y="4" width="4.5" height="14" rx="1" fill="var(--pine)" />
      <rect x="8.75" y="8" width="4.5" height="10" rx="1" fill="var(--pine-deep)" />
      <rect x="16.5" y="12" width="4.5" height="6" rx="1" fill="var(--brass)" />
    </svg>
  );
}

export function App() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <BrandMark />
          LBO Lab
        </NavLink>
        {/* No API link here. The OpenAPI schema is worth reaching — it is
            generated from the same Pydantic contract the model validates
            against, which is the strongest evidence the layers cannot drift —
            but it is a developer tool, and putting it in the primary nav says
            it is a destination on a par with the simulator. It lives in the
            footer instead. */}
        <nav className="topnav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/simulator">Simulator</NavLink>
          <NavLink to="/cases">Case studies</NavLink>
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/cases" element={<Cases />} />
        <Route path="/cases/:slug" element={<CaseStudy />} />
      </Routes>
    </div>
  );
}
