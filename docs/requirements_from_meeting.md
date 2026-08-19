# Project requirements, as stated in the 2026-08-06 supervisor meeting

Source: `2026_08_06_13_09_32.mp3` (21m 50s), transcribed on-device; raw ASR in
`docs/transcript_raw.txt`. The audio is a noisy multi-speaker room recording, so
the transcript is lossy. Everything below is a reading of it — passages marked
**[uncertain]** are where the ASR is too degraded to be sure and should be
confirmed with the supervisor.

## The instruction that reframes the brief

The written brief is broad (all products, 52 banks, best/weak analysis, scenarios,
optimisation). The meeting narrows it hard, and the narrowing is the actual
assignment:

> "For now, we just focus on ... credit cards." / "we just focus on credit ... only.
> I mean, mostly banks are offering credit cards, they're the most common for us to
> understand." / "because you have to focus on only credit cards and ... small banks
> ... that is your start."

So: **credit cards, small banks, first.** Everything else is later scope.

## Ordered work items

1. **Extract the rules.** "Your first job is to bring out what all different rules
   are there."
2. **Classify them by kind.** "Not all the rules are related to liquidity management.
   There are rules related to the compliance, ... to the operations, issuance,
   liquidity." A flat list of rules is explicitly not the deliverable.
3. **Derive parameters from the rules.** "From those rules come the parameters.
   Which parameters do we look into?" This is the hinge of the whole project.
4. **Find those parameters in the quarterly reports.** "You need to find out the
   relevant rules. You need to find out the relevant sections in the financial
   report. Compare these two." He immediately flags the difficulty: the report
   "is structured, but ... it is not necessarily [in] the rules['] [terms]. It's
   using certain terms ... Can we really figure out that ...?"
5. **Categorise the banks by size first.** "I believe that you have to first do a
   categorization ... 50, 50 billion, like that ... because depending on the size
   of the bank, the regulatory requirements — some of them will change. That is why
   you have to do that first. If a small bank up to this level, if this is your
   turnover, then this applies to you, [otherwise] not."
   His rough US shape: ~4-5 very big, ~10-15 medium, the rest small; and about 15
   in the small group he wants worked on. **[uncertain — the numbers are garbled]**
6. **Define a performance criterion, then rank.** "What is your performance?
   Profitability [is] one performance. Number of users who signed up is maybe
   another performance. So you have to find out the better performing — I use that
   word in quotes — better performing banks."
7. **Benchmark and redistribute.** Pick a strong bank of similar size as benchmark,
   find one at the lower end, then: "Can I redistribute the portfolio, seeing this
   as benchmark? If I try to do that, am I still compliant with the rules?"
8. **Scenarios.** Build 3-4 adverse scenarios and re-test the redistribution.

## The worked example he gave (use this as the acceptance test)

> "If you have issued ... credit cards, and there is a credit limit set on each of
> the cards, you have to prepare for default. ... you will actually have to have
> certain amount of liquid cash at your hand to cover up on that. So [the] rule ...
> tells you that if you are planning to issue 1,000,000 credit cards or 10,000
> credit cards, you must not do that unless you have got that much of liquid cash.
> ... From these financial reports, [find] how much cash you [have], [and] on the
> other hand, how many credit cards you [issued]. ... So the bank can raise money
> from outside also, right? So we take that into consideration."

That is, precisely: **undrawn committed credit-card lines → credit conversion
factor → capital and liquidity requirement → check against reported liquid assets
and funding capacity.** If the pipeline can answer this end to end for one small
bank, phase 1 is done.

## Constraints on scenario generation (the anti-hallucination requirement)

- "If you use a language model to build a scenario, you must have a way to verify
  that it is a [plausible] scenario."
- "It should not create a scenario like ... the NASA rocket falls on the moon.
  It might create ... a risk scenario, but that is possibly not related to this.
  So if it gives you a scenario, there should be [a justification] that it is a
  plausible scenario."
- Magnitudes need bounding too: "removal [of] investment is 100% ... you can tell
  that the plausible scenario is not more than this much ... There is a threshold."
- Sourcing: scrape published financial news and feed it with the quarter's report
  into the prompt — "get one report and [combine] with your prompt and that one
  quarter report: this is the current portfolio, this is how it is distributed.
  What can you foresee as ... scenario[s]?"
- Explicit prohibition: do **not** build a crawler that generates or probes
  security threats — "if they demonstrate an attack, they can come back and say,
  hey, why did you generate that security threat?" Scrape financial situation
  reporting only.

## On method

- LLMs may be used off the shelf; no training required. He fine-tuned Llama on
  Basel rules himself and "one of them had to be later manually corrected", so
  extraction output needs a post-processing and verification step, and the rules
  carry section/subsection structure that must be preserved.
- Verification is not optional: "I don't trust unless a human expert [verifies]."
- Data source: **North America, not India** — "because the regulations are ...
  much more clean" there.

## Deliverable shape

A rudimentary but real UI, not pickle files:

> "All the banks' portfolio ... you click there, and it immediately opens ...
> the rules — [product], then section, subsection, there is where the rules will
> come. Then if I click on one of the rules, then it goes into that investment of
> the bank ... I will come and ask you [about] the rules for it, you should be able
> to show me. ... If I want to see how the bank is working [over the] last 3
> quarters, quickly pick up those three [and] put some charts or graphs."

Excel-shaped output is acceptable early; the end state is screens.

## Logistics

- Deadline: **December**. Weekly meetings, **Thursday, 11:30-13:30**, mail ahead.
- Framing: academic project, not a production system. A paper is possible if it
  gets far enough, with co-authors added.

## Open questions to put to the supervisor

1. Basel is the international standard, but US small banks are actually bound by
   **12 CFR 217 (Regulation Q)**, which diverges materially — e.g. Basel assigns
   45%/75% risk weights to regulatory retail, while the US assigns a flat 100% to
   most retail, and US banks under $10bn can opt into the community bank leverage
   ratio and skip risk-based ratios entirely. Extract Basel as specified, or the
   US implementation the reports actually reflect, or both with a divergence map?
2. "Small" = under $10bn (the CBLR threshold) is the regulation-grounded cut. Is
   that the intended tier, or the ~15-bank group he described?
3. Undrawn credit-card lines — the quantity his worked example turns on — are not
   in the FDIC's published series; they need Call Report Schedule RC-L. Confirm
   that pulling raw Call Report schedules is in scope.
