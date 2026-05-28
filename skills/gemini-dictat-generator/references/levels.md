# Dictation Level Rubric

Use this language-neutral rubric to choose transcript complexity, pacing, repetition, punctuation handling, and audio variants. Apply all examples in the requested language.

## initial

Target: first exposure, young children, or very early adult learners.

- Text length: 50-120 words.
- Sentence length: 4-8 words per spoken unit.
- Vocabulary: concrete classroom, family, objects, weather, food, basic actions, and culturally familiar nouns.
- Grammar: present tense and only the simplest past forms if familiar; avoid subordinate clauses.
- Repetition: repeat every phrase or short dictation unit twice.
- Pace: extremely slow; about one second between many words and several seconds between sentences.
- Punctuation: say the target-language words for comma, full stop/period, new paragraph, and final stop.
- Audio: produce only the original-speed audio by default.

## basic

Target: primary school dictation or A1-A2 learners.

- Text length: 100-180 words.
- Sentence length: 8-14 words per unit.
- Vocabulary: familiar school and daily-life topics with a few new words.
- Grammar: present, common past forms, and simple connectors equivalent to `and`, `but`, `then`, `when`.
- Repetition: repeat every phrase or short dictation unit twice unless the user asks for a faster version.
- Pace: slow and clear, with phrase pauses.
- Punctuation: say punctuation cues aloud.
- Audio: produce only the original-speed audio by default.

## intermediate

Target: upper primary, secondary, or B1 learners.

- Text length: 160-260 words.
- Sentence length: 12-22 words per unit.
- Vocabulary: descriptive language, school/science/social topics, moderate abstraction.
- Grammar: subordinate clauses, pronouns, common irregular forms, and language-specific spelling challenges such as accents, apostrophes, capitalization, or agreement.
- Repetition: default to repeating each phrase twice for classroom dictation; use selective repetition only if the user asks for a more natural pace.
- Pace: clear classroom speed, not exaggerated.
- Punctuation: include commas, full stops, paragraph cues, and occasional accents if useful.
- Audio: produce only the original-speed audio by default.

## advanced

Target: confident learners, C1 school practice, or exam-style dictation.

- Text length: 220-400 words.
- Sentence length: natural, with longer clauses.
- Vocabulary: precise and varied, including abstract nouns and idioms when appropriate.
- Grammar: varied tenses, relative clauses, pronoun combinations, contrastive connectors.
- Repetition: default to phrase repetition if this is still a classroom dictation; use minimal repetition only if the user asks for exam-like or near-natural delivery.
- Pace: near-natural but articulated.
- Punctuation: include paragraphing, quotes, semicolons, accents, or spelling cues if requested.
- Audio: produce only the original-speed audio by default.

## Optional Speed Variants

Create speed variants only when the user asks for them, or suggest them after the default package if the result is clearly too slow or too fast. Generate variants from the finished WAV with audio processing, not with another TTS call.

## Transcript Cues

Use bracketed cues for the TTS prompt, not for final clean text unless useful:

- `[slow]`: request slower speech.
- `[short pause]`: pause between repeated units.
- `[long pause]`: pause between sentences or paragraphs.

For dictations, punctuation words are part of the audio because learners need to write them. Choose the names in the target language. Examples:

- Catalan: `coma`, `punt i seguit`, `punt i apart`, `punt final`.
- Spanish: `coma`, `punto y seguido`, `punto y aparte`, `punto final`.
- English: `comma`, `period` or `full stop`, `new paragraph`, `final period`.
- French: `virgule`, `point`, `nouveau paragraphe`, `point final`.
