from __future__ import division
from graph_tool.all import *
from tools.printing import print_f
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix, csc_matrix
from collections import defaultdict
import random
import operator


class CostFunction():
    def __init__(self, graph, deg_weight=0.1, cos_weight=0.9, pairs=None, pairs_reduce=None, cos_sim_th=0.0, verbose=2, ranking_weights=None):
        assert deg_weight + cos_weight == 1
        self.verbose = verbose
        self.deg_weight = deg_weight
        self.cos_weight = cos_weight
        self.graph = graph
        self.print_f('Init cost function', verbose=1)
        self.ranking_weights = self.calc_weights_ranking()
        self.print_f('\tget adjacency matrix', verbose=1)
        self.adj_mat = adjacency(graph)  # .tocsc()
        self.print_f('\tgenerate pairs', verbose=1)
        if pairs is None:
            all_shortest_dist = True
            # format destination, array_of_sources
            self.pairs = [(i, np.array([j for j in xrange(self.adj_mat.shape[1]) if j != i])) for i in xrange(self.adj_mat.shape[0])]
        else:
            all_shortest_dist = False
            self.pairs = pairs
        self.print_f('\tgenerate degrees vector', verbose=1)
        deg_map = graph.degree_property_map('total')
        self.deg = csr_matrix((([deg_map[v] for v in graph.vertices()]), (range(graph.num_vertices()), [0] * graph.num_vertices())), shape=(graph.num_vertices(), 1))
        self.deg = self.deg.multiply(self.adj_mat)
        # self.deg = self.deg.multiply(csr_matrix(1 / self.deg.sum(axis=0)))
        self.deg = csr_matrix(self.deg.T)
        self.print_f('\tdeg matrix: type:', type(self.deg), 'shape:', self.deg.shape, 'filled elements:', self.deg.nnz / (self.deg.shape[0] * self.deg.shape[1]), verbose=2)
        self.print_f('\tgenerate cosine similarity matrix', verbose=1)
        self.src = None
        self.src_n = None
        self.cos_sim = filter(lambda x: x[2] > cos_sim_th,
                              ((int(src), int(dest), self.calc_cossim(src, dest)) for src in graph.vertices() for dest in graph.vertices() if int(dest) >= int(src)))
        i, j, data = zip(*self.cos_sim)
        self.cos_sim = csr_matrix(coo_matrix((data, (i, j)), shape=(graph.num_vertices(), graph.num_vertices())))
        self.cos_sim = self.cos_sim + self.cos_sim.T
        # self.cos_sim.setdiag(1)
        # self.cos_sim = self.cos_sim.multiply(self.adj_mat).T
        self.print_f('\tcos sim matrix: type:', type(self.cos_sim), 'shape', self.cos_sim.shape, 'filled elements:',
                     self.cos_sim.nnz / (self.cos_sim.shape[0] * self.cos_sim.shape[1]), verbose=2)
        self.print_f('\tcalc shortest distances for pairs', verbose=1)
        tmp_pairs = defaultdict(set)
        for dest, srcs in self.pairs:
            for i in srcs:
                tmp_pairs[i].add(dest)
        shortest_distances = defaultdict(lambda: defaultdict(int))
        if not all_shortest_dist:
            # shortest_distances = [(src, dest, shortest_distance(graph.vertex(src), graph.vertex(dest))) for src, dests in tmp_pairs.iteritems() for dest in dests]
            exit()
        else:
            s_map = shortest_distance(graph)
            for src, dests in tmp_pairs.iteritems():
                src_s_map = s_map[graph.vertex(src)]
                for dest in dests:
                    shortest_distances[dest][src] = src_s_map[dest]

        # TODO: is there a way to include all shortest distance neigbours?
        if pairs_reduce is not None:
            self.print_f('\treduce targets of pairs to:', pairs_reduce, verbose=1)
            self.print_f('\tall targets:', len(self.pairs), verbose=2)
            num_targets = int(round(len(self.pairs) * pairs_reduce))
            self.pairs = random.sample(self.pairs, num_targets)
            self.print_f('\treduced targets:', len(self.pairs), verbose=2)
        self.print_f('\tfind best next hop for each pair', verbose=1)
        best_neighbours = defaultdict(lambda: dict())
        for dest, srcs in self.pairs:
            sd = shortest_distances[dest]
            for src in srcs:
                best_n = set()
                best_sd = None
                for n in map(int, graph.vertex(src).out_neighbours()):
                    n_sd = sd[n]
                    if best_sd is None or n_sd < best_sd:
                        best_sd = n_sd
                        best_n = {n}
                    elif n_sd == best_sd:
                        best_n.add(n)
                # best_n = random.sample(best_n, 1)[0]
                best_neighbours[dest][src] = best_n

        # TODO: check matrix correct
        # data, i, j = zip(*[(best_neighbours[j][i], i, j) for i, srcs in self.pairs for j in srcs])
        # self.best_next_hops = csr_matrix((data, (i, j)), shape=self.adj_mat.shape)
        self.best_next_hops = best_neighbours

        # each row: index destination, elements best next neighbour from col-index-node to destination
        self.print_f('\ttranspose and convert adj matrix', verbose=1)
        self.adj_mat = csr_matrix(self.adj_mat.T)
        self.print_f('\tadj matrix: type:', type(self.adj_mat), 'shape', self.adj_mat.shape, 'filled elements:', self.adj_mat.nnz / (self.adj_mat.shape[0] * self.adj_mat.shape[1]),
                     verbose=2)

    def calc_cossim(self, src, dest):
        if src == dest:
            return 1.0
        if self.src != src:
            self.src_n = set(src.all_neighbours())
            self.src = src
        dest_n = set(dest.all_neighbours())
        return len(self.src_n & dest_n) / np.sqrt(len(self.src_n) * len(dest_n))

    def calc_weights_ranking(self, ranking_weights=None, num_nodes=None):
        if num_nodes is None:
            num_nodes = self.graph.num_vertices()
        if ranking_weights is None:
            self.print_f('use linear weighting for ranking')
            ranking_weights = reversed(range(num_nodes))
        elif isinstance(ranking_weights, str):
            if ranking_weights == 'linear':
                self.print_f('use default (linear) weighting for ranking')
                ranking_weights = reversed(range(num_nodes))
            elif ranking_weights == 'quadratic':
                self.print_f('use quadratic weighting for ranking')
                ranking_weights = reversed(range(num_nodes))
                ranking_weights = np.power(np.array(ranking_weights), 2)
            elif ranking_weights == 'exponential':
                self.print_f('use exponential weighting for ranking')
                ranking_weights = reversed(range(num_nodes))
                ranking_weights = np.exp(np.array(ranking_weights))
        ranking_weights = np.array(list(ranking_weights))
        result = ranking_weights / ranking_weights.max()
        self.print_f(result, type(result), verbose=2)
        return result

    def print_f(self, *args, **kwargs):
        if not 'verbose' in kwargs or kwargs['verbose'] <= self.verbose:
            kwargs.update({'class_name': 'CostFunction'})
            print_f(*args, **kwargs)

    def calc_cost(self, ranking=None):
        self.print_f('calc cost')
        if ranking is not None:
            self.print_f('known nodes:', len(ranking), '(', str(len(ranking) / self.adj_mat.shape[0] * 100) + '% )')
            ranking = self.create_mask_vector(ranking)
            assert ranking.shape[0] == 1 and ranking.shape[1] == self.adj_mat.shape[1]
        cost = 0
        for dest, srcs in self.pairs:
            cossims = self.cos_sim[dest, :]
            if ranking is not None:
                cossims = cossims.multiply(ranking)
            neigh_cossim = self.adj_mat.multiply(cossims)
            neigh_cossim = neigh_cossim.multiply(csr_matrix(1 / (neigh_cossim.sum(axis=1))))
            degs = self.deg
            if ranking is not None:
                degs = degs.multiply(ranking)
            degs = degs.multiply(csr_matrix(1 / (degs.sum(axis=1))))
            prob = neigh_cossim * self.cos_weight + degs * self.deg_weight
            # each row => index is src, elments are prob to select this neighbour
            # print self.best_next_hops[dest, :].toarray()[0][srcs]
            best_next_hops = self.best_next_hops[dest]
            best_per_src = [best_next_hops[i] for i in srcs]
            n_best_per_src = np.array([len(i) for i in best_per_src])
            self.print_f('cos shape:', neigh_cossim.shape)
            self.print_f('deg shape:', degs.shape)
            self.print_f('prob shape:', prob.shape)
            self.print_f('min,max src:', min(srcs), max(srcs))
            self.print_f('best src min,max:', min((j for i in best_per_src for j in i)), max((j for i in best_per_src for j in i)))
            mask = csr_matrix(
                ([1] * n_best_per_src.sum(), ([src for src, n_src in zip(srcs, n_best_per_src) for i in xrange(n_src)], [j for i in best_per_src for j in i])),
                shape=prob.shape)
            prob_of_best_n = prob.multiply(mask)
            cost += prob_of_best_n.max(axis=1).sum()
            self.print_f('probability sum:', cost)
        return cost

    def create_mask_vector(self, known_nodes):
        num_known_nodes = len(known_nodes)
        return csr_matrix(([1] * num_known_nodes, ([0] * num_known_nodes, known_nodes)), shape=(1, self.adj_mat.shape[1]))

