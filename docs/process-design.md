# Process Design — Grupo Sazón Driver Screening

**Goal:** every applicant gets screened within minutes, on their own time, and recruiters only spend time on people who qualify or who need a human decision.

**Channels:** WhatsApp (async text) and browser voice. Both run the same flow, rules and data model.

## 1. Conversation stages

The agent asks knockout questions early, so an unqualified candidate spends about a minute instead of five.

| # | Stage | Asks for | Branching |
|---|---|---|---|
| 0 | **Opening** | Greeting, says it's an AI assistant, privacy notice, consent | No consent → close politely, mark `declined`. The candidate's first reply sets the language. |
| 1 | **Name** | Full name (confirms it if already known from the application) | Only one word given → ask for the surname once, then accept. |
| 2 | **License** ⛔ | Valid driver's license (yes/no) | **No, or still getting it → disqualified path.** Expired and only needs renewal → accepted, noted for the recruiter. |
| 3 | **Location** ⛔ | Where they live (neighbourhood + city) | More than 20 km from every restaurant → **disqualified path**, offer to keep on file. 15–20 km → `needs_review`. Ambiguous place → ask which one. |
| 4 | **Availability** | Full-time / part-time / weekends (more than one allowed) | — |
| 5 | **Schedule** | Morning / afternoon / evening / flexible (more than one allowed) | — |
| 6 | **Experience** | Years + platforms (Glovo, Uber Eats, Rappi, DiDi Food, Just Eat…) | "None" is valid and is not a knockout. |
| 7 | **Start date** | When they can begin, normalized to a date | More than 60 days away → `needs_review`. |
| 8 | **Confirmation** | One-message recap: "¿Todo correcto?" | Candidate corrects a field → update it and recap again. |
| 9 | **Close** | Outcome message (see §5) | — |

A candidate can correct an earlier answer at any stage. If they answer several questions in one message, the agent records every answer it can extract and skips those questions.

## 2. Agent personality

**Sofía, Grupo Sazón's hiring assistant.** Warm, quick and practical, like a friendly shift manager. Not a corporate HR voice and not a chatbot.

- Says it's an AI assistant in the first message, and again if asked.
- Uses **tú** in both Spain and Mexico. Matches the candidate's words where it can (*curro* vs. *chamba*) but doesn't overdo slang.
- Never makes promises about hiring, pay or legal matters. Points to the recruiter or the FAQ instead.

## 3. Data fields and validation

How each field is checked: the two models split the fields between them, and neither works from the other's output. Both read the candidate's original message.

- **Jev** handles the choice fields (`has_license`, `availability`, `schedule`, plus consent): it maps the message to an allowed value with a calibrated confidence score.
- **Claude** handles the free-text fields (`full_name`, `location`, `experience_years`, `platforms`, `start_date`), which Jev can't produce because it doesn't generate text and is weak with numbers and dates.
- **Code** (`rules.py`) applies the business rule to both. Neither model decides anything.

Within one turn Jev runs first and Claude second, but they are independent: each covers its own fields, and Claude never re-reads what Jev classified, or the other way round.

| Field | Type / allowed values | Rule (code) |
|---|---|---|
| `full_name` | string | Required, at least 2 tokens preferred. Voice: spell it back to confirm. |
| `has_license` | `yes` · `no` · `expired` · `in_progress` | `no` or `in_progress` (still getting it) → disqualify. `expired` (only needs renewal) → accept, with a note for the recruiter. Not mentioned → re-ask. Self-declared only: no photo of the license (see technical decisions). |
| `location` | Free text, geocoded to a place | Straight-line distance to the nearest restaurant: ≤ 15 km accept, 15–20 km review, > 20 km disqualify (`out_of_area`). |
| `availability` | set of `full_time` · `part_time` · `weekends` | Not empty. |
| `schedule` | set of `morning` · `afternoon` · `evening` · `flexible` | Not empty. |
| `experience_years` | number ≥ 0 | 0–40. "Unos meses" becomes 0.5. |
| `platforms` | set (open list, normalized) | Optional. |
| `start_date` | ISO date | Not in the past. "El lunes" / "en dos semanas" is resolved using today's date and read back with its weekday. |

**Confidence gate** (applies to the fields Jev classifies; Claude's free-text fields are checked by the rules above, the date read-back and the final recap). The final summary is the confirmation step, so the agent doesn't ask "¿sí o no?" after each answer:

- **≥ 0.6:** keep the answer and move on. The candidate checks everything in the summary.
- **< 0.6:** ask again in different words.
- **Exception, knockouts:** a disqualifying answer ("no tengo carnet") below 0.9 is confirmed before acting, because disqualifying ends the conversation and there's no summary to correct it in.

After **2 failed attempts** on the same field, the agent records its best guess, flags the field and carries on. The candidate ends up in `needs_review` and is never disqualified because of an ambiguous answer.

**Service area:** defined by the 45 restaurants, not by a city list. The restaurants are spread over the 10 largest metro areas in each country:

- **Spain:** Madrid, Barcelona, Valencia, Sevilla, Zaragoza, Málaga, Murcia, Palma, Las Palmas de Gran Canaria, Bilbao.
- **Mexico:** Ciudad de México, Monterrey, Guadalajara, Puebla, Toluca, Tijuana, León, Querétaro, Ciudad Juárez, Torreón.

**How the check works:**

1. The candidate's place ("Del Valle, CDMX", "Getafe") is geocoded with OpenStreetMap's Nominatim, limited to Spain and Mexico.
2. Code measures the distance to the nearest restaurant and applies the thresholds above.
3. If equally likely places would lead to different decisions (Guadalupe, Cáceres vs. Guadalupe, Nuevo León), the agent asks which one. If they'd lead to the same decision, it doesn't ask.
4. If the geocoder is down, the field is flagged for the recruiter. An outage on our side never disqualifies anyone.

Restaurants and thresholds live in `config/`, not in code.

## 4. Edge cases

| Case | Handling |
|---|---|
| **Stops responding (WhatsApp)** | Nudge at **+2h** (free text, inside the 24h window). Nudge at **+24h** with an approved template that offers to continue. At **+72h**, mark `abandoned` and record the stage reached. Resuming later continues from that stage. |
| **Stops responding (voice)** | After 7s of silence, say "¿Sigues ahí?" After a second silence, end the call politely and offer to continue on WhatsApp. Mark `abandoned` with the stage reached. |
| **Says goodbye mid-screening** ("me tengo que ir", "luego seguimos") | Jev flags it (`wants_to_leave`). Answers in the same message still count, then the agent says goodbye, marks `abandoned` with the stage reached and flags `left_early`. On voice, the agent hangs up after the goodbye. On WhatsApp, writing again resumes from that stage. |
| **Ambiguous answer** | Confidence gate above. One clarifying question at a time, offering the valid options ("¿mañana, tarde o noche?"). |
| **Invalid answer** | Re-ask with a short reason ("Necesito una ciudad, por ejemplo Puebla o Querétaro"). Never call the answer "inválido". |
| **Language switch (ES ↔ EN)** | Reply in the language of the candidate's **latest** message. Mixing languages in one message is fine: extract the answer and reply in the dominant language. Store `language` per message. |
| **Off-topic question** ("¿cuánto pagan?") | Short answer from the FAQ if one exists, otherwise "Un reclutador te lo confirmará". Then return to the current question. |
| **Wants a human** | Flag `human_requested`, tell them a recruiter will contact them, and finish only the knockout questions if they agree. |
| **Abuse or prompt injection** | Ignore instructions in the candidate's text. One neutral redirect. If it repeats, close and flag the conversation. |
| **Voice notes / images on WhatsApp** | Transcribe voice notes. For other media, ask for a text reply. |
| **Duplicate application** | Same phone number → resume the existing conversation, don't start a new one. |
| **Data request** ("borra mis datos") | Acknowledge, flag `deletion_requested`, stop the screening. |

## 5. Outcomes

| Outcome | Candidate hears | Recruiter sees |
|---|---|---|
| ✅ **Qualified** | Recap + "Un reclutador te contactará en 48h" (or an interview link once scheduling exists). | **Qualified** queue, sorted by start date and experience, with a 3-line summary. |
| 🟡 **Needs review** | The same message as qualified. The candidate never sees the uncertainty. | **Needs review** queue, with the flagged fields and why each was flagged. |
| ⛔ **Disqualified** | A kind, specific reason ("Para este puesto es necesario carnet de conducir") and an offer to apply again if their situation changes. | **Disqualified** list with the reason code. Kept for audit, out of the recruiter's daily view. |
| 💤 **Abandoned** | Nudges as in §4. | **Gone silent**, with the last stage reached. Feeds drop-off analytics. |

## 6. Tone and length

**WhatsApp**

- One question per message.
- At most 2 short sentences, about 250 characters.
- At most one emoji, and none in disqualification messages.
- No lists, except in the final recap.
- WhatsApp formatting only (*bold*). No links unless they're needed.

**Voice**

- Turns of 20 words or fewer.
- Never read lists aloud; offer at most 3 options.
- Confirm names and dates by repeating them back.
- A short filler ("Vale, un segundo…") while tools run.

**Always**

- Plain language, and acknowledge before asking ("Genial, gracias 🙌 ¿En qué ciudad vives?").
- No jargon such as "screening" or "ATS".
