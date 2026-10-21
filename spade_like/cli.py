from __future__ import annotations
import argparse
from .core import run_algorithm, write_results

def main():
    p=argparse.ArgumentParser(description='SPADE-like: dSPADE, bSPADE i warianty maxLength')
    p.add_argument('algorithm', choices=['dSPADE','bSPADE','maxLength-dSPADE','maxLength-bSPADE'])
    p.add_argument('input')
    p.add_argument('--sup', type=int, required=True, help='minimalne wsparcie bezwzględne')
    p.add_argument('--max-length', type=int)
    p.add_argument('--out-dir', default='results')
    a=p.parse_args()
    if a.algorithm.startswith('maxLength') and a.max_length is None:
        p.error('--max-length jest wymagane dla wariantu maxLength')
    stats=run_algorithm(a.algorithm,a.input,a.sup,a.max_length)
    out,stat=write_results(stats,a.out_dir)
    print(out); print(stat)
if __name__=='__main__': main()
