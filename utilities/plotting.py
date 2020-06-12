from .partition_utilities import num_communities, ami
from random import shuffle
import numpy as np
import matplotlib
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
import matplotlib.pyplot as plt
import seaborn as sbn


def plot_adjacency(adj):
    plt.imshow(adj, cmap='Greys', interpolation='nearest')
    plt.title("Adjacency matrix")


def plot_estimates(gamma_estimates):
    """Plot partition dominance ranges with gamma estimates."""

    ax = plt.gca()
    num_parts = len(gamma_estimates)

    for i in range(num_parts):
        g_0, g_f, part, g_est = gamma_estimates[i]
        k = num_communities(part)
        plt.plot([g_0, g_f], [k, k], zorder=1, linewidth=2)
        plt.scatter([g_0, g_f], [k, k], s=30, marker='x', zorder=1)

    x_low, x_high = ax.get_xlim()
    y_low, y_high = ax.get_ylim()

    for i in range(num_parts):
        g_0, g_f, part, g_est = gamma_estimates[i]
        k = num_communities(part)
        if g_est is not None:
            middle = (g_0 + g_f) / 2
            k_new = 0
            for gamma_start, gamma_end, part, _ in gamma_estimates:
                if gamma_start <= g_est <= gamma_end:
                    k_new = num_communities(part)

            if k_new != 0:
                ax.plot([g_est], [k_new], c='black', marker='o', markersize=3)

            if k_new != 0 and x_low <= g_est <= x_high and y_low <= k_new <= y_high:
                ax.annotate("", xy=(g_est, k_new), xytext=(middle, k),
                            arrowprops=dict(alpha=0.5, facecolor="black", linewidth=1.5,
                                            arrowstyle="->, head_width=0.5, head_length=0.5"))
            else:
                truncated_x, truncated_y = g_est, k_new
                if g_est > x_high:
                    truncated_x = x_high
                elif g_est < x_low:
                    truncated_x = x_low
                if k_new == 0 or k_new > y_high:
                    truncated_y = y_high  # TODO: don't assume falling off high end of plot
                elif k_new < y_low:
                    truncated_y = y_low

                ax.annotate("", xy=(truncated_x, truncated_y), xytext=(middle, k),
                            arrowprops=dict(alpha=0.5, facecolor="black", linewidth=1.5,
                                            arrowstyle="->, head_width=0.5, head_length=0.5"))
                # plt.arrow(middle, k, arrow_scale * (g_est - middle), arrow_scale * (k_new - k),
                #           width=0.005, head_length=0.1, head_width=0.1, color="black",
                #           length_includes_head=True, alpha=0.5, zorder=2, **{"overhang": 0.5})


def plot_2d_domains(domains, xlim, ylim):
    """Plot partition dominance ranges in the (gamma, omega) plane, using the domains from CHAMP_3D.

    Limits output to xlim and ylim dimensions. Note that the plotting here has x=omega and y=gamma."""
    fig, ax = plt.subplots()
    patches = []

    for polyverts, membership in domains:
        polygon = Polygon(polyverts, True)
        patches.append(polygon)

    cnorm = matplotlib.colors.Normalize(vmin=0, vmax=len(domains))
    cmap = matplotlib.cm.get_cmap("Set1")
    colors = [cmap(cnorm(i)) for i in range(len(domains))]
    p = PatchCollection(patches, facecolors=colors, alpha=1.0, edgecolors='black', linewidths=2)
    ax.add_collection(p)
    plt.xlim(xlim)
    plt.ylim(ylim)


def plot_2d_domains_with_estimates(domains_with_estimates, xlim, ylim, plot_estimate_points=True, flip_axes=True):
    """Plot partition dominance ranges in the (gamma, omega) plane, using the domains from CHAMP_3D with their gamma
    and omega estimates overlaid.

    Limits output to xlim and ylim dimensions. Note that the plotting here has x=omega and y=gamma."""
    assert flip_axes
    fig, ax = plt.subplots()
    patches = []

    for polyverts, membership, gamma_est, omega_est in domains_with_estimates:
        if flip_axes:
            polyverts = [(x[1], x[0]) for x in polyverts]

        polygon = Polygon(polyverts, True)
        patches.append(polygon)

        centroid_x = np.mean([x[0] for x in polyverts])
        centroid_y = np.mean([x[1] for x in polyverts])

        if gamma_est is not None and omega_est is not None:
            width = xlim[1] - xlim[0]
            if centroid_x < xlim[0] - 0.05 * width or centroid_x > xlim[1] + 0.05 * width:
                continue

            if ylim[0] <= gamma_est <= ylim[1] and xlim[0] <= omega_est <= xlim[1]:
                # truncate arrows to edges of plot
                centroid_x = min(xlim[1], max(xlim[0], centroid_x))
                centroid_y = min(ylim[1], max(ylim[0], centroid_y))

                if plot_estimate_points:
                    ax.plot([omega_est], [gamma_est], c='black', marker='o', markersize=3)
                ax.annotate("", xy=(omega_est, gamma_est), xytext=(centroid_x, centroid_y),
                            annotation_clip=True,
                            arrowprops=dict(alpha=0.75, linewidth=1.5, color="black",
                                            arrowstyle="->, head_width=0.5, head_length=0.5"))

    cnorm = matplotlib.colors.Normalize(vmin=0, vmax=len(domains_with_estimates))
    cmap = matplotlib.cm.get_cmap("Set1")
    colors = [cmap(cnorm(i)) for i in range(len(domains_with_estimates))]
    shuffle(colors)

    p = PatchCollection(patches, facecolors=colors, alpha=1.0, edgecolors='black', linewidths=1.5)
    ax.add_collection(p)
    plt.xlim(xlim)
    plt.ylim(ylim)


def plot_2d_domains_with_num_communities(domains_with_estimates, xlim, ylim, flip_axes=True, K_max=None, tick_step=2):
    """Plot partition dominance ranges in the (gamma, omega) plane, using the domains from CHAMP_3D and coloring by the
    number of communities.

    Limits output to xlim and ylim dimensions. Note that the plotting here has x=omega and y=gamma."""
    assert flip_axes
    fig, ax = plt.subplots()
    patches = []
    cm = matplotlib.cm.viridis
    Ks = []

    for polyverts, membership, gamma_est, omega_est in domains_with_estimates:
        if flip_axes:
            polyverts = [(x[1], x[0]) for x in polyverts]

        if any(xlim[0] <= x[0] <= xlim[1] and ylim[0] <= x[1] <= ylim[1] for x in polyverts):
            polygon = Polygon(polyverts, True)
            patches.append(polygon)
            Ks.append(num_communities(membership))

    if K_max is not None:
        Ks = [min(K, K_max) for K in Ks]
    else:
        K_max = max(Ks)

    p = PatchCollection(patches, cmap=cm, alpha=1.0, edgecolors='black', linewidths=2)
    p.set_array(np.array(Ks))
    ax.add_collection(p)

    cbar = plt.colorbar(p, ticks=range(2, K_max + 1, tick_step))
    cbar.ax.tick_params(labelsize=12)
    cbar.set_label("Number of Communities", fontsize=16, labelpad=10)

    plt.xlim(xlim)
    plt.ylim(ylim)


def plot_2d_domains_with_ami(domains_with_estimates, ground_truth, xlim, ylim, flip_axes=False):
    """Plot partition dominance ranges in the (gamma, omega) plane, using the domains from CHAMP_3D and coloring by the
    AMI between the partitions and ground truth.

    Limits output to xlim and ylim dimensions. Note that the plotting here has x=omega and y=gamma."""
    assert flip_axes
    fig, ax = plt.subplots()
    patches = []
    cm = matplotlib.cm.copper
    amis = []

    for polyverts, membership, gamma_est, omega_est in domains_with_estimates:
        if flip_axes:
            polyverts = [(x[1], x[0]) for x in polyverts]

        if any(xlim[0] <= x[0] <= xlim[1] and ylim[0] <= x[1] <= ylim[1] for x in polyverts):
            polygon = Polygon(polyverts, True)
            patches.append(polygon)
            amis.append(ami(membership, ground_truth))

    p = PatchCollection(patches, cmap=cm, alpha=1.0, edgecolors='black', linewidths=2)
    p.set_array(np.array(amis + [1.0]))  # this extends the colorbar to include 1.0
    ax.add_collection(p)

    cbar = plt.colorbar(p)
    cbar.set_label('AMI', fontsize=14, labelpad=15)

    plt.xlim(xlim)
    plt.ylim(ylim)


def plot_multiplex_community(membership, layer_vec):
    """Plot multiplex community membership"""
    T = max(layer_vec) + 1
    N = len(membership) // T
    communities_per_layer = np.zeros((N, T))
    for i, layer in enumerate(range(T)):
        communities_per_layer[:, i] = membership[layer_vec == layer]

    ax = plt.axes()
    cmap = sbn.cubehelix_palette(as_cmap=True)

    ax.pcolormesh(communities_per_layer, cmap=cmap, linewidth=0, rasterized=True)
    return ax
