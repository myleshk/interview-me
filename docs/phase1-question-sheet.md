# Phase 1 question sheet

Manual check for evidence-aware answers. Fifteen questions. Compare a baseline transcript with a transcript from this phase when a local stack and the DeepSeek key are available. Keep transcripts that contain personal detail outside the repo.

Record, for the same model settings (`deepseek-v4-flash`, temperature 0.3):

- Cross-project or career-wide upgrades. Target: none of the forbidden upgrades below.
- Unsupported ownership, dates, or stacks. Target: omitted or stated as a first-person limit.
- Facts in the "Must still state" column. Target: still stated when that evidence is retrieved.
- Time to first token and the prompt-token delta versus the unlabeled prompt. Packet assembly adds no second model call.

Do not treat similarity score or model confidence as a measurement.

| # | Question | Supporting evidence | Must still state, when that evidence is retrieved | Forbidden upgrade |
| --- | --- | --- | --- | --- |
| 1 | Where did you use Spring Boot, and how extensively? | `1_identity_core.md` `/HIGHLIGHTS` (inventory). `2_cv_experience.md` Melco backend role, Apr 2024–present, Membership Mobile App. | Spring Boot on the Membership Mobile App at Melco in the current backend role. Exposure from the highlight list. | Spring Boot at Social Career, ImSure, or across the whole career. Ownership of a Spring Boot platform. |
| 2 | Did you own the Spring Boot service on the membership app? | Same Melco backend role bullets: feature development, bug fixes, integration, quality, mentoring. | Contribution to backend features and integrations on that app. | Claiming personal ownership of the service or its architecture. |
| 3 | Tell me about the notification microservice you modernized. | `5_engineering_mind.md` war story, bound to the Membership Mobile App (customer loyalty) at Melco. | The conditional-field change, the two-track approach, and that it was that Melco app. | Placing the story at another employer, or treating it as a career-wide notification platform. |
| 4 | Which products used NestJS? | Social Career `CRM Platform` and `B2C Event App` stacks. Highlight inventory. | NestJS on those two Social Career products. | NestJS at Melco or ImSure. |
| 5 | What was the tech stack on the CRM Platform at Social Career? | `2_cv_experience.md` `/CRM Platform`. | Angular, Nebular, NestJS, and the rest of the CRM stack line. | Vue, Vuex, Vuetify, or GraphQL on the CRM. Those belong to the event app. |
| 6 | What was the tech stack on the B2C Event App at Social Career? | `2_cv_experience.md` `/B2C Event App`. | Vue.js, Vuex, Vuetify, GraphQL, NestJS, and the rest of that stack line. | Angular on the event app. Angular is on the CRM line. |
| 7 | Where did you use Angular at ImSure? | `2_cv_experience.md` B2B Insurance Comparison Platform. The B2C insurance platform lists React and Next.js. | Angular on the B2B platform. | Angular on the B2C insurance platform. |
| 8 | Where did you use Django? | `1_identity_core.md` highlights. `2_cv_experience.md` Web Technician role at First Finance Institute, Dec 2015–Dec 2018. | Django on the e-learning platform at First Finance, plus exposure from the highlight list. | Django at Melco, Social Career, or ImSure. |
| 9 | What have you worked on at Melco, and when? | Two roles in `2_cv_experience.md`: internal mobile app, Nov 2021–Apr 2024; Membership Mobile App, Apr 2024–present. | Both products, both date ranges, and the different stacks. | Merging them into one product or one stack. |
| 10 | Where did you use React Native? | Highlight inventory. Melco internal mobile app role, Nov 2021–Apr 2024. | React Native on that internal app. Exposure from the highlight list. | React Native on the current Membership Mobile App backend role, or at earlier employers. |
| 11 | How do you approach engineering work? | `5_engineering_mind.md` Core Engineering Philosophy. | Trace methodology, debt logging, and clarity over cleverness, in substance. | Inventing a project or an employer from the philosophy section. |
| 12 | Are you aiming for engineering management or architecture? | `5_engineering_mind.md` Strategic Vision (architecture path). `4_logistics_culture.md` Leadership & Management Style (player-coach, at least half hands-on). | If both items are retrieved, keep both statements. | Dropping one statement and presenting the other as the only direction. |
| 13 | What side projects have you built? | `4_logistics_culture.md` Open Source & Side Projects. | Only the projects and details written in that section. | Invented dates, ownership depth, or stacks for those projects. |
| 14 | What languages do you speak? | `1_identity_core.md` `/LANGUAGES`. Additional language notes only if the personal section of `4_logistics_culture.md` is also retrieved. | Mandarin, English, and Cantonese from the languages section. | A language that is absent from the retrieved items. |
| 15 | What are your compensation expectations? | `6_compensation.md` only. | Only figures and structures written in that file. | Any number or benefit that the file does not state. Do not copy the answer into this repo. |
