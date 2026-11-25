---
name: marimo-academic-writing
description: Write, rewrite or improve the prose of marimo notebooks (mo.md cells) in academic paper style — methods, results and decisions, with numbered sections, LaTeX, tables and a "points to check" review. Use for any marimo notebook text meant for a thesis, paper or research report.
---

# Academic writing in marimo notebooks

Use this skill when the user wants to write, rewrite or improve the text of a marimo notebook (introduction, method, results, decision, discussion), or pastes notebook text and asks to make it clearer or more academic. The text must read as a section of a research paper or thesis, not as code comments or a changelog.

## 1. Get the context first

Before writing, establish:

1. **Project context.** Look for a context file next to the notebook, at the repository root, in the project's documents, or pasted in the conversation (`notebook-context.md`, `CONTEXT.md` or similar). It describes the research question, data, key definitions, section structure and vocabulary. If there is none, infer the context from the notebook's introduction cells and the surrounding sections. If the user's message contradicts the context file, the message wins.
2. **Which section, and which part.** Infer the section number and the type of text (introduction, method, results, decision, discussion) from what was pasted or from the cell being edited. Ask only if it genuinely cannot be inferred.
3. **Neighbouring sections.** When writing results or decisions, read the method section of the same step first (in the notebook or the conversation) so numbering, symbols and vocabulary stay consistent.

## 2. Two working modes

**Chat mode (text pasted into a conversation).** Return:
1. one single ```markdown code block with the rewritten section, ready to paste into `mo.md()`;
2. below it, a short list headed **Points to check** (at most about 6 items, one or two sentences each).
No other commentary.

**Editor mode (the agent can edit the `.py` notebook, e.g. in Cursor or Claude Code).**
- Edit only the text of `mo.md(...)` cells unless the user asks for more. Never change computations, variable names or cell logic as a side effect.
- Keep the marimo rules intact (see §6). After editing, run `marimo check <notebook>.py` if it is available, otherwise at least `python -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" <notebook>.py`.
- Report the **Points to check** in the chat, not inside the notebook.

## 3. Structure

Use numbered sections and subsections (§N, §N.1, §N.2, …). Typical patterns:

| Kind of section | Typical subsections |
|---|---|
| Introduction / data | Data and sources → Motivation → Design of the analysis or pipeline → Reproducibility |
| Method (a check, a model, a transformation) | Objective → Background / why it matters → Method (rules, formulas, parameters) → Outputs |
| Results | Headline finding → Interpretation → Detail (tables) |
| Decision / correction | Principles → What was decided and why (one justification per case) → Consequences for later steps |
| Model estimation | Hypothesis → Specification → Estimates (table with standard errors) → Interpretation → Robustness |

When the notebook is a sequence of steps, open each step with "**Sample at entry.**" and close it with "**Sample at exit.**" (units, observations, series), if the sample can change.

## 4. Style rules

1. **Academic register.** Plain, precise, impersonal. Short paragraphs. No marketing tone, no filler, no "we simply…".
2. **Purpose before mechanics.** Start with what the section does and why it matters for the research question; give the mechanics afterwards.
3. **Formulas in LaTeX.** `$...$` inline, `$$...$$` display. Define each symbol once (e.g. $r_{i,t}$, the return of series $i$ on day $t$) and reuse it. Bold the name of each condition or rule.
4. **Tables when they help.** Use them for classifications, summary counts, decision logs, before/after values and estimates. Number them per section (Table N.1, Table N.2) and give each a title. Keep only the columns a reader needs, with readable names and units.
5. **Code stays out of the prose.** Function names, variable names and file paths go in a footnote, appendix or code cell, except where essential. Dataset column or series names may stay in `backticks`.
6. **Consistent vocabulary.** Use the terms defined in the context file. Do not alternate synonyms for the same object (e.g. "series" vs "columns" vs "variables").
7. **Numbers.** Round sensibly (e.g. −98.96%, 0.77%), use thousands separators, get singular and plural right, and give units.
8. **Results: finding → meaning → detail.** Lead with the headline result, then say what it means for the analysis, then give the detail. Each manual decision gets a short justification citing its evidence.
9. **No duplication.** Do not repeat content that belongs to another subsection; refer to it instead (§N.x, Table N.x).
10. **Citations.** Author–year in the text (Smith & Jones, 2021). Never invent a reference; if a claim needs a source that is missing, say so in Points to check.
11. **Language.** Write the section in the notebook's language (English by default). Reply to the user in the language they write in.

## 5. Content discipline

- **Do not invent** facts, numbers, dates, thresholds, sources or justifications. Use only what is in the user's text, the notebook or the context file.
- **Ambiguity or contradiction:** do not fix it silently. Write the most plausible reading and flag it in Points to check.
- **Internal consistency:** check that counts sum, that numbers match across sections and tables, and that terminology matches earlier sections.
- **Referee's eye:** flag what a thesis examiner or journal referee would challenge: unjustified thresholds or parameters, benchmark or model choices, manual decisions, reproducibility (data vintages, download dates, random seeds), missing citations.
- **Notebook-generated text:** when numbers in the prose come from computed variables, recommend keeping them as f-string variables instead of hard-coding them (see §6).

## 6. marimo specifics

- A notebook is a `.py` file. Each cell is a function decorated with `@app.cell`; the last expression of the cell is what gets displayed.
- Write markdown with raw strings so LaTeX backslashes survive: `mo.md(r"""...""")`.
- **f-strings and LaTeX:** in `mo.md(rf"""...""")`, literal braces must be doubled: `$r_{{i,t}}$`. To avoid mistakes, keep long static text with LaTeX in its own `r"""` cell and put dynamic numbers in a separate short f-string cell, or format numbers beforehand (`n_txt = f"{n:,}"`).
- Plural helper for generated text: `f"{n} break day{'s' if n != 1 else ''}"`.
- Markdown tables render inside `mo.md`. For dataframes use `mo.ui.table(df)`, after selecting, renaming and rounding the columns a reader needs.
- Useful layout elements: `mo.callout(mo.md(...), kind="info" | "warn" | "danger" | "success")` for warnings or key findings; `mo.accordion({"Details": mo.md(...)})` for long technical detail that would clutter the main text; `mo.vstack([...])` to stack outputs.
- marimo forbids defining the same global variable in two cells. Prefix cell-local helper names with `_` (e.g. `_txt`) when adding text-building code.
- Do not add side effects (file writes, network calls) to cells that only render text.

## 7. Points to check: what to include

At most about 6 items, most important first. Each item is one or two sentences and names the fix. Typical content:
- assumptions made where the source text was ambiguous;
- inconsistencies found (numbers, counts, terminology, contradictions with earlier sections);
- likely referee objections;
- suggested fixes in the notebook code (labels, rounding, plurals, column names, hard-coded numbers).

## 8. Project context file template

If the project has no context file and the user works on the notebook repeatedly, offer to create `notebook-context.md` next to the notebook with this structure:

```markdown
# Notebook context
## Research question
## Data and sources
## Key definitions and symbols
## Notebook structure (sections / steps, one line each)
## Vocabulary (preferred terms; terms to avoid)
## Conventions (benchmark, units, rounding, citation style, language)
## Known pitfalls specific to this project
```
