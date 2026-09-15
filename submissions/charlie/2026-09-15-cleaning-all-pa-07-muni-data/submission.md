---
title: Cleaning All PA 07 Muni Data
assignment: Data Anomalies Fix
---
Errors in the "All PA07 Voting Data" tab, checked against certified state and county results:

Nazareth and Lower Nazareth are swapped. Each row has the other town's numbers in every race for 2018, 2020, 2022, and in 2024 President and Senate. Only 2024 House is correct.
Williams Township and Wilson have their President numbers swapped in 2020 and 2024. Senate and House are fine.
Carbon County's 2022 and 2024 numbers are in the wrong year's columns for all 23 municipalities. 2024 President holds 2022 Senate, 2024 Senate holds 2022 Governor, 2022 Governor holds 2024 Senate, 2022 Senate holds 2024 President. Carbon's 2024 House also uses an early, uncertified count.
Seven typos in Northampton 2020 House: Bethlehem, Bethlehem Township, Bushkill, Easton, Lower Mount Bethel, Upper Mount Bethel, Wilson. One number wrong in each.
72 "Party that won" labels don't match the votes in the same row, mostly because of the swaps above.
2020 House incumbent is listed as Republican in every row. It was Susan Wild, a Democrat.
Three turnout cells contain a party name instead of a number (Bethlehem 2024, Bethlehem Township 2018 and 2022).
