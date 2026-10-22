# Matcher evaluation

How the matcher's setup (model, fusion weights, reranker, translation) was chosen, and how to re-check it after a change.

## Test set

- `queries.json`: 40 applicant-style descriptions. 30 are statement-style, written to cover the field's subareas, regions, methods and some niche topics; 6 are short keyword queries; 4 are in Chinese.
- `judgments.json`: 1,309 query–faculty pairs graded 0–3 under `RUBRIC.md`.
  - Pairs were pooled from the top 10 of every system compared, in two rounds, so every system in the final table is fully judged at depth 10.
  - Graders were independent model reviewers. They saw only the profile card (summary, keywords, research areas, labels and a short profile excerpt), with no system names and in shuffled order.

## Results (nDCG@10)

| System | all | statement | short | Chinese | browser download |
|---|---|---|---|---|---|
| Previous production (bge-small, saturated keyword score) | 0.693 | 0.758 | 0.820 | 0.010 | 34 MB |
| bge-small, new fusion | 0.741 | 0.804 | 0.875 | 0.065 | 34 MB |
| bge-small, new fusion + MiniLM rerank | 0.762 | 0.827 | 0.895 | 0.080 | 57 MB |
| arctic-embed-m-v1.5, dense only | 0.758 | 0.813 | 0.883 | 0.163 | 110 MB |
| arctic, new fusion | 0.787 | 0.852 | 0.875 | 0.167 | 110 MB |
| arctic, new fusion + MiniLM rerank | 0.796 | 0.862 | 0.877 | 0.180 | 133 MB |
| **arctic + fusion + rerank + translation and glossary (shipped)** | **0.849** | 0.862 | 0.877 | 0.708 | 133 MB (+110 MB for Chinese without a built-in translator) |
| Qwen3-Embedding-0.6B, dense only (reference) | 0.763 | 0.760 | 0.877 | 0.616 | 614 MB |
| Qwen3-Embedding-0.6B + bge-reranker-v2-m3 (reference) | 0.817 | 0.814 | 0.898 | 0.713 | ~1.2 GB |

What the experiments showed:
- **The fusion was the cheapest fix.** The old keyword score capped at 100, so many people tied. Per-query z-score fusion (85/15) with BM25 over the published text gained about 0.05 with the same model.
- **The model mattered next.** arctic-embed-m-v1.5 beat every small or multilingual alternative tried on English queries, and matched or beat Qwen3-0.6B. The alternatives were bge-small, bge-base, arctic-s, mxbai-xsmall, nomic-v1.5, multilingual-e5-small and -base, gte-multilingual and bge-m3.
- **Document views:** profile text alone embeds poorly (0.25). The LLM summary carries most of the signal, and summing the summary, profile-text and published views is best.
- **Not worth keeping:**
  - Splitting long queries into sentences did not help.
  - Label hints are nearly neutral, so they stay small.
  - Truncating vectors below 768 dimensions cost about 0.01.
- **Rerankers:** only ms-marco-MiniLM-L-6 helped among the small cross-encoders; mxbai-rerank-xsmall and bge-reranker-base did not. Blending it 50/50 with the first-pass order beats replacing that order.
- **Chinese:** this pipeline translates first. The small opus-mt model garbles platform names and method terms, so a glossary (`pipeline/glossary_zh.json`) appends them as an English keyword line. The query vector averages the translated sentence and the keyword line, which keeps a bad translation from dominating.
  - With the browser's own (quantized) translations this scores 0.708.
  - Caveat: there are only 4 Chinese test queries, and the glossary was written with them in view, so treat 0.71 as optimistic.

## Re-running

```bash
conda activate nlp
python pipeline/eval/run_systems.py                      # runs for the judging pool (cached under data/cache/eval/)
python pipeline/eval/experiments.py                      # metrics table for every cached run
python pipeline/eval/make_packets.py 10 4 <system> ...   # blind packets for pairs not yet judged
python pipeline/eval/merge_judgments.py                  # fold graded packets into judgments.json
```

`harness.py` replicates the browser scoring. The tokenizer, BM25 and published text come from `pipeline/textmatch.py`, which `src/lib/match.ts` mirrors. Profile excerpts in the packets come from the local raw files and are never committed.
