import re
import os
import argparse
import subprocess
import pandas as pd
import numpy as np
import lib.sql_lib as sql_lib
import lib.plot_lib as plot_lib
import lib.psl_lib as psl_lib
from lib.general_lib import mkdir_p
import etc.config
from jobTree.scriptTree.target import Target
from jobTree.scriptTree.stack import Stack
from sonLib.bioio import getRandomAlphaNumericString, system


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
    parser.add_argument("--mode", choices=["transMap", "augustus", "reference"], help="transMap/augustus/reference")
    return parser


def drop_low_sums(s, m, cutoff=1.0):
    """
    Drops any classifiers with below cutoff classifications. Cutoff is a percentage of total.
    """
    for c, v in s.iteritems():
        if v < cutoff:
            s.drop(c, inplace=True)
            m.drop(c, axis=1, inplace=True)


def munge_intron_data(d, num_original_introns, filter_set):
    """
    Used to munge input data.
    """
    d["HasOriginalIntrons"] = np.logical_or(d["HasOriginalIntrons"] >= 0.5 * num_original_introns["NumberIntrons"] - 0.5,
                                             num_original_introns["NumberIntrons"] == 0)
    m = d.ix[filter_set]
    return munge_data(d, filter_set)


def munge_data(d, filter_set=None):
    """
    Used to munge input data.
    """
    if filter_set is not None:
        m = d.ix[filter_set]
    else:
        m = d
    m = m.astype(bool)
    s = m.sum(axis=0)
    s.sort(ascending=False)
    normed_s = s / (0.01 * len(m))
    drop_low_sums(normed_s, m)
    s = [[x, normed_s[x], y] for x, y in s.iteritems() if x in normed_s]
    return m, s


def r_wrapper(target, data_path, clust_title, out_cluster_file):
    # TODO: why do I need to do this in order for R to work on the cluster?
    base_cmd = ("export R_HOME=/cluster/home/ifiddes/lib64/R && /cluster/home/ifiddes/bin/Rscript {}/plotting/cluster.R"
                " {} {} {}")
    cmd = base_cmd.format(os.getcwd(), data_path, clust_title, out_cluster_file)
    system(cmd)


def main_fn(target, comp_ann_path, gencode, genome, ref_genome, base_out_path, filter_chroms):
    clust_title = "Hierarchical_clustering_of_transMap_classifiers"
    base_barplot_title = ("Classifiers failed by {} transcripts in the category {} in transMap analysis\n"
                          "Genome: {}.  Gencode set: {}.  {:,} ({:0.2f}%) of transcripts")
    out_path = os.path.join(base_out_path, "classifier_breakdown", genome)
    mkdir_p(out_path)
    con, cur = sql_lib.attach_databases(comp_ann_path, mode="transMap")
    fail_ids, passing_specific_ids, excellent_ids = sql_lib.get_fail_passing_excel_ids(cur, ref_genome, genome, biotype)
    biotype_ids = sql_lib.get_biotype_ids(cur, ref_genome, biotype, filter_chroms=filter_chroms)
    if len(biotype_ids) > 50:
        sql_data = sql_lib.load_data(con, genome, etc.config.clustering_classifiers)
        num_original_introns = sql_lib.load_data(con, genome, ["NumberIntrons"], table="attributes")
        for mode, ids in zip(*[["Fail", "Pass/NotExcellent"], [fail_ids, passing_specific_ids]]):
            mode_underscore = mode.replace("/", "_")
            out_barplot_file = os.path.join(out_path, "barplot_{}_{}_{}".format(genome, biotype, mode_underscore))
            percentage_of_set = 100.0 * len(ids) / len(biotype_ids)
            barplot_title = base_barplot_title.format(biotype.replace("_" , " "), mode, genome, gencode, len(ids), 
                                                      percentage_of_set)
            munged, stats = munge_intron_data(sql_data, num_original_introns, ids)
            plot_lib.barplot(stats, out_path, out_barplot_file, barplot_title)
            data_path = os.path.join(target.getGlobalTempDir(), getRandomAlphaNumericString())
            munged.to_csv(data_path)
            out_cluster_file = os.path.join(out_path, "clustering_{}_{}_{}".format(genome, biotype, mode_underscore))
            target.addChildTargetFn(r_wrapper, args=[data_path, clust_title, out_cluster_file])


def main_augustus_fn(target, comp_ann_path, gencode, genome, base_out_path, filter_chroms):
    clust_title = "Hierarchical_clustering_of_augustus_classifiers"
    base_barplot_title = ("Augustus classifiers failed by {:,} transcripts derived from transMap\n"
                          "on the reference set {} with Augustus {}")
    out_path = os.path.join(base_out_path, "augustus_classifier_breakdown", genome)
    mkdir_p(out_path)
    con, cur = sql_lib.attach_databases(comp_ann_path, mode="augustus")
    highest_cov_dict = sql_lib.highest_cov_aln(cur, genome)
    highest_cov_ids = set(zip(*highest_cov_dict.itervalues())[0])
    sql_data = sql_lib.load_data(con, genome, etc.config.aug_classifiers, primary_key="AugustusAlignmentId", 
                                 table="augustus")
    base_filter_set = {x for x in sql_data.index if psl_lib.remove_augustus_alignment_number(x) in highest_cov_ids}
    for mode in ["1", "2"]:
        i = "I{}".format(mode)
        aug_mode = "trusting RNAseq more" if mode == "2" else "trusting RNAseq less"
        filter_set = {x for x in base_filter_set if i in x}
        out_barplot_file = os.path.join(out_path, "augustus_barplot_{}_{}_{}".format(genome, gencode, i))
        barplot_title = base_barplot_title.format(len(filter_set), gencode, aug_mode)
        munged, stats = munge_data(sql_data, filter_set)
        plot_lib.barplot(stats, out_path, out_barplot_file, barplot_title)
        data_path = os.path.join(target.getGlobalTempDir(), getRandomAlphaNumericString())
        munged.to_csv(data_path)
        out_cluster_file = os.path.join(out_path, "augustus_clustering_{}_{}_{}".format(genome, gencode, i))
        target.addChildTargetFn(r_wrapper, args=[data_path, clust_title, out_cluster_file])


def main_ref_fn(target, comp_ann_path, gencode, ref_genome, base_out_path, filter_chroms):
    clust_title = "Hierarchical_clustering_of_transcript_classifiers"
    base_barplot_title = ("Classifiers failed by {} transcripts in the reference set {}\n")
    out_path = os.path.join(base_out_path, "clustering", ref_genome)
    mkdir_p(out_path)
    con, cur = sql_lib.attach_databases(comp_ann_path, mode="reference")
    biotype_ids = sql_lib.get_biotype_ids(cur, ref_genome, biotype, filter_chroms=filter_chroms)
    if len(biotype_ids) > 50:
        sql_data = sql_lib.load_data(con, ref_genome, etc.config.ref_classifiers, primary_key="TranscriptId")
        out_barplot_file = os.path.join(out_path, "reference_barplot_{}".format(gencode))
        barplot_title = base_barplot_title.format(biotype.replace("_", " "), gencode)
        munged, stats = munge_data(sql_data, biotype_ids)
        plot_lib.barplot(stats, out_path, out_barplot_file, barplot_title)
        data_path = os.path.join(target.getGlobalTempDir(), getRandomAlphaNumericString())
        munged.to_csv(data_path)
        out_cluster_file = os.path.join(out_path, "reference_clustering_{}".format(gencode))
        target.addChildTargetFn(r_wrapper, args=[data_path, clust_title, out_cluster_file])


def main():
    parser = build_parser()
    Stack.addJobTreeOptions(parser)
    args = parser.parse_args()
    if args.mode == "reference":
        s = Stack(Target.makeTargetFn(main_ref_fn, args=[args.comparativeAnnotationDir, args.gencode, args.genome,
                                                         args.outDir, args.filterChroms]))
    elif args.mode == "transMap":
        s = Stack(Target.makeTargetFn(main_fn, args=[args.comparativeAnnotationDir, args.gencode, args.genome,
                                                     args.refGenome, args.outDir, args.filterChroms]))
    else:
        s = Stack(Target.makeTargetFn(main_augustus_fn, args=[args.comparativeAnnotationDir, args.gencode, args.genome,
                                                              args.outDir, args.filterChroms]))
    i = s.startJobTree(args)
    if i != 0:
        raise RuntimeError("Got failed jobs")


if __name__ == '__main__':
    from plotting.clustering import *
    main()