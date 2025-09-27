# GM Simulator Project Status

## Completion Snapshot
The backend delivers the bulk of the GM gameplay loop today:

- **Core and seasonal simulation** – `SeasonSimulator` runs multi-week schedules with injuries, narratives, and analytics for every drive.
- **Postseason engine** – A dedicated `PlayoffSimulator` seeds brackets, handles injury carryover, and persists narratives for each elimination game.
- **Narrative + LLM guardrails** – The OpenRouter client enforces structured recaps with score validation before any text is accepted.
- **Roster management and cap math** – Contract helpers, roster-rule enforcement, and transaction routers cover signings, cuts, elevations, and cap impacts.
- **Draft, trades, and development** – Rookie generation, trade AI, and player development flows are exposed through dedicated routers and services.
- **Persistent franchise state & injury reporting** – Franchise snapshots plus injury dashboards give LLMs and clients a canonical record across seasons.
- **Assistant + web client** – Lightweight assistant endpoints and the bundled browser client surface dashboards, highlights, and narrative recaps to drive a chat-first experience.
- **Coaching modifiers** – Staff models feed rating and development boosts into the season/playoff sims while new routers expose hiring workflows.
- **Free-agency bidding** – Multi-team offer evaluation ranks market pitches and surfaces rationale so LLMs can narrate negotiations without drifting from cap math.

Taken together, 17 of the 20 roadmap bullet points in `README.md` and `OVERNIGHT_REPORT.md` are shipped and regression-tested, leaving roughly **85 %** of the planned functionality complete.

## Outstanding Work
The remaining 5 roadmap items keep the last quarter of scope open:

1. **Negotiation state & FA UX** – The bidding evaluator ranks offers, but persistent negotiations, counter offers, and contract history still need to be modeled.
2. **Command/receipt tool surface** – REPORT/SIGN/CUT style transactional endpoints with diff receipts are still required for the LLM-first workflow.
3. **Expanded NFL scheduling** – The season simulator still runs a round-robin slate rather than the full 17-game NFL matrix called out in the roadmap.
4. **Multiplayer league support** – Authentication, concurrency control, and shared league coordination are not implemented anywhere in the stack.
5. **Deeper transaction narratives & cap blending** – Narrative hooks are limited to game recaps; integrating LLM outputs with transaction APIs and tying blended ratings into offseason cap churn remain future work.

## Next Steps
- Formalize a negotiation engine that tracks simultaneous offers, rejects, and cap impacts over time.
- Add the transactional command layer (REPORT/SIGN/CUT/DEPTHCHART) with diff receipts so assistants stay grounded.
- Extend schedule generation to honor NFL divisional matchups, bye weeks, and 17-game constraints before postseason seeding.
- Decide on multiplayer primitives (league ownership, invitations, locks) and extend persistence/state APIs accordingly.
- Pipe narrative generation into trade/transaction routers and connect the ratings blending pipeline to contract/cap projections so offseason moves stay data-driven.
