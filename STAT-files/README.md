# STAT Files

This directory contains statistical reports generated during the execution of the SPADE-like sequential pattern mining algorithms.

Each STAT file provides detailed information about an experiment, including:

- Input dataset characteristics (number of sequences, transactions, and distinct items)
- Algorithm variant (dSPADE, bSPADE, maxLength-dSPADE, or maxLength-bSPADE)
- Minimum support threshold (`sup`)
- Maximum pattern length (`maxLength`), if applicable
- Execution times for individual processing stages
- Total execution time
- Number of generated candidates and discovered frequent patterns
- Maximum candidate and pattern lengths
- Support and tidlist statistics
- Detailed statistics grouped by pattern length

These files were generated to analyze and compare the performance of different SPADE-like algorithm variants across multiple datasets and parameter configurations.
