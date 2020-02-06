from collections import defaultdict
from sklearn.metrics import adjusted_mutual_info_score, normalized_mutual_info_score


def ami(p1, p2):
    return adjusted_mutual_info_score(p1, p2)


def nmi(p1, p2):
    return normalized_mutual_info_score(p1, p2, average_method='arithmetic')


def all_degrees(G):
    return G.degree()


def membership_to_communities(membership):
    communities = defaultdict(list)
    for v, c in enumerate(membership):
        communities[c].append(v)
    return communities