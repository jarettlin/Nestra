# Nestra roadmap

## Done
- Simulated home: rooms, lights, fans, airconds (mode, fan speed, timers), blinds, locks, appliances
- Rule-based NLU + fuzzy logic for vague words ("comfortable", "a bit cooler")
- Firebase sign-in, a home per user in Firestore, readable activity history
- Voice: push-to-talk with local Whisper, spoken replies
- Hands-free "Hi Nestra" with follow-up conversation ("ok thanks" ends it)
- "Everything" commands, all-rooms switch, clock, per-tile power buttons

## Ideas for next
- **Feelings instead of commands**: "I'm hot", "it's too bright in here", "I'm going to sleep".
  Map the feeling to devices using room temperature, time of day and the fuzzy rules.
- **Scenes and routines**: "movie time" (dim lights, close shades, aircond 24°C),
  "good night" (everything off except the bedroom aircond on a quiet fan speed).
- **Learning preferences**: if "comfortable" keeps getting nudged a degree cooler,
  shift that person's fuzzy membership functions over time.
- **Context in a conversation**: "turn on the bedroom fan" → "a bit faster" →
  "and the light too", keeping the room and device in mind between turns.

## Small things noticed
- With hands-free on, the greeting wraps to three lines at mid-size window widths.
- A plain "ok" doesn't end a conversation (on purpose); revisit if it feels wrong.
