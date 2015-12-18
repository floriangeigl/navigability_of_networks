from __future__ import division, print_function

from sys import platform as _platform

import matplotlib

if _platform == "linux" or _platform == "linux2":
    matplotlib.use('Agg')
from matplotlib import gridspec
from post_processing.plotting import *
import os
from tools.basics import create_folder_structure, find_files
import traceback
import numpy as np
from graph_tool.all import *
import datetime
import network_matrix_tools
import random
import tools.mpl_tools as plt_tools
from scipy.sparse import diags, csr_matrix
import sys
import itertools
from collections import Counter
import multiprocessing as mp

pd.set_option('display.width', 600)
pd.set_option('display.max_colwidth', 600)
matplotlib.rcParams.update({'font.size': 25})
default_x_ticks_pad = matplotlib.rcParams['xtick.major.pad']
default_y_ticks_pad = matplotlib.rcParams['xtick.major.pad']
matplotlib.rcParams['xtick.major.pad'] *= 2
matplotlib.rcParams['ytick.major.pad'] *= 2


class GetOutOfLoops(Exception):
    pass


def mix_bias_linkins_and_calc((sample_size, com_nodes), adj, bias_strength=2, mixture=0.5, net=None, num_links=1,
                              top_measure=None, verbose=False, print_prefix=''):
    if sample_size > 0.21:
        # print 'skip sample-size:', sample_size
        return np.nan
    if not np.isclose(sample_size, mix_bias_linkins_and_calc.sample_size):
        mix_bias_linkins_and_calc.sample_size = sample_size
        mix_bias_linkins_and_calc.calc_counter = 0
        mix_bias_linkins_and_calc.ss_string = "%.3f" % sample_size
        # print('')
    orig_adj = adj
    if isinstance(num_links, str):
        if num_links == 'fair':
            bias_m = np.ones(orig_adj.shape[0])
            bias_m[com_nodes] = bias_strength
            bias_m = diags(bias_m, 0)
            # calc number of (technical seen) new created links due to bias (#links in biased adj - #links in orig adj)
            num_links = int(bias_m.dot(orig_adj).sum()) - orig_adj.sum()
            # print 'fair links:', num_links
    print_num_links = (str(num_links / 1000) + 'k') if num_links > 1000 else num_links
    assert 0 <= mixture <= 1. or np.isclose(mixture, 1.) or np.isclose(mixture, 0.)
    bias_links = int(np.round(num_links * mixture))
    top_new_links = num_links - bias_links
    if verbose:
        print('')
        print('mixture:', mixture)
        print('bias links:', bias_links)
        print('new links:', top_new_links)
        print('--')
        print('orig')
        print(orig_adj.todense())

    orig_num_com_nodes = len(com_nodes)
    if orig_num_com_nodes >= orig_adj.shape[0]:
        return None
    com_nodes_set = set(com_nodes)
    other_nodes = set(range(0, orig_adj.shape[0])) - com_nodes_set

    if top_new_links > 0:
        # create top-measure links
        if top_measure is None:
            if net is not None:
                nodes_measure = np.array(net.degree_property_map('in').a)
            else:
                print('no top measure defined.')
                raise Exception()
        else:
            nodes_measure = top_measure

        sorted_other_nodes = sorted(other_nodes, key=lambda x: nodes_measure[x], reverse=True)
        sorted_com_nodes = sorted(com_nodes, key=lambda x: nodes_measure[x], reverse=True)
        new_edges = list()
        while True:
            block_size = int(np.sqrt(top_new_links-len(new_edges))) + 1
            all_com_nodes = False
            if block_size > len(com_nodes):
                all_com_nodes = True
                block_size = int((top_new_links-len(new_edges))/len(com_nodes)) + 1

            if all_com_nodes:
                sorted_com_nodes_block = sorted_com_nodes
            else:
                sorted_com_nodes_block = sorted_com_nodes[:block_size]
            sorted_other_nodes_block = sorted_other_nodes[:block_size]
            # if verbose:
            # print('\n')
            # print('all com nodes:', all_com_nodes)
            # print('needed links:', top_new_links - len(new_edges))
            # print('max link for block-size:', len(sorted_other_nodes_block) * len(sorted_com_nodes_block))
            # print('block-size:', block_size)
            # sorted_com_nodes_block = sorted_com_nodes
            new_edges.extend(list(
                    itertools.islice(
                            ((src, dest) for dest in sorted_com_nodes_block for src in sorted_other_nodes_block),
                            (top_new_links - len(new_edges)))))
            if len(new_edges) >= top_new_links:
                break
            elif verbose:
                print('could not insert all links:', len(new_edges), 'of', top_new_links, 'add parallel')
        assert len(new_edges) == top_new_links
        edge_counter = Counter(new_edges)
        indizes, num_e = map(list, zip(*edge_counter.iteritems()))
        rows, cols = map(list, zip(*indizes))
        top_edge_matrix = csr_matrix((list(num_e), (rows, cols)), shape=orig_adj.shape).T
        if verbose:
            print('new links')
            print(top_edge_matrix.todense())
    else:
        top_edge_matrix = csr_matrix(orig_adj.shape, dtype='float')

    # insert biased links
    if bias_links > 0:
        if bias_links == num_links:
            print('bias ALL')

        # mix in and out degree to get prob.
        out_d = csr_matrix(diags(np.array(orig_adj.sum(axis=0)).flatten(), 0))
        in_d = csr_matrix(diags(np.array(orig_adj.sum(axis=1)).flatten(), 0))
        prob_mat = out_d.dot(orig_adj).dot(in_d)
        row_idx, col_idx = prob_mat.nonzero()
        unbiased_row_idx, unbiased_col_idx = zip(
            *filter(lambda (r, c): not(r in com_nodes_set and c not in com_nodes_set), zip(row_idx, col_idx)))
        prob_mat[unbiased_row_idx, unbiased_col_idx] = 0.
        prob_mat.eliminate_zeros()
        prob_mat.data /= prob_mat.data.sum()
        row_idx, col_idx = prob_mat.nonzero()
        bias_edges_idx = np.random.choice(range(prob_mat.nnz), size=min(bias_links, prob_mat.nnz), replace=False,
                                          p=prob_mat.data)
        row_idx, col_idx = row_idx[bias_edges_idx], col_idx[bias_edges_idx]
        bias_cum_sum_links = (np.array(orig_adj[row_idx, col_idx]).flatten() * (bias_strength - 1)).cumsum()
        last_idx = np.searchsorted(bias_cum_sum_links, bias_links, side='right')
        if last_idx > 1:
            last_idx = min(last_idx, len(bias_cum_sum_links))
            last_idx = last_idx if abs(bias_links - bias_cum_sum_links[last_idx - 1]) < abs(
                    bias_links - bias_cum_sum_links[last_idx - 2]) else (last_idx - 1)
        if last_idx == len(row_idx):
            print('biased all available links')
        row_idx, col_idx = row_idx[:last_idx], col_idx[:last_idx]

        if verbose:
            print('biased links:', row_idx, col_idx)
        bias_mat = orig_adj.astype('bool').astype('float') + csr_matrix(
                ([(bias_strength - 1.)] * len(row_idx), (row_idx, col_idx)), shape=orig_adj.shape)
        if verbose:
            print('bias')
            print(bias_mat.todense())

        biased_mat = orig_adj.multiply(bias_mat)
        if verbose:
            print('biased')
            print(biased_mat.todense())
    else:
        biased_mat = orig_adj

    combined_mat = biased_mat + top_edge_matrix

    if verbose:
        print('combined')
        print(combined_mat.todense())

    _, relinked_stat_dist = network_matrix_tools.calc_entropy_and_stat_dist(combined_mat, method='EV',
                                                                            smooth_bias=False,
                                                                            calc_entropy_rate=False, verbose=False)
    assert orig_num_com_nodes == len(com_nodes)
    relinked_stat_dist_sum = relinked_stat_dist[com_nodes].sum()
    print('\r', print_prefix, mix_bias_linkins_and_calc.ss_string, mix_bias_linkins_and_calc.calc_counter, '#links:',
          print_num_links, ' || mod. #links:', int(combined_mat.sum()), '|| bias strength:', bias_strength,
          '|| mixture:', mixture, '|| stat sum:', relinked_stat_dist_sum, end='')
    sys.stdout.flush()
    return relinked_stat_dist_sum


def worker_helper(sample_size, node_ids, adj, mixture, bias_strength, num_links, top_measure, print_prefix):
    # print('calc', sample_size, mixture, bias_strength)
    try:
        stat_dist = mix_bias_linkins_and_calc((sample_size, node_ids), adj=adj, mixture=mixture,
                                              bias_strength=bias_strength,
                                              num_links=num_links, top_measure=top_measure,
                                              print_prefix=print_prefix)
    except:
        print('WARN! worker worker helper failed')
        print(traceback.format_exc())
        raise Exception()
    return sample_size, mixture, bias_strength, stat_dist


def optimize_net(net_fn, df_fn, num_samples, bias_strength_range, mixture_range, num_processes=1):
    try:
        print('*' * 120)
        print('load network:', net_fn.rsplit('/', 1)[-1])
        adj = adjacency(load_graph(net_fn))
        top_measure = np.array(adj.sum(axis=1)).flatten()
        preprocessed_filename = df_fn.rsplit('.df', 1)[0] + '_preprocessed.df'
        try:
            df = pd.read_pickle(preprocessed_filename)
        except:
            df = pd.read_pickle(df_fn)
        result = list()
        mix_bias_linkins_and_calc.sample_size = -1.
        df = df[df['sample-size'] < 2.1]
        df_g = df.groupby('sample-size')

        for key, g_df in df_g:
            g_df = g_df.iloc[:num_samples]
            for idx, data in g_df[['sample-size', 'node-ids']].iterrows():
                ss, node_ids = list(data)
                for bs in bias_strength_range:
                    my_worker_pool = mp.Pool(processes=num_processes)
                    for mix in mixture_range:
                        my_worker_pool.apply_async(worker_helper, args=(
                        ss, node_ids, adj, mix, bs, 'fair', top_measure, net_fn.rsplit('/', 1)[-1]),
                                                   callback=result.append)
                        # stat_dist = mix_bias_linkins_and_calc((ss, node_ids), adj=adj, mixture=mix, bias_strength=bs,
                        #                                     num_links='fair', top_measure=top_measure,
                        #                                      print_prefix=net_fn.rsplit('/', 1)[-1])
                        # result.append((ss, mix, bs, stat_dist))
                    my_worker_pool.close()
                    my_worker_pool.join()
                    # print('')
                print('')
                # mix_bias_linkins_and_calc.calc_counter += 1
                result_df = pd.DataFrame(data=result,
                                         columns=['sample-size', 'mixture', 'bias_strength', 'sample_stat_dist'])
                result_df.to_pickle(os.path.dirname(preprocessed_filename) + '/' + net_fn.rsplit('/', 1)[
                    -1] + '_mixture_res.df')
            print('')
    except:
        print('WARNING!!')
        print(traceback.format_exc())


def main():
    if False:
        net = price_network(100, m=4, directed=False)
        sample_size = 0.2
        com_nodes = np.random.choice(np.array(range(net.num_vertices())), size=int(sample_size * net.num_vertices()),
                                     replace=False)
        print(net)
        print('com nodes:', com_nodes)
        mix_bias_linkins_and_calc.sample_size = 0.
        com_stat_dist = list()
        adj = adjacency(net)
        for df_fn in np.linspace(0, 1, num=11):
            com_stat_dist.append(
                    (df_fn, mix_bias_linkins_and_calc((sample_size, com_nodes), adj=adj, mixture=df_fn, net=net,
                                                      bias_strength=2, num_links='fair')))
        df = pd.DataFrame(data=com_stat_dist)
        print(df)
    else:

        base_dir = '/home/fgeigl/navigability_of_networks/output/bias_link_ins/'
        out_dir = base_dir + 'plots/'
        create_folder_structure(out_dir)
        mixture_range = np.linspace(0, 1, num=11)
        num_samples = 10
        bias_strength_range = [2, 3, 5, 10, 15]
        result_files = filter(lambda x: '_bs' in x, find_files(base_dir, '.df'))
        print(result_files)
        cors = list()
        all_dfs = list()
        net_name = ''
        net = None
        skipped_ds = set()
        # skipped_ds.add('daserste')
        # skipped_ds.add('wiki4schools')
        # skipped_ds.add('tvthek_orf')
        #my_worker_pool = mp.Pool(processes=3)
        for df_fn in sorted(filter(lambda x: 'preprocessed' not in x, result_files), reverse=True):
            current_net_name = df_fn.rsplit('_bs', 1)[0]
            bias_strength = int(df_fn.split('_bs')[-1].split('.')[0])
            if bias_strength > 2:
                print('skip bs:', bias_strength)
                continue
            elif any((i in current_net_name for i in skipped_ds)):
                print('skip ds:', current_net_name)
                continue
#            my_worker_pool.apply_async(worker_helper,
#                                       args=())
            optimize_net(current_net_name, df_fn, num_samples, bias_strength_range, mixture_range, num_processes=4)
#        my_worker_pool.close()
#        my_worker_pool.join()

if __name__ == '__main__':
    start = datetime.datetime.now()
    print('START:', start)
    main()
    print('ALL DONE. Time:', datetime.datetime.now() - start)

