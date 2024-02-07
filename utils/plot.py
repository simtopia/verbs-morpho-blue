import os
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np


def plot_results_borrowers(
    records: List[List[Tuple[int, float, float, float, float]]], dirname: str
):
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    n_steps = len(records)
    records = np.array(records).reshape(n_steps, -1, 5)
    n_borrow_agents = records.shape[1]

    fig, ax = plt.subplots(figsize=(6, 3))
    for i in range(n_borrow_agents):
        hf = records[:, i, 1]
        step = records[:, i, 0]
        ax.plot(step[hf < 100], hf[hf < 100], label=f"Borrower {i}")
    ax.set_xlabel("simulation step")
    ax.set_ylabel("health factor")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(dirname, "hf.pdf"))

    fig, ax = plt.subplots(figsize=(6, 3))
    for i in range(n_borrow_agents):
        ax.plot(records[:, i, 0], records[:, i, 2], label=f"Borrower {i}")
    ax.set_xlabel("simulation step")
    ax.set_ylabel("debt assets")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(dirname, "debt.pdf"))

    fig, ax = plt.subplots(figsize=(6, 3))
    for i in range(n_borrow_agents):
        ax.plot(records[:, i, 0], records[:, i, 3], label=f"Borrower {i}")
    ax.set_xlabel("simulation step")
    ax.set_ylabel("collateral assets")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(dirname, "collateral.pdf"))

    fig, ax = plt.subplots(figsize=(6, 3))
    for i in range(n_borrow_agents):
        ax.plot(records[:, i, 0], records[:, i, 4], label=f"Borrower {i}")
    ax.set_xlabel("simulation step")
    ax.set_ylabel("price")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(dirname, "price.pdf"))

    plt.close()
