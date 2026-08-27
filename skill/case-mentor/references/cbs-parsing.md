# CBS Parsing — PDF → Case Book Schema

Read this once per session, at `/case` invocation. Goal: convert one case PDF into (a) a CBS object held in working memory for the whole interview and (b) exhibit images ready for Telegram.

## Step 0 — Validation gate (refuse early)

Before building anything, confirm ALL of:
1. The PDF text is machine-readable (extractable text, not a pure image scan). Try text extraction first; if empty/garbage, attempt OCR only if tooling is available, else fail.
2. It contains exactly ONE case: a prompt plus interviewer material. A multi-case book (index of many cases), a resume, an article, or slides without a case prompt → fail. Note: prep providers (e.g. RocketBlocks) wrap single cases in boilerplate — cover page, "how to use" instructions, marketing outro. Wrapper pages are normal; skip them entirely and judge "one case" by the number of distinct case prompts, not page count.
3. A case prompt (client + problem statement) is identifiable.
4. At least one question, exhibit, or guided section exists beyond the prompt.

On failure: emit the TOS error turn (state `error`, `session_over: true`) with a Partner-voice message naming the problem ("This looks like a full casebook — send me a single case, ideally 2–10 pages"). Never guess or invent case content to compensate.

## Step 1 — Classify every piece of content: SHARABLE vs INTERVIEWER-ONLY

This classification is the core of parsing. Casebooks interleave both audiences on the same page.

**Sharable (may reach the candidate verbatim):**
- The case prompt / client situation.
- Question stems as posed to the candidate.
- Exhibit titles and chart content (minus footnotes — see Step 3).
- Data explicitly marked "provide if asked" (share only when asked).

Casebooks usually mark the split explicitly — use their markers as primary cues. RocketBlocks conventions: "👀 For interviewer only 👀" boxes, "Sample Response" / "Sample framework" sections (model answers), "Interviewer notes on candidate response" boxes (evaluation prompts), and "Information to be shared if the candidate asks" (ask-gated facts). Other providers use equivalents; the yellow-box/green-box pattern generalizes.

**Interviewer-only (NEVER appears in `message`; used to steer and judge):**
- Sections labeled "Interviewer Guidance", "Notes to interviewer", "For the interviewer", or equivalent.
- Model answers, sample frameworks, expected insights, answer-key math and target numbers.
- Evaluation commentary ("a strong candidate will..."), difficulty notes, timing suggestions.
- Exhibit footnotes and fine print.
- "Reveal only if the candidate asks X" conditions themselves (the condition is guidance; the data behind it is sharable once triggered).

When a passage is ambiguous, classify it interviewer-only. Leaking guidance ruins the mock; withholding a borderline detail merely makes you a slightly stingier interviewer.

## Step 2 — Build the CBS

```json
{
  "case_name": "...",
  "firm_style": "McKinsey / BCG / Bain / generic, if stated",
  "case_type": "e.g. market entry, profitability",
  "sector": "...",
  "prompt_sharable": "verbatim candidate-facing prompt",
  "clarifying_facts": [ {"fact": "...", "provide_when": "asked about X / freely"} ],
  "framework_expected": true,
  "sub_states": [
    {
      "id": "ms1",
      "order": 1,
      "question_sharable": "the question as posed to the candidate",
      "dimension": "analytical | conceptual | quantitative",
      "interviewer_guidance": "hidden steering notes, expected insights, model answer",
      "target_numbers": "answer-key values for quant states, else null",
      "exhibits": ["ex1"],
      "reveal_trigger": "when to hand the exhibit over (e.g. 'after candidate proposes a revenue approach' / 'at question start')",
      "advance_condition": "what must be demonstrated to move on",
      "rubric_anchor": "1-2 sentences: what a strong vs weak answer to THIS question looks like, distilled from the guidance"
    }
  ],
  "closure": {
    "synthesis_prompt_sharable": "e.g. 'The CEO walks in — what do you tell her?' or null",
    "model_recommendation": "hidden"
  }
}
```

Dimension tagging heuristics: structure/framework/prioritization questions → `analytical`; brainstorming, interpretation-of-meaning, judgment, and synthesis questions → `conceptual`; anything requiring calculation or reading numbers off an exhibit → `quantitative`. A question mixing calculation and interpretation: tag the sub_state by its center of gravity, and note the secondary dimension inside `interviewer_guidance` so per-turn `private_eval` can occasionally tag the minority dimension when the candidate's contribution is clearly of that kind.

Number sub_states in the order the casebook poses them. If the casebook has an untitled flowing structure, cut it into sub_states at each distinct question or exhibit handoff.

Provider-pattern rules learned from real casebooks:
- **"Question 1 - Introduction" pattern:** the opening section often contains both the case prompt AND the first real question ("What is your approach?"). Split it: the prompt feeds case_intro; the approach question becomes sub_state ms1 (analytical, framework).
- **Rubric anchors:** when an "Interviewer notes on candidate response" box lists evaluation questions ("Was the response MECE?", "Did it show original thought?"), those ARE the sub_state's `rubric_anchor` — adopt them. When the box is empty (common), synthesize the anchor yourself from the sample response: what distinguishes its strong answer from an obvious one.
- **Ask-gated data:** facts under "shared if the candidate asks" go into `clarifying_facts` with `provide_when: asked about X` and are ALSO the inputs to quant sub_states. Never volunteer them: part of the drill is whether the candidate requests the data they need. Record in `interviewer_guidance` that failure to ask is private_eval evidence, and that the hint ladder starts at "What information would you need?".
- **VERIFY THE ANSWER KEY.** Real casebooks contain arithmetic errors and mislabeled figures in their sample responses. During parsing, recompute every `target_number` yourself from the given inputs. If your verified math conflicts with the key, trust your computation, store it as the target, and note the discrepancy in `interviewer_guidance` — otherwise you will mark a correct candidate wrong. The same skepticism applies to totals quoted in the model synthesis.

## Step 3 — Exhibit extraction (images for Telegram)

Some cases have no graphical exhibits at all (all data is ask-gated text) — that's normal, skip this step. Every exhibit — charts, graphs, AND data tables — is delivered as a cropped image via `exhibit_files`, never re-typed as text in `message`. Reading the exhibit as presented is part of the skill being tested.

For each exhibit:
1. Locate its page/region in the PDF.
2. Render that page region to PNG at readable resolution (150–200 DPI is enough for phone screens). Rendering the full page and cropping to the exhibit is fine; prefer a crop that excludes surrounding interviewer text.
3. **Strip footnotes:** if footnotes/fine print sit inside the exhibit region, crop them out. If they are inseparable from the chart (e.g. embedded in the image), note this in `interviewer_guidance` and prefer describing the chart's sharable content in `message` while still sending the image ONLY if the footnote does not leak guidance or answers; when in doubt, redraw is out of scope — just crop tighter or withhold the contaminated area and convey the sharable data as a clean table in `message`.
4. Save to the session working directory as `ex<N>.png` and record the path in the CBS entry. These paths go in TOS `exhibit_files` when revealed.

Footnote content and axis fine print you cropped away remain available to YOU (from text extraction) — use them to answer candidate questions about the exhibit the way a real interviewer would ("Assume that's annual, yes").

## Step 4 — Confirm readiness

After parsing, do a self-check: every sub_state has a dimension, an advance_condition, and a rubric_anchor; every exhibit file exists. Then open the interview (case_intro) — do not show the candidate any parsing detail beyond a one-line "I've read the case" acknowledgment inside the greeting.
