# Project requirements

Derived from a supervisor meeting on 2026-08-06. This is a paraphrase of the
requirements as given, not a record of the discussion. Points marked
**[confirm]** are ones the source material left ambiguous and that should be
settled before they drive design decisions.

## The instruction that reframes the brief

The written brief is broad: all products, 52 banks, best/weak analysis, scenario
building, portfolio optimisation. The meeting narrowed it substantially, and the
narrowing is the actual assignment — **credit cards, small banks, first**. Cards
were chosen because nearly every bank offers them, which makes the product easy
to reason about and comparable across institutions. Everything else in the
written brief is later scope.

## Ordered work items

1. **Extract the rules.** Identify every distinct regulatory rule bearing on the
   product.
2. **Classify them by kind.** A flat list is explicitly not the deliverable. The
   categories called out were liquidity management, compliance, operations and
   issuance — that is, rules differ in what they constrain, not just in what they
   say.
3. **Derive parameters from the rules.** This is the hinge of the project: which
   measurable quantities do the rules actually turn on?
4. **Locate those parameters in the quarterly reports.** Find the relevant
   sections of the financial report and match them to the rules. The difficulty
   was flagged directly: the report is structured, but it is not written in the
   vocabulary of the rules, and it is an open question whether a given regulatory
   quantity can be recovered from it at all.
5. **Categorise the banks by size before anything else.** The reason is that
   regulatory requirements change with size — a threshold on the balance sheet
   decides which rules apply to a given bank. The rough shape described for the
   US was a handful of very large banks, ten to fifteen mid-sized ones, and the
   remainder small, with the small group being the intended subject.
   **[confirm]** the exact tier boundaries intended.
6. **Define a performance criterion, then rank.** Profitability was offered as
   one candidate and number of customers signed up as another; the choice of
   criterion is ours to make and justify. "Better performing" was used with
   explicit scare quotes — it is a modelling decision, not a given.
7. **Benchmark and redistribute.** Take a strong bank of comparable size as the
   benchmark, identify one at the lower end, and ask whether the weaker bank's
   portfolio can be redistributed toward the benchmark *while remaining
   compliant* with the extracted rules.
8. **Scenarios.** Build three or four adverse scenarios and re-test the proposed
   redistribution under them.

## The worked example (use as the phase 1 acceptance test)

The example given was this. A bank issues credit cards, each carrying a credit
limit. Those limits are a commitment to lend, so the bank must be prepared for
drawdown and default against them, which requires holding liquid resources in
proportion. The rule therefore constrains issuance: a bank cannot write a given
volume of card limits unless it holds the corresponding liquidity. Testing that
means reading two things out of the financial reports — how much liquid capacity
the bank has, and how much card exposure it has written — and noting that a bank
can also raise funds externally, which has to enter the calculation.

Mechanically: **undrawn committed card lines → credit conversion factor →
capital and liquidity requirement → checked against reported liquid assets and
funding capacity.** If the pipeline answers this end to end for one small bank,
phase 1 is done.

## Constraints on scenario generation (the anti-hallucination requirement)

- A scenario produced by a language model is not usable until there is a way to
  verify it is *plausible*. The illustration given was that a model might return
  a technically-valid risk scenario that has nothing to do with banking; that
  output has to be rejectable on principle, not by taste.
- Magnitudes need bounding as well as subject matter. A scenario that assumes
  100% withdrawal of an investment is not plausible; there needs to be a
  defensible threshold on how severe a shock the model is allowed to posit.
- Sourcing: scrape published financial news, and prompt the model with that
  material together with the bank's quarter — its current portfolio and how it is
  distributed — asking what is foreseeable from there.
- **Explicit prohibition:** do not build anything that generates or probes
  security threats. Scraping financial reporting is fine; anything that could be
  construed as producing an attack is out of scope and was ruled out directly.

## On method

- Off-the-shelf language models are acceptable; no training is required. The
  supervisor's own experience fine-tuning a small model on Basel rules produced
  output needing manual correction, so **extraction must have a post-processing
  and verification step**, and the section/subsection structure of the rules has
  to be preserved rather than flattened.
- Verification is not optional — machine output is not to be trusted without a
  check that a human expert would accept.
- **Data source: North America, not India**, on the grounds that the regulatory
  data is cleaner and more consistently available.

## Deliverable shape

A rudimentary but real interface, not serialised objects. The navigation
described was: bank portfolios at the top level; drilling into a product opens
its rules organised by section and subsection; clicking a rule links through to
the corresponding exposure in the bank's own figures. It should be possible to
ask for the rules governing a product and be shown them, and to ask how a bank
has moved over the last three quarters and get a readable report with charts.
Spreadsheet-shaped output is acceptable early; the end state is screens.

## Logistics

- Deadline: **December**, with weekly check-in meetings.
- Framing: an academic project, not a production system. A paper is a possible
  outcome if the work gets far enough.

## Open questions for the supervisor

1. Basel is the international standard, but US small banks are actually bound by
   **12 CFR 217 (Regulation Q)**, which diverges materially on exactly the rules
   this project centres on. Basel assigns 45%/75% risk weights to regulatory
   retail split by transactor status; the US assigns a flat 100% to most retail
   and does not recognise the split. US banks under $10bn can also elect the
   community bank leverage ratio and skip risk-based ratios entirely. Extract
   Basel as specified, the US implementation the reports actually reflect, or
   both with an explicit divergence map?
2. Is "small" the regulation-grounded cut at $10bn (the community bank leverage
   ratio threshold), or the roughly fifteen-bank group described in the meeting?
3. Undrawn credit-card lines — the quantity the worked example turns on — are not
   in the FDIC's published series; they require Call Report Schedule RC-L. Is
   pulling raw Call Report schedules in scope?
