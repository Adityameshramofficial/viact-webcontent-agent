# Industry Page Generator — SOP

## Purpose
Generate a complete viAct.ai industry vertical landing page matching the format of the live Construction and Manufacturing dynamic pages. Output goes to Google Sheets → manual copy-paste into Wix CMS dynamic fields.

## Agent Personas
Three personas run simultaneously inside one Groq/Llama call:
- **Aria Singh** (Content) — specificity over adjectives; real numbers; hazard + consequence
- **Marcus Webb** (SEO) — long-tail keywords; 150-160 char meta descriptions; alt text formula
- **Dani Cruz** (Images) — CCTV perspective + AI overlay; viGent = dark dashboard never CCTV; exact px dimensions in every prompt

## Output Structure (8 Sections)

| Section | Format |
|---|---|
| Hero | H1 eyebrow + H2 % headline + H3 description (35-45 words) + YouTube embed |
| Proven Impact | Title + subtitle + 3 metrics (label: "X% ↑ Short Label", description: 10-15 words with real numbers) |
| AI CCTV Use Cases | Section title + 6 use cases (H3 title max 6 words + description 20-30 words: hazard + consequence) |
| Pre-Built Solutions | 15-20 word description |
| viGent | 30-40 words: continuous data → specific job titles → real-time insights |
| Voices from the Field | 5 testimonials (35-50 words, first-person, different role/country each) |
| CTA | Headline + description (20-30 words, names 2+ specific job titles) |

## H-Tag Rules
- `[H1]`: exactly one — "AI for Safety & Productivity in [Industry]"
- `[H2]`: hero % headline + all section titles
- `[H3]`: hero description, metric titles, use case titles
- Never `[H4]`

## Image Prompts (11 total)
1-6: Use cases (520x327, 488x293, 520x303×3, 520x317) — CCTV perspective, high angle, industry environment, AI bounding boxes
7: viGent dashboard (422x377) — dark-mode dashboard render, NEVER CCTV
8-11: Reviewer headshots (56x56 each) — professional LinkedIn-style, plain dark background

## Wix CMS Fields (industry_cms_fields)
Each sub-field maps to one Wix CMS dynamic field:
`hero_subheadline`, `hero_body_copy`, `impact_section_title`, `impact_subtitle`, `metrics[3]`, `use_cases_section_title`, `use_cases[6]`, `solutions_description`, `vigent_description`, `testimonials[5]`, `cta_headline`, `cta_description`

## Quality Gates
- metrics: exactly 3, real numbers in each description
- use_cases: exactly 6, hazard + consequence in each
- testimonials: exactly 5, first-person, different country each
- nano_banana_prompts: exactly 11, pixel dimensions in every prompt string
- meta_title: ≤60 chars
- meta_description: 150-160 chars

## viAct Verified Stats (use ONLY these)
- 90% site risk reduction | 50% TRIR reduction | 65% LTI reduction
- 80% safety expenditure reduction | $2.5M+ savings per project
- 400+ sites | 32,000+ workers protected | 7,200+ lost workdays prevented

## Custom Industries
For industries not in the preset list, the agent derives:
- `industry_slug` from the name (lowercase, hyphenated)
- `viact_url` = empty → generates fresh content
- `competitor_urls` = empty → uses only viAct reference data + custom instructions
Use the Custom Instructions field to specify key hazards, regional regulations, and focus areas.
