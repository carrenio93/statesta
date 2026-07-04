# CRITICAL RULES — Read in full. Always.

> **For Claude:** This file is short on purpose. Keep all of it in active attention for the entire session. If you find yourself about to violate any rule below, stop and ask the user. These are non-negotiable.
>
> **For the user:** Paste this file alongside PROJECT_STATUS.md at the start of every session.

---

## RULE 1 — Start every session with verification

Before doing anything else, summarize back to the user:
- The session number you're in.
- What the last completed session produced.
- The current active task (from PROJECT_STATUS.md Section 9).
- Any open questions relevant to today (from Section 8).
- What you understood today's session goal to be.

**Wait for the user to confirm "yes, correct" before proposing anything.** If they correct you, restart the summary. Do not proceed on assumptions.

---

## RULE 2 — One deliverable per session

Each session has ONE focused output (one document, one schema layer, one feature spec). If the conversation drifts to a second topic, stop and ask:

> "This is heading to a second topic. Should we (a) defer it as a future session, or (b) pivot from today's goal to this instead?"

Never silently expand scope.

---

## RULE 3 — Plan before producing

Before generating any artifact, propose:
- What the artifact will contain (sections, structure).
- How long it will take.
- What questions you need answered first.

Wait for user approval. Only then start producing.

---

## RULE 4 — Beginner pace, always

The user is a beginner. Default behavior:
- Explain *why* before *what*.
- Use concrete examples.
- Avoid jargon without definitions.
- If proposing a technical decision, give the trade-offs in plain language.
- If a section feels too dense, split it.

If the user says "I don't understand," stop and explain. Never apologize for asking.

---

## RULE 5 — End-of-session protocol is non-skippable

Before the session ends, do all of these. No exceptions:

1. Update PROJECT_STATUS.md Section 6 (Sessions Log) — mark this session ✅ Complete.
2. Update Section 7 (Decisions Log) — log every meaningful decision with D-XXX ID.
3. Update Section 8 (Open Questions) — add new ones, resolve closed ones.
4. Update Section 9 (Current Active Task) — describe next session.
5. Update Section 10 (File Inventory) — add new files.
6. Produce the updated PROJECT_STATUS.md as a downloadable file.
7. Produce all session artifacts as files.
8. **Show the user what changed in PROJECT_STATUS.md** — explicit list: "Section 6: added Session N row. Section 7: added D-0XX. Section 9: updated active task to Session N+1." This lets the user verify nothing was missed.
9. Tell the user explicitly: which files to save, which ClickUp task to update, what to paste at the start of the next session.

If you skip any of these, the user loses context permanently.

---

## RULE 6 — No code before requirements

Until REQUIREMENTS.md exists (Session 2's deliverable), do NOT produce:
- Database schema.
- API endpoint definitions.
- Frontend component code.
- Any implementation artifact.

Architecture documents and decision logs are OK. Implementation is not. The schema rebuilt without requirements failed once already (Decision D-004); do not repeat that mistake.

---

## RULE 7 — Files, not chat dumps

Long-form artifacts (>30 lines) ALWAYS go in a named file. Never embedded in a chat message. This is so:
- The user can save them cleanly.
- The user can attach them to ClickUp tasks.
- They survive across sessions.

Short responses, explanations, and summaries are fine inline.

---

## RULE 8 — Trust the pasted files over your assumptions

If the user pastes PROJECT_STATUS.md and you remember (or seem to remember) something different from a previous chat — trust the file, not memory. Anthropic's project memory can be summarized or wrong. PROJECT_STATUS.md is the authoritative record.

If they conflict, raise it: "Project memory suggests X, but PROJECT_STATUS.md says Y. Going with the file. Confirm?"

---

## RULE 9 — When in doubt, ask

These are good signals to stop and ask the user:
- A user request seems to contradict an earlier decision.
- A scope change is implied but not stated.
- The work feels too big to fit one session.
- You're about to make an architectural choice with long-term consequences.
- Something in the pasted files seems incomplete or stale.

Asking is never the wrong move. Guessing usually is.

---

*That's all 9 rules. Re-read this file if any session feels like it's drifting.*
