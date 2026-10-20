# LearningMAP KC components

Repository: https://github.com/ai-for-edu/LearningMAP

Pinned commit: `bb17f6a7e8c105248d80126b2bf07ff07209b83f`. License: Apache-2.0 (included).

- `kc.py`: unchanged `group_questions_by_route`, `sample_questions` from `run/build_kc_skills.py`, and `KCSkill` from `src/llm/schemas.py`; imports reduced to those needed by these definitions.
- `prompts/loader.py`, `kc_skill_from_bank.j2`: copied unchanged from `src/prompts/`.
- `prompts/kc_skill_block.j2`: translated display labels; removed an unconditional claim of question-bank evidence.
- `prompts/kc_skill_from_bank_zh.j2`: local Chinese adaptation with explicit knowledge-only draft mode and frozen knowledge inputs.

Question adapters, boundary sampling, revision binding, coverage and job persistence belong to Lingzhi. No XES3G5M dataset or learner memory data is included.
