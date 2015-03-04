from __future__ import division
from sys import platform as _platform
import matplotlib

if _platform == "linux" or _platform == "linux2":
    matplotlib.use('Agg')
import matplotlib.pylab as plt
import numpy as np
import scipy.stats as stats

import math

from graph_tool.all import *
import graph_tool as gt

from community import SBMGenerator
from linalg import matrix_spectrum
from linalg import katz_sim_matrix
from linalg import adj_matrix
import multiprocessing
from multiprocessing import Pool
import navigator as nav
import operator
import os
import traceback
import utils as ut
import time


def blocks2():
    blocks = np.array([40, 30, 30])
    blockp = np.matrix("0.8, 0.01, 0.05; 0.01, 0.7, 0.05; 0.05, 0.05, 0.6")
    sbm = SBMGenerator(blocks, blockp)
    A = sbm.generate()
    return A


def blocks3():
    blocks = np.array([40, 30, 30])
    blockp = np.matrix("0.02, 0.02, 0.02; 0.02, 0.02, 0.02; 0.02, 0.02, 0.02")
    sbm = SBMGenerator(blocks, blockp)
    A = sbm.generate()
    return A


def blocks4():
    blocks = np.array([40, 30, 30])
    blockp = np.matrix("0.9, 0.01, 0.01; 0.01, 0.9, 0.01; 0.01, 0.01, 0.9")
    sbm = SBMGenerator(blocks, blockp)
    A = sbm.generate()
    return A


def generate_blocks(blocks, blockp):
    sbm = SBMGenerator(blocks, blockp)
    A = sbm.generate()
    return A


def generate_blocks_degree_corrected(blocks, blockp, degree_sequence):
    sbm = SBMGenerator(blocks, blockp)
    A = sbm.generate_degree_corrected(degree_sequence)
    return A


'''
def wiki():
    gif = "/home/dhelic/work/courses/netsci_slides/examples/measures/ipython/graph"
    G, nodelist = read_graph(gif)
    A = adj_matrix(G, nodelist)
    print A
    return A, G.number_of_nodes()
'''


def corr(x, y):
    print x, y
    if x == y:
        return 0.099
    else:
        return 0.00025


def graph_gen(self_con, other_con, nodes=500, groups=5):
    for i in range(10):
        print stats.powerlaw.rvs(2.1, size=1)
    g, bm = random_graph(nodes, lambda: (1 - stats.powerlaw.rvs(2.7, size=1)) * 50, directed=False,
                         model="blockmodel-traditional", block_membership=lambda: np.random.randint(int(groups)),
                         vertex_corr=corr)
    # lambda: (1 - stats.powerlaw.rvs(2.7, size=1)) * 50
    #lambda: stats.poisson.rvs(10),
    return g, bm


def do_calc(i, blockp, plot, id):
    try:
        c_list = ut.get_colors_list()
        p_id = multiprocessing.current_process()._identity[0]
        c = c_list[p_id % len(c_list)]
        p_name = ut.color_string('[Worker ' + str(p_id) + ']', type=c)
        print p_name, 'start calc of id:', id
        if i < len(blockp):
            A = generate_blocks(2 * blocks, 0.5 * np.matrix(blockp[i]))
            g = gt.Graph(directed=False)
            g.add_edge_list(np.transpose(A.nonzero()))
            if plot:
                pos = gt.draw.sfdp_layout(g)
                deg = g.degree_property_map("total")
                gt.draw.graph_draw(g, pos=pos, output=dir + "blocks%d.png" % i)
        elif i == len(blockp):
            g = gt.generation.price_network(1000, m=5, directed=False)
            A = np.zeros((1000, 1000))
            gt.spectral.adjacency(g).todense(out=A)
            if plot:
                pos = gt.draw.sfdp_layout(g)
                deg = g.degree_property_map("total")
                gt.draw.graph_draw(g, pos=pos, vertex_size=deg, output=dir + "power-law.png")
        else:
            degree_sequence = (1 - stats.powerlaw.rvs(2.7, size=1000)) * 80 + 5
            # print degree_sequence
            A = generate_blocks_degree_corrected(blocks, np.matrix(blockp[i - 2]), degree_sequence)
            g = gt.Graph(directed=False)
            g.add_edge_list(np.transpose(A.nonzero()))
            if plot:
                pos = gt.draw.sfdp_layout(g)
                deg = g.degree_property_map("total")
                gt.draw.graph_draw(g, pos=pos, vertex_fill_color=deg, vcmap=matplotlib.cm.gist_heat_r,
                                   output=dir + "power-law-blocks.png")

                #plot the largest component
                l = gt.topology.label_largest_component(g)
                u = gt.GraphView(g, vfilt=l)
                pos = gt.draw.sfdp_layout(u)
                deg = u.degree_property_map("total")
                gt.draw.graph_draw(u, pos=pos, vertex_size=deg, output=dir + "power-law-blocks-lcc.png")

        l, v = matrix_spectrum(A)
        kappa_1 = l[0].real
        alpha_max = 1.0 / kappa_1
        print p_name, 'kappa1:', kappa_1
        print p_name, 'alpha max:', alpha_max

        alpha_max *= 0.99
        alpha = alpha_max
        sigma_global = katz_sim_matrix(A, alpha)
        np.fill_diagonal(sigma_global, 0.0)
        gpearson = stats.pearsonr(A.flatten(), sigma_global.flatten())
        print p_name, "global vs adjacency"
        print p_name, gpearson

        alphas = [0.0, alpha_max * 1e-8, alpha_max * 1e-7, alpha_max * 1e-6, alpha_max * 1e-5, alpha_max * 1e-4,
                  alpha_max * 1e-3, alpha_max * 1e-2,
                  alpha_max * 1e-1, alpha_max * 0.15, alpha_max * 0.2, alpha_max * 0.25, alpha_max * 0.3,
                  alpha_max * 0.35, alpha_max * 0.4,
                  alpha_max * 0.45, alpha_max * 0.5, alpha_max * 0.55, alpha_max * 0.6, alpha_max * 0.65,
                  alpha_max * 0.7, alpha_max * 0.75,
                  alpha_max * 0.8, alpha_max * 0.85, alpha_max * 0.9, alpha_max * 0.95, alpha_max * 0.96,
                  alpha_max * 0.97, alpha_max * 0.98,
                  alpha_max * 0.99, alpha_max]

        data = [gpearson[0]]
        pearson80 = 0.0
        set_pearson80 = False
        for idx, alpha in enumerate(alphas):
            if alpha == 0.0:
                continue
            # print p_name, 'katz sim:', idx / len(alphas) * 100, '%'
            sigma = katz_sim_matrix(A, alpha)
            np.fill_diagonal(sigma, 0.0)
            pearson = stats.pearsonr(sigma.flatten(), sigma_global.flatten())
            if not set_pearson80 and pearson[0] > 0.8:
                pearson80 = alpha * kappa_1
                set_pearson80 = True
            data.append(pearson[0])
            # print "global vs %e"%alpha
            #print pearson[0]
        sr, stretch = nav.random_walk(g, max_steps=0, avoid_revisits=False, num_pairs=1000)
        stretch_avg = np.mean(stretch)
        res_string = ''
        res_string += legend[i] + "\n"
        res_string += "m = " + str(sum(sum(A)) / 2) + '\n'
        res_string += "kappa_1 = " + str(kappa_1) + '\n'
        res_string += "alpha_max = " + str(1 / kappa_1) + '\n'
        res_string += "gpearson = " + str(gpearson[0]) + '\n'
        res_string += "pearson80 = " + str(pearson80) + '\n'
        res_string += "alpha80 = " + str(pearson80 / kappa_1) + '\n'
        res_string += "stretch = " + str(stretch_avg) + '\n'

        # aalphas.append([a * kappa_1 for a in alphas])
        #adata.append(data)
        #print data
    except:
        print str(traceback.format_exc())
        exit()
    return (([a * kappa_1 for a in alphas], data, res_string), id)


np.set_printoptions(linewidth=225)

blocks = np.array([100, 100, 100, 100, 100])
blockp = [
    "0.02, 0.02, 0.02, 0.02, 0.02; 0.02, 0.02, 0.02, 0.02, 0.02; 0.02, 0.02, 0.02, 0.02, 0.02; 0.02, 0.02, 0.02, 0.02, 0.02; 0.02, 0.02, 0.02, 0.02, 0.02",
    "0.08, 0.005, 0.005, 0.005, 0.005; 0.005, 0.08, 0.005, 0.005, 0.005; 0.005, 0.005, 0.08, 0.005, 0.002; 0.005, 0.005, 0.005, 0.08, 0.005; 0.005, 0.005, 0.005, 0.005, 0.08",
    "0.099, 0.00025, 0.00025, 0.00025, 0.00025; 0.00025, 0.099, 0.00025, 0.00025, 0.00025; 0.00025, 0.00025, 0.099, 0.00025, 0.00025; 0.00025, 0.00025, 0.00025, 0.099, 0.00025; 0.00025, 0.00025, 0.00025, 0.00025, 0.099"]
legend = ["Random", "Weak Comm.", "Strong Comm.", "Power-Law", "Deg. Stoch. Blocks"]

dir = "output/"
rfile = dir + "/gvsl.txt"
if not os.path.isdir(dir):
    os.mkdir(dir)

# A = blocks2()
#A = blocks3()
#A = blocks4()
#A, n = wiki()
#adata = []
#aalphas = []
n_exper = 10
plot = True
results = []
res_appender = results.append

worker_pool = Pool(processes=5)
id = 0
for count in range(n_exper):
    for i in range(len(blockp) + 2):
        worker_pool.apply_async(func=do_calc, args=(i, blockp, plot, id), callback=res_appender)
        if i > len(blockp):
            plot = False
        id += 1
worker_pool.close()
while True:
    time.sleep(60)
    remaining_processes = len(worker_pool._cache)
    print str(' overall process status:' + str((id - remaining_processes) / id * 100) + '% ').center(100, '-')
    if remaining_processes == 0:
        break
worker_pool.join()
results.sort(key=operator.itemgetter(1))
results, result_ids = zip(*results)
aalphas, adata, file_cont = zip(*results)
with open(rfile, 'w') as f:
    for i in file_cont:
        f.write(i)
        f.write('-' * 80)
        f.write('\n')

for i in range(len(blockp) + 2):
    data = []
    alphas = aalphas[i]
    #print alphas
    for j in range(n_exper):
        data.append(adata[j * (len(blockp) + 2) + i])
    d = np.array(data)
    print d.shape
    avg = np.mean(d, axis=0)
    print avg
    sem = stats.sem(d, axis=0)
    print sem
    # std = np.std(d, axis=0)
    # print std
    # print std / math.sqrt(10)
    plt.errorbar(alphas, avg, yerr=sem, label=legend[i])

plt.grid()
plt.title("Corr. between global and fractional knowledge ($n=1000, m\\approx5000$)")
plt.legend(loc=4)
plt.xlabel("Fraction of global knowledge")
plt.ylabel("$\\rho$")
plt.ylim([0, 1])
plt.show()