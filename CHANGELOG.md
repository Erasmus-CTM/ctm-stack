# Changes

## 0.4.0 (step 6, for review)

- Rename the component and repository to ctm-stack; authors keep `.stack-question`.
- Prepare backend data through ctm-checkers and build the card shell in Lua.
- Use an unpublished CTMWorker behind the page-side backend contract. Stop and restart target that backend only; loading and queued time do not consume the calculation ceiling.
- Use shared settings, the six-language catalogue, matrix input and optional answer-store integration. Source panels are off by default.
- STACK gets its own feedback integration. Feedback defaults to `auto`, like math-exercise; `feedback: false` and no-AI builds suppress it.
- Maxima remains a build-time diagnostic until its adapter arrives. There is no runtime fallback.
