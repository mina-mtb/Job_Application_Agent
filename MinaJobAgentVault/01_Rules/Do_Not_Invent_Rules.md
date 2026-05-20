# Do Not Invent Rules

> ⚠️ This file is a hard constraint. It overrides ALL other instructions.

## Absolute Prohibitions

The AI agent MUST NEVER:

1. **Invent work experience** — no fake companies, roles, or dates
2. **Inflate duration** — if Mina worked 3 months, never write "6 months"
3. **Fabricate skills** — if a skill is not in `Base_CV.md`, it does not exist
4. **Invent projects** — no fake GitHub projects, no fake thesis titles
5. **Claim certifications** — only certifications explicitly listed in the base CV
6. **Exaggerate seniority** — Mina is junior-to-mid level; never write "senior" or "led a team of 10"
7. **Add fake metrics** — no "reduced latency by 40%" unless Mina said so herself

## What Triggers a Violation
- Saying Mina has "5 years of Azure experience" (she has basics)
- Adding "Terraform" to the skills section (not in base CV)
- Writing "led cross-functional teams" without evidence
- Claiming a specific degree GPA that wasn't provided

## The Test Before Every CV Line
Ask: *"Can I find this exact claim in base_cv.md or mina_profile.yaml?"*
- YES → allowed
- NO → remove it or rewrite as something truthful

## Why This Matters
False CVs damage Mina's reputation, create legal risk,
and destroy trust if discovered in an interview.
Honesty is the only strategy.
