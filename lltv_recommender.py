import argparse

import simulations

if __name__ == "__main__":

    parser = argparse.ArgumentParser(prog="Morpho Blue agent-based simulation")

    parser.add_argument("--seed", type=int, default=101, help="Random seed")
    parser.add_argument(
        "--n_borrow_agents", type=int, default=10, help="Number of borrowing agents"
    )
    parser.add_argument("--sigma", type=float, default=0.3, help="price volatility")

    parser.add_argument(
        "--n_steps", type=int, default=100, help="Number of steps of the simulation"
    )
    args = parser.parse_args()

    assert (
        0 < args.n_borrow_agents < 100
    ), "Number of borrow agents must be between 0 and 100"

    lltv = 9 * 10**17
    results = simulations.morpho_blue.sim.run_from_cache(
        seed=args.seed,
        n_steps=args.n_steps,
        n_borrow_agents=args.n_borrow_agents,
        sigma=args.sigma,
        lltv=lltv,
    )

    simulations.morpho_blue.plotting.plot_results_borrowers(
        records=results, lltv=lltv / 10**18, n_borrow_agents=args.n_borrow_agents
    )
