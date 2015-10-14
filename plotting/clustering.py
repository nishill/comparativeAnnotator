import re
import os
import argparse
import subprocess
import pandas as pd
import lib.sql_lib as sql_lib
import lib.plot_lib as plot_lib
from lib.general_lib import mkdir_p
import etc.config
from jobTree.scriptTree.target import Target
from jobTree.scriptTree.stack import Stack
from sonLib.bioio import getRandomAlphaNumericString


# we only do this on protein_coding transcripts
biotype = "protein_coding"


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--genome", type=str, required=True, help="genome in this comparison")
    parser.add_argument("--refGenome", type=str, required=True, help="reference genome in this comparison")
    parser.add_argument("--outDir", required=True, help="output directory")
    parser.add_argument("--comparativeAnnotationDir", required=True, help="directory containing databases")
    parser.add_argument("--gencode", type=str, required=True, help="current gencode set being analyzed")
    parser.add_argument("--filterChroms", nargs="+", default=["Y", "chrY"], help="chromosomes to ignore")
    return parser


def drop_low_sums(m, s, cutoff=2.0):
    """
    Drops any classifiers with below cutoff classifications. Cutoff is a percentage of total.
    """
    for c, v in s.iteritems():
        if v < cutoff:
            m.drop(c, inplace=True, axis=1)


def munge_data(d, filter_set):
    """
    Used to munge input data.
    """
    m = d.ix[filter_set]
    m = m.fillna(0)
    m = m.astype(bool)
    s = m.sum(axis=0)
    normed_s = s / (0.01 * len(m))
    normed_s.sort(ascending=False)
    s.sort(ascending=False)
    drop_low_sums(m, normed_s)
    s = [[x, normed_s[x], y] for x, y in s.iteritems()]
    return m, s


def find_ids(cur, ref_genome, genome, filter_chroms):
    chr_y_ids = sql_lib.get_ids_by_chromosome(cur, ref_genome, filter_chroms)
    biotype_ids = sql_lib.filter_biotype_ids(cur, ref_genome, biotype, chr_y_ids, mode="Transcript")
    good_query = etc.config.transMapEval(ref_genome, genome, biotype, good=True)
    pass_query = etc.config.transMapEval(ref_genome, genome, biotype, good=False)
    best_covs = sql_lib.highest_cov_aln(cur, genome)
    best_ids = set(zip(*best_covs.itervalues())[0])
    good_ids = {x for x in sql_lib.get_query_ids(cur, good_query) if x in best_ids}
    pass_ids = {x for x in sql_lib.get_query_ids(cur, pass_query) if x in best_ids}
    all_ids = sql_lib.get_biotype_aln_ids(cur, genome, biotype)
    fail_ids = all_ids - good_ids
    good_specific_ids = good_ids - pass_ids
    return fail_ids, good_specific_ids, biotype_ids


def main_fn(target, comp_ann_path, gencode, genome, ref_genome, base_out_path, filter_chroms):
    clust_title = "Hierarchical_clustering_of_transMap_classifiers"
    base_barplot_title = ("Classifiers failed by transcripts in the category {} in transMap analysis\n"
                          "Genome: {}.  Gencode set: {}.  {:,} ({:0.2f}%) of transcripts")
    out_path = os.path.join(base_out_path, "clustering", genome)
    con, cur = sql_lib.attach_databases(comp_ann_path, mode="transMap")
    fail_ids, good_specific_ids, biotype_ids = find_ids(cur, ref_genome, genome, filter_chroms)
    sql_data = sql_lib.load_data(con, genome, etc.config.tm_pass_classifiers)
    for mode, ids in zip(*[["Fail", "Good/NotPass"], [fail_ids, good_specific_ids]]):
        out_barplot_file = os.path.join(out_path, "barplot_{}_{}".format(genome, biotype))
        percentage_of_set = 100.0 * len(ids) / len(biotype_ids)
        barplot_title = base_barplot_title.format(mode, genome, gencode, len(ids), percentage_of_set)
        munged, stats = munge_data(sql_data, ids)
        plot_lib.barplot(stats, out_path, out_barplot_file, barplot_title)
        data_path = os.path.join(target.getGlobalTempDir(), getRandomAlphaNumericString())
        munged.to_csv(data_path)
        out_cluster_file = os.path.join(out_path, "clustering_{}_{}".format(genome, biotype))
        target.addChildTargetFn(r_wrapper, args=[data_path, clust_title, out_cluster_file])


def r_wrapper(data_path, clust_title, out_cluster_file):
    base_cmd = ("export R_HOME=/cluster/home/ifiddes/lib64/R && /cluster/home/ifiddes/bin/Rscript {}/plotting/cluster.R"
                " {} {} {}")
    cmd = base_cmd.format(os.getcwd(), data_path, clust_title, out_cluster_file)
    subprocess.call(cmd, shell=True)


def main():
    parser = build_parser()
    Stack.addJobTreeOptions(parser)
    args = parser.parse_args()
    i = Stack(Target.makeTargetFn(main_fn, args=[args.comparativeAnnotationDir, args.gencode, args.genome,
                                                 args.refGenome, args.outDir, args.filterChroms])).startJobTree(args)
    if i != 0:
        raise RuntimeError("Got failed jobs")


if __name__ == '__main__':
    from plotting.clustering import *
    main()