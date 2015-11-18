"""
Takes a comparative Augustus transcript set with the name2 field set to the best gencode gene ID.
Produces a new consensus from this transcript set, following these rules:

1) Align every CGP transcript to the consensus transcript's reference transcript. If one or more CGP transcript 
fufills the coverage/identity heuristics above, replace the consensus transcript with the best CGP by % identity.
2) If there are any remaining CGP transcripts that have not been moved into the consensus set, we look for RNAseq 
supported splice junctions not present in any of the transcripts for this gene. If so, we include it. 
3) If any augustus CGP transcripts do not overlap any existing transcripts, include them

"""
import argparse
import os
import cPickle as pickle
import lib.sql_lib as sql_lib
import lib.psl_lib as psl_lib
import lib.seq_lib as seq_lib

__author__ = "Ian Fiddes"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cgpDb", required=True)
    parser.add_argument("--cgpGp", required=True)
    parser.add_argument("--consensusProteinCodingGp", required=True)
    parser.add_argument("--compAnnPath", required=True)
    parser.add_argument("--intronBitsPath", required=True)
    parser.add_argument("--genome", required=True)
    parser.add_argument("--outDir", required=True)
    parser.add_argument("--metricsOutDir", required=True)
    return parser.parse_args()


def load_intron_bits(intron_bits_path):
    """
    Load the intron bit vector files into a dictionary, properly handling cases where there are no introns
    """
    intron_dict = {}
    for line in open(intron_bits_path):
        l = line.split()
        if len(l) == 1:
            intron_dict[l[0]] = []
        else:
            intron_dict[l[0]] = map(int, l[1].split(","))
    return intron_dict


def get_cgp_stats(cur, cgp_id, genome):
    """
    Query the CDS database for stats on a CGP transcript, reporting all alignments
    """
    base_cmd = "SELECT EnsId,AlignmentIdentity,AlignmentCoverage FROM '{}_cgp' WHERE CgpId = '{}'"
    cmd = base_cmd.format(genome, cgp_id)
    return sql_lib.get_query_dict(cur, cmd)


def get_consensus_stats(cur, ens_ids, genome):
    """
    Query the CDS database for TMR/transMap stats who are in ens_ids
    """
    base_cmd = "SELECT AlignmentId,AlignmentIdentity,AlignmentCoverage FROM '{}_consensus' WHERE EnsId = '{}'"
    results = {}
    for ens_id in ens_ids:
        cmd = base_cmd.format(genome, ens_id)
        result = cur.execute(cmd).fetchall()
        for r in result:
            results[r[0]] = r[1:]
    return results


def build_splice_junction_set(gps):
    """
    Given an iterable of GenePredTranscript objects, returns a set of all splice junction intervals
    as ChromosomeIntervals
    """
    sjs = set()
    for gp in gps:
        for intron_interval in gp.intron_intervals:
            sjs.add(intron_interval)
    return sjs


def filter_cgp_splice_junctions(gp, intron_vector):
    """
    Returns a set of ChromosomeInterval objects that are filtered based on the intron vector provided
    """
    sjs = set()
    assert len(intron_vector) == len(gp.intron_intervals)
    for support, intron_interval in zip(*[intron_vector, gp.intron_intervals]):
        if support == 1:
            sjs.add(intron_interval)
    return sjs


def determine_if_better(cgp_stats, consensus_stats):
    """
    Determines if this CGP transcript is better than any of the consensus transcripts it may come from
    """
    ens_ids = []
    for aln_id, (consensus_ident, consensus_cov) in consensus_stats.iteritems():
        ens_id = psl_lib.strip_alignment_numbers(aln_id)
        cgp_ident, cgp_cov = cgp_stats[ens_id]
        if ((cgp_ident > consensus_ident and cgp_cov >= consensus_cov) or 
                (cgp_cov > consensus_cov and cgp_ident >= consensus_ident)):
            ens_ids.append(ens_id)
    return ens_ids


def determine_if_new_introns(cgp_id, cgp_tx, ens_ids, consensus_dict, gene_transcript_map, intron_dict):
    """
    Use intron bit information to build a set of CGP introns, and compare this set to all consensus introns
    for a given set of genes.
    """
    gps = [consensus_dict[x] for x in ens_ids if x in consensus_dict]
    ens_splice_junctions = build_splice_junction_set(gps)
    cgp_splice_junctions = filter_cgp_splice_junctions(cgp_tx, intron_dict[cgp_id])
    if len(cgp_splice_junctions - ens_splice_junctions) > 0:
        return True
    return False


def find_new_transcripts(cgp_dict, final_consensus, metrics):
    """
    For each CGP transcript, if it was not assigned a gene ID, incorporate it into the final set
    """
    jg_genes = set()
    for cgp_id, cgp_tx in cgp_dict.iteritems():
        if 'jg' in cgp_tx.name2:
            final_consensus[cgp_id] = cgp_tx
            jg_genes.add(cgp_id.split(".")[0])
    metrics["CgpNewGenes"] = len(jg_genes)
    metrics["CgpNewTranscripts"] = len(final_consensus)


def build_final_consensus(consensus_dict, replace_map, new_isoforms, final_consensus):
    """
    Builds the final consensus gene set given the replace map as well as the new isoforms.
    """
    for consensus_id, consensus_tx in consensus_dict.iteritems():
        if consensus_id in replace_map:
            cgp_tx = replace_map[consensus_id]
            cgp_tx.id = cgp_id
            cgp_tx.name = consensus_id
            final_consensus[consensus_id] = cgp_tx
        else:
            final_consensus[consensus_id] = consensus_tx
    for cgp_tx in new_isoforms:
        final_consensus[cgp_tx.name] = cgp_tx


def update_transcripts(cgp_dict, consensus_dict, cur, genome, gene_transcript_map, intron_dict, final_consensus, 
                       metrics):
    """
    Main transcript replacement/inclusion algorithm.
    For every cgp transcript, determine if it should replace one or more consensus transcripts.
    If it should not, then determine if it should be kept because it adds new splice junctions.
    """
    replace_map = {}  # will store a mapping between consensus IDs and the CGP IDs that will replace them
    new_isoforms = []  # will store cgp IDs which represent new potential isoforms of a gene
    for cgp_id, cgp_tx in cgp_dict.iteritems():
        cgp_stats = get_cgp_stats(cur, cgp_id, genome)
        ens_ids = cgp_stats.keys()
        consensus_stats = get_consensus_stats(cur, ens_ids, genome)
        to_replace_ids = determine_if_better(cgp_stats, consensus_stats)
        if len(to_replace_ids) > 0:
            for to_replace_id in to_replace_ids:
                replace_map[to_replace_id] = cgp_tx
        elif determine_if_new_introns(cgp_id, cgp_tx, ens_ids, consensus_dict, gene_transcript_map, intron_dict):
            new_isoforms.append(cgp_tx)
    # calculate some metrics for plots once all genomes are analyzed
    metrics["CgpReplaceRate"] = len(replace_map)
    metrics["CgpCollapseRate"] = len(set(replace_map.itervalues()))
    metrics["NewIsoforms"] = len(new_isoforms)
    build_final_consensus(consensus_dict, replace_map, new_isoforms, final_consensus)


def main():
    args = parse_args()
    # attach regular comparativeAnnotator reference databases in order to build gene-transcript map
    con, cur = sql_lib.attach_databases(args.compAnnPath, mode="reference")
    gene_transcript_map = sql_lib.get_gene_transcript_map(cur, args.refGenome, biotype="protein_coding")
    # open CGP database -- we don't need comparativeAnnotator databases anymore
    con, cur = sql_lib.open_database(args.cgpDb)
    consensus_base_path = os.path.join(args.outDir, args.genome)
    # load both consensus and CGP into dictionaries
    consensus_dict = seq_lib.get_transcript_dict(args.consensusProteinCodingGp)
    cgp_dict = seq_lib.get_transcript_dict(args.cgpGp)
    # load the intron bits
    intron_dict = load_intron_bits(args.intronBitsPath)
    # final dictionaries
    final_consensus = {}
    metrics = {}
    # easy case - save all CGP transcripts which have no associated genes
    find_new_transcripts(cgp_dict, final_consensus, metrics)
    # remove all such transcripts from the cgp dict before we evaluate for updating
    cgp_dict = {x: y for x, y in cgp_dict.iteritems() if x not in final_consensus}
    update_transcripts(cgp_dict, consensus_dict, cur, genome, gene_transcript_map, intron_dict, final_consensus, 
                       metrics)
    # write results out to disk
    with open(os.path.join(args.outDir, args.genome + ".CGP.consensus.gp"), "w") as outf:
        for tx_id, tx in final_consensus.iteritems():
            outf.write("\t".join(map(str, tx.get_bed())) + "\n")
    with open(os.path.join(args.metricsOutDir, args.genome + ".metrics.pickle"), "w") as outf:
        pickle.dump(metrics, outf)


if __name__ == "__main__":
    main()