from .louvain_utilities import singlelayer_louvain, multilayer_louvain
from .parameter_estimation_utilities import louvain_part_with_membership, estimate_singlelayer_SBM_parameters, \
    gamma_estimate_from_parameters, omega_function_from_model, estimate_multilayer_SBM_parameters
from .partition_utilities import in_degrees
import louvain


def iterative_monolayer_resolution_parameter_estimation(G, gamma=1.0, tol=1e-2, max_iter=25, verbose=False,
                                                        method="louvain"):
    """
    Monolayer variant of ALG. 1 from "Relating modularity maximization and stochastic block models in multilayer
    networks." The nested functions here are just used to match the pseudocode in the paper.

    :param G: input graph
    :param gamma: starting gamma value
    :param tol: convergence tolerance
    :param max_iter: maximum number of iterations
    :param verbose: whether or not to print verbose output
    :param method: community detection method to use
    :return: gamma to which the iteration converged and the resulting partition
    """

    if 'weight' not in G.es:
        G.es['weight'] = [1.0] * G.ecount()
    m = sum(G.es['weight'])

    if method == "louvain":
        def maximize_modularity(resolution_param):
            return singlelayer_louvain(G, resolution_param, return_partition=True)
    elif method == "2-spinglass":
        def maximize_modularity(resolution_param):
            membership = G.community_spinglass(spins=2, gamma=resolution_param).membership
            return louvain_part_with_membership(G, membership)
    else:
        raise ValueError(f"Community detection method {method} not supported")

    def estimate_SBM_parameters(partition):
        return estimate_singlelayer_SBM_parameters(G, partition, m=m)

    def update_gamma(omega_in, omega_out):
        return gamma_estimate_from_parameters(omega_in, omega_out)

    part, last_gamma = None, None
    for iteration in range(max_iter):
        part = maximize_modularity(gamma)
        omega_in, omega_out = estimate_SBM_parameters(part)

        last_gamma = gamma
        gamma = update_gamma(omega_in, omega_out)

        if gamma is None:
            raise ValueError(f"gamma={last_gamma:.3f} resulted in degenerate partition")

        if verbose:
            print(f"Iter {iteration:>2}: {len(part)} communities with Q={part.q:.3f} and "
                  f"gamma={last_gamma:.3f}->{gamma:.3f}")

        if abs(gamma - last_gamma) < tol:
            break  # gamma converged
    else:
        if verbose:
            print(f"Gamma failed to converge within {max_iter} iterations. "
                  f"Final move of {abs(gamma - last_gamma):.3f} was not within tolerance {tol}")

    if verbose:
        print(f"Returned {len(part)} communities with Q={part.q:.3f} and gamma={gamma:.3f}")

    return gamma, part


def check_multilayer_graph_consistency(G_intralayer, G_interlayer, layer_vec, model, m_t, T, N=None, Nt=None):
    """
    Checks that the structures of the intralayer and interlayer graphs are consistent and match the given model.

    :param G_intralayer: input graph containing all intra-layer edges
    :param G_interlayer: input graph containing all inter-layer edges
    :param layer_vec: vector of each vertex's layer membership
    :param model: network layer topology (temporal, multilevel, multiplex)
    :param m_t: vector of total edge weights per layer
    :param T: number of layers in input graph
    :param N: number of nodes per layer
    :param Nt: vector of nodes per layer
    """

    rules = [T > 1,
             "Graph must have multiple layers",
             G_interlayer.is_directed(),
             "Interlayer graph should be directed",
             G_interlayer.vcount() == G_intralayer.vcount(),
             "Inter-layer and Intra-layer graphs must be of the same size",
             len(layer_vec) == G_intralayer.vcount(),
             "Layer membership vector must have length matching graph size",
             all(m > 0 for m in m_t),
             "All layers of graph must contain edges",
             all(layer_vec[e.source] == layer_vec[e.target] for e in G_intralayer.es),
             "Intralayer graph should not contain edges across layers",
             model != 'temporal' or G_interlayer.ecount() == N * (T - 1),
             "Interlayer temporal graph must contain (nodes per layer) * (number of layers - 1) edges",
             model != 'temporal' or (G_interlayer.vcount() % T == 0 and G_intralayer.vcount() % T == 0),
             "Vertex count of a temporal graph should be a multiple of the number of layers",
             model != 'temporal' or all(nt == N for nt in Nt),
             "Temporal networks must have the same number of nodes in every layer",
             model != 'multilevel' or all(nt > 0 for nt in Nt),
             "All layers of a multilevel graph must be consecutive and nonempty",
             model != 'multilevel' or all(in_degree <= 1 for in_degree in in_degrees(G_interlayer)),
             "Multilevel networks should have at most one interlayer in-edge per node",
             model != 'multiplex' or all(nt == N for nt in Nt),
             "Multiplex networks must have the same number of nodes in every layer",
             model != 'multiplex' or G_interlayer.ecount() == N * T * (T - 1),
             "Multiplex interlayer networks must contain edges between all pairs of layers"]

    checks, messages = rules[::2], rules[1::2]

    if not all(checks):
        raise ValueError("Input graph is malformed\n" + "\n".join(m for c, m in zip(checks, messages) if not c))


def iterative_multilayer_resolution_parameter_estimation(G_intralayer, G_interlayer, layer_vec, gamma=1.0, omega=1.0,
                                                         gamma_tol=1e-2, omega_tol=5e-2, omega_max=1000, max_iter=25,
                                                         model='temporal', verbose=False):
    """
    Multilayer variant of ALG. 1 from "Relating modularity maximization and stochastic block models in multilayer
    networks." The nested functions here are just used to match the pseudocode in the paper.

    :param G_intralayer: input graph containing all intra-layer edges
    :param G_interlayer: input graph containing all inter-layer edges
    :param layer_vec: vector of each vertex's layer membership
    :param gamma: starting gamma value
    :param omega: starting omega value
    :param gamma_tol: convergence tolerance for gamma
    :param omega_tol: convergence tolerance for omega
    :param max_iter: maximum number of iterations
    :param omega_max: maximum allowed value for omega
    :param model: network layer topology (temporal, multilevel, multiplex)
    :param verbose: whether or not to print verbose output
    :return: gamma, omega to which the iteration converged and the resulting partition
    """

    if 'weight' not in G_intralayer.es:
        G_intralayer.es['weight'] = [1.0] * G_intralayer.ecount()

    if 'weight' not in G_interlayer.es:
        G_interlayer.es['weight'] = [1.0] * G_interlayer.ecount()

    T = max(layer_vec) + 1  # layer count
    optimiser = louvain.Optimiser()

    # compute total edge weights per layer
    m_t = [0] * T
    for e in G_intralayer.es:
        m_t[layer_vec[e.source]] += e['weight']

    # compute total node counts per layer
    N = G_intralayer.vcount() // T
    Nt = [0] * T
    for layer in layer_vec:
        Nt[layer] += 1

    check_multilayer_graph_consistency(G_intralayer, G_interlayer, layer_vec, model, m_t, T, N, Nt)
    update_omega = omega_function_from_model(model, omega_max, T=T)
    update_gamma = gamma_estimate_from_parameters

    def maximize_modularity(intralayer_resolution, interlayer_resolution):
        return multilayer_louvain(G_intralayer, G_interlayer, layer_vec, intralayer_resolution, interlayer_resolution,
                                  optimiser=optimiser, return_partition=True)

    def estimate_SBM_parameters(partition):
        return estimate_multilayer_SBM_parameters(G_intralayer, G_interlayer, layer_vec, partition, model,
                                                  N=N, T=T, Nt=Nt, m_t=m_t)

    part, K, last_gamma, last_omega = (None,) * 4
    for iteration in range(max_iter):
        part = maximize_modularity(gamma, omega)
        theta_in, theta_out, p, K = estimate_SBM_parameters(part)

        if not 0.0 <= p <= 1.0:
            raise ValueError(f"gamma={gamma:.3f}, omega={omega:.3f} resulted in impossible estimate p={p:.3f}")

        last_gamma, last_omega = gamma, omega
        gamma = update_gamma(theta_in, theta_out)

        if gamma is None:
            raise ValueError(f"gamma={last_gamma:.3f}, omega={last_omega:.3f} resulted in degenerate partition")

        omega = update_omega(theta_in, theta_out, p, K)

        if verbose:
            print(f"Iter {iteration:>2}: {K} communities with Q={part.q:.3f}, gamma={last_gamma:.3f}->{gamma:.3f}, "
                  f"omega={last_omega:.3f}->{omega:.3f}, and p={p:.3f}")

        if abs(gamma - last_gamma) < gamma_tol and abs(omega - last_omega) < omega_tol:
            break  # gamma and omega converged
    else:
        if verbose:
            print(f"Parameters failed to converge within {max_iter} iterations. "
                  f"Final move of ({abs(gamma - last_gamma):.3f}, {abs(omega - last_omega):.3f}) "
                  f"was not within tolerance ({gamma_tol}, {omega_tol})")

    if verbose:
        print(f"Returned {K} communities with Q={part.q:.3f}, gamma={gamma:.3f}, and omega={omega:.3f}")

    return gamma, omega, part
