---
title: PA07 All Regressions
assignment: PA07 All Regressions
---
The regressions ask one simple question: does X/Twitter sentiment help predict the 2024 PA-07 House vote better than recent election results alone?

Here’s what we actually did:

Starting point (fundamentals)
For each municipality, we used the 2022 Democratic House share to predict the 2024 Democratic House share. That alone works very well — about 97% of the pattern across towns is already explained by 2022.
Add social media
We then added two things from our X posts: average VADER sentiment (positive/negative tone) and how many posts mentioned that town. We asked whether those improve the prediction.
Answer so far
Sentiment and post volume don’t meaningfully help once 2022 vote share is in the model. They’re still useful as an attention / nowcast signal in the bigger forecast mesh — just not as a standalone vote machine.
Allentown / Bethlehem / Easton check
We also looked at just those three cities, using residual errors and candidate-focused, time-weighted sentiment. Same story: weak link, and too few cities to lean on hard.
