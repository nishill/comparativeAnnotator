"""
This is the main driver script for comparativeAnnotator in transMap mode.
"""

import argparse
import os
import subprocess
import cPickle as pickle

from jobTree.scriptTree.target import Target
from jobTree.scriptTree.stack import Stack

import lib.sql_lib as sql_lib
import lib.seq_lib as seq_lib
from lib.general_lib import classes_in_module, mkdir_p

import src.classifiers
import src.augustus_classifiers
import src.attributes
import etc.config

__author__ = "Ian Fiddes"


augustus_classifier_tracks = [etc.config.allAugustusClassifiers]
tm_classifier_tracks = [etc.config.allClassifiers, etc.config.potentiallyInterestingBiology, etc.config.assemblyErrors,
                        etc.config.alignmentErrors]


def parse_args():
    """
    Builds an argument parser for this run
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--refGenome', type=str, required=True)
    parser.add_argument('--genome', required=True)
    parser.add_argument('--annotationGp', required=True)
    parser.add_argument('--psl', required=True)
    parser.add_argument('--gp', required=True)
    parser.add_argument('--fasta', required=True)
    parser.add_argument('--refFasta', type=str, required=True)
    parser.add_argument('--sizes', required=True)
    parser.add_argument('--gencodeAttributes', required=True)
    parser.add_argument('--outDir', type=str, required=True)
    parser.add_argument('--augustus', action="store_true")
    parser.add_argument('--augustusGp')
    Stack.addJobTreeOptions(parser)  # add jobTree options
    args = parser.parse_args()
    if args.augustus and args.augustusGp is None:
        raise RuntimeError("Error: augustus mode activated but no augustusGp provided.")
    elif args.augustus is False and args.augustusGp is not None:
        raise RuntimeError("Error: augustusGp provided but augustus flag not set.")
    return args


def build_analyses(target, ref_genome, genome, annotation_gp, psl, gp, fasta, ref_fasta, sizes, gencode_attributes,
                   out_dir, augustus, augustus_gp):
    """
    Wrapper function that will call all classifiers. Each classifier will dump its results to disk as a pickled dict.
    Calls database_wrapper to load these into a sqlite3 database.
    """
    # find all user-defined classes in the categories of analyses
    tmp_dir = target.getGlobalTempDir()
    if augustus is True:
        augustus_classifiers = classes_in_module(src.augustus_classifiers)
        for classifier in augustus_classifiers:
            target.addChildTarget(classifier(genome, psl, fasta, ref_fasta, annotation_gp, gencode_attributes, gp,
                                             ref_genome, tmp_dir, augustus_gp))
    else:
        classifiers = classes_in_module(src.classifiers) + classes_in_module(src.attributes)
        #classifiers = [src.classifiers.EndStop, src.classifiers.BeginStart, src.classifiers.AlignmentPartialMap, src.attributes.AlignmentIdentity]
        for classifier in classifiers:
            target.addChildTarget(classifier(genome, psl, fasta, ref_fasta, annotation_gp, gencode_attributes, gp,
                                             ref_genome, tmp_dir))
        # merge the resulting pickled files into sqlite databases and construct BED tracks
    target.setFollowOnTargetFn(database_wrapper, memory=8 * (1024 ** 3),
                               args=[out_dir, genome, sizes, gp, augustus, tmp_dir])


def database_wrapper(target, out_dir, genome, sizes, gp, augustus, tmp_dir):
    """
    Calls database for each database in this analysis.
    """
    if augustus is True:
        for db in ["classify", "details"]:
            db_path = os.path.join(out_dir, "augustus_{}.db".format(db))
            target.addChildTargetFn(database, args=[genome, db, db_path, tmp_dir])
    else:
        for db in ["classify", "details", "attributes"]:
            db_path = os.path.join(out_dir, "{}.db".format(db))
            target.addChildTargetFn(database, args=[genome, db, db_path, tmp_dir])
    target.setFollowOnTargetFn(build_tracks_wrapper, args=[out_dir, genome, sizes, gp, augustus])


def database(target, genome, db, db_path, tmp_dir):
    data_dict = {}
    data_path = os.path.join(tmp_dir, db)
    for col in os.listdir(data_path):
        p = os.path.join(data_path, col)
        with open(p) as p_h:
            data_dict[col] = pickle.load(p_h)
    sql_lib.write_dict(data_dict, db_path, genome)


def build_tracks_wrapper(target, out_dir, genome, sizes, gp, augustus):
    if augustus:
        classifier_tracks = augustus_classifier_tracks
    else:
        classifier_tracks = tm_classifier_tracks
    for f in classifier_tracks:
        query = f(genome)
        query_name = f.__name__
        target.addChildTargetFn(build_classifier_tracks, args=[query, query_name, out_dir, genome, sizes, augustus])
    target.addChildTargetFn(build_ok_track, args=[out_dir, genome, sizes, gp, augustus])


def get_bed_paths(out_dir, query_name, genome):
    out_bed_dir = os.path.join(out_dir, "bedfiles", query_name, genome)
    out_bed_path = os.path.join(out_bed_dir, "{}.bed".format(genome))
    out_big_bed_dir = os.path.join(out_dir, "bigBedfiles", query_name, genome)
    out_big_bed_path = os.path.join(out_big_bed_dir, "{}.bb".format(genome))
    mkdir_p(out_bed_dir)
    mkdir_p(out_big_bed_dir)
    return out_bed_path, out_big_bed_path


def make_big_bed(out_bed_path, sizes, out_big_bed_path):
    subprocess.call(["bedSort", out_bed_path, out_bed_path])
    subprocess.call(["bedToBigBed", "-extraIndex=name", out_bed_path, sizes, out_big_bed_path])


def build_classifier_tracks(target, query, query_name, out_dir, genome, sizes, augustus):
    con, cur = sql_lib.attach_databases(out_dir, has_augustus=augustus)
    bed_recs = cur.execute(query)
    out_bed_path, out_big_bed_path = get_bed_paths(out_dir, query_name, genome)
    with open(out_bed_path, "w") as outf:
        for recs in bed_recs:
            for rec in recs:
                if rec is not None:
                    outf.write(rec)
    make_big_bed(out_bed_path, sizes, out_big_bed_path)


def get_all_tm_ok(cur, genome):
    """
    transMap OK varies depending on if the transcript is coding or noncoding. We will build a set of OK for both.
    This is a hacky way to solve the problem I found in build_ok_track() - that we need two OK queries for transMap.
    """
    coding_query = etc.config.transMapOk(genome, coding=True)
    non_coding_query = etc.config.transMapOk(genome, coding=False)
    coding_ok_ids = sql_lib.get_ok_ids(cur, coding_query)
    non_coding_ok_ids = sql_lib.get_ok_ids(cur, non_coding_query)
    coding_id_query = "SELECT AlignmentId FROM attributes.'{}' WHERE TranscriptType == 'protein_coding'".format(genome)
    coding_gencode_ids = {x[0] for x in cur.execute(coding_id_query).fetchall()}
    coding_ok = coding_gencode_ids & coding_ok_ids
    non_coding_id_query = "SELECT AlignmentId FROM attributes.'{}' WHERE TranscriptType != 'protein_coding'".format(genome)
    non_coding_gencode_ids = {x[0] for x in cur.execute(non_coding_id_query).fetchall()}
    non_coding_ok = non_coding_gencode_ids & non_coding_ok_ids
    return non_coding_ok, coding_ok


def build_ok_track(target, out_dir, genome, sizes, gp, augustus):
    """
    Had to hack up this function a bit to get non-coding OK tracks.
    TODO: clean this up.
    """
    colors = {"coding": "100,209,61", "noncoding": "209,61,115"}
    con, cur = sql_lib.attach_databases(out_dir, has_augustus=augustus)
    if augustus is True:
        query = etc.config.augustusOk(genome)
        ok_ids = sql_lib.get_ok_ids(cur, query)
        out_bed_path, out_big_bed_path = get_bed_paths(out_dir, "augustusOk", genome)
    else:
        non_coding_ok, coding_ok = get_all_tm_ok(cur, genome)
        out_bed_path, out_big_bed_path = get_bed_paths(out_dir, "transMapOk", genome)
    gp_recs = seq_lib.get_gene_pred_transcripts(gp)
    gp_dict = seq_lib.transcript_list_to_dict(gp_recs)
    with open(out_bed_path, "w") as outf:
        for aln_id, rec in gp_dict.iteritems():
            if (augustus is True and aln_id in ok_ids) or (augustus is False and aln_id in coding_ok):
                bed = rec.get_bed(rgb=colors["coding"])
                outf.write("".join(["\t".join(map(str, bed)), "\n"]))
            elif augustus is False and aln_id in non_coding_ok:
                bed = rec.get_bed(rgb=colors["noncoding"])
                outf.write("".join(["\t".join(map(str, bed)), "\n"]))                
    make_big_bed(out_bed_path, sizes, out_big_bed_path)


def main():
    args = parse_args()
    i = Stack(Target.makeTargetFn(build_analyses, memory=8 * (1024 ** 3),
                                  args=[args.refGenome, args.genome, args.annotationGp, args.psl, args.gp, args.fasta, 
                                        args.refFasta, args.sizes, args.gencodeAttributes, args.outDir, args.augustus,
                                        args.augustusGp])).startJobTree(args)
    if i != 0:
        raise RuntimeError("Got failed jobs")


if __name__ == '__main__':
    from src.annotation_pipeline import *
    main()
