SPADE-like Sequential Pattern Mining

A Python implementation of a SPADE-inspired algorithm for discovering frequent sequential patterns.

This project was developed as part of the Data Mining Methods in Knowledge Discovery (Metody eksploracji danych w odkrywaniu wiedzy) university course.


Project Overview

The goal of this project is to implement and evaluate algorithms for frequent sequential pattern mining using a vertical database representation.

The implementation is inspired by the SPADE (Sequential Pattern Discovery using Equivalence classes) algorithm and uses temporal ID lists (tidlists) to efficiently calculate pattern support.


Four algorithm variants were implemented:

dSPADE – Depth-First Search (DFS)
bSPADE – Breadth-First Search (BFS)
maxLength-dSPADE – DFS with a maximum pattern length constraint
maxLength-bSPADE – BFS with a maximum pattern length constraint

The project also includes automated tests, experiment execution scripts, and performance analysis on real-world sequential datasets.
