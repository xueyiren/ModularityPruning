from .louvain_utilities import louvain_part_with_membership, part_modularity
from .partition_utilities import all_degrees, membership_to_communities
from .progress import Progress
from collections import defaultdict
from champ import get_intersection
import math
import numpy as np
from numpy.random import choice
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from utilities.louvain_utilities import louvain_part_with_membership
import igraph as ig


def manual_CHAMP(G, all_parts, gamma_0, gamma_f, gamma_iters=5000, show_progress=True):
    """
    Inefficiently calculates the CHAMP set at :gamma_iters: gamma points in [:gamma_0:, :gamma_f:].

    Returns a list of optimal [(gamma, quality, membership), ...] from :all_parts:.
    """

    all_parts = sorted(all_parts)
    optimal_parts = [(g, -math.inf, None) for g in np.linspace(gamma_0, gamma_f, gamma_iters)]
    if show_progress:
        progress = Progress(len(all_parts))

    for i, p in enumerate(all_parts):
        part = louvain_part_with_membership(G, p)
        for j in range(len(optimal_parts)):
            g, best_Q, best_part = optimal_parts[j]
            if part.quality(g) > best_Q + 1e-10:
                optimal_parts[j] = (g, part_modularity(G, p, g), p)

        if show_progress:
            progress.update(i)

    if show_progress:
        progress.done()

    return optimal_parts


def get_interior_point(halfspaces, singlelayer=True):
    '''
    Find interior point to calculate intersections
    :param halfspaces: list of halfspaces
    :return: an approximation to the point most interior to the halfspace intersection polyhedron (Chebyshev center).
    '''

    normals, offsets = np.split(halfspaces, [-1], axis=1)

    if singlelayer:
        # in our case, the last two halfspaces are boundary halfspaces
        interior_hs, boundaries = np.split(halfspaces, [-2], axis=0)
    else:
        # the last six halfspaces are boundary halfspaces
        interior_hs, boundaries = np.split(halfspaces, [-6], axis=0)

    # randomly sample up to 50 of the halfspaces
    sample_len = min(50, len(interior_hs))  # len(interior_hs)
    sampled_hs = np.vstack((interior_hs[choice(interior_hs.shape[0], sample_len, replace=False)], boundaries))

    # compute the Chebyshev center of the sampled halfspaces' intersection
    norm_vector = np.reshape(np.linalg.norm(sampled_hs[:, :-1], axis=1), (sampled_hs.shape[0], 1))
    c = np.zeros((sampled_hs.shape[1],))
    c[-1] = -1
    A = np.hstack((sampled_hs[:, :-1], norm_vector))
    b = -sampled_hs[:, -1:]

    res = linprog(c, A_ub=A, b_ub=b, bounds=None, method='interior-point')

    assert res.status == 0, {1: "Interior point calculation: scipy.optimize.linprog exceeded iteration limit",
                             2: "Interior point calculation: scipy.optimize.linprog problem is infeasible",
                             3: "Interior point calculation: scipy.optimize.linprog problem is unbounded"}[res.status]

    intpt = res.x[:-1]  # res.x contains [interior_point, distance to enclosing polyhedron]

    # ensure that the computed point is actually interior to all halfspaces
    assert (np.dot(normals, intpt) + np.transpose(offsets) < 0).all() and res.success
    return intpt


def CHAMP_2D(G, all_parts, gamma_0, gamma_f, show_progress=True):
    """Calculates the CHAMP set at :gamma_0: <= gamma <= :gamma_f:."""

    all_parts = list(all_parts)
    num_partitions = len(all_parts)

    partition_coefficients = partition_coefficients_2D(G, all_parts)
    A_hats, P_hats = partition_coefficients

    # TODO: optimize
    top = max(A_hats - P_hats * gamma_0)
    right = gamma_f  # TODO: max intersection x?
    halfspaces = np.vstack((halfspaces_from_coefficients_2D(*partition_coefficients),
                            np.array([[0, 1, -top], [1, 0, -right]])))

    # TODO: scale axes so Chebyshev center is better for problem?
    interior_point = get_interior_point(halfspaces)
    hs = HalfspaceIntersection(halfspaces, interior_point)

    # scipy does not support facets by halfspace directly, so we must compute them
    facets_by_halfspace = defaultdict(list)
    for v, idx in zip(hs.intersections, hs.dual_facets):
        assert np.isfinite(v).all()
        for i in idx:
            if i < num_partitions:
                facets_by_halfspace[i].append(v)

    ranges = []
    for i, intersections in facets_by_halfspace.items():
        x1, x2 = intersections[0][0], intersections[1][0]
        if x1 > x2:
            x1, x2 = x2, x1
        ranges.append((x1, x2, all_parts[i]))

    return sorted(ranges, key=lambda x: x[0])


def CHAMP_3D(G_intralayer, G_interlayer, layer_vec, all_parts, gamma_0, gamma_f, omega_0, omega_f):
    """Calculates the CHAMP set at :gamma_0: <= gamma <= :gamma_f: and :omega_0: <= omega <= :omega_f:.

    Defers to the original CHAMP implementation for most of the halfspace intersection for now.

    Returns a list of [(list of polygon vertices in (gamma, omega) plane, membership), ...]"""

    # NOTE: layer_vec should be a numpy array here

    all_parts = list(all_parts)
    partitions_coefficients = partition_coefficients_3D(G_intralayer, G_interlayer, layer_vec, all_parts)
    A_hats, P_hats, C_hats = partitions_coefficients

    champ_coef_array = np.vstack((A_hats, P_hats, C_hats)).T

    for attempt in range(1, 10):
        try:
            champ_domains = get_intersection(champ_coef_array, max_pt=(omega_f, gamma_f))
            break
        except:  # QhullError
            continue
    else:
        # If this actually occurs, it's best to break your input partitions into smaller subsets
        # Then, repeatedly combine the somewhere dominant (or "admissible") domains with CHAMP
        assert False, "CHAMP failed, " \
                      "perhaps break your input partitions into smaller subsets and then combine with CHAMP?"

    domains = [([x[:2] for x in polyverts], all_parts[part_idx]) for part_idx, polyverts in champ_domains.items()]
    return domains


def optimal_parts_to_ranges(optimal_parts):
    """Converts a list of [(gamma, quality, membership), ...] to their ranges of dominance.

    Returns a list of [(gamma_start, gamma_end, membership), ...]."""

    ranges = []
    i = 0
    while i < len(optimal_parts):
        gamma_start, Q, part = optimal_parts[i]
        gamma_end = gamma_start
        while i + 1 < len(optimal_parts) and optimal_parts[i + 1][2] == part:
            gamma_end = optimal_parts[i + 1][0]
            i += 1
        ranges.append((gamma_start, gamma_end, part))

        i += 1

    return ranges


def partition_coefficients_2D(G, partitions):
    """Computes A_hat and P_hat for partitions of :G:.

    TODO: support edge weights"""

    all_edges = [(e.source, e.target) for e in G.es]
    degree = all_degrees(G)
    twom = 2 * G.ecount()

    # multiply by 2 only if undirected here
    if G.is_directed():
        A_hats = np.array([sum([membership[u] == membership[v] for u, v in all_edges])
                           for membership in partitions])
    else:
        A_hats = np.array([2 * sum([membership[u] == membership[v] for u, v in all_edges])
                           for membership in partitions])

    if G.is_directed():
        P_hats = np.array([sum(sum(degree[v] for v in vs) ** 2 for vs in membership_to_communities(membership).values())
                           for membership in partitions]) / (2 * twom)
    else:
        P_hats = np.array([sum(sum(degree[v] for v in vs) ** 2 for vs in membership_to_communities(membership).values())
                           for membership in partitions]) / twom

    # P_hats = np.array([
    #     louvain_part_with_membership(G, part).quality(resolution_parameter=0.0) -
    #     louvain_part_with_membership(G, part).quality(resolution_parameter=1.0) for part in partitions
    # ])

    return A_hats, P_hats


def halfspaces_from_coefficients_2D(A_hats, P_hats):
    """Converts partitions' coefficients to halfspace normal, offset.

    Q >= -P_hat*gamma + A_hat
    -Q - P_hat*gamma + A_hat <= 0
    (-P_hat, -1) * (Q, gamma) + A_hat <= 0
    """
    return np.vstack((-P_hats, -np.ones_like(P_hats), A_hats)).T


def partition_coefficients_3D(G_intralayer, G_interlayer, layer_vec, partitions):
    """Computes A_hat, P_hat, C_hat for partitions of a graph with intralayer edges given in :G_intralayer:,
    interlayer edges given in :G_interlayer:, and layer membership :layer_vec:.

    TODO: support edge weights"""

    all_intralayer_edges = [(e.source, e.target) for e in G_intralayer.es]
    all_interlayer_edges = [(e.source, e.target) for e in G_interlayer.es]
    degree = all_degrees(G_intralayer)

    # multiply by 2 only if undirected here
    if G_intralayer.is_directed():
        A_hats = np.array([sum([membership[u] == membership[v] for u, v in all_intralayer_edges])
                           for membership in partitions])
    else:
        A_hats = np.array([2 * sum([membership[u] == membership[v] for u, v in all_intralayer_edges])
                           for membership in partitions])

    P_hats = []
    num_layers = max(layer_vec) + 1
    if G_intralayer.is_directed() and G_interlayer.is_directed():
        # Note: layer_vec seems to need to be a numpy array here

        # Just to be entirely sure our coefficients are correct in this case, we split into layers separately.
        # This isn't strictly necessary (this can be made much more efficient), but makes the reasoning easier.
        for membership in partitions:
            P_hat = 0
            part_obj = louvain_part_with_membership(G_intralayer, membership)
            for layer in range(num_layers):
                cind = np.where(layer_vec == layer)[0]
                if len(cind) > 0:
                    subgraph = part_obj.graph.subgraph(cind)
                    submem = np.array(part_obj.membership)[cind]
                    layer_part = louvain_part_with_membership(subgraph, submem)
                    P_hat += layer_part.quality(resolution_parameter=0.0) - layer_part.quality(resolution_parameter=1.0)
            P_hats.append(P_hat)
    else:
        twom_per_layer = [0] * num_layers
        for e in G_intralayer.es:
            twom_per_layer[layer_vec[e.source]] += 2
        for membership in partitions:
            strength = 0
            for vs in membership_to_communities(membership).values():
                layer_strengths = [0] * num_layers
                for v in vs:
                    layer_strengths[layer_vec[v]] += degree[v]
                strength += sum(layer_strengths[layer] ** 2 / twom_per_layer[layer] for layer in range(num_layers))
            P_hats.append(strength)
    P_hats = np.array(P_hats)

    # multiply by 2 only if undirected here
    if G_interlayer.is_directed():
        C_hats = np.array([sum([membership[u] == membership[v] for u, v in all_interlayer_edges])
                           for membership in partitions])
    else:
        C_hats = np.array([2 * sum([membership[u] == membership[v] for u, v in all_interlayer_edges])
                           for membership in partitions])

    return A_hats, P_hats, C_hats