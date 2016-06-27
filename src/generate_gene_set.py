"""
Produces a gene set from transMap alignments.
"""
import argparse
import os
import cPickle as pickle
from collections import defaultdict, OrderedDict
import lib.sql_lib as sql_lib
import lib.psl_lib as psl_lib
import lib.seq_lib as seq_lib
from lib.general_lib import mkdir_p, merge_dicts, format_ratio
import etc.config


__author__ = "Ian Fiddes"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--genome", required=True)
    parser.add_argument("--refGenome", required=True)
    parser.add_argument("--compAnnPath", required=True)
    parser.add_argument("--outDir", required=True)
    parser.add_argument("--workDir", required=True)
    parser.add_argument("--augGp")
    parser.add_argument("--tmGp", required=True)
    parser.add_argument("--filterChroms", nargs="+", default=["Y", "chrY"], help="chromosomes to ignore")
    args = parser.parse_args()
    if args.augGp is None:
        args.mode = "transMap"
        args.gps = [args.tmGp]
    else:
        args.mode = "augustus"
        args.gps = [args.tmGp, args.augGp]
    return args


def load_gps(gp_paths):
    """
    Get a dictionary mapping all gene IDs from a genePred into its entire record. If the gene IDs are not unique
    this function will not work like you want it to.
    """
    return {l.split()[0]: l for p in gp_paths for l in open(p)}


def get_stats(cur, genome, mode):
    """
    Adapter function to return the combination of the stats dicts produced for augustus and transMap
    """
    tm_stats = sql_lib.get_stats(cur, genome, mode="transMap")
    if mode == "augustus":
        aug_stats = sql_lib.get_stats(cur, genome, mode="augustus")
        return merge_dicts([tm_stats, aug_stats])
    else:
        return tm_stats


def build_data_dict(id_names, id_list, transcript_gene_map, gene_transcript_map):
    """
    Builds a dictionary mapping gene_id -> transcript_ids -> aln_ids in id_names bins (as an OrderedDict)
    """
    data_dict = defaultdict(dict)
    for gene_id in gene_transcript_map:
        for ens_id in gene_transcript_map[gene_id]:
            data_dict[gene_id][ens_id] = OrderedDict((x, []) for x in id_names)
    for ids, n in zip(*[id_list, id_names]):
        for aln_id in ids:
            ens_id = psl_lib.strip_alignment_numbers(aln_id)
            if ens_id not in transcript_gene_map:
                # Augustus was fed chrY transcripts
                continue
            gene_id = transcript_gene_map[ens_id]
            if gene_id in data_dict and ens_id in data_dict[gene_id]:
                data_dict[gene_id][ens_id][n].append(aln_id)
    return data_dict


def find_best_alns(stats, ids, cov_cutoff=80.0):
    """
    Takes the list of transcript Ids and finds the best alignment(s) by highest percent identity and coverage
    We sort by ID to favor Augustus transcripts going to the consensus set in the case of ties
    """
    s = []
    for aln_id in ids:
        cov, ident = stats[aln_id]
        # round to avoid floating point issues when finding ties
        cov = round(cov, 6)
        ident = round(ident, 6)
        s.append([aln_id, cov, ident])
    # put aug names first
    s = sorted(s, key=lambda (aln_id, cov, ident): aln_id, reverse=True)
    # first we see if any transcripts pass cov_cutoff
    cov_s = filter(lambda (aln_id, cov, ident): cov >= cov_cutoff, s)
    # if no transcripts
    if len(cov_s) == 0:
        return None
    else:
        best_ident = sorted(cov_s, key=lambda (aln_id, cov, ident): ident, reverse=True)[0][2]
    best_overall = [aln_id for aln_id, cov, ident in cov_s if ident >= best_ident]
    return best_overall


def evaluate_ids(fail_ids, pass_specific_ids, excel_ids, aug_ids, stats):
    """
    For a given ensembl ID, we have augustus/transMap ids in 4 categories. Based on the hierarchy Excellent>Pass>Fail,
    return the best transcript in the highest category with a transMap transcript.
    """
    if len(excel_ids) > 0:
        best_alns = find_best_alns(stats, excel_ids + aug_ids)
        return best_alns, "Excellent"
    elif len(pass_specific_ids) > 0:
        best_alns = find_best_alns(stats, pass_specific_ids + aug_ids)
        return best_alns, "Pass"
    elif len(fail_ids) > 0:
        best_alns = find_best_alns(stats, fail_ids + aug_ids)
        return best_alns, "Fail"
    else:
        return None, "NoTransMap"


def is_tie(best_alns):
    """
    If we have more than one best transcript, is at least one from transMap and one from Augustus?
    """
    seen = set()
    for aln_id in best_alns:
        ens_id = psl_lib.remove_augustus_alignment_number(aln_id)
        if ens_id in seen:
            return True
        else:
            seen.add(ens_id)
    return False


def find_best_transcripts(data_dict, stats, mode, biotype):
    """
    For all of the transcripts categorized in data_dict, evaluate them and bin them.
    """
    binned_transcripts = {}
    for gene_id in data_dict:
        binned_transcripts[gene_id] = {}
        for ens_id in data_dict[gene_id]:
            tx_recs = data_dict[gene_id][ens_id]
            if mode == "augustus" and biotype == "protein_coding":
                fail_ids, pass_specific_ids, excel_ids, aug_ids = tx_recs.values()
            else:
                fail_ids, pass_specific_ids, excel_ids = tx_recs.values()
                aug_ids = []
            best_alns, category = evaluate_ids(fail_ids, pass_specific_ids, excel_ids, aug_ids, stats)
            if best_alns is None:
                binned_transcripts[gene_id][ens_id] = [best_alns, category, None]
            else:
                tie = is_tie(best_alns)
                binned_transcripts[gene_id][ens_id] = [best_alns[0], category, tie]
    return binned_transcripts


def find_longest_for_gene(bins, stats, gps, mode, cov_cutoff=60.0, ident_cutoff=80.0):
    """
    Finds the longest transcript(s) for a gene. This is used when all transcripts failed, and has more relaxed cutoffs.
    If this is in Augustus mode, will only consider Augustus transcripts.
    """
    aln_ids = zip(*bins.itervalues())[0]
    keep_ids = []
    for aln_id in aln_ids:
        if aln_id is None:
            continue
        cov, ident = stats[aln_id]
        if cov >= cov_cutoff and ident >= ident_cutoff:
            keep_ids.append(aln_id)
    if mode == 'augustus':
        keep_ids = [x for x in keep_ids if 'aug' in x]
    if len(keep_ids) > 0:
        sizes = [[x, len(gps[x])] for x in keep_ids]
        longest_size = max(zip(*sizes)[1])
        return [x for x, y in sizes if y == longest_size]
    else:
        return None


def has_only_short(bins, ids_included, ref_interval, tgt_intervals, percentage_of_ref=60.0):
    """
    Are all of the consensus transcripts we found for this gene too short?
    """
    source_size = len(ref_interval)
    tgt_sizes = [len(tgt_intervals[x]) for x in zip(*bins.itervalues())[0] if x in ids_included]
    return all([100 * format_ratio(tgt_size, source_size) < percentage_of_ref for tgt_size in tgt_sizes])


def find_consensus(binned_transcripts, stats, gps, ref_intervals, tgt_intervals, mode):
    """
    Takes the binned transcripts and builds a consensus gene set.
    """
    consensus = []
    for gene_id in binned_transcripts:
        gene_in_consensus = False
        ids_included = set()
        for ens_id in binned_transcripts[gene_id]:
            best_id, category, tie = binned_transcripts[gene_id][ens_id]
            if category in ["Excellent", "Pass"]:
                consensus.append(best_id)
                ids_included.add(best_id)
                gene_in_consensus = True
        if gene_id not in ref_intervals:
            # we really have none, no transMap here. TODO; fix this, see how we generate ref_intervals
            has_only_short_txs = True
        else:
            has_only_short_txs = has_only_short(binned_transcripts[gene_id], ids_included, ref_intervals[gene_id],
                                                tgt_intervals)
        if gene_in_consensus is False or has_only_short_txs is True:
            # find the single longest transcript for this gene
            best_for_gene = find_longest_for_gene(binned_transcripts[gene_id], stats, gps, mode)
            if best_for_gene is not None:
                consensus.append(best_for_gene[0])
    return consensus


def consensus_by_biotype(cur, ref_genome, genome, biotype, gps, transcript_gene_map, gene_transcript_map, stats, mode,
                         ref_intervals, tgt_intervals):
    """
    Main consensus finding function.
    """
    fail_ids, pass_specific_ids, excel_ids = sql_lib.get_fail_passing_excel_ids(cur, ref_genome, genome, biotype,
                                                                                best_cov_only=False)
    # hacky way to avoid duplicating code in consensus finding - we will always have an aug_id set, it just may be empty
    if mode == "augustus" and biotype == "protein_coding":
        aug_query = etc.config.augustusEval(genome, ref_genome)
        aug_ids = sql_lib.get_query_ids(cur, aug_query)
        id_names = ["fail_ids", "pass_specific_ids", "excel_ids", "aug_ids"]
        id_list = [fail_ids, pass_specific_ids, excel_ids, aug_ids]
    else:
        id_names = ["fail_ids", "pass_specific_ids", "excel_ids"]
        id_list = [fail_ids, pass_specific_ids, excel_ids]
    data_dict = build_data_dict(id_names, id_list, transcript_gene_map, gene_transcript_map)
    binned_transcripts = find_best_transcripts(data_dict, stats, mode, biotype)
    consensus = find_consensus(binned_transcripts, stats, gps, ref_intervals, tgt_intervals, mode)
    return binned_transcripts, consensus


def evaluate_transcript(best_id, category, tie):
    """
    Evaluates the best transcript(s) for a given ensembl ID for being excel/fail/ok and asks if it is a tie
    """
    if category is "NoTransMap":
        return category
    elif tie is True:
        c = "Tie"
    elif psl_lib.aln_id_is_augustus(best_id):
        c = "Aug"
    elif psl_lib.aln_id_is_transmap(best_id):
        c = "TM"
    else:
        assert False, "ID was not TM/Aug"
    s = "".join([category, c])
    return s


def evaluate_gene(categories):
    """
    Same as evaluate_transcript, but on the gene level. Does this gene have at least one transcript categorized
    as excellent/passing/fail?
    """
    if "Excellent" in categories:
        return "Excellent"
    elif "Pass" in categories:
        return "Pass"
    elif "Fail" in categories:
        return "Fail"
    elif "NoTransMap" in categories:
        return "NoTransMap"
    else:
        assert False, "Should not be able to get here."


def evaluate_best_for_gene(tx_ids):
    return "NoTransMap" if tx_ids is None else "Fail"


def evaluate_coding_consensus(binned_transcripts, stats, ref_gene_intervals, gps, mode):
    """
    Evaluates the coding consensus for plots. Reproduces a lot of code from find_consensus()
    TODO: split out duplicated code.
    TODO: Assigning s to FailTM is a hack in cases where we filter out all transcripts due to coverage. This really
    needs to be addressed, primarly by re-writing this code to actually happen simultaneously with find_consensus.
    Ideally, we also generate a new specific plot showing how often we only report longest-per-gene as well as how often
    the short_transcript filter gets hit.
    """
    if mode == "augustus":
        transcript_evaluation = OrderedDict((x, 0) for x in ["ExcellentTM", "ExcellentAug", "ExcellentTie", "PassTM", "PassAug",
                                                             "PassTie", "FailTM", "FailAug", "FailTie", "NotInConsensus"])
        gene_evaluation = OrderedDict((x, 0) for x in ["Excellent", "Pass", "Fail", "NoTransMap"])
    else:
        transcript_evaluation = OrderedDict((x, 0) for x in ["Excellent", "Pass", "Fail", "NoTransMap"])
        gene_evaluation = OrderedDict((x, 0) for x in ["Excellent", "Pass", "Fail", "NoTransMap"])
    gene_fail_evaluation = OrderedDict((x, 0) for x in ["Fail", "NoTransMap"])
    for gene_id in binned_transcripts:
        categories = set()
        for ens_id in binned_transcripts[gene_id]:
            best_id, category, tie = binned_transcripts[gene_id][ens_id]
            categories.add(category)
            if best_id is not None:
                s = evaluate_transcript(best_id, category, tie) if mode == "augustus" else category
            else:
                s = 'NotInConsensus'
            transcript_evaluation[s] += 1
        s = evaluate_gene(categories)
        gene_evaluation[s] += 1
        if s == "Fail":
            best_for_gene = find_longest_for_gene(binned_transcripts[gene_id], stats, gps, mode)
            s = evaluate_best_for_gene(best_for_gene)
            gene_fail_evaluation[s] += 1
    r = {"transcript": transcript_evaluation, "gene": gene_evaluation, "gene_fail": gene_fail_evaluation}
    return r


def evaluate_noncoding_consensus(binned_transcripts, stats, gps):
    transcript_evaluation = OrderedDict((x, 0) for x in ["ExcellentTM", "PassTM", "FailTM", "NoTransMap"])
    gene_evaluation = OrderedDict((x, 0) for x in ["Excellent", "Pass", "Fail", "NoTransMap"])
    gene_fail_evaluation = OrderedDict((x, 0) for x in ["Fail", "NoTransMap"])
    for gene_id in binned_transcripts:
        categories = set()
        for ens_id in binned_transcripts[gene_id]:
            best_id, category, tie = binned_transcripts[gene_id][ens_id]
            categories.add(category)
            if best_id is not None:
                s = evaluate_transcript(best_id, category, tie)
            else:
                s = "FailTM"
            transcript_evaluation[s] += 1
        s = evaluate_gene(categories)
        gene_evaluation[s] += 1
        if s == "Fail":
            best_for_gene = find_longest_for_gene(binned_transcripts[gene_id], stats, gps, 'transMap')
            s = evaluate_best_for_gene(best_for_gene)
            gene_fail_evaluation[s] += 1
    r = {"transcript": transcript_evaluation, "gene": gene_evaluation, "gene_fail": gene_fail_evaluation}
    return r


def deduplicate_consensus(consensus, gps, stats):
    """
    In the process of consensus building, we may find that we have ended up with more than one transcript for a gene
    that are actually identical. Remove these, picking the best based on the stats dict.
    """
    duplicates = defaultdict(list)
    for tx_id in consensus:
        tx_str = gps[tx_id]
        tx = seq_lib.GenePredTranscript(tx_str.rstrip().split("\t"))
        duplicates[frozenset(tx.exon_intervals)].append(tx)
    deduplicated_consensus = []
    dup_count = 0
    for gp_list in duplicates.itervalues():
        if len(gp_list) > 1:
            dup_count += 1
            # we have duplicates to collapse - which has the highest %ID followed by highest %coverage?
            dup_stats = sorted([[x, stats[x.name]] for x in gp_list], key=lambda (n, (cov, ident)): (ident, cov))
            best = dup_stats[0][0].name
            deduplicated_consensus.append(best)
        else:
            deduplicated_consensus.append(gp_list[0].name)
    return deduplicated_consensus, dup_count


def fix_gene_pred(gp, transcript_gene_map):
    """
    These genePreds have a few problems. First, the alignment numbers must be removed. Second, we want to fix
    the name2 field to be the gene name. Third, we want to set the unique ID field. Finally, we want to sort the whole
    thing by genomic coordinates.
    Also reports the number of genes and transcripts seen.
    """
    genes = set()
    txs = set()
    gp = sorted([x.split("\t") for x in gp], key=lambda x: [x[1], x[3]])
    fixed = []
    for x in gp:
        x[10] = x[0]  # use unique Aug/TM ID as unique identifier
        tx_id = psl_lib.strip_alignment_numbers(x[0])
        x[0] = tx_id
        gene_id = transcript_gene_map[tx_id]
        x[11] = gene_id
        fixed.append(x)
        genes.add(gene_id)
        txs.add(tx_id)
    return len(genes), len(txs), ["\t".join(x) for x in fixed]


def write_gps(consensus, gps, consensus_base_path, biotype, transcript_gene_map, mode):
    """
    Writes the final consensus gene set to a genePred, after fixing the names. Reports the number of genes and txs
    in the final set
    """
    if mode == "transMap":
        p = os.path.join(consensus_base_path, biotype + ".transmap_gene_set.gp")
    else:
        p = os.path.join(consensus_base_path, biotype + ".augustus_consensus_gene_set.gp")
    mkdir_p(os.path.dirname(p))
    gp_recs = [gps[aln_id] for aln_id in consensus]
    num_genes, num_txs, fixed_gp_recs = fix_gene_pred(gp_recs, transcript_gene_map)
    with open(p, "w") as outf:
        for rec in fixed_gp_recs:
            outf.write(rec)
    return num_genes, num_txs


def build_ref_intervals(cur, genome):
    """
    Build ChromosomeInterval objects for each source transcript, finding a max per-gene.
    TODO: add refStart, refEnd to reference comparative annotator to avoid hacks used here.
    """
    def largest(intervals):
        intervals = [seq_lib.ChromosomeInterval(*x) for x in intervals]
        s = [[len(x), x] for x in intervals]
        return s[0][1]
    query = "SELECT GeneId, SourceChrom, SourceStart, SourceStop, SourceStrand FROM attributes.'{}'".format(genome)
    ref_sizes = sql_lib.get_non_unique_query_dict(cur, query, flatten=False)
    r = {}
    for gene, intervals in ref_sizes.iteritems():
        r[gene] = largest(intervals)
    return r


def build_tgt_intervals(gps):
    """
    Constructs a ChromosomeInterval object for each transcript in gps
    """
    r = {}
    for aln_id, tx in gps.iteritems():
        l = tx.rstrip().split("\t")
        r[aln_id] = seq_lib.ChromosomeInterval(l[1], int(l[3]), int(l[4]), l[2])
    return r


def main():
    args = parse_args()
    con, cur = sql_lib.attach_databases(args.compAnnPath, mode=args.mode)
    biotypes = sql_lib.get_all_biotypes(cur, args.refGenome, gene_level=True)
    transcript_gene_map = sql_lib.get_transcript_gene_map(cur, args.refGenome, biotype=None,
                                                          filter_chroms=args.filterChroms)
    gps = load_gps(args.gps)  # load all Augustus and transMap transcripts into one big dict
    consensus_base_path = os.path.join(args.outDir, args.genome)
    stats = get_stats(cur, args.genome, args.mode)
    ref_gene_intervals = build_ref_intervals(cur, args.genome)
    tgt_intervals = build_tgt_intervals(gps)
    for biotype in biotypes:
        gene_transcript_map = sql_lib.get_gene_transcript_map(cur, args.refGenome, biotype=biotype,
                                                              filter_chroms=args.filterChroms)
        binned_transcripts, consensus = consensus_by_biotype(cur, args.refGenome, args.genome, biotype, gps,
                                                             transcript_gene_map, gene_transcript_map, stats, args.mode,
                                                             ref_gene_intervals, tgt_intervals)
        deduplicated_consensus, dup_count = deduplicate_consensus(consensus, gps, stats)
        if len(deduplicated_consensus) > 0:  # some biotypes we may have nothing
            num_genes, num_txs = write_gps(deduplicated_consensus, gps, consensus_base_path, biotype,
                                           transcript_gene_map, args.mode)
            if biotype == "protein_coding":
                gene_transcript_evals = evaluate_coding_consensus(binned_transcripts, stats, ref_gene_intervals, gps, args.mode)
            else:
                gene_transcript_evals = evaluate_noncoding_consensus(binned_transcripts, stats, gps)
            p = os.path.join(args.workDir, "_".join([args.genome, biotype]))
            mkdir_p(os.path.dirname(p))
            gene_transcript_evals["duplication_rate"] = dup_count
            gene_transcript_evals["gene_counts"] = num_genes
            gene_transcript_evals["tx_counts"] = num_txs
            with open(p, "w") as outf:
                pickle.dump(gene_transcript_evals, outf)


if __name__ == "__main__":
    main()
