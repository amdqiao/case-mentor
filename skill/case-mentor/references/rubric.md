# Grading Rubric — read at case_closure, before any grade

McKinsey-style scheme: three dimensions (A Analytical, B Conceptual, C Quantitative), each graded 1–4 from accumulated `private_eval` evidence. Sub_states are evaluated independently — strong work in one never rescues or taints another.

This file is deliberately modular for tuning. Each numbered section can be edited without touching SKILL.md or the other sections.

## Section 1 — Dimension anchors (4-point ladder each)

### A — Analytical (structuring & driving)
What counts as evidence: framework quality (tailored to THIS case, MECE in substance even if the word is never used), branch prioritization, hypothesis stated and updated, driving the case forward, decomposition of later problems.
- **1 (fail):** No usable structure; random idea-listing; passenger throughout — interviewer had to carry every transition.
- **2 (obvious-only):** Cookie-cutter framework loosely fitted to the case; covers the obvious branches; little prioritization; drives only when pushed.
- **3 (comprehensive):** Case-tailored, substantively MECE structure; prioritizes by likely impact with a stated reason; forms a working hypothesis; proactively proposes next steps.
- **4 (spike):** All of level 3, plus the structure demonstrably steers the whole case: hypothesis sharpened as data arrived, non-obvious branch surfaced early that the case rewards, near-zero interviewer steering needed.

### B — Conceptual (judgment, creativity, synthesis)
What counts as evidence: commercial sense of assumptions, second-level/creative ideas in brainstorms, meaningful data interpretation (the "so what"), and the closing recommendation.
- **1 (fail):** Assumptions commercially nonsensical; brainstorms empty or generic; describes exhibits without interpretation; no real recommendation.
- **2 (obvious-only):** Sensible but generic ideas; reads data correctly but stops at description; recommendation restates findings without a decision or with none of risk/next-step.
- **3 (comprehensive):** Comprehensive, case-specific idea sets with at least one non-obvious item; consistent "so what" after data; closing is answer-first — decision, supporting reasons tied to case data, a risk, a next step.
- **4 (spike):** All of level 3, plus a genuinely insightful angle the guidance flags as strong-candidate territory (or better), and a closing a Partner could repeat to the client unedited.

### C — Quantitative
What counts as evidence: setting up the calculation before crunching, arithmetic accuracy and sensible rounding, unit discipline, reading exhibits correctly, independence (hint-ladder depth needed), translating results into business meaning.
- **1 (fail):** Cannot set up the math; major errors uncorrected; needed the answer revealed (ladder step 4) on quant work.
- **2 (obvious-only):** Correct setup and execution on simple calculations with minor slips self-corrected; needs prompting on multi-step math; interprets the number only when asked.
- **3 (comprehensive):** Clean setup stated first; accurate multi-step math at reasonable pace; ≤1 calibrated hint across all quant states; unprompted sanity checks or interpretation.
- **4 (spike):** All of level 3 with zero hints, fast confident execution, and the number immediately converted into an implication that advances the case.

**Communication is NOT graded.** Collect impressions (top-down delivery, clarity, composure, concision) into ungraded "Style notes" for the debrief (Section 4).

## Section 2 — Evidence aggregation

- For each dimension, gather every `private_eval` tagged with it. Grade the dimension on THIS case's actual evidence — an evidence-weighted judgment across its tagged sub_states, not an average of per-turn scores.
- A dimension with **fewer than 2** distinct sub_states of evidence gets a grade plus a **low-confidence flag** ("C: 3 — low confidence, one data point"), stated plainly in the debrief and Notion Notes.
- A dimension with **zero** evidence (e.g. `/quit` before any quant work) is **not graded**: report "no evidence" rather than a number, in both debrief and Notion (leave the select blank; explain in Notes).
- Partial sessions (quit/timeout/second-PDF wrap-up): grade normally over completed sub_states only; mark Completion = Partial. Partial is a legitimate practice mode — the debrief tone treats it as such.

## Section 3 — Overall verdict & spike rule

Spike definitions:
- **Strong spike:** a dimension at 4 supported by evidence from at least 2 distinct sub_states.
- **Weak spike:** a dimension at 4 from only a single sub_state of evidence (this coincides with the low-confidence flag). A weak spike is named in the debrief as a promising signal but counts as a 3 for verdict purposes.

No single overall number. The verdict is a sentence, computed as:
- **Strong performance:** at least one STRONG spike AND no dimension at 1.
- **Solid:** all graded dimensions ≥ 2, no strong spike. If a weak spike exists, phrase it as "Solid, with a promising <dimension> signal."
- **Not yet passing:** any dimension at 1, regardless of spikes elsewhere.
Ungraded dimensions are excluded from the verdict but named as coverage gaps ("no quantitative evidence this session").

Notion "Spike" column records STRONG spikes only; weak spikes go in Notes.

## Section 4 — Debrief format (the closure `message`)

Partner voice, top-down, no tables. Order:
1. **Verdict sentence** (Section 3 wording, plainly: "Overall: strong performance — your analytical work spiked.").
2. **Per-dimension:** grade + one or two concrete evidence moments from the session justifying it ("B: 3. Your reading of the margin chart went straight to the mix-shift — that's the level.").
3. **One priority:** the single highest-leverage improvement, phrased as a drill they can practice.
4. **Style notes:** 2–3 ungraded sentences on communication.
5. **Invitation** to discuss the feedback (grades final).

Keep the whole debrief under ~300 words — Telegram, not a memo. Then write the Notion log per SKILL.md.

## Section 5 — Tuning notes (for the maintainer, not runtime)

Anchor wording (S1), confidence thresholds (S2), and the spike rule (S3) are the intended tuning dials. Changing the number of levels or dimensions requires syncing: SKILL.md's private_eval dimensions, the Notion Case Log select options, and this file.
